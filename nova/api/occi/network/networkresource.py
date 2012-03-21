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


# TODO: implement create
#       implement delete
#       implement retreive
#       implement actions
#       implement updates

# Also see nova/api/openstack/compute/contrib/networks.py


from nova import flags, log as logging
from occi import backend
from occi.extensions.infrastructure import UP, DOWN, NETWORK
from nova.network.quantum.client import Client as QuantumClient

from occi.extensions import infrastructure

#Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.network')

FLAGS = flags.FLAGS


class NetworkBackend(backend.KindBackend, backend.ActionBackend):
    '''
    Backend to handle network resources.
    '''
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


class IpNetworkBackend(backend.MixinBackend):
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


# work in progress
class QuantumNetworkBackend(backend.KindBackend, backend.ActionBackend):
    '''
    Backend to handle network resources.
    '''
    def __init__(self):
        super(QuantumNetworkBackend, self).__init__()
        # TODO: read from FLAGS
        self.qclient = QuantumClient(host='10.211.55.85', format='json')

    def create(self, entity, extras):
        LOG.info('Creating a virtual network')

        if 'occi.network.label' not in entity.attributes:
            raise Exception()

        self.qclient.tenant = extras['nova_ctx'].project_id
        params = {'network': {'name': entity.attributes['occi.network.label']}}

        try:
            res = self.qclient.create_network(params)
        except Exception:
            raise Exception()

        entity.attributes['occi.core.id'] = res["network"]["id"]
        # VLANs are stored in the openvswitch db - vlan_bindings
        # Need to access these some way. Note this is only OVS functionality
        entity.attributes['occi.network.vlan'] = ''
        entity.attributes['occi.network.state'] = 'active'
        entity.actions = [infrastructure.DOWN]

    def retrieve(self, entity, extras):
        # FIXME: hackish - subclass network?
        if entity.title == 'Default Network':
            self.qclient.tenant = 'default'
        else:
            self.qclient.tenant = extras['nova_ctx'].project_id
        try:
            res = self.qclient.show_network_details(
                                            entity.attributes['occi.core.id'])
        except:
            raise Exception()

        if res['network']['op-status'] == 'UP':
            entity.attributes['occi.network.state'] = 'active'
            entity.actions = [infrastructure.DOWN]
        else:
            entity.attributes['occi.network.state'] = 'inactive'
            entity.actions = [infrastructure.UP]

    def delete(self, entity, extras):
        # and deactivate it
        LOG.info('Removing network of with id:' + entity.identifier)
        self.qclient.tenant = extras['nova_ctx'].project_id
        try:
            self.qclient.show_network_details(
                                            entity.attributes['occi.core.id'])
        except Exception:
            raise Exception()
        self.qclient.delete_network(entity.attributes['occi.core.id'])

    def action(self, entity, action, extras):
        if action not in entity.actions:
            raise AttributeError("This action is currently no applicable.")
        elif action.kind == infrastructure.UP:
            entity.attributes['occi.network.state'] = 'active'
            # read attributes from action and do something with it :-)
            print('Starting vnet with id: ' + entity.identifier)
        elif action.kind == infrastructure.DOWN:
            entity.attributes['occi.network.state'] = 'inactive'
            # read attributes from action and do something with it :-)
            print('Stopping vnet with id: ' + entity.identifier)
