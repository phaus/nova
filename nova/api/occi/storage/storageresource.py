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

from nova import exception
from nova import log as logging 
from nova import volume
from nova.api.occi.backends import MyBackend
from occi.extensions.infrastructure import ONLINE, BACKUP, SNAPSHOT, RESIZE, \
    OFFLINE
from webob import exc


# FIXME: Storage allows to go offline and online. StorageLink allows to go
#        active or inactive. How should storage 'go offline' or 'come online'?

# L8R: there is no error state in the OCCI model!


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
        size = float(resource.attributes['occi.storage.size'])
        
        # L8R: Right, this sucks. Suggest a patch to OpenStack.
        # OpenStack deals with size in terms of integer.
        # Need to convert float to integer for now and only if the float
        # can be losslessly converted to integer
        # e.g. See nova/quota.py:allowed_volumes(...)
        if not size.is_integer:
            LOG.error('Volume sizes cannot be specified as fractional floats. \
                                            OpenStack does not support this.')
            raise exc.HTTPBadRequest()
        
        size = str(int(size))
        
        LOG.audit(_("Create volume of %s GB"), size,
                                                context=extras['nova_ctx'])
        
        disp_name = ''
        try:
            disp_name = resource.attributes['occi.core.title']
        except KeyError:
            #Generate more suitable name as it's used for hostname
            #where no hostname is supplied.
            disp_name = resource.attributes['occi.core.title'] = \
                            str(random.randrange(0, 99999999)) + \
                                                        '-storage.occi-wg.org'
        if 'occi.core.summary' in resource.attributes:
            disp_descr = resource.attributes['occi.core.summary']
        else:
            disp_descr = disp_name
            
        snapshot = None
        #volume_type could be specified by mixin
        volume_type = None
        metadata = None
        availability_zone = None
        new_volume = self.volume_api.create(extras['nova_ctx'],
                                            size,
                                            disp_name,
                                            disp_descr,
                                            snapshot=snapshot,
                                            volume_type=volume_type,
                                            metadata=metadata,
                                            availability_zone=availability_zone)
        
        # Work around problem that instance is lazy-loaded...
        new_volume = self.volume_api.get(extras['nova_ctx'], new_volume['id'])
        
        if new_volume['status'] == 'error':
            msg = 'There was an error creating the volume'
            LOG.error(msg)
            raise exc.HTTPServerError(msg)
        
        resource.attributes['occi.core.id'] = str(new_volume['id'])
        
        if new_volume['status'] == 'available':
            resource.attributes['occi.storage.state'] = 'online'
        
        resource.actions = [OFFLINE, BACKUP, SNAPSHOT, RESIZE]


    def retrieve(self, entity, extras):
        v_id = int(entity.attributes['occi.core.id'])
        
        # handle the case where the volume id is not an integer and is a uuid
        if v_id.is_integer():
            volume_id = v_id
        else:
            volume_id = entity.attributes['occi.core.id']
        
        try:
            vol = self.volume_api.get(extras['nova_ctx'], volume_id)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        entity.attributes['occi.storage.size'] = float(vol['size'])
        
        # OS volume states:
        #       available, creating, deleting, in-use, error, error_deleting
        if vol['status'] == 'available' or vol['status'] == 'in-use':
            entity.attributes['occi.storage.state'] = 'online'
            entity.actions = [OFFLINE, BACKUP, SNAPSHOT, RESIZE]
            

    def delete(self, entity, extras):
        # call the management framework to delete this storage instance...
        print('Removing storage device with id: ' + entity.identifier)
        
        volume_id = int(entity.attributes['occi.core.id'])
        
        try:
            vol = self.volume_api.get(extras['nova_ctx'], volume_id)
            self.volume_api.delete(extras['nova_ctx'], vol)
        except exception.NotFound:
            raise exc.HTTPNotFound()
        

    def action(self, entity, action, extras):
        if action not in entity.actions:
            raise AttributeError("This action is currently no applicable.")
        
        elif action == ONLINE:
            # ONLINE, ready for service, default state of a created volume.
            # could this cover the attach functionality in storage link?
            # The following is not an approach to use:
            # self.volume_api.initialize_connection(context, volume, connector)
            
            # By default storage is ONLINE and can not be brought OFFLINE
            
            LOG.warn('Online storage requested resource with id: ' + \
                                                            entity.identifier)
            raise exc.HTTPNotImplemented()
            
        elif action == OFFLINE:
            # OFFLINE, disconnected? disconnection supported in API otherwise
            # not. The following is not an approach to use:
            # self.volume_api.terminate_connection(context, volume, connector)
            
            # By default storage cannot be brought OFFLINE
            LOG.warn('Offline storage requested resource with id: ' + \
                                                            entity.identifier)
            raise exc.HTTPNotImplemented()
            
        elif action == BACKUP:
            # FIXME: Same as a snapshot?
            # BACKUP: create a complete copy of the volume.
            # self.volume_api.create_snapshot(\
            #                               context, volume, name, description)
            print('Backing up...storage resource with id: '
                  + entity.identifier)
            self._snapshot_storage(entity, extras)
            
        elif action == SNAPSHOT:
            # SNAPSHOT: create a time-stamped copy of the volume? Supported in 
            # OS volume API
            self._snapshot_storage(entity, extras)
            

        elif action == RESIZE:
            # L8R: not supported by API. Patch to OS?
            # RESIZE: increase, decrease size of volume. Not supported directly
            #         by the API
            
            LOG.warn('Resize storage requested resource with id: ' + \
                                                            entity.identifier)
            raise exc.HTTPNotImplemented()
    
    # L8R: OCCI has no way to manage snapshots or backups once created :-(
    def _snapshot_storage(self, entity, extras, backup=False):
        LOG.info('Snapshoting...storage resource with id: ' + \
                                                            entity.identifier)
        volume_id = int(entity.attributes['occi.core.id'])
        volume = self.volume_api.get(extras['nova_ctx'], volume_id)
        if backup:
            name = 'backup name'
            description = 'backup description'
        else:
            name = 'snapshot name'
            description = 'snapshot description'
        self.volume_api.create_snapshot(extras['nova_ctx'],
                                        volume, name, description)        


    def update(self, old, new, extras):
        # FIXME: this is the same code taken from computeresource.
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
                raise exc.HTTPBadRequest()
        else:
            raise exc.HTTPBadRequest()
        
    
