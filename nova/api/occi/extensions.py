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
from nova import log

from occi import backend
from occi import core_model
from occi import registry
from occi.extensions import infrastructure

LOG = log.getLogger('nova.api.occi.extensions')

FLAGS = flags.FLAGS

# Trusted Compute Pool technology mixin definition
TCP_ATTRIBUTES = {'eu.fi-ware.compute.tcp': ''}
TCP = core_model.Mixin(\
    'http://schemas.fi-ware.eu/occi/infrastructure/compute#',
    'tcp', attributes=TCP_ATTRIBUTES)


class TCPBackend(backend.MixinBackend):
    '''
    Trusted Compute Pool technology mixin backend handler
    '''
    def create(self, entity):
        if not entity.kind == infrastructure.COMPUTE:
            raise AttributeError('This mixin cannot be applied to this kind.')
        entity.attributes['eu.fi-ware.compute.tcp'] = 'true'

    def delete(self, entity):
        entity.attributes.pop('eu.fi-ware.compute.tcp')


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

    def os_url(self):
        glance_hosts = FLAGS.get('glance_api_servers', ['localhost:9292'])
        #TODO handle when there are more than one glance hosts
        if len(glance_hosts) > 1:
            LOG.warn('There are more than one glance host. Using the first: '
                      + glance_hosts[0])
        return 'http://' + glance_hosts[0] + '/v1/images/' + str(self.os_id)


class ResourceTemplate(core_model.Mixin):
    '''
    Represents the Resource Template mechanism as per OCCI specification.
    An Resource template is equivocal to a flavor in OpenStack.
    '''
    def __init__(self, scheme, term, related=None, actions=None, title='',
                 attributes=None, location=None):
        super(ResourceTemplate, self).__init__(scheme, term, related, actions,
                                         title, attributes, location)


class OpenStackOCCIRegistry(registry.NonePersistentRegistry):

    def add_resource(self, key, resource):
        '''
        Make sure OS keys get used!
        '''
        key = self.get_hostname() + resource.kind.location
        key += resource.identifier
        registry.NonePersistentRegistry.add_resource(self, key, resource)
