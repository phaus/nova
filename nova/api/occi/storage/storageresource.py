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


# TODO: implement actions
# TODO: implement updates

import random

from nova import exception
from nova import log as logging 
from nova import volume
from nova.api.occi.backends import MyBackend
from occi.extensions.infrastructure import ONLINE, BACKUP, SNAPSHOT, RESIZE, \
    OFFLINE
from webob import exc



#Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.storage')

#NOTE: for this to operate the nova-vol service must be running
class StorageBackend(MyBackend):
    '''
    Backend to handle storage resources.
    '''
    def __init__(self):
        self.volume_api = volume.API()
    
        
    def create(self, resource, extras):
        """Creates a new volume."""
        context = extras['nova_ctx']
        size = float(resource.attributes['occi.storage.size'])
        
        # Right, this sucks. Suggest a patch to OpenStack.
        # OpenStack deals with size in terms of integer.
        # Need to convert float to integer for now and only if the float
        # can be losslessly converted to integer
        # e.g. See nova/quota.py:108
        if not size.is_integer:
            LOG.error('Volume sizes cannot be specified as fractional floats. \
                                            OpenStack does not support this.')
            raise exc.HTTPBadRequest
        
        size = str(int(size))
        
        LOG.audit(_("Create volume of %s GB"), size, context=context)
        
#        vol = body['volume']
#        size = vol['size']
#        vol_type = vol.get('volume_type', None)
#        if vol_type:
#            try:
#                vol_type = volume_types.get_volume_type_by_name(context,
#                                                                vol_type)
#            except exception.NotFound:
#                raise exc.HTTPNotFound()
#        metadata = vol.get('metadata', None)
        #volume type can be specified by mixin
        #a metadata mixin???
        name = ''
        try:
            name = resource.attributes['occi.core.title']
        except KeyError:
            #TODO: generate more suitable name as it's used for hostname
            #      where no hostname is supplied.
            name = resource.attributes['occi.core.title'] = \
                            str(random.randrange(0, 99999999)) + \
                                                        '-storage.occi-wg.org'
        disp_name = disp_descr = name
        new_volume = self.volume_api.create(context,
                                            size,
                                            disp_name,
                                            disp_descr,
                                            snapshot=None,
                                            volume_type=None,
                                            metadata=None,
                                            availability_zone=None)

        # Work around problem that instance is lazy-loaded...
        new_volume = self.volume_api.get(context, new_volume['id'])
        
        if new_volume['status'] == 'error':
            msg = 'There was an error creating the volume'
            LOG.error(msg)
            raise exc.HTTPServerError(msg)
        
        resource.attributes['occi.core.id'] = str(new_volume['id'])
        resource.attributes['occi.storage.state'] = 'online'
        resource.actions = [OFFLINE]


    def retrieve(self, entity, extras):
        context = extras['nova_ctx']
        volume_id = int(entity.attributes['occi.core.id'])
        
        try:
            vol = self.volume_api.get(context, volume_id)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        #TODO: review states        
        if vol['status'] == 'available':
            entity.attributes['occi.storage.state'] = 'online'
            entity.actions = [BACKUP, SNAPSHOT, RESIZE]
            
        if entity.attributes['occi.storage.state'] == 'offline':
            entity.actions = [ONLINE]
            

    def delete(self, entity, extras):
        # call the management framework to delete this storage instance...
        print('Removing storage device with id: ' + entity.identifier)
        
        context = extras['nova_ctx']
        volume_id = int(entity.attributes['occi.core.id'])
        
        try:
            vol = self.volume_api.get(context, volume_id)
            self.volume_api.delete(context, vol)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        

    def action(self, entity, action, extras):
        
        #Semantics:
        # ONLINE, ready for service, default state of a created volume.
        # supported in volume API. Maybe use initialize_connection?
        # OFFLINE, disconnected? disconnection supported in API otherwise
        # not. Maybe use terminate_connection?
        # BACKUP: create a complete copy of the volume.
        # SNAPSHOT: create a time-stamped copy of the volume. Supported in 
        # OS volume API
        # RESIZE: increase, decrease size of volume.
        
        # NOTE: OCCI has no way to manage snapshots or backups :-(
        
        #TODO: Implement mappings to OpenStack
        raise exc.HTTPNotImplemented
        
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

    def update(self, old, new, extras):
        raise exc.HTTPNotImplemented
