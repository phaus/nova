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


from nova import flags
from nova import compute, exception, log as logging
from nova.compute import task_states
from nova.compute import vm_states
from nova.api.occi.backends import MyBackend
from nova.api.occi.extensions import ResourceTemplate, OsTemplate
from nova.compute import instance_types
from nova.rpc import common as rpc_common
import nova.policy

from occi.exceptions import HTTPError
from occi.extensions import infrastructure
from nova.api.occi import extensions
from webob import exc


FLAGS = flags.FLAGS

# Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.compute')

class ComputeBackend(MyBackend):
    '''
    A Backend for compute instances.
    '''

    # TODO: implement update in super class

    def __init__(self):
        
        nova.policy.reset()
        nova.policy.init()
        self.compute_api = compute.API()
        #self.network_api = network.API()

    def create(self, entity, extras):

        LOG.info('Creating the virtual machine with id: ' + entity.identifier)

        try:
            name = entity.attributes['occi.core.title']
        except KeyError:
            name = 'Default Title (OCCI)'
        
        key_name = None
        metadata = {}
        access_ip_v4 = None
        access_ip_v6 = None
        injected_files = []
        password = 'password'
        zone_blob = 'blob'
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

        # context is mainly authorisation information
        # its assembled in AuthMiddleware - we can pipeline this with the 
        # OCCI service
        context = extras['nova_ctx']
        
        #essential, required to get a vm image e.g. 
        #            image_href = 'http: // 10.211.55.20:9292 / v1 / images / 1'
        #extract resource template from entity and get the flavor name. 
        #            Flavor name is the term
        os_tpl_url = None
        flavor_name = None
        if len(entity.mixins) > 0:
            rc = oc = 0
            for mixin in entity.mixins:
                if isinstance(mixin, ResourceTemplate):
                    r = mixin
                    rc += 1
                elif isinstance(mixin, OsTemplate):
                    o = mixin
                    oc += 1

            if rc > 1:
                msg = 'There is more than one resource template in the request'
                LOG.error(msg)
                raise AttributeError(msg=unicode(msg))
            if oc > 1:
                msg = 'There is more than one resource template in the request'
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

            # all are None by default except context, inst_type and image_href
            (instances, resv_id) = self.compute_api.create(context,
                            inst_type,
                            image_href=os_tpl_url,
                            display_name=name,
                            display_description=name,
                            key_name=key_name,
                            metadata=metadata,
                            access_ip_v4=access_ip_v4,
                            access_ip_v6=access_ip_v6,
                            injected_files=injected_files,
                            admin_password=password,
                            zone_blob=zone_blob,
                            reservation_id=reservation_id,
                            min_count=min_count,
                            max_count=max_count,
                            requested_networks=requested_networks,
                            security_group=sg_names,
                            user_data=user_data,
                            availability_zone=availability_zone,
                            config_drive=config_drive,
                            block_device_mapping=block_device_mapping)
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
            msg = _("Invalid flavorRef provided.")
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
        
        entity.attributes['occi.core.id'] = instances[0]['uuid']
        entity.attributes['occi.compute.hostname'] = instances[0]['hostname']
        # TODO: can't we tell this from the image used?
        # architecture is sometimes encoded in the image file's name
        # This is not reliable. db::glance::image_properties could be used
        # reliably so long as the information is supplied.
        entity.attributes['occi.compute.architecture'] = 'x86'
        entity.attributes['occi.compute.cores'] = str(instances[0]['vcpus'])
        # occi.compute.speed is not available in instances by default
        # cpu speed is not available but could be made available through
        # db::nova::compute_nodes::cpu_info
        # additional code is required in 
        #     nova/nova/virt/libvirt/connection.py::get_cpu_info()
        # note: this would be the physical node's speed not necessarily
        #     the VMs.
        entity.attributes['occi.compute.speed'] = str(2.4)
        entity.attributes['occi.compute.memory'] = \
                                str(float(instances[0]['memory_mb']) / 1024)
        entity.attributes['occi.compute.state'] = 'active'

        # TODO: Once created, the VM is attached to a public network with an 
        # addresses allocated by DHCP
        # Then create link to this network (IP) and set the ip to that of the
        # allocated ip
        # To create an OS floating IP then dhcp would be switched to static

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
        
        # TODO: at some stage the uid gets munged with location.
        if uid.find(entity.kind.location) > -1:
            uid = uid.replace(entity.kind.location, '')
  
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
        # TODO expose OS specific states by mixin
         
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
        # TODO: implement OS-OCCI extension or can be done via update()
        elif instance['vm_state'] in (vm_states.REBUILDING,
                       task_states.RESIZE_CONFIRMING,
                       task_states.RESIZE_FINISH,
                       task_states.RESIZE_MIGRATED,
                       task_states.RESIZE_MIGRATING,
                       task_states.RESIZE_PREP,
                       task_states.RESIZE_REVERTING):
            entity.attributes['occi.compute.state'] = 'inactive'
            entity.actions = []
        
        return instance

    def delete(self, entity, extras):
        # call the management framework to delete this compute instance...
        LOG.info('Removing representation of virtual machine with id: '
              + entity.identifier)

        context = extras['nova_ctx']
        
        uid = entity.attributes['occi.core.id']
        # TODO: at some stage the uid gets munged with location.
        if uid.find(entity.kind.location) > -1:
            uid = uid.replace(entity.kind.location, '')
        
        try:
            instance = self.compute_api.routing_get(context, uid)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        if FLAGS.reclaim_instance_interval:
            self.compute_api.soft_delete(context, instance)
        else:
            self.compute_api.delete(context, instance)

    def action(self, entity, action, extras):

        # TODO: Review: when retrieve is called the representation of the 
        # resource is rendered. We don't want that!

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
            self.compute_api.start(context, instance)

        elif action == infrastructure.STOP:
            # OCCI -> graceful, acpioff, poweroff
            # OS -> unclear
            LOG.info('Stopping virtual machine with id' + entity.identifier)
            if entity.attributes.has_key('method'):
                LOG.info('OS only allows one type of stop. What is \
                            specified in the request will be ignored.')
            entity.attributes['occi.compute.state'] = 'inactive'
            self.compute_api.stop(context, instance)
        elif action == infrastructure.RESTART:
            LOG.info('Restarting virtual machine with id' + entity.identifier)
            entity.attributes['occi.compute.state'] = 'active'
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
            self.compute_api.suspend(context, instance)
        elif action == extensions.OS_CHG_PWD:
            # TODO: Review - it'll need the password sent as well as the
            #                new password value.
            if not entity.attributes.has_key('method'):
                raise exc.HTTPBadRequest()
            self.compute_api.set_admin_password(context, instance, \
                                                entity.attributes['method'])
        elif action == extensions.OS_REBUILD:
            #TODO: there must be an OsTemplate mixin with the request and
            #      there must be the admin password to the instance
            raise exc.HTTPNotImplemented()
            image_href = 'TODO'
            admin_password = 'TODO'
            self.compute_api.rebuild(context, instance, image_href, \
                                            admin_password, None, None, None)
        elif action == extensions.OS_REVERT_RESIZE:
            LOG.info('Reverting resized virtual machine with id' + \
                                                            entity.identifier)
            self.compute_api.revert_resize(context, instance)
        elif action == extensions.OS_CONFIRM_RESIZE:
            LOG.info('Confirming resize of virtual machine with id' + \
                                                            entity.identifier)
            self.compute_api.confirm_resize(context, instance)

