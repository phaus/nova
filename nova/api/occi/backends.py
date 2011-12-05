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

from webob import exc

from nova import compute
from nova import exception
from nova import flags
from nova import network
from nova.compute import instance_types
from nova.rpc import common as rpc_common

from nova import log as logging
from occi.backend import ActionBackend, KindBackend, MixinBackend
from occi.exceptions import HTTPError
from occi.extensions.infrastructure import START, STOP, SUSPEND, RESTART, UP, \
    DOWN, ONLINE, BACKUP, SNAPSHOT, RESIZE, OFFLINE, NETWORK, NETWORKINTERFACE
from nova.api.occi.extensions import ResourceTemplate, OsTemplate


LOG = logging.getLogger('nova.api.occi.backends')

FLAGS = flags.FLAGS


class MyBackend(KindBackend, ActionBackend):
    '''
    An very simple abstract backend which handles update and replace for
    attributes. Support for links and mixins would need to added.
    '''

    def update(self, old, new, extras):
        # here you can check what information from new_entity you wanna bring
        # into old_entity

        # trigger your hypervisor and push most recent information
        print('Updating a resource with id: ' + old.identifier)
        for item in new.attributes.keys():
            old.attributes[item] = new.attributes[item]

    def replace(self, old, new, extras):
        print('Replacing a resource with id: ' + old.identifier)
        old.attributes = {}
        for item in new.attributes.keys():
            old.attributes[item] = new.attributes[item]
        old.attributes['occi.compute.state'] = 'inactive'


class ComputeBackend(MyBackend):
    '''
    A Backend for compute instances.
    '''

    def __init__(self):
        self.compute_api = compute.API()
        self.network_api = network.API()

    def create(self, entity, extras):
        # e.g. check if all needed attributes are defined...

        # adding some default dummy values:
#        if 'occi.compute.hostname' not in entity.attributes:
#            entity.attributes['occi.compute.hostname'] = 'dummy'
#        if 'occi.compute.memory' not in entity.attributes:
#            entity.attributes['occi.compute.memory'] = '2'
#        # rest is set by SERVICE provider...
#        entity.attributes['occi.compute.architecture'] = 'x86'
#        entity.attributes['occi.compute.cores'] = '2'
#        entity.attributes['occi.compute.speed'] = '1'
#
#        # trigger your management framework to start the compute instance...
#        entity.attributes['occi.compute.state'] = 'inactive'
#        entity.actions = [START]

        print('Creating the virtual machine with id: ' + entity.identifier)

        #optional params
        name = 'an_occi_vm'
        key_name = None # only set if a key-pair is registered
        metadata = {} #server_dict.get('metadata', {})
        access_ip_v4 = '192.168.1.23' #server_dict.get('accessIPv4')
        access_ip_v6 = 'DEAD:BEEF:BABE' #server_dict.get('accessIPv6')
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
        
        #TODO it's unlikely that this uuid is the instance id     
        entity.attributes['occi.core.id'] = instances[0]['hostname']
        entity.attributes['occi.compute.hostname'] = instances[0]['hostname']
        entity.attributes['occi.compute.architecture'] = 'x86'
        entity.attributes['occi.compute.cores'] = instances[0]['vcpus']
        #this is not available in instances
        # could possible be retreived from flavour info 
        # if not where?
        entity.attributes['occi.compute.speed'] = str(2.4) 
        entity.attributes['occi.compute.memory'] = \
                                    str(float(instances[0]['memory_mb']) / 1024)
        entity.attributes['occi.compute.state'] = 'inactive'
        
        #Once created, the VM is attached to a public network with an address
        # allocated by DHCP
        # To create an OS floating IP then dhcp would be switched to static
        
    #TODO best import this from openstack api? it was taken from there
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
        # trigger your management framework to get most up to date information

        # add up to date actions...
        if entity.attributes['occi.compute.state'] == 'inactive':
            entity.actions = [START]
        if entity.attributes['occi.compute.state'] == 'active':
            entity.actions = [STOP, SUSPEND, RESTART]
        if entity.attributes['occi.compute.state'] == 'suspended':
            entity.actions = [START]

    def delete(self, entity, extras):
        # call the management framework to delete this compute instance...
        print('Removing representation of virtual machine with id: '
              + entity.identifier)

        context = extras['nova_ctx']

        try:
            instance = self.compute_api.routing_get(context, entity.identifier)
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

