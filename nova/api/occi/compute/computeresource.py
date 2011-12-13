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


# TODO: implement update
# TODO: implement action

from nova import flags
from nova import compute, exception, log as logging
from nova.api.occi.backends import MyBackend
from nova.api.occi.extensions import ResourceTemplate, OsTemplate
from nova.compute import instance_types
from nova.rpc import common as rpc_common

from occi.exceptions import HTTPError
from occi.extensions.infrastructure import START, STOP, SUSPEND, RESTART
from webob import exc


FLAGS = flags.FLAGS

#Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.compute')

class ComputeBackend(MyBackend):
    '''
    A Backend for compute instances.
    '''

    def __init__(self):
        self.compute_api = compute.API()
        #self.network_api = network.API()

    def create(self, entity, extras):

        LOG.info('Creating the virtual machine with id: ' + entity.identifier)

        #optional params
        name = 'an_occi_vm' #TODO: should be taken from the OCCI request
        key_name = None # only set if a key-pair is registered
        metadata = {} #server_dict.get('metadata', {})
        access_ip_v4 = None #'192.168.1.23' #server_dict.get('accessIPv4')
        access_ip_v6 = None #'DEAD:BEEF:BABE' #server_dict.get('accessIPv6')
        injected_files = [] # self._get_injected_files(personality)
        password = 'password' #self._get_server_admin_password(server_dict)
        zone_blob = 'blob' #server_dict.get('blob')
        reservation_id = None #server_dict.get('reservation_id') <- used by admins!
        min_count = max_count = 1
        requested_networks = None #self._get_requested_networks(requested_networks)
        sg_names = []
        sg_names.append('default')
        sg_names = list(set(sg_names))
        user_data = None #server_dict.get('user_data')
        availability_zone = None #server_dict.get('availability_zone')
        config_drive = None #server_dict.get('config_drive')
        block_device_mapping = None #self._get_block_device_mapping(server_dict)

        #required params
        #context is mainly authorisation information
        #its assembled in AuthMiddleware - we can pipeline this with the OCCI service
        context = extras['nova_ctx']
        
        #essential, required to get a vm image e.g. 
        #            image_href = 'http://10.211.55.20:9292/v1/images/1'
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
                msg = 'There is more that one resource template in the request.'
                LOG.error(msg)
                raise AttributeError(msg=unicode(msg))
            if oc > 1:
                msg = 'There is more that one resource template in the request.'
                LOG.error(msg)
                raise AttributeError()            
            
            flavor_name = r.term
            os_tpl_url = o.os_url()
            
        try:
            if flavor_name:
                inst_type = instance_types.get_instance_type_by_name(flavor_name)
            else:
                inst_type = instance_types.get_default_instance_type()
                LOG.warn('No resource template was found in the request. \
                                Using the default: ' + inst_type['name'])
            
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
        #TODO: can't we tell this from the image used?
        entity.attributes['occi.compute.architecture'] = 'x86'
        entity.attributes['occi.compute.cores'] = str(instances[0]['vcpus'])
        #this is not available in instances
        # TODO: could possible be retreived from flavour info 
        # if not where?
        entity.attributes['occi.compute.speed'] = str(2.4) 
        entity.attributes['occi.compute.memory'] = \
                                    str(float(instances[0]['memory_mb']) / 1024)
        entity.attributes['occi.compute.state'] = 'inactive'
        
        #TODO: Once created, the VM is attached to a public network with an addresses
        # allocated by DHCP
        # Then create link to this network (IP) and set the ip to that of the
        # allocated ip
        # To create an OS floating IP then dhcp would be switched to static
        
    #TODO: best import this from openstack api? it was taken from there
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
        context = extras['nova_ctx']
        try:
            instance = self.compute_api.routing_get(context, entity.attributes['occi.core.id'])
        except exception.NotFound:
            raise exc.HTTPNotFound()
        
        #TODO: OpenStack supports differenet states - need to do a mapping
        #   see nova/compute/vm_states.py
        entity.attributes['occi.compute.state'] = instance['vm_state']

        # add up to date actions...
        if entity.attributes['occi.compute.state'] in ('inactive', 'building', 'rebuilding'):
            entity.attributes['occi.compute.state'] = 'inactive'
            entity.actions = [START]
        elif entity.attributes['occi.compute.state'] == 'active':
            entity.actions = [STOP, SUSPEND, RESTART]
        elif entity.attributes['occi.compute.state'] == 'suspended':
            entity.actions = [START]

    def delete(self, entity, extras):
        # call the management framework to delete this compute instance...
        print('Removing representation of virtual machine with id: ' 
              + entity.identifier)

        context = extras['nova_ctx']

        try:
            instance = self.compute_api.routing_get(context,
                                            entity.attributes['occi.core.id'])
        except exception.NotFound:
            raise exc.HTTPNotFound()

        if FLAGS.reclaim_instance_interval:
            self.compute_api.soft_delete(context, instance)
        else:
            self.compute_api.delete(context, instance)

    def action(self, entity, action, extras):
        if action not in entity.actions:
            raise AttributeError("This action is currently no applicable.")
        elif action == START:
            entity.attributes['occi.compute.state'] = 'active'
            # read attributes from action and do something with it :-)
            print('Starting virtual machine with id' + entity.identifier)
        elif action == STOP:
            entity.attributes['occi.compute.state'] = 'inactive'
            # read attributes from action and do something with it :-)
            print('Stopping virtual machine with id' + entity.identifier)
        elif action == RESTART:
            entity.attributes['occi.compute.state'] = 'active'
            # read attributes from action and do something with it :-)
            print('Restarting virtual machine with id' + entity.identifier)
        elif action == SUSPEND:
            entity.attributes['occi.compute.state'] = 'suspended'
            # read attributes from action and do something with it :-)
            print('Suspending virtual machine with id' + entity.identifier)
