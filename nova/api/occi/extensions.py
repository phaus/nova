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

from nova import flags, log
from occi import backend, core_model

#TODO: This all has to be abstracted and made easy to use and provide other
#      extensions. E.g. scan all classes in extensions.py and load dynamically

#Hi I'm a logger, use me! :-)
LOG = log.getLogger('nova.api.occi.extensions')

FLAGS = flags.FLAGS

#OS action extensions
OS_CHG_PWD = core_model.Action(
                'http://schemas.openstack.org/instance/action#',
                 'chg_pwd', 'Removes all data on the server and replaces' + \
                                    'it with the specified image (via Mixin).',
                 {'org.openstack.credentials.admin_pwd': ''})

OS_REVERT_RESIZE = core_model.Action(
                'http://schemas.openstack.org/instance/action#',
                 'revert_resize', 'Revert the resize and roll back to \
                                                     the original server')

OS_CONFIRM_RESIZE = core_model.Action(
                'http://schemas.openstack.org/instance/action#',
                 'confirm_resize', 'Use this to confirm the resize action')

OS_CREATE_IMAGE = core_model.Action(
                'http://schemas.openstack.org/instance/action#',
                 'create_image', 'Creates a new image for the given server.',
                 {'image_name': ''})

# SSH Console Kind Extension
SSH_CONSOLE_ATTRIBUTES = {'org.openstack.compute.console.ssh': '', }
SSH_CONSOLE = core_model.Mixin(\
    'http://schemas.openstack.org/occi/infrastructure/compute#',
    'ssh_console', attributes=SSH_CONSOLE_ATTRIBUTES)

# VNC Console Kind Extension
VNC_CONSOLE_ATTRIBUTES = {'org.openstack.compute.console.vnc': '', }
VNC_CONSOLE = core_model.Mixin(\
    'http://schemas.openstack.org/occi/infrastructure/compute#',
    'vnc_console', attributes=VNC_CONSOLE_ATTRIBUTES)

# Trusted Compute Pool technology mixin definition
TCP_ATTRIBUTES = {'eu.fi-ware.compute.tcp': '', }
TCP = core_model.Mixin(\
    'http://schemas.fi-ware.eu/occi/infrastructure/compute#',
    'tcp', attributes=TCP_ATTRIBUTES)

# Key pair extension
KEY_PAIR_ATTRIBUTES = {'org.openstack.credentials.publickey.name': '',
                       'org.openstack.credentials.publickey.data': '', }
KEY_PAIR_EXT = core_model.Mixin(\
    'http://schemas.openstack.org/instance/credentials#',
    'public_key', attributes=KEY_PAIR_ATTRIBUTES)

# VM Administrative password extension 
ADMIN_PWD_ATTRIBUTES = {'org.openstack.credentials.admin_pwd': '', }
ADMIN_PWD_EXT = core_model.Mixin(\
    'http://schemas.openstack.org/instance/credentials#',
    'admin_pwd', attributes=ADMIN_PWD_ATTRIBUTES)

# TODO: use empty backend - kind/mixin
class ConsoleBackend(backend.MixinBackend):
    '''
    Console mixin backend handler
    '''
    pass

class TCPBackend(backend.MixinBackend):
    '''
    Trusted Compute Pool technology mixin backend handler
    '''
    pass

class KeyPairBackend(backend.MixinBackend):
    '''
    Public SSH Keypair mixin backend handler
    '''
    pass

class AdminPasswordBackend(backend.MixinBackend):
    '''
    Administrative password mixin backend handler
    '''
    pass


class OsTemplate(core_model.Mixin):
    '''
    Represents the OS Template mechanism as per OCCI specification.
    An OS template is equivocal to an image in OpenStack
    '''
    def __init__(self, scheme, term, os_id, related=None, actions=None,
                 title='', attributes=None, location=None):
        super(OsTemplate, self).__init__(scheme, term, related, actions,
                                         title, attributes, location)
        self.os_id = os_id


class ResourceTemplate(core_model.Mixin):
    '''
    Represents the Resource Template mechanism as per OCCI specification.
    An Resource template is equivocal to a flavor in OpenStack.
    '''

    pass
