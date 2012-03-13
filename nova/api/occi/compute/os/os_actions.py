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

from nova import logging
from nova import compute
from nova import exception
from nova import policy
from nova.api.occi import extensions

from occi import backend

from webob import exc


# Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.compute.os')


class OsComputeActionBackend(backend.ActionBackend):

    def __init__(self):
        super(OsComputeActionBackend, self).__init__()
        policy.reset()
        policy.init()
        self.compute_api = compute.API()

    def action(self, entity, action, extras):

        context = extras['nova_ctx']

        uid = entity.attributes['occi.core.id']

        try:
            instance = self.compute_api.get(context, uid)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        if action == extensions.OS_CHG_PWD:
            self._os_chg_passwd_vm(entity, instance, context)
        elif action == extensions.OS_REVERT_RESIZE:
            self._os_revert_resize_vm(entity, instance, context)
        elif action == extensions.OS_CONFIRM_RESIZE:
            self._os_confirm_resize_vm(entity, instance, context)
        elif action == extensions.OS_CREATE_IMAGE:
            self._os_create_image(entity, instance, context)

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
        if 'occi.compute.image.name' not in entity.attributes:
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