#from quantum.client import cli_lib as cli
#from quantum.client import Client

class NetworkBackend(MyBackend):
    '''
    Backend to handle network resources.
    '''
#    def __init__(self):
#        self.tenant_id = 'admin'
#        FORMAT = 'json'
#        self.client = Client(tenant=self.tenant_id, format=FORMAT)
        
    def create(self, entity, extras):
        # create a VNIC...
        entity.attributes['occi.network.vlan'] = '1'
        entity.attributes['occi.network.label'] = 'dummy interface'
        entity.attributes['occi.network.state'] = 'inactive'
        entity.actions = [UP]
        print('Creating a VNIC')
        
        #here comes the pain/fun!
#        params = {'network': {'name': 'a name'}}
#        try:
#            res = self.client.create_network(params)
#        except Exception as ex:
#            raise ex
#        
#        LOG.debug("Operation 'create_network' executed.")
#        entity.attributes['occi.core.id'] = res["network"]["id"]
        
    def retrieve(self, entity, extras):
        # update a VNIC
        if entity.attributes['occi.network.state'] == 'active':
            entity.actions = [DOWN]
        elif entity.attributes['occi.network.state'] == 'inactive':
            entity.actions = [UP]

    def delete(self, entity, extras):
        # and deactivate it
        print('Removing representation of a VNIC with id:' + entity.identifier)

    def action(self, entity, action, extras):
        if action not in entity.actions:
            raise AttributeError("This action is currently no applicable.")
        elif action.kind == UP:
            entity.attributes['occi.network.state'] = 'active'
            # read attributes from action and do something with it :-)
            print('Starting VNIC with id: ' + entity.identifier)
        elif action.kind == DOWN:
            entity.attributes['occi.network.state'] = 'inactive'
            # read attributes from action and do something with it :-)
            print('Stopping VNIC with id: ' + entity.identifier)

from nova import volume

class StorageBackend(MyBackend):
    '''
    Backend to handle storage resources.
    '''
    def __init__(self):
        self.volume_api = volume.API()
        
    def create(self, entity, extras):
        # create a storage container here!

        entity.attributes['occi.storage.size'] = '1'
        entity.attributes['occi.storage.state'] = 'offline'
        entity.actions = [ONLINE]
        print('Creating a storage device')
        
        
        """Creates a new volume."""
        context = extras['nova_ctx']

#        vol = body['volume']
#        size = vol['size']
        size = entity['occi.storage.size']
        LOG.audit(_("Create volume of %s GB"), size, context=context)

#        vol_type = vol.get('volume_type', None)
#        if vol_type:
#            try:
#                vol_type = volume_types.get_volume_type_by_name(context,
#                                                                vol_type)
#            except exception.NotFound:
#                raise exc.HTTPNotFound()
#
#        metadata = vol.get('metadata', None)
        
        vol_type = None
        metadata = None
        disp_name = 'a volume' #vol.get('display_name')
        disp_descr = 'a volume' #vol.get('display_description')
        new_volume = self.volume_api.create(context, size, None,
                                            disp_name,
                                            disp_descr,
                                            volume_type=vol_type,
                                            metadata=metadata)

        # Work around problem that instance is lazy-loaded...
        new_volume = self.volume_api.get(context, new_volume['id'])

