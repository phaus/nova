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

#TODO: implement actions
#      implement updates

from nova import flags, log as logging
from occi import backend
from occi.extensions import infrastructure

from nova.network.quantum.client import Client as QuantumClient

#Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.network')

FLAGS = flags.FLAGS


class QuantumNetworkBackend(backend.KindBackend, backend.ActionBackend):
    '''
    Backend to handle network resources.
    '''
    def __init__(self):
        super(QuantumNetworkBackend, self).__init__()
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
        entity.attributes['occi.network.vlan'] = ''
        entity.attributes['occi.network.state'] = 'active'
        entity.actions = [infrastructure.DOWN]

    def retrieve(self, entity, extras):
        self.qclient.tenant = extras['nova_ctx'].project_id
        try:
            res = self.qclient.show_network_details(
                                            entity.attributes['occi.core.id'])
        except:
            raise Exception()

        if res['op-status'] == 'UP':
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
            print('Starting VNIC with id: ' + entity.identifier)
        elif action.kind == infrastructure.DOWN:
            entity.attributes['occi.network.state'] = 'inactive'
            # read attributes from action and do something with it :-)
            print('Stopping VNIC with id: ' + entity.identifier)
