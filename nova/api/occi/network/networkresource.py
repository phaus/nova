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

# TODO: implement create - note: this must handle either nova-network or
#        quantum APIs - detect via flags and secondarily via import exceptions
# TODO: implement delete
# TODO: implement retreive
# TODO: implement actions
# TODO: implement updates

from nova import flags, log as logging
from nova.api.occi.backends import MyBackend
from occi.backend import MixinBackend
from occi.extensions.infrastructure import UP, DOWN, NETWORK

#from quantum.client import cli_lib as cli
#from quantum.client import Client


#Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.network')

FLAGS = flags.FLAGS


class NetworkBackend(MyBackend):
    '''
    Backend to handle network resources.
    '''
#    def __init__(self):
#        self.tenant_id = 'admin'
#        FORMAT = 'json'
#        self.client = Client(tenant=self.tenant_id, format=FORMAT)
        
    def create(self, entity, extras):
        # create a VNIC...
        entity.attributes['occi.network.vlan'] = '1'
        entity.attributes['occi.network.label'] = 'dummy interface'
        entity.attributes['occi.network.state'] = 'inactive'
        entity.actions = [UP]
        print('Creating a VNIC')
        
        #here comes the pain/fun!
#        params = {'network': {'name': 'a name'}}
#        try:
#            res = self.client.create_network(params)
#        except Exception as ex:
#            raise ex
#        
#        LOG.debug("Operation 'create_network' executed.")
#        entity.attributes['occi.core.id'] = res["network"]["id"]
        
    def retrieve(self, entity, extras):
        # update a VNIC
        if entity.attributes['occi.network.state'] == 'active':
            entity.actions = [DOWN]
        elif entity.attributes['occi.network.state'] == 'inactive':
            entity.actions = [UP]

    def delete(self, entity, extras):
        # and deactivate it
        print('Removing representation of a VNIC with id:' + entity.identifier)

    def action(self, entity, action, extras):
        if action not in entity.actions:
            raise AttributeError("This action is currently no applicable.")
        elif action.kind == UP:
            entity.attributes['occi.network.state'] = 'active'
            # read attributes from action and do something with it :-)
            print('Starting VNIC with id: ' + entity.identifier)
        elif action.kind == DOWN:
            entity.attributes['occi.network.state'] = 'inactive'
            # read attributes from action and do something with it :-)
            print('Stopping VNIC with id: ' + entity.identifier)

class IpNetworkBackend(MixinBackend):
    '''
    A mixin backend for the IPnetworking.
    '''

    def create(self, entity, extras):
        if not entity.kind == NETWORK:
            raise AttributeError('This mixin cannot be applied to this kind.')
        entity.attributes['occi.network.allocation'] = 'dynamic'
        entity.attributes['occi.network.gateway'] = '10.0.0.1'
        entity.attributes['occi.network.address'] = '10.0.0.1/24'

    def delete(self, entity, extras):
        entity.attributes.pop('occi.network.allocation')
        entity.attributes.pop('occi.network.gateway')
        entity.attributes.pop('occi.network.address')


