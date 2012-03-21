# vim: tabstop=4 shiftwidth=4 softtabstop=4

#
#    Copyright (c) 2012, Intel Performance Learning Solutions Ltd.
#
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

from occi import backend
from occi import core_model

from webob import exc


# Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.compute.os')


######################## OpenStack Specific Addtitions #######################
######### 1. define the method to retreive all extension information #########
def get_extensions():

    return  [
             {
              'categories':[OS_CHG_PWD, OS_REVERT_RESIZE,
                            OS_CONFIRM_RESIZE, OS_CREATE_IMAGE,
                            OS_ACCESS_IP_EXT],
              'handler': OsComputeActionBackend(),
             },
             {
              'categories':[OS_KEY_PAIR_EXT, OS_ADMIN_PWD_EXT],
              'handler': backend.MixinBackend(),
             }
            ]


##### 2. define the extension categories - OpenStack Specific Additions ######

#OS action extensions
# OS change adminstrative password action
OS_CHG_PWD = core_model.Action(
                'http://schemas.openstack.org/instance/action#',
                 'chg_pwd', 'Removes all data on the server and replaces' + \
                                    'it with the specified image (via Mixin).',
                 {'org.openstack.credentials.admin_pwd': ''})

# OS revert a resized VM action
OS_REVERT_RESIZE = core_model.Action(
                'http://schemas.openstack.org/instance/action#',
                 'revert_resize', 'Revert the resize and roll back to \
                                                     the original server')

# OS confirm a resized VM action
OS_CONFIRM_RESIZE = core_model.Action(
                'http://schemas.openstack.org/instance/action#',
                 'confirm_resize', 'Use this to confirm the resize action')

# OS create image from VM action
OS_CREATE_IMAGE = core_model.Action(
                'http://schemas.openstack.org/instance/action#',
                 'create_image', 'Creates a new image for the given server.',
                 {'image_name': ''})

# OS Key pair extension
OS_KEY_PAIR_ATTRIBUTES = {'org.openstack.credentials.publickey.name': '',
                       'org.openstack.credentials.publickey.data': '', }
OS_KEY_PAIR_EXT = core_model.Mixin(\
    'http://schemas.openstack.org/instance/credentials#',
    'public_key', attributes=OS_KEY_PAIR_ATTRIBUTES)


# OS VM Administrative password extension
OS_ADMIN_PWD_ATTRIBUTES = {'org.openstack.credentials.admin_pwd': '', }
OS_ADMIN_PWD_EXT = core_model.Mixin(\
    'http://schemas.openstack.org/instance/credentials#',
    'admin_pwd', attributes=OS_ADMIN_PWD_ATTRIBUTES)

# OS access IP extension
OS_ACCESS_IP_ATTRIBUTES = {'org.openstack.network.access.ip': '',
                           'org.openstack.network.access.version': ''}
OS_ACCESS_IP_EXT = core_model.Mixin(\
    'http://schemas.openstack.org/instance/network#',
    'access_ip', attributes=OS_ACCESS_IP_ATTRIBUTES)


##################### 3. define the extension handler(s) #####################
class OsComputeActionBackend(backend.ActionBackend):

    def __init__(self):
        super(OsComputeActionBackend, self).__init__()
#        policy.reset()
#        policy.init()
        self.compute_api = compute.API()

    def action(self, entity, action, extras):
        '''
        This is called by pyssf when an action request is issued.
        '''
        context = extras['nova_ctx']

        uid = entity.attributes['occi.core.id']

        try:
            instance = self.compute_api.get(context, uid)
        except exception.NotFound:
            raise exc.HTTPNotFound()

        if action == OS_CHG_PWD:
            self._os_chg_passwd_vm(entity, instance, context)
        elif action == OS_REVERT_RESIZE:
            self._os_revert_resize_vm(entity, instance, context)
        elif action == OS_CONFIRM_RESIZE:
            self._os_confirm_resize_vm(entity, instance, context)
        elif action == OS_CREATE_IMAGE:
            self._os_create_image(entity, instance, context)

    def _os_chg_passwd_vm(self, entity, instance, context):
        '''
        Implements changing of a vm's admin password
        '''
        # Use the password extension?
        LOG.info('Changing admin password of virtual machine with id' \
                                                        + entity.identifier)
        if 'org.openstack.credentials.admin_pwd' not in entity.attributes:
            exc.HTTPBadRequest()

        new_password = entity.attributes['org.openstack.credentials.admin_pwd']
        self.compute_api.set_admin_password(context, instance, new_password)

        # No need to update attributes - state remains the same.

    def _os_revert_resize_vm(self, entity, instance, context):
        '''
        Implements reverting of a resized vm
        '''
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
        '''
        Implements the confirmation of a resized vm.
        '''
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
        '''
        implements the creation of an image of the specified vm
        '''
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
