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

from occi.core_model import Mixin
from occi.backend import MixinBackend
from occi.extensions.infrastructure import COMPUTE

# Trusted Compute Pool technology mixin definition
TCP_ATTRIBUTES = {'eu.fi-ware.compute.tcp': ''}
TCP = Mixin('http://schemas.fi-ware.eu/occi/infrastructure/compute#',
                  'tcp', attributes=TCP_ATTRIBUTES)


class TCPBackend(MixinBackend):
    '''
    Trusted Compute Pool technology mixin backend handler
    '''

    def create(self, entity):
        if not entity.kind == COMPUTE:
            raise AttributeError('This mixin cannot be applied to this kind.')
        entity.attributes['eu.fi-ware.compute.tcp'] = 'true'

    def delete(self, entity):
        entity.attributes.pop('eu.fi-ware.compute.tcp')
