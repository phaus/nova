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

from nova import log as logging
from nova import volume
from nova import compute

from occi import backend
from occi.extensions import infrastructure

from webob import exc


#Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.storage.link')


class StorageLinkBackend(backend.KindBackend):
    '''
    A backend for the storage links.
    '''

    def __init__(self):
        super(StorageLinkBackend, self).__init__()
        self.volume_api = volume.API()
        self.compute_api = compute.API()

    def create(self, link, extras):
        LOG.info('Linking compute to storage via StorageLink.')

        #FIXME: temporary. For some reason the admin is not seen as having
        #       admin permissions!
        extras['nova_ctx'].is_admin = True

        inst_to_attach = self._get_inst_to_attach(extras['nova_ctx'], link)
        vol_to_attach = self._get_vol_to_attach(extras['nova_ctx'], link)

        #Uh?! volume and compute APIs have an attach method
        self.compute_api.attach_volume(
                                extras['nova_ctx'],
                                inst_to_attach, \
                                vol_to_attach['id'], \
                                link.attributes['occi.storagelink.deviceid'])

#        self.volume_api.attach(
#                               extras['nova_ctx'],
#                               vol_to_attach, \
#                               inst_to_attach['id'], \
#                               link.attributes['occi.storagelink.deviceid'])
#        def attach_volume(, context, instance, volume_id, device):

        link.attributes['occi.core.id'] = str(uuid.uuid4())
        link.attributes['occi.storagelink.deviceid'] = \
                                link.attributes['occi.storagelink.deviceid']
        link.attributes['occi.storagelink.mountpoint'] = ''
        link.attributes['occi.storagelink.state'] = 'active'

    def _get_inst_to_attach(self, context, link):
        # it's instance_id not UUID
        if link.target.kind == infrastructure.COMPUTE:
            instance = self.compute_api.get(context, \
                                        link.target.attributes['occi.core.id'])
        elif link.source.kind == infrastructure.COMPUTE:
            instance = self.compute_api.get(context, \
                                        link.source.attributes['occi.core.id'])
        else:
            raise exc.HTTPBadRequest()
        return instance

    def _get_vol_to_attach(self, context, link):
        if link.target.kind == infrastructure.STORAGE:
            vol_to_attach = self.volume_api.get(context, \
                                        link.target.attributes['occi.core.id'])
        elif link.source.kind == infrastructure.STORAGE:
            vol_to_attach = self.volume_api.get(context, \
                                        link.source.attributes['occi.core.id'])
        else:
            raise exc.HTTPBadRequest()

        return vol_to_attach

    def delete(self, link, extras):
        LOG.info('Unlinking entity from storage via StorageLink.')

        #FIXME: temporary. For some reason the admin is not seen as having
        #       admin permissions!
        extras['nova_ctx'].is_admin = True

        try:
            vol_to_detach = self._get_vol_to_attach(extras['nova_ctx'], link)
            self.compute_api.detach_volume(extras['nova_ctx'],
                                                        vol_to_detach['id'])
#            self.volume_api.detach(extras['nova_ctx'], vol_to_detach)
        except Exception, e:
            LOG.error('Error in detaching storage volume. ' + str(e))
            raise e

        link.attributes.pop('occi.storagelink.deviceid')
        link.attributes.pop('occi.storagelink.mountpoint')
        link.attributes.pop('occi.storagelink.state')