#        retval = _translate_volume_detail_view(context, new_volume)
#
#        return {'volume': retval}
        

    def retrieve(self, entity, extras):
        # check the state and return it!

        if entity.attributes['occi.storage.state'] == 'offline':
            entity.actions = [ONLINE]
        if entity.attributes['occi.storage.state'] == 'online':
            entity.actions = [BACKUP, SNAPSHOT, RESIZE]

    def delete(self, entity, extras):
        # call the management framework to delete this storage instance...
        print('Removing storage device with id: ' + entity.identifier)

    def action(self, entity, action, extras):
        if action not in entity.actions:
            raise AttributeError("This action is currently no applicable.")
        elif action == ONLINE:
            entity.attributes['occi.storage.state'] = 'online'
            # read attributes from action and do something with it :-)
            print('Bringing up storage with id: ' + entity.identifier)
        elif action == OFFLINE:
            entity.attributes['occi.storage.state'] = 'offline'
            # read attributes from action and do something with it :-)
            print('Bringing down storage with id: ' + entity.identifier)
        elif action == BACKUP:
            print('Backing up...storage resource with id: '
                  + entity.identifier)
        elif action == SNAPSHOT:
            print('Snapshoting...storage resource with id: '
                  + entity.identifier)
        elif action == RESIZE:
            print('Resizing...storage resource with id: ' + entity.identifier)


class IpNetworkBackend(MixinBackend):
    '''
    A mixin backend for the IPnetworking.
    '''

    def create(self, entity, extras):
        if not entity.kind == NETWORK:
            raise AttributeError('This mixin cannot be applied to this kind.')
        entity.attributes['occi.network.allocation'] = 'dynamic'
        entity.attributes['occi.network.gateway'] = '10.0.0.1'
        entity.attributes['occi.network.address'] = '10.0.0.1/24'

    def delete(self, entity, extras):
        entity.attributes.pop('occi.network.allocation')
        entity.attributes.pop('occi.network.gateway')
        entity.attributes.pop('occi.network.address')


class IpNetworkInterfaceBackend(MixinBackend):
    '''
    A mixin backend for the IPnetowkringinterface.
    '''

    def create(self, entity, extras):
        if not entity.kind == NETWORKINTERFACE:
            raise AttributeError('This mixin cannot be applied to this kind.')
        entity.attributes['occi.networkinterface.address'] = '10.0.0.65'
        entity.attributes['occi.networkinterface.gateway'] = '10.0.0.1'
        entity.attributes['occi.networkinterface.allocation'] = 'dynamic'

    def delete(self, entity, extras):
        entity.attributes.pop('occi.networkinterface.address')
        entity.attributes.pop('occi.networkinterface.gateway')
        entity.attributes.pop('occi.networkinterface.allocation')


class StorageLinkBackend(KindBackend):
    '''
    A backend for the storage links.
    '''

    def create(self, entity, extras):
        entity.attributes['occi.storagelink.deviceid'] = 'sda1'
        entity.attributes['occi.storagelink.mountpoint'] = '/'
        entity.attributes['occi.storagelink.state'] = 'mounted'

    def delete(self, entity, extras):
        entity.attributes.pop('occi.storagelink.deviceid')
        entity.attributes.pop('occi.storagelink.mountpoint')
        entity.attributes.pop('occi.storagelink.state')


class NetworkInterfaceBackend(KindBackend):
    '''
    A backend for the network links.
    '''

    def create(self, link, extras):
        link.attributes['occi.networkinterface.state'] = 'up'
        link.attributes['occi.networkinterface.mac'] = 'aa:bb:cc:dd:ee:ff'
        link.attributes['occi.networkinterface.interface'] = 'eth0'

    def delete(self, link, extras):
        link.attributes.pop('occi.networkinterface.state')
        link.attributes.pop('occi.networkinterface.mac')
        link.attributes.pop('occi.networkinterface.interface')

class ResourceMixinBackend(MixinBackend):
    pass

class OsMixinBackend(MixinBackend):
    pass
