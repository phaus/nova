# coding=utf-8
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2012 Hendrik Volkmer, Thijs Metsch
# Copyright (c) 2013 Daniele Stroppa
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
A connection to the SmartOS VM management system (vmadm)
"""

from oslo.config import cfg

from nova import db
from nova import exception
from nova.openstack.common import log as logging
from nova.openstack.common import jsonutils

from nova.virt import driver
from nova.virt.smartosapi import vmops

import socket

LOG = logging.getLogger(__name__)

smartos_opts = [
    cfg.StrOpt('rescue_image_id',
        default=None,
        help='Rescue ami image'),
    cfg.StrOpt('rescue_kernel_id',
        default=None,
        help='Rescue aki image'),
    cfg.StrOpt('rescue_ramdisk_id',
        default=None,
        help='Rescue ari image'),
    cfg.StrOpt('smartos_type',
        default='kvm',
        help='smartos domain type (valid options are: '
             'kvm, lxc, qemu, uml, xen)'),
    cfg.StrOpt('smartos_uri',
        default='',
        help='Override the default smartos URI '
             '(which is dependent on smartos_type)'),
    cfg.BoolOpt('smartos_inject_password',
        default=False,
        help='Inject the admin password at boot time, '
             'without an agent.'),
    cfg.BoolOpt('smartos_inject_key',
        default=True,
        help='Inject the ssh public key at boot time'),
    cfg.IntOpt('smartos_inject_partition',
        default=1,
        help='The partition to inject to : '
             '-2 => disable, -1 => inspect (libguestfs only), '
             '0 => not partitioned, >0 => partition number'),
    cfg.BoolOpt('use_usb_tablet',
        default=True,
        help='Sync virtual and real mouse cursors in Windows VMs'),
    cfg.StrOpt('live_migration_uri',
        default="qemu+tcp://%s/system",
        help='Migration target URI '
             '(any included "%s" is replaced with '
             'the migration target hostname)'),
    cfg.StrOpt('live_migration_flag',
        default='VIR_MIGRATE_UNDEFINE_SOURCE, VIR_MIGRATE_PEER2PEER',
        help='Migration flags to be set for live migration'),
    cfg.StrOpt('block_migration_flag',
        default='VIR_MIGRATE_UNDEFINE_SOURCE, VIR_MIGRATE_PEER2PEER, '
                'VIR_MIGRATE_NON_SHARED_INC',
        help='Migration flags to be set for block migration'),
    cfg.IntOpt('live_migration_bandwidth',
        default=0,
        help='Maximum bandwidth to be used during migration, in Mbps'),
    cfg.StrOpt('snapshot_image_format',
        default=None,
        help='Snapshot image format (valid options are : '
             'raw, qcow2, vmdk, vdi). '
             'Defaults to same as source image'),
    cfg.StrOpt('smartos_vif_driver',
        default='nova.virt.smartos.vif.smartosGenericVIFDriver',
        help='The smartos VIF driver to configure the VIFs.'),
    cfg.ListOpt('smartos_volume_drivers',
        default=[
            'iscsi=nova.virt.smartos.volume.smartosISCSIVolumeDriver',
            'local=nova.virt.smartos.volume.smartosVolumeDriver',
            'fake=nova.virt.smartos.volume.smartosFakeVolumeDriver',
            'rbd=nova.virt.smartos.volume.smartosNetVolumeDriver',
            'sheepdog=nova.virt.smartos.volume.smartosNetVolumeDriver',
            'nfs=nova.virt.smartos.volume.smartosNFSVolumeDriver',
            'aoe=nova.virt.smartos.volume.smartosAOEVolumeDriver',
            'glusterfs='
            'nova.virt.smartos.volume.smartosGlusterfsVolumeDriver',
            'fibre_channel=nova.virt.smartos.volume.'
            'smartosFibreChannelVolumeDriver',
            'scality='
            'nova.virt.smartos.volume.smartosScalityVolumeDriver',
            ],
        help='smartos handlers for remote volumes.'),
    cfg.StrOpt('smartos_disk_prefix',
        default=None,
        help='Override the default disk prefix for the devices attached'
             ' to a server, which is dependent on smartos_type. '
             '(valid options are: sd, xvd, uvd, vd)'),
    cfg.IntOpt('smartos_wait_soft_reboot_seconds',
        default=120,
        help='Number of seconds to wait for instance to shut down after'
             ' soft reboot request is made. We fall back to hard reboot'
             ' if instance does not shutdown within this window.'),
    cfg.BoolOpt('smartos_nonblocking',
        default=True,
        help='Use a separated OS thread pool to realize non-blocking'
             ' smartos calls'),
    cfg.StrOpt('smartos_cpu_mode',
        default=None,
        help='Set to "host-model" to clone the host CPU feature flags; '
             'to "host-passthrough" to use the host CPU model exactly; '
             'to "custom" to use a named CPU model; '
             'to "none" to not set any CPU model. '
             'If smartos_type="kvm|qemu", it will default to '
             '"host-model", otherwise it will default to "none"'),
    cfg.StrOpt('smartos_cpu_model',
        default=None,
        help='Set to a named smartos CPU model (see names listed '
             'in /usr/share/smartos/cpu_map.xml). Only has effect if '
             'smartos_cpu_mode="custom" and smartos_type="kvm|qemu"'),
    cfg.StrOpt('smartos_snapshots_directory',
        default='$instances_path/snapshots',
        help='Location where smartos driver will store snapshots '
             'before uploading them to image service'),
    cfg.StrOpt('xen_hvmloader_path',
        default='/usr/lib/xen/boot/hvmloader',
        help='Location where the Xen hvmloader is kept'),
    cfg.ListOpt('disk_cachemodes',
        default=[],
        help='Specific cachemodes to use for different disk types '
             'e.g: ["file=directsync","block=none"]'),
    ]

CONF = cfg.CONF
CONF.register_opts(smartos_opts)
CONF.import_opt('host', 'nova.netconf')
CONF.import_opt('my_ip', 'nova.netconf')
CONF.import_opt('default_ephemeral_format', 'nova.virt.driver')
CONF.import_opt('use_cow_images', 'nova.virt.driver')
CONF.import_opt('live_migration_retry_count', 'nova.compute.manager')
CONF.import_opt('vncserver_proxyclient_address', 'nova.vnc')
CONF.import_opt('server_proxyclient_address', 'nova.spice', group='spice')



class Failure(Exception):
    """Base Exception class for handling task failures."""

    def __init__(self, details):
        self.details = details

    def __str__(self):
        return str(self.details)


def get_connection(_read_only):
    """Sets up the smartOS connection."""
    return SmartOSDriver()


class SmartOSDriver(driver.ComputeDriver):
    """The smartOS host connection object."""

    capabilities = {
        "has_imagecache": True,
        "supports_recreate": True,
        }

    def __init__(self):
        self._host_state = None
        self.read_only = False
        self._vmops = vmops.SmartOSOps()

    def init_host(self, host):
        """Do the initialization that needs to be done."""
        # FIXME(sateesh): implement this
        pass

    def list_instances(self):
        """List VM instances."""
        return self._vmops.list_instances()

    def list_instance_uuids(self):
        """
        Return the UUIDS of all the instances known to the virtualization
        layer, as a list.
        """
        return self._vmops.list_instances_uuids()

    def spawn(self, context, instance, image_meta, injected_files,
              admin_password, network_info=None, block_device_info=None):
        """Create VM instance."""
        self._vmops.spawn(context, instance, image_meta, network_info)

    def snapshot(self, context, instance, name):
        """Create snapshot from a running VM instance."""
        self._vmops.snapshot(context, instance, name)

    def reboot(self, instance, network_info, reboot_type,
               block_device_info=None):
        """Reboot VM instance."""
        self._vmops.reboot(instance, network_info)

    def destroy(self, instance, network_info, block_device_info=None):
        """Destroy VM instance."""
        LOG.error("HXO: instance %s" % repr(instance))
        self._vmops.destroy(instance, network_info)

    def pause(self, instance):
        """Pause VM instance."""
        self._vmops.pause(instance)

    def unpause(self, instance):
        """Unpause paused VM instance."""
        self._vmops.unpause(instance)

    def suspend(self, instance):
        """Suspend the specified instance."""
        self._vmops.suspend(instance)

    def resume(self, instance):
        """Resume the suspended VM instance."""
        self._vmops.resume(instance)

    def get_info(self, instance):
        """Return info about the VM instance."""
        return self._vmops.get_info(instance)

    def get_diagnostics(self, instance):
        """Return data about VM diagnostics."""
        return self._vmops.get_info(instance)

    def get_console_output(self, instance):
        """Return snapshot of console."""
        return self._vmops.get_console_output(instance)

    def get_volume_connector(self, _instance):
        """Return volume connector information"""
        # TODO(vish): When volume attaching is supported, return the
        #             proper initiator iqn.
        # return {
        #     'ip': FLAGS.vmwareapi_host_ip,
        #     'initiator': None
        # }
        raise NotImplementedError()

    def attach_volume(self, connection_info, instance_name, mountpoint):
        """Attach volume storage to VM instance."""
        pass

    def detach_volume(self, connection_info, instance_name, mountpoint):
        """Detach volume storage to VM instance."""
        pass

    def get_disk_available_least(self):
        return 100

    def update_available_resource(self, ctxt, host):
        """Updates compute manager resource info on ComputeNode table.
       This method is called as an periodic tasks and is used only
          in live migration currently.
             :param ctxt: security context
                :param host: hostname that compute manager is currently running
        """

        try:
            service_ref = db.service_get_all_compute_by_host(ctxt, host)[0]
        except exception.NotFound:
            raise exception.ComputeServiceUnavailable(host=host)

        # Updating host information
        dic = {'vcpus': self.get_vcpu_total(),
           'memory_mb': self.get_memory_mb_total(),
           'local_gb': self.get_local_gb_total(),
           'vcpus_used': self.get_vcpu_used(),
       'memory_mb_used': self.get_memory_mb_used(),
       'local_gb_used': self.get_local_gb_used(),
           'hypervisor_type': self.get_hypervisor_type(),
           'hypervisor_version': self.get_hypervisor_version(),
           'cpu_info': self.get_cpu_info(),
           'service_id': service_ref['id'],
           'disk_available_least': self.get_disk_available_least()}

        compute_node_ref = service_ref['compute_node']
        if not compute_node_ref:
            LOG.info(_('Compute_service record created for %s ') % host)
            db.compute_node_create(ctxt, dic)
        else:
            LOG.info(_('Compute_service record updated for %s ') % host)
            db.compute_node_update(ctxt, compute_node_ref[0]['id'], dic)

    def get_available_resource(self):
        """Retrieve resource info.

        This method is called as a periodic task and is used only
        in live migration currently.

        :returns: dictionary containing resource info
        """
        dic = {'vcpus': self.get_vcpu_total(),
               'memory_mb': self.get_memory_mb_total(),
               'local_gb': self.get_local_gb_total(),
               'vcpus_used': self.get_vcpu_used(),
               'memory_mb_used': self.get_memory_mb_used(),
               'local_gb_used': self.get_local_gb_used(),
               'hypervisor_type': self.get_hypervisor_type(),
               'hypervisor_version': self.get_hypervisor_version(),
               'hypervisor_hostname': self.get_hypervisor_hostname(),
               'cpu_info': self.get_cpu_info(),
               'disk_available_least': self.get_disk_available_least()}
        return dic

    def get_hypervisor_hostname(self):
        return socket.gethostname()

    def host_power_action(self, host, action):
        """Reboots, shuts down or powers up the host."""
        raise NotImplementedError()

    def host_maintenance_mode(self, host, mode):
        """Start/Stop host maintenance window. On start, it triggers
        guest VMs evacuation."""
        raise NotImplementedError()

    def set_host_enabled(self, host, enabled):
        """Sets the specified host's ability to accept new instances."""
        raise NotImplementedError()

    def update_host_status(self):
        """Refresh host stats"""
        return self.host_state.update_status()

    @property
    def host_state(self):
        if not self._host_state:
            self._host_state = HostState(self.read_only)
        return self._host_state

    def get_host_stats(self, refresh=False):
        """Return currently known host stats"""
        return self.host_state.get_host_stats(refresh=refresh)

    def plug_vifs(self, instance, network_info):
        """Plug VIFs into networks."""
        self._vmops.plug_vifs(instance, network_info)

    def unplug_vifs(self, instance, network_info):
        """Unplug VIFs from networks."""
        self._vmops.unplug_vifs(instance, network_info)

    @staticmethod
    def get_vcpu_total():
        # Use psrinfo
        return 10

    @staticmethod
    def get_vcpu_used():
        # vmadm list -o vcpus
        return 0

    @staticmethod
    def get_cpu_info():
        cpu_info = dict()

        cpu_info['arch'] = "x86_64"
        cpu_info['model'] = "Xeon"
        cpu_info['vendor'] = "Intel"

        topology = dict()
        topology['sockets'] = 1
        topology['cores'] = 2
        topology['threads'] = 4
        cpu_info['topology'] = topology

        features = list()
        features.append("sse")
        cpu_info['features'] = features

        guest_arches = list()
        guest_arches.append("i386")
        guest_arches.append("x86_64")
        cpu_info['permitted_instance_types'] = guest_arches
        # TODO: See smartos/driver.py:2149
        return jsonutils.dumps(cpu_info)

    @staticmethod
    def get_memory_mb_total():
        # prtconf |grep -i mem
        return 12000

    @staticmethod
    def get_memory_mb_used():
        #  echo ::memstat | mdb -k
        return 0

    @staticmethod
    def get_local_gb_used():
        # zpool list -p zones
        return 0

    @staticmethod
    def get_local_gb_total():
        return 20

    @staticmethod
    def get_hypervisor_type():
        return "kvm"

    @staticmethod
    def get_hypervisor_version():
        return 1


