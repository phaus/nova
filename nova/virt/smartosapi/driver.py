# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2012 Hendrik Volkmer
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

import time

from eventlet import event

from nova import context
from nova import db
from nova import exception
from nova import flags
from nova.openstack.common import log as logging
from nova.openstack.common import cfg
from nova.openstack.common import jsonutils

from nova import utils
from nova.virt import driver
from nova.virt.smartosapi import vmops

import socket

LOG = logging.getLogger(__name__)

FLAGS = flags.FLAGS


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

    def spawn(self, context, instance, image_meta,
                              injected_files, admin_password,
                              network_info,
                              block_device_info=None):
        """Create VM instance."""
        self._vmops.spawn(context, instance, image_meta, network_info)

    def snapshot(self, context, instance, name):
        """Create snapshot from a running VM instance."""
        self._vmops.snapshot(context, instance, name)

    def reboot(self, instance, network_info, reboot_type):
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

    def get_console_pool_info(self, console_type):
        """Get info about the host on which the VM resides."""
        return {'address': FLAGS.vmwareapi_host_ip,
                'username': FLAGS.vmwareapi_host_username,
                'password': FLAGS.vmwareapi_host_password}


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
        # TODO: See libvirt/driver.py:2149
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
    """Manages information about the compute node through libvirt"""
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
        """Retrieve status info from libvirt."""
        LOG.debug(_("Updating host stats"))
        if self.connection is None:
            self.connection = get_connection(self.read_only)
        data = {}
        data["vcpus"] = self.connection.get_vcpu_total()
        data["vcpus_used"] = self.connection.get_vcpu_used()
        data["cpu_info"] = jsonutils.loads(self.connection.get_cpu_info())
        data["disk_total"] = self.connection.get_local_gb_total()
        data["disk_used"] = self.connection.get_local_gb_used()
        data["disk_available"] = data["disk_total"] - data["disk_used"]
        data["host_memory_total"] = self.connection.get_memory_mb_total()
        data["host_memory_free"] = (data["host_memory_total"] -
                                    self.connection.get_memory_mb_used())
        data["hypervisor_type"] = self.connection.get_hypervisor_type()
        data["hypervisor_version"] = self.connection.get_hypervisor_version()

        self._stats = data

        return data

