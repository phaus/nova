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


# TODO: implement create
# TODO: implement delete
# TODO: implement retreive

from nova import log as logging
from nova import volume

from occi.backend import KindBackend

from webob import exc

#Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.storage.link')


class StorageLinkBackend(KindBackend):
    '''
    A backend for the storage links.
    '''
    
    def __init__(self):
        self.volume_api = volume.API()
        
    def create(self, entity, extras):
        context = extras['nova_ctx']
        LOG.info('Linking entity to storage via StorageLink.')
        
        import ipdb
        ipdb.set_trace()
        
        vol_to_attach = self.volume_api.get(context, entity['occi.core.id'])
        instance_id = entity['occi.core.id']
        mountpoint = entity.attributes['occi.storagelink.mountpoint']
        
        self.volume_api.attach(context, vol_to_attach, instance_id, mountpoint)
        
        vol_to_attach = self.volume_api.get(context, entity['occi.core.id'])
        
        entity.attributes['occi.storagelink.deviceid'] = 'sda1'
        entity.attributes['occi.storagelink.mountpoint'] = '/'
        entity.attributes['occi.storagelink.state'] = 'mounted'
    
    def retrieve(self, entity, extras):
        raise exc.HTTPNotImplemented
    
    def delete(self, entity, extras):
        LOG.info('Unlinking entity from storage via StorageLink.')
        
        import ipdb
        ipdb.set_trace()
        
        context = extras['nova_ctx']
        vol_to_detach = self.volume_api.get(context, entity['occi.core.id'])
        self.volume_api.detach(context, vol_to_detach)
        
        entity.attributes.pop('occi.storagelink.deviceid')
        entity.attributes.pop('occi.storagelink.mountpoint')
        entity.attributes.pop('occi.storagelink.state')

    def action(self, entity, action, extras):
        raise exc.HTTPNotImplemented
