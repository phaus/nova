# vim: tabstop=4 shiftwidth=4 softtabstop=4
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

import uuid        
import json
# TODO: use OCCI exceptions
from webob import exc

from nova import utils
from nova import image
from nova import flags
from nova import compute
from nova.network import api as net_api
from nova import exception
from nova import log as logging
from nova.compute import task_states
from nova.compute import vm_states
from nova.compute import instance_types
from nova.rpc import common as rpc_common
from nova import policy

from nova.api.occi import extensions
from nova.api.occi import backends

from occi.exceptions import HTTPError
from occi.extensions import infrastructure
from occi import core_model


FLAGS = flags.FLAGS

# Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.compute')

# pop/delete attributes on DELETE
# TODO: move _os_* actions to their own backend
# TODO: remove MyBackend
class ComputeBackend(backends.MyBackend):
    '''
    A Backend for compute instances.
    '''

    def __init__(self):
        #super(backends.MyBackend, self).__init__()
        policy.reset()
        policy.init()
        self.compute_api = compute.API()
        self.network_api = net_api.API()

    def create(self, resource, extras):

        # If a request arrives with explicit values for certain attrs
        # like occi.compute.cores then a bad request must be issued
        # OpenStack does not support this. 

        if ('occi.compute.cores' in resource.attributes) \
            or ('occi.compute.speed' in resource.attributes) \
            or ('occi.compute.memory' in resource.attributes) \
            or ('occi.compute.architecture' in resource.attributes):
            msg = 'There are unsupported attributes in the request.'
            LOG.error(msg)
            raise AttributeError(msg)
        
        LOG.info('Creating the virtual machine with id: ' + resource.identifier)

        try:
            name = resource.attributes['occi.compute.hostname']
        except KeyError:
            name = None 
            #str(random.randrange(0, 99999999)) + '-compute.occi-wg.org'
        
        # Supplied by OCCI extension
        key_name = None
        key_data = None
        
        #Auto-gen'ed 1st if OCCI extension supplied this will overwrite this
        password = utils.generate_password(FLAGS.password_length)
        
        # L8R: see what the effect on VM network config is when these are set
        access_ip_v4 = None
        access_ip_v6 = None
        #L8R: would be good to specify user_data via OCCI
        user_data = None
        metadata = {}
        injected_files = []
        min_count = max_count = 1
        requested_networks = None
        sg_names = []
        availability_zone = None
        config_drive = None
        block_device_mapping = None
        #L8R: this can be specified through OS Templates
        kernel_id = None
        #L8R: this can be specified through OS Templates
        ramdisk_id = None
        auto_disk_config = None
        scheduler_hints = None
        
        os_tpl_url = None
        flavor_name = None
        
        if len(resource.mixins) > 0:
            rc = oc = 0
            for mixin in resource.mixins:
                if isinstance(mixin, extensions.ResourceTemplate):
                    r = mixin
                    rc += 1
                elif isinstance(mixin, extensions.OsTemplate):
                    o = mixin
                    oc += 1
                elif (mixin.scheme + mixin.term) == \
                                    (extensions.KEY_PAIR_EXT.scheme + extensions.KEY_PAIR_EXT.term):
                    # TODO: see nova/api/openstack/compute/contrib/keypairs.py
                    key_name = resource.attributes \
                                ['org.openstack.credentials.publickey.name']
                    key_data = resource.attributes \
                                ['org.openstack.credentials.publickey.data']
                elif (mixin.scheme + mixin.term) == \
                                (extensions.ADMIN_PWD_EXT.scheme + extensions.ADMIN_PWD_EXT.term):
                    password = resource.attributes \
                                        ['org.openstack.credentials.admin_pwd']
                elif mixin.scheme == \
                    'http://schemas.ogf.org/occi/infrastructure/security/group#':
                    sg_names.append(mixin.term)

            if rc < 1 and oc < 1:
                LOG.error('No resource or OS template in the request.')
                exc.HTTPBadRequest()
            if rc > 1:
                msg = 'There is more than one resource template in the request'
                LOG.error(msg)
                raise AttributeError(msg=unicode(msg))
            if oc > 1:
                msg = 'There is more than one OS template in the request'
                LOG.error(msg)
                raise AttributeError(msg=unicode(msg))
            #If no security group, ensure the default is applied
            if len(sg_names) == 0:
                sg_names.append('default')
                
            flavor_name = r.term
            os_tpl_url = o.os_id
            sg_names = list(set(sg_names))
            
        try:
            if flavor_name:
                inst_type = \
                        instance_types.get_instance_type_by_name(flavor_name)
            else:
                inst_type = instance_types.get_default_instance_type()
                msg = 'No resource template was found in the request. \
                                Using the default: ' + inst_type['name']
                LOG.warn(msg)

            if not os_tpl_url: #possibly an edge case
                msg = 'No URL to an image file has been found.'
                LOG.error(msg)
                raise HTTPError(404, msg)

            (instances, _) = self.compute_api.create(
                                    context=extras['nova_ctx'],
                                    instance_type=inst_type,
                                    image_href=os_tpl_url,
                                    kernel_id=kernel_id,
                                    ramdisk_id=ramdisk_id,
                                    min_count=min_count,
                                    max_count=max_count,
                                    display_name=name,
                                    display_description=name,
                                    key_name=key_name,
                                    key_data=key_data,
                                    security_group=sg_names,
                                    availability_zone=availability_zone,
                                    user_data=user_data,
                                    metadata=metadata,
                                    injected_files=injected_files,
                                    admin_password=password,
                                    block_device_mapping=block_device_mapping,
                                    access_ip_v4=access_ip_v4,
                                    access_ip_v6=access_ip_v6,
                                    requested_networks=requested_networks,
                                    config_drive=config_drive,
                                    auto_disk_config=auto_disk_config,
                                    scheduler_hints=scheduler_hints)
            
        except exception.QuotaError as error:
            self._handle_quota_error(error)
        except exception.InstanceTypeMemoryTooSmall as error:
            raise exc.HTTPBadRequest(explanation=unicode(error))
        except exception.InstanceTypeDiskTooSmall as error:
            raise exc.HTTPBadRequest(explanation=unicode(error))
        except exception.ImageNotFound as error:
            msg = _("Can not find requested image")
            raise exc.HTTPBadRequest(explanation=msg)
        except exception.FlavorNotFound as error:
            msg = _("Invalid flavor provided.")
            raise exc.HTTPBadRequest(explanation=msg)
        except exception.KeypairNotFound as error:
            msg = _("Invalid key_name provided.")
            raise exc.HTTPBadRequest(explanation=msg)
        except exception.SecurityGroupNotFound as error:
            raise exc.HTTPBadRequest(explanation=unicode(error))
        except rpc_common.RemoteError as err:
            msg = "%(err_type)s: %(err_msg)s" % \
                  {'err_type': err.exc_type, 'err_msg': err.value}
            raise exc.HTTPBadRequest(explanation=msg)
        
        resource.attributes['occi.core.id'] = instances[0]['uuid']
        resource.attributes['occi.compute.hostname'] = instances[0]['hostname']
        resource.attributes['occi.compute.architecture'] = \
                                    self._get_vm_arch(extras['nova_ctx'], o)
        # We try to guess this
        resource.attributes['occi.compute.cores'] = str(instances[0]['vcpus'])
        # L8R: occi.compute.speed is not available in instances by default.
        # CPU speed is not available but could be made available through
        # db::nova::compute_nodes::cpu_info
        # additional code is required in 
        #     nova/nova/virt/libvirt/connection.py::get_cpu_info()
        # note: this would be the physical node's speed not necessarily
        #     the VMs.
        
        #L8R: find a way to get CPU speed
        resource.attributes['occi.compute.speed'] = str(0.0)
        resource.attributes['occi.compute.memory'] = \
                                str(float(instances[0]['memory_mb']) / 1024)
        resource.attributes['occi.compute.state'] = 'active'

        # Once created, the VM is attached to a public network with an 
        # addresses allocated by DHCP
        # A link is created to this network (IP) and set the ip to that of the
        # allocated ip
        
        # this must be called as 'live' on create as the cached info 
        # has not been updated at this point
        vm_net_info = self._get_adapter_info(instances[0], extras, True)
        self._attach_to_default_network(vm_net_info, resource, extras)
        
        self._get_console_info(resource, extras)
        
        #set valid actions
        resource.actions = [infrastructure.STOP,
                          infrastructure.SUSPEND, \
                          infrastructure.RESTART, \
                          extensions.OS_REVERT_RESIZE, \
                          extensions.OS_CONFIRM_RESIZE, \
                          extensions.OS_CREATE_IMAGE]
        

    def _get_vm_arch(self, context, os_template_mixin):

        # Extract architecture from either: 
        # - image name, title or metadata. The architecture is sometimes 
        #   encoded in the image's name
        # - db::glance::image_properties could be used reliably so long as the 
        # information is supplied when registering an image with glance.
        
        # Heuristic:
        # - if term, title or description has x86_32 or x86_x64 then the arch
        #   is x86 or x64 respectively.
        # - if associated OS image has properties arch or architecture that 
        #   equal x86 or x64.
        # - else return a default of x86
        
        arch = ''
        
        if (os_template_mixin.term.find('x86_64') \
                        or os_template_mixin.title.find('x86_64')) >= 0:
            arch = 'x64'
        elif (os_template_mixin.term.find('x86_32') \
                        or os_template_mixin.title.find('x86_32')) >= 0:
            arch = 'x86'
        else:
            image_service = image.get_default_image_service()
            img = image_service.show(context, os_template_mixin.os_id)
            img_props = img['properties']
            if ('arch' in img_props):
                arch = img['properties']['arch']
            elif ('architecture' in img_props):
                arch = img['properties']['architecture']
        
        # if all attempts fail set it to a default value 
        if arch == '':
            arch = 'x86'
        
        return arch
    
    def _get_adapter_info(self, instance, extras, live_query=False):
        
        vm_net_info = {'vm_iface':'', 'address': '', 'gateway': ''}
        
        if live_query:
            sj = self.network_api.get_instance_nw_info(extras['nova_ctx'], \
                                                                    instance)
        else:
            sj = instance['info_cache'].network_info
        
        #catches an odd error whereby no network info is returned back
        if len(sj) <= 0:
            LOG.warn('No network info was returned either live or cached.')
            return vm_net_info
        
        # L8R: currently this assumes one adapter on the VM.
        # It's likely that this will not be the case when using 
        # Quantum
        if not live_query:
            sj = json.loads(sj)
        vm_net_info['vm_iface'] = \
                        sj[0]['network']['meta']['bridge_interface']
        #OS-specific if a VM is stopped it has no IP address
        if len(sj[0]['network']['subnets'][0]['ips']) > 0:
            vm_net_info['address'] = \
                        sj[0]['network']['subnets'][0]['ips'][0]['address']
        else:
            vm_net_info['address'] = ''
        vm_net_info['gateway'] = \
                        sj[0]['network']['subnets'][0]['gateway']['address']
        
        return vm_net_info
    
    def _attach_to_default_network(self, vm_net_info, resource, extras):
        # check that existing network does not exist
        if len(resource.links) > 0:
            for link in resource.links:
                if link.kind.term == "networkinterface" and \
                link.kind.scheme == "http://schemas.ogf.org/occi/infrastructure#":
                    LOG.debug('A link to the network already exists. \
                                            Will update the links attributes.')
                    link.attributes['occi.networkinterface.interface'] = \
                                                        vm_net_info['vm_iface']
                    link.attributes['occi.networkinterface.address'] = \
                                                        vm_net_info['address']
                    link.attributes['occi.networkinterface.gateway'] = \
                                                        vm_net_info['gateway']
                    return
        
        # If the network association does not exist...        
        # Get a handle to the default network
        # TODO: use occi.workflow
        #       this will remove need of registry in extras
        registry = extras['registry']
        default_network = registry.get_resource('/network/DEFAULT_NETWORK')
        source = resource
        target = default_network

        # Create the link to the default network
        identifier = str(uuid.uuid4())
        link = core_model.Link(identifier, infrastructure.NETWORKINTERFACE, \
                    [infrastructure.IPNETWORKINTERFACE], source, target)
        link.attributes['occi.core.id'] = identifier 
        link.attributes['occi.networkinterface.interface'] = vm_net_info['vm_iface']
        #TODO: mac address info is not available
        link.attributes['occi.networkinterface.mac'] = ''
        link.attributes['occi.networkinterface.state'] = 'active'
        link.attributes['occi.networkinterface.address'] = vm_net_info['address']
        link.attributes['occi.networkinterface.gateway'] = vm_net_info['gateway']
        #TODO: set this based on API not by default
        link.attributes['occi.networkinterface.allocation'] = 'dhcp'
        
        resource.links.append(link)
        
        registry.add_resource(identifier, link)
    
    def _get_console_info(self, resource, extras):
        #L8R: There are assumptions here about port numbers, URL fragments
        address = resource.links[0].attributes['occi.networkinterface.address']
        
        ssh_console_present = False
        vnc_console_present = False

        for link in resource.links:
            if link.target.kind.term == "ssh_console" and \
                link.target.kind.scheme == "http://schemas.openstack.org/occi/infrastructure/compute#":
                link.target.attributes['org.openstack.compute.console.ssh'] = \
                                                    'ssh://' + address + ':22'
                ssh_console_present = True
            elif link.target.kind.term == "vnc_console" and \
                link.target.kind.scheme == "http://schemas.openstack.org/occi/infrastructure/compute#":
                link.target.attributes['org.openstack.compute.console.vnc'] = \
                                                    'http://' + address + ':80'
                vnc_console_present = True
        
        if not ssh_console_present:
            
            registry = extras['registry']
                        
            identifier = str(uuid.uuid4())
            ssh_console = core_model.Resource(
                identifier, extensions.SSH_CONSOLE, [],
                links=None, summary='',
                title='')
            ssh_console.attributes['occi.core.id'] = identifier
            ssh_console.attributes['org.openstack.compute.console.ssh'] = \
                                                    'ssh://' + address + ':22'
            registry.add_resource(identifier, ssh_console)
            
            identifier = str(uuid.uuid4())
            ssh_console_link = core_model.Link(
                                    identifier,
                                    extensions.CONSOLE_LINK, \
                                    [], resource, ssh_console)
            ssh_console_link.attributes['occi.core.id'] = identifier
            registry.add_resource(identifier, ssh_console_link)
            
            resource.links.append(ssh_console_link)

        
        if not vnc_console_present:
            
            registry = extras['registry']
                        
            identifier = str(uuid.uuid4())
            vnc_console = core_model.Resource(
                identifier, extensions.VNC_CONSOLE, [],
                links=None, summary='',
                title='')
            vnc_console.attributes['occi.core.id'] = identifier
            vnc_console.attributes['org.openstack.compute.console.vnc'] = \
                                                    'http://' + address + ':80'
            registry.add_resource(identifier, vnc_console)
            
            identifier = str(uuid.uuid4())
            vnc_console_link = core_model.Link(
                                    identifier,
                                    extensions.CONSOLE_LINK, \
                                    [], resource, vnc_console)
            vnc_console_link.attributes['occi.core.id'] = identifier
            registry.add_resource(identifier, vnc_console_link)
            
            resource.links.append(vnc_console_link)
    
    # Note this is a direct lift from nova/api/openstack/compute/servers.py
    # however as it is protected we cannot import it :-(
    def _handle_quota_error(self, error):
        """
        Reraise quota errors as api-specific http exceptions
        """

        code_mappings = {
            "OnsetFileLimitExceeded":
                    _("Personality file limit exceeded"),
            "OnsetFilePathLimitExceeded":
                    _("Personality file path too long"),
            "OnsetFileContentLimitExceeded":
                    _("Personality file content too long"),

            # NOTE(bcwaldon): expose the message generated below in order
            # to better explain how the quota was exceeded
            "InstanceLimitExceeded": error.message,
        }

        expl = code_mappings.get(error.kwargs['code'], error.message)
        raise exc.HTTPRequestEntityTooLarge(explanation=expl,
                                            headers={'Retry-After': 0})


    def retrieve(self, entity, extras):
        context = extras['nova_ctx']
        
        uid = entity.attributes['occi.core.id']
        
        try:
            instance = self.compute_api.get(context, uid)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        
        # See nova/compute/vm_states.py nova/compute/task_states.py
        #
        # Mapping assumptions:
        #  - active == VM can service requests from network. These requests
        #            can be from users or VMs
        #  - inactive == the oppose! :-)
        #  - suspended == machine in a frozen state e.g. via suspend or pause
         
        # change password - OS 
        # confirm resized server
        if instance['vm_state'] in (vm_states.ACTIVE, \
                                    task_states.UPDATING_PASSWORD, \
                                    task_states.RESIZE_VERIFY):
            entity.attributes['occi.compute.state'] = 'active'
            entity.actions = [infrastructure.STOP, \
                              infrastructure.SUSPEND, \
                              infrastructure.RESTART, \
                              extensions.OS_CONFIRM_RESIZE, \
                              extensions.OS_REVERT_RESIZE, \
                              extensions.OS_CHG_PWD, \
                              extensions.OS_CREATE_IMAGE]
        
        # reboot server - OS, OCCI
        # start server - OCCI
        elif instance['vm_state'] in (task_states.STARTING, \
                                      task_states.POWERING_ON, \
                                      task_states.REBOOTING, \
                                      task_states.REBOOTING_HARD):
            entity.attributes['occi.compute.state'] = 'inactive'
            entity.actions = []
        
        # pause server - OCCI, suspend server - OCCI, stop server - OCCI
        elif instance['vm_state'] in (task_states.STOPPING, \
                                      task_states.POWERING_OFF):
            entity.attributes['occi.compute.state'] = 'inactive'
            entity.actions = [infrastructure.START]
        
        # resume server - OCCI
        elif instance['vm_state'] in (task_states.RESUMING, \
                                      task_states.PAUSING, \
                                      task_states.SUSPENDING):
            entity.attributes['occi.compute.state'] = 'suspended'
            if instance['vm_state'] in (vm_states.PAUSED, \
                                        vm_states.SUSPENDED):
                entity.actions = [infrastructure.START]
            else:
                entity.actions = []
        
        # rebuild server - OS
        # resize server confirm rebuild
        # revert resized server - OS (indirectly OCCI)
        elif instance['vm_state'] in (
                       vm_states.RESIZING,
                       vm_states.REBUILDING,
                       # TODO: make sure this is ok
                       task_states.RESIZE_CONFIRMING,
                       task_states.RESIZE_FINISH,
                       task_states.RESIZE_MIGRATED,
                       task_states.RESIZE_MIGRATING,
                       task_states.RESIZE_PREP,
                       task_states.RESIZE_REVERTING):
            entity.attributes['occi.compute.state'] = 'inactive'
            entity.actions = []
        
        #Now we have the instance state, get its updated network info
        vm_net_info = self._get_adapter_info(instance, extras)
        self._attach_to_default_network(vm_net_info, entity, extras)
        self._get_console_info(entity, extras)
        
        return instance


    def delete(self, entity, extras):
        # call the management framework to delete this compute instance...
        LOG.info('Removing representation of virtual machine with id: '
              + entity.identifier)

        context = extras['nova_ctx']
        uid = entity.attributes['occi.core.id']
        
        try:
            instance = self.compute_api.get(context, uid)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        
        if FLAGS.reclaim_instance_interval:
            self.compute_api.soft_delete(context, instance)
        else:
            self.compute_api.delete(context, instance)


    def update(self, old, new, extras):
        
        #Here we can update mixins, links and attributes
        LOG.info('Partial update requested for instance: ' + \
                                            old.attributes['occi.core.id'])
        
        instance = self.retrieve(old, extras)

        # update attributes.
        if len(new.attributes) > 0:
            LOG.info('Updating mutable attributes of instance')
            # support only title and summary changes now.
            if ('occi.core.title' in new.attributes) \
                                    or ('occi.core.title' in new.attributes):
                if len(new.attributes['occi.core.title']) > 0:
                    old.attributes['occi.core.title'] = \
                                            new.attributes['occi.core.title'] 

                if len(new.attributes['occi.core.summary']) > 0:
                    old.attributes['occi.core.summary'] = \
                                            new.attributes['occi.core.summary'] 
            else:
                LOG.error('Cannot update the supplied attributes.')
                raise exc.HTTPBadRequest

        # for now we will only handle one mixin change per request
        
        #Find out what the mixin is.
        mixin = new.mixins[0]
        # check for scale up in new
        if isinstance(mixin, extensions.ResourceTemplate):
            self._os_resize_vm(old, extras, instance, mixin)
            
        # check for new os rebuild in new
        # supported by all hypervisors
        elif isinstance(mixin, extensions.OsTemplate):
            self._os_rebuild_vm(old, extras, instance, mixin)
        elif isinstance(mixin, extensions.SecurityGroupMixin):
            #TODO
            LOG.info('Updating security rule group')
        else:
            LOG.error('I\'ve no idea what this mixin is! ' + \
                                                mixin.scheme + mixin.term)
            raise exc.HTTPBadRequest()
 
        
    def _os_resize_vm(self, old, extras, instance, mixin):
        LOG.info('Resize requested') 
        # Update: libvirt now supports resize see:
        # http://wiki.openstack.org/HypervisorSupportMatrix
        flavor = instance_types.get_instance_type_by_name(mixin.term)
        kwargs = {}
        try:
            self.compute_api.resize(extras['nova_ctx'], instance, \
                                        flavor_id=flavor['flavorid'], **kwargs)
        except exception.FlavorNotFound:
            msg = _("Unable to locate requested flavor.")
            raise exc.HTTPBadRequest(explanation=msg)
        except exception.CannotResizeToSameSize:
            msg = _("Resize requires a change in size.")
            raise exc.HTTPBadRequest(explanation=msg)
        except exception.InstanceInvalidState:
            exc.HTTPConflict()
        old.attributes['occi.compute.state'] = 'inactive'
        #now update the mixin info
        for m in old.mixins:
            if m.term == mixin.term and m.scheme == mixin.scheme:
                m = mixin
                LOG.debug('Resource template is changed: ' + m.scheme + m.term)


    def _os_rebuild_vm(self, old, extras, instance, mixin):
        LOG.info('Rebuild requested')
        image_href = mixin.os_id # L8R: Use the admin_password extension
        admin_password = utils.generate_password(FLAGS.password_length)
        kwargs = {}
        try:
            self.compute_api.rebuild(extras['nova_ctx'], instance, \
                                        image_href, admin_password, **kwargs)
        except exception.InstanceInvalidState:
            exc.HTTPConflict()
        except exception.InstanceNotFound:
            msg = _("Instance could not be found")
            raise exc.HTTPNotFound(explanation=msg)
        except exception.ImageNotFound:
            msg = _("Cannot find image for rebuild")
            raise exc.HTTPBadRequest(explanation=msg)
        old.attributes['occi.compute.state'] = 'inactive'
        #now update the mixin info
        for m in old.mixins:
            if m.term == mixin.term and m.scheme == mixin.scheme:
                m = mixin
                LOG.debug('OS template is changed: ' + m.scheme + m.term)


    def action(self, entity, action, extras):
        # As there is no callback mechanism to update the state  
        # of computes known by occi, a call to get the latest representation 
        # must be made.
        # openstack also allows pause and unpause
        
        instance = self.retrieve(entity, extras)

        context = extras['nova_ctx']
        
        if action not in entity.actions:
            raise AttributeError("This action is not currently applicable.")
        elif action == infrastructure.START:
            self._start_vm(entity, instance, context)
        elif action == infrastructure.STOP:
            self._stop_vm(entity, instance, context)
        elif action == infrastructure.RESTART:
            self._restart_vm(entity, instance, context)
        elif action == infrastructure.SUSPEND:
            self._suspend_vm(entity, instance, context)
        elif action == extensions.OS_CHG_PWD:
            self._os_chg_passwd_vm(entity, instance, context)
        elif action == extensions.OS_REVERT_RESIZE:
            self._os_revert_resize_vm(entity, instance, context)
        elif action == extensions.OS_CONFIRM_RESIZE:
            self._os_confirm_resize_vm(entity, instance, context)
        elif action == extensions.OS_CREATE_IMAGE:
            self._os_create_image(entity, instance, context)
        else:
            raise exc.HTTPBadRequest()
   
        
    def _start_vm(self, entity, instance, context):
        LOG.info('Starting virtual machine with id' + entity.identifier)
        
        try:
            if entity.attributes['occi.compute.state'] == 'suspended':
                self.compute_api.unpause(context, instance)
            else:
                self.compute_api.resume(context, instance)
        except Exception:
            LOG.error('Error in starting VM')
            raise exc.HTTPServerError()
        entity.attributes['occi.compute.state'] = 'active'
        entity.actions = [infrastructure.STOP,
                          infrastructure.SUSPEND, \
                          infrastructure.RESTART, \
                          extensions.OS_REVERT_RESIZE, \
                          extensions.OS_CONFIRM_RESIZE, \
                          extensions.OS_CREATE_IMAGE]


    def _stop_vm(self, entity, instance, context):
        # OCCI -> graceful, acpioff, poweroff
        # OS -> unclear
        LOG.info('Stopping virtual machine with id' + entity.identifier)
        if entity.attributes.has_key('method'):
            LOG.info('OS only allows one type of stop. \
                            What is specified in the request will be ignored.')
        try:
            # L8R: There are issues with the stop and start methods of OS
            #      For now we'll use suspend.
            # self.compute_api.stop(context, instance)
            self.compute_api.suspend(context, instance)
        except Exception:
            LOG.error('Error in stopping VM')
            raise exc.HTTPServerError()
        entity.attributes['occi.compute.state'] = 'inactive'
        entity.actions = [infrastructure.START]


    def _restart_vm(self, entity, instance, context):
        LOG.info('Restarting virtual machine with id' + entity.identifier)
        # OS types == SOFT, HARD
        # OCCI -> graceful, warm and cold
        # mapping:
        #  - SOFT -> graceful, warm
        #  - HARD -> cold
        if not entity.attributes.has_key('method'):
            raise exc.HTTPBadRequest()
        if entity.attributes['method'] in ('graceful', 'warm'):
            reboot_type = 'SOFT'
        elif entity.attributes['method'] is 'cold':
            reboot_type = 'HARD'
        else:
            raise exc.HTTPBadRequest()
        try:
            self.compute_api.reboot(context, instance, reboot_type)
        except exception.InstanceInvalidState:
            exc.HTTPConflict()
        except Exception as e:
            LOG.exception(_("Error in reboot %s"), e)
            raise exc.HTTPUnprocessableEntity()
        entity.attributes['occi.compute.state'] = 'inactive'
        entity.actions = []


    def _suspend_vm(self, entity, instance, context):
        LOG.info('Stopping (suspending) virtual machine with id' + \
                                                            entity.identifier)
        if entity.attributes.has_key('method'):
            LOG.info('OS only allows one type of suspend. \
                            What is specified in the request will be ignored.')
        try:
            self.compute_api.pause(context, instance)
        except Exception:
            LOG.error('Error in stopping VM')
            raise exc.HTTPServerError()
        entity.attributes['occi.compute.state'] = 'suspended'
        entity.actions = [infrastructure.START]


    def _os_chg_passwd_vm(self, entity, instance, context):
        # Use the password extension?
        LOG.info('Changing admin password of virtual machine with id' \
                                                        + entity.identifier)
        if 'org.openstack.credentials.admin_pwd' not in entity.attributes:
            exc.HTTPBadRequest()
            
        new_password = entity.attributes['org.openstack.credentials.admin_pwd']
        self.compute_api.set_admin_password(context, instance, new_password)
        
        # No need to update attributes - state remains the same.


    def _os_revert_resize_vm(self, entity, instance, context):
        LOG.info('Reverting resized virtual machine with id' \
                                                        + entity.identifier)
        try:
            self.compute_api.revert_resize(context, instance)
        except exception.MigrationNotFound:
            msg = _("Instance has not been resized.")
            raise exc.HTTPBadRequest(explanation=msg)
        except exception.InstanceInvalidState:
            exc.HTTPConflict()
        except Exception as e:
            LOG.exception(_("Error in revert-resize %s"), e)
            raise exc.HTTPBadRequest()
        #TODO: update actions


    def _os_confirm_resize_vm(self, entity, instance, context):
        LOG.info('Confirming resize of virtual machine with id' + \
                                                            entity.identifier)
        try:
            self.compute_api.confirm_resize(context, instance)
        except exception.MigrationNotFound:
            msg = _("Instance has not been resized.")
            raise exc.HTTPBadRequest(explanation=msg)
        except exception.InstanceInvalidState:
            exc.HTTPConflict()
        except Exception as e:
            LOG.exception(_("Error in confirm-resize %s"), e)
            raise exc.HTTPBadRequest()
        #TODO: update actions

    
    def _os_create_image(self, entity, instance, context):
        #L8R: There might be a more 'occi' way of doing this
        #     e.g. a POST against /-/
        LOG.info('Creating image from virtual machine with id' + \
                                                            entity.identifier)
        if 'org.openstack.snapshot.image_name' not in entity.attributes:
            exc.HTTPBadRequest()
            
        image_name = entity.attributes['org.openstack.snapshot.image_name']
        props = {}

        try:
            self.compute_api.snapshot(context,
                                      instance,
                                      image_name,
                                      extra_properties=props)

        except exception.InstanceInvalidState:
            exc.HTTPConflict()
        #TODO: update actions
    
