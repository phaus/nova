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

from nova import log as logging
from occi.backend import KindBackend, MixinBackend
#from occi.extensions.infrastructure import NETWORKINTERFACE

# Retrieve functionality is already present via pyssf

# With Quantum:
#     TODO: implement create - note: this must handle either nova-network or
#            quantum APIs - detect via flags and secondarily via import exceptions
#           implement delete
#           implement update

# Also see nova/api/openstack/compute/contrib/multinic.py


#Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.network.link')

class NetworkInterfaceBackend(KindBackend):
    '''
    A backend for the network links.
    '''

    def create(self, link, extras):
        # TODO implement with Quantum
        raise exc.HTTPBadRequest
        #link.attributes['occi.networkinterface.state'] = 'up'
        #link.attributes['occi.networkinterface.mac'] = 'aa:bb:cc:dd:ee:ff'
        #link.attributes['occi.networkinterface.interface'] = 'eth0'

    def update(self, old, new, extras):
        raise exc.HTTPBadRequest()

    def delete(self, link, extras):
        raise exc.HTTPBadRequest()
#        link.attributes.pop('occi.networkinterface.state')
#        link.attributes.pop('occi.networkinterface.mac')
#        link.attributes.pop('occi.networkinterface.interface')

class IpNetworkInterfaceBackend(MixinBackend):
    '''
    A mixin backend for the IpNetworkingInterface.
    '''

    def create(self, link, extras):
        raise exc.HTTPBadRequest()
    
#        if not link.kind == NETWORKINTERFACE:
#            raise AttributeError('This mixin cannot be applied to this kind.')
#        link.attributes['occi.networkinterface.address'] = '10.0.0.65'
#        link.attributes['occi.networkinterface.gateway'] = '10.0.0.1'
#        link.attributes['occi.networkinterface.allocation'] = 'dynamic'

    def delete(self, entity, extras):
        raise exc.HTTPBadRequest()
#        entity.attributes.pop('occi.networkinterface.address')
#        entity.attributes.pop('occi.networkinterface.gateway')
#        entity.attributes.pop('occi.networkinterface.allocation')
