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

from nova import log as logging
from nova.network.quantum.quantum_connection import QuantumClientConnection
from nova import network
from nova import compute

from occi import backend

from webob import exc

# Retrieve functionality is already present via pyssf

# With Quantum:
#     TODO: implement create - note: this must handle either nova-network or
#            quantum APIs - detect via flags and secondarily via import
#            exceptions
#           implement delete
#           implement update

# Also see nova/api/openstack/compute/contrib/multinic.py


#Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.network.link')


class QuantumNetworkInterfaceBackend(backend.KindBackend):
    '''
    A backend for the network links.
    '''

    def __init__(self):
        super(QuantumNetworkInterfaceBackend, self).__init__()
        self.network_api = network.API()
        self.compute_api = compute.API()

    # in effect this creates an IPNetworkInterface
    # more code is required to only create a NetworkInterface and means
    # bring explicit qunatum dependencies into nova, which may not be desired
    # should we move this create operation to IPNetworkInterface and 401 here?
    def create(self, link, extras):
        # TODO implement with Quantum
        # Number of steps required here:
        # 1. create the VIF
        # 2. add a port to the target network
        # 3. attach the VIF to the port
        # See nova/network/quantum/manager.py:allocate_for_instance

        import ipdb
        ipdb.set_trace()

        instance_id = link.source.attributes['occi.core.id']
        instance = self.compute_api.get(extras['nova_ctx'], instance_id)
        # supply this through requested_networks kwarg
        network_id = link.target.attributes['occi.core.id']
        req_net = [(network_id, None)]

        # note this will allocate an ip
        # if only the L2 capabilities are needed then more code is needed
        # and that code is directly dependent on quantum
        try:
            res = self.network_api.allocate_for_instance(
                                    extras['nova_ctx'], instance,
                                    vpn=False, requested_networks=req_net)
        except Exception, e:
            raise e
        print res

        #link.attributes['occi.networkinterface.state'] = 'up'
        #link.attributes['occi.networkinterface.mac'] = 'aa:bb:cc:dd:ee:ff'
        #link.attributes['occi.networkinterface.interface'] = 'eth0'

    #TODO: here we associate a security group
    # What happens here if there are two adapters associated with the VM
    # and different rule groups are to be applied to one adapter and another
    # set to the second?
    def update(self, old, new, extras):
        # make sure the link has an IP mixin
        # get a reference to the compute instance
        # get the security group
        # associate the security group with the compute instance
        for mixin in old.mixins:
            if mixin.term == '' and mixin.scheme == '':
                _update_sec_grps()

        raise exc.HTTPBadRequest()

    def delete(self, link, extras):

        import ipdb
        ipdb.set_trace()

        instance_id = link.source.attributes['occi.core.id']
        instance = self.compute_api.get(extras['nova_ctx'], instance_id)
        try:
            res = self.network_api.deallocate_for_instance(
                                            extras['nova_ctx'], instance)
        except Exception, e:
            raise e
        print res
#        link.attributes.pop('occi.networkinterface.state')
#        link.attributes.pop('occi.networkinterface.mac')
#        link.attributes.pop('occi.networkinterface.interface')

# This function will be shared between networklink and quantumnetworklink

def _update_sec_grps():
    pass


class IpNetworkInterfaceBackend(backend.MixinBackend):
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
        pass
        #raise exc.HTTPBadRequest()
#        entity.attributes.pop('occi.networkinterface.address')
#        entity.attributes.pop('occi.networkinterface.gateway')
#        entity.attributes.pop('occi.networkinterface.allocation')