class HostState(object):
    """Manages information about the compute node through smartos"""
    def __init__(self, read_only):
        super(HostState, self).__init__()
        self.read_only = read_only
        self._stats = {}
        self.connection = None
        self.update_status()

    def get_host_stats(self, refresh=False):
        """Return the current state of the host.

        If 'refresh' is True, run update the stats first."""
        if refresh:
            self.update_status()
        return self._stats

    def update_status(self):
        """Retrieve status info from smartos."""
        LOG.debug(_("Updating host stats"))
        if self.connection is None:
            self.connection = get_connection(self.read_only)
        data = {"vcpus": self.connection.get_vcpu_total(),
                "vcpus_used": self.connection.get_vcpu_used(),
                "cpu_info": jsonutils.loads(self.connection.get_cpu_info()),
                "disk_total": self.connection.get_local_gb_total(),
                "disk_used": self.connection.get_local_gb_used()}
        data["disk_available"] = data["disk_total"] - data["disk_used"]
        data["host_memory_total"] = self.connection.get_memory_mb_total()
        data["host_memory_free"] = (data["host_memory_total"] -
                                    self.connection.get_memory_mb_used())
        data["hypervisor_type"] = self.connection.get_hypervisor_type()
        data["hypervisor_version"] = self.connection.get_hypervisor_version()

        self._stats = data

        return data
