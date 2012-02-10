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

import random
import uuid        
import json

from nova import flags
from nova import compute
import nova.network.api
from nova import exception
from nova import log as logging
from nova.compute import task_states
from nova.compute import vm_states
from nova.compute import instance_types
from nova.rpc import common as rpc_common
import nova.policy
from nova.api.occi.backends import MyBackend
from nova.api.occi.extensions import ResourceTemplate, KEY_PAIR_EXT, \
    ADMIN_PWD_EXT
from nova.api.occi.extensions import OsTemplate

from occi.exceptions import HTTPError
from occi.extensions import infrastructure
from nova.api.occi import extensions
from webob import exc
from occi.extensions.infrastructure import NETWORKINTERFACE
from occi.core_model import Link
from occi.extensions.infrastructure import IPNETWORKINTERFACE

FLAGS = flags.FLAGS

# Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.compute')

class ComputeBackend(MyBackend):
    '''
    A Backend for compute instances.
    '''

    def __init__(self):
        
        nova.policy.reset()
        nova.policy.init()
        self.compute_api = compute.API()
        self.network_api = nova.network.api.API()

    def create(self, resource, extras):

        #TODO: if a request arrives with explicit values for certain attrs
        # like occi.compute.cores then a bad request must be issued
        # OpenStack does not support this. 

        LOG.info('Creating the virtual machine with id: ' + resource.identifier)

        try:
            name = resource.attributes['occi.core.title']
        except KeyError:
            name = resource.attributes['occi.core.title'] = \
                            str(random.randrange(0, 99999999)) + \
                                                        '-compute.occi-wg.org'

        key_name = None
        key_data = None
        password = None
        metadata = {}
        access_ip_v4 = None
        access_ip_v6 = None
        injected_files = []
        zone_blob = None
        reservation_id = None
        min_count = max_count = 1
        requested_networks = None
        sg_names = []
        sg_names.append('default')
        sg_names = list(set(sg_names))
        user_data = None
        availability_zone = None
        config_drive = None
        block_device_mapping = None
        #TODO: this can be specified through OS Templates
        kernel_id = None
        #TODO: this can be specified through OS Templates
        ramdisk_id = None
        auto_disk_config = None
        scheduler_hints = None
        
        # Essential, required to get a vm image e.g. 
        #            image_href = 'http: // 10.211.55.20:9292/v1/images/1'
        # Extract resource template from link and get the flavor name. 
        # Flavor name is the term
        os_tpl_url = None
        flavor_name = None
        
        if len(resource.mixins) > 0:
            rc = oc = 0
            for mixin in resource.mixins:
                if isinstance(mixin, ResourceTemplate):
                    r = mixin
                    rc += 1
                elif isinstance(mixin, OsTemplate):
                    o = mixin
                    oc += 1
                elif (mixin.scheme + mixin.term) == \
                                    (KEY_PAIR_EXT.scheme + KEY_PAIR_EXT.term):
                    key_name = resource.attributes\
                                ['org.openstack.credentials.publickey.name']
                    key_data = resource.attributes\
                                ['org.openstack.credentials.publickey.data']
                elif (mixin.scheme + mixin.term) == \
                                (ADMIN_PWD_EXT.scheme + ADMIN_PWD_EXT.term):
                    password = resource.attributes\
                                        ['org.openstack.credentials.admin_pwd']

            if rc > 1:
                msg = 'There is more than one resource template in the request'
                LOG.error(msg)
                raise AttributeError(msg=unicode(msg))
            if oc > 1:
                msg = 'There is more than one OS template in the request'
                LOG.error(msg)
                raise AttributeError()

            flavor_name = r.term
            os_tpl_url = o.os_id
        
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

            (instances, resv_id) = self.compute_api.create(
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
                                    zone_blob=zone_blob,
                                    reservation_id=reservation_id,
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
        # TODO: can't we tell this from the image used?
        # The architecture is sometimes encoded in the image file's name
        # This is not reliable. db::glance::image_properties could be used
        # reliably so long as the information is supplied.
        # To use this the image must be registered with the required
        # metadata.
        resource.attributes['occi.compute.architecture'] = 'x86'
        resource.attributes['occi.compute.cores'] = str(instances[0]['vcpus'])
        # occi.compute.speed is not available in instances by default.
        # CPU speed is not available but could be made available through
        # db::nova::compute_nodes::cpu_info
        # additional code is required in 
        #     nova/nova/virt/libvirt/connection.py::get_cpu_info()
        # note: this would be the physical node's speed not necessarily
        #     the VMs.
        resource.attributes['occi.compute.speed'] = str(2.4)
        resource.attributes['occi.compute.memory'] = \
                                str(float(instances[0]['memory_mb']) / 1024)
        resource.attributes['occi.compute.state'] = 'active'

        # this must be called on create as the cached info 
        # has not been updated at this point
        self._get_network_info(instances[0], resource, extras, True)

    def _get_network_info(self, instance, resource, extras, live_query):
        # Once created, the VM is attached to a public network with an 
        # addresses allocated by DHCP
        # A link is created to this network (IP) and set the ip to that of the
        # allocated ip
    
        if live_query:
            sj = self.network_api.get_instance_nw_info(extras['nova_ctx'], instance)
        else:
            sj = instance['info_cache'].network_info
        
        # TODO: currently this assumes one adapter on the VM. It must account
        # for more than one adaptor
        # can probably remove this check 
        if sj != None:
            dj = json.loads(sj)
            vm_iface = dj[0]['network']['meta']['bridge_interface']
            address = dj[0]['network']['subnets'][0]['ips'][0]['address']
            gateway = dj[0]['network']['subnets'][0]['gateway']['address']
        else:
            vm_iface = ''
            address = ''
            gateway = ''
        
        #Get a handle to the default network
        registry = extras['registry']
        default_network = registry.get_resource('/network/DEFAULT_NETWORK')
        source = resource
        target = default_network
    
        identifier = str(uuid.uuid4())
        link = Link(identifier, NETWORKINTERFACE, [IPNETWORKINTERFACE], source, target)
        
        link.attributes['occi.core.id'] = identifier 
        link.attributes['occi.networkinterface.interface'] = vm_iface
        #TODO mac address info is not available
        link.attributes['occi.networkinterface.mac'] = 'DE:AD:BE:EF:BA:BE'
        link.attributes['occi.networkinterface.state'] = 'active'
        link.attributes['occi.networkinterface.address'] = address
        link.attributes['occi.networkinterface.gateway'] = gateway
        link.attributes['occi.networkinterface.allocation'] = 'dhcp'
        
    #        target = 'ssh://' + address + ':22'
    #        identifier = str(uuid.uuid4())
    #        sshlink = Link(identifier, Link.kind, [], source, target)
    #        sshlink.attributes['occi.core.id'] = identifier
        
        resource.links = [link] #, sshlink

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
            "InstanceLimitExceeded":
                    _("Instance quotas have been exceeded")}

        expl = code_mappings.get(error.code)
        if expl:
            raise exc.HTTPRequestEntityTooLarge(explanation=expl,
                                                headers={'Retry-After': 0})
        # if the original error is okay, just reraise it
        raise error

    def retrieve(self, entity, extras):
        self._retrieve(entity, extras)

    def _retrieve(self, entity, extras):
        context = extras['nova_ctx']
        
        uid = entity.attributes['occi.core.id']
        
        #if uid.find(entity.kind.location) > -1:
        #    uid = uid.replace(entity.kind.location, '')
  
        try:
            instance = self.compute_api.routing_get(context, uid)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        
        # See nova/compute/vm_states.py nova/compute/task_states.py
        #
        # Mapping assumptions:
        #  - active == VM can service requests from network. These requests
        #            can be from users or VMs
        #  - inactive == the oppose! :-)
        #  - suspended == machine in a frozen state e.g. via suspend or pause
        #
         
        # change password - OS 
        # confirm resized server
        if instance['vm_state'] in (vm_states.ACTIVE, task_states.UPDATING_PASSWORD, \
                     task_states.RESIZE_VERIFY):
            entity.attributes['occi.compute.state'] = 'active'
            entity.actions = [infrastructure.STOP, infrastructure.SUSPEND, \
                                                        infrastructure.RESTART]
        
        # reboot server - OS, OCCI
        # start server - OCCI
        elif instance['vm_state'] in (task_states.STARTING, task_states.POWERING_ON, \
                       task_states.REBOOTING, task_states.REBOOTING_HARD):
            entity.attributes['occi.compute.state'] = 'inactive'
            entity.actions = []
        
        # pause server - OCCI, suspend server - OCCI, stop server - OCCI
        elif instance['vm_state'] in (task_states.STOPPING, task_states.POWERING_OFF):
            entity.attributes['occi.compute.state'] = 'inactive'
            entity.actions = [infrastructure.START]
        
        # resume server - OCCI
        elif instance['vm_state'] in (task_states.RESUMING, task_states.PAUSING, \
                       task_states.SUSPENDING):
            entity.attributes['occi.compute.state'] = 'suspended'
            if instance['vm_state'] in (vm_states.PAUSED, vm_states.SUSPENDED):
                entity.actions = [infrastructure.START]
            else:
                entity.actions = []
        
        # rebuild server - OS
        # resize server confirm rebuild
        # revert resized server - OS (indirectly OCCI)
        elif instance['vm_state'] in (
                       vm_states.RESIZING,
                       vm_states.REBUILDING,
                       task_states.RESIZE_CONFIRMING,
                       task_states.RESIZE_FINISH,
                       task_states.RESIZE_MIGRATED,
                       task_states.RESIZE_MIGRATING,
                       task_states.RESIZE_PREP,
                       task_states.RESIZE_REVERTING):
            entity.attributes['occi.compute.state'] = 'inactive'
            entity.actions = []
        
        #Now we have the instance state, get its network info
        self._get_network_info(instance, entity, extras)
        
        return instance

    def delete(self, entity, extras):
        # call the management framework to delete this compute instance...
        LOG.info('Removing representation of virtual machine with id: '
              + entity.identifier)

        context = extras['nova_ctx']
        
        uid = entity.attributes['occi.core.id']
        # TODO at some stage the uid gets munged with location.
        #if uid.find(entity.kind.location) > -1:
        #    uid = uid.replace(entity.kind.location, '')
        
        try:
            instance = self.compute_api.routing_get(context, uid)
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
        
        context = extras['nova_ctx']
        instance = self._retrieve(old, extras)
        
        # for now we will only handle one mixin change per request
        if len(new.mixins) == 1:
            #Find out what the mixin is.
            mixin = new.mixins[0]
            # check for scale up in new
            if isinstance(mixin, ResourceTemplate):
                LOG.info('Resize requested')
                raise exc.HTTPForbidden
                # XXX: Ok, this sucks a little... resize is only supported on 
                #      Xen: http://wiki.openstack.org/HypervisorSupportMatrix
                flavor = \
                        instance_types.get_instance_type_by_name(mixin.term)
                self.compute_api.resize(context, instance, flavor['flavorid'])
                #now update the mixin info
                
                
            # check for new os rebuild in new
            elif isinstance(mixin, OsTemplate):
                LOG.info('Rebuild requested')
                raise exc.HTTPForbidden
                image_href = mixin.os_id
                # TODO: where's best to supply this info?
                # as an atttribute?
                admin_password = 'TODO'
                old.attributes['occi.compute.state'] = 'inactive'
                self.compute_api.rebuild(context, instance, image_href, \
                                            admin_password, None, None, None)
            else:
                LOG.error('I\'ve no idea what this mixin is! ' + \
                                                    mixin.scheme + mixin.term)
                raise exc.HTTPBadRequest()
        elif len(new.mixins) > 1:
            raise exc.HTTPBadRequest()
        
        # if new.attributes > 0 then ignore for now
        # you can change occi.core.title, what about hostname?
        # in the specific case of openstack, you cannot directly change things
        # like occi.core.memory - you must resize i.e. change the resource
        # template 
        if new.attributes > 0:
            LOG.info('Updating mutable attributes of instance')

        # if new.links > 0 then ignore
        # this will be important to enable linking of a resource to another
        if new.links == 1:
            LOG.info('Associate resource with another.')
        elif len(new.mixins) > 1:
            raise exc.HTTPBadRequest()

    def action(self, entity, action, extras):

        # As there is no callback mechanism to update the state  
        # of computes known by occi, a call to get the latest representation 
        # must be made.
        instance = self._retrieve(entity, extras)

        context = extras['nova_ctx']

        if action not in entity.actions:
            raise AttributeError("This action is not currently applicable.")
        elif action == infrastructure.START:
            LOG.info('Starting virtual machine with id' + entity.identifier)
            entity.attributes['occi.compute.state'] = 'active'
            entity.actions = [infrastructure.STOP, infrastructure.SUSPEND, \
                                                        infrastructure.RESTART]
            self.compute_api.start(context, instance)

        elif action == infrastructure.STOP:
            # OCCI -> graceful, acpioff, poweroff
            # OS -> unclear
            LOG.info('Stopping virtual machine with id' + entity.identifier)
            if entity.attributes.has_key('method'):
                LOG.info('OS only allows one type of stop. What is \
                            specified in the request will be ignored.')
            entity.attributes['occi.compute.state'] = 'inactive'
            entity.actions = [infrastructure.START]
            self.compute_api.stop(context, instance)
            self.compute_api.pause(context, instance)
            
        elif action == infrastructure.RESTART:
            LOG.info('Restarting virtual machine with id' + entity.identifier)
            entity.attributes['occi.compute.state'] = 'inactive'
            entity.actions = []
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
            self.compute_api.reboot(context, instance, reboot_type)
        elif action == infrastructure.SUSPEND:
            LOG.info('Suspending virtual machine with id' + entity.identifier)
            if entity.attributes.has_key('method'):
                LOG.info('OS only allows one type of suspend. What is \
                            specified in the request will be ignored.')
            entity.attributes['occi.compute.state'] = 'suspended'
            entity.actions = [infrastructure.START]
            self.compute_api.suspend(context, instance)
        elif action == extensions.OS_CHG_PWD:
            # TODO: Review - it'll need the password sent as well as the
            #                new password value.
            raise exc.HTTPNotImplemented()
        
            if not entity.attributes.has_key('method'):
                raise exc.HTTPBadRequest()
            entity.attributes['occi.compute.state'] = 'active'
            entity.actions = [infrastructure.STOP, infrastructure.SUSPEND, \
                                                        infrastructure.RESTART]
            self.compute_api.set_admin_password(context, instance, \
                                                entity.attributes['method'])
        elif action == extensions.OS_REBUILD:
            #TODO: there must be an OsTemplate mixin with the request and
            #      there must be the admin password to the instance
            raise exc.HTTPNotImplemented()
        
            image_href = 'TODO'
            admin_password = 'TODO'
            entity.attributes['occi.compute.state'] = 'inactive'
            self.compute_api.rebuild(context, instance, image_href, \
                                            admin_password, None, None, None)
        elif action == extensions.OS_REVERT_RESIZE:
            raise exc.HTTPNotImplemented()
            LOG.info('Reverting resized virtual machine with id' + \
                                                            entity.identifier)
            self.compute_api.revert_resize(context, instance)
        elif action == extensions.OS_CONFIRM_RESIZE:
            raise exc.HTTPNotImplemented()
            LOG.info('Confirming resize of virtual machine with id' + \
                                                            entity.identifier)
            self.compute_api.confirm_resize(context, instance)
        else:
            raise exc.HTTPBadRequest()
        

