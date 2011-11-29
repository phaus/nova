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

from extensions import TCP, TCPBackend

from nova import wsgi
from nova.api.occi.backends import ComputeBackend, NetworkBackend, \
    StorageBackend, IpNetworkBackend, IpNetworkInterfaceBackend, \
    StorageLinkBackend, NetworkInterfaceBackend
from occi.extensions.infrastructure import COMPUTE, START, STOP, RESTART, \
    SUSPEND, NETWORK, UP, DOWN, STORAGE, ONLINE, OFFLINE, BACKUP, SNAPSHOT, \
    RESIZE, IPNETWORK, IPNETWORKINTERFACE, STORAGELINK, NETWORKINTERFACE
from occi.wsgi import Application
import logging
import webob

LOG = logging.getLogger('nova.api.occi.wsgi')


class OCCIApplication(wsgi.Application):
    '''
    Adapter which 'translates' represents a nova WSGI application into and OCCI
    WSGI application.
    '''

    def __init__(self):
        '''
        Initialize the WSGI OCCI application.
        '''
        self.application = Application()
        self._setup_occi_service()

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        '''
        Deals with incoming requests and outgoing responses

        Takes the incoming request, sends it on to the OCCI WSGI application,
        which finds the appropriate backend for it and then executes the
        request. The backend then is responsible for the return content.

        req -- a WSGI request supplied by a HTTP client
        '''
        return req.get_response(self.application)

    def _setup_occi_service(self):
        '''
        Register the OCCI backends within the OCCI WSGI application.
        '''
        compute_backend = ComputeBackend()
        network_backend = NetworkBackend()
        storage_backend = StorageBackend()
        ipnetwork_backend = IpNetworkBackend()
        ipnetworking_backend = IpNetworkInterfaceBackend()
        storage_link_backend = StorageLinkBackend()
        networkinterface_backend = NetworkInterfaceBackend()

        # register kinds with backends
        self.application.register_backend(COMPUTE, compute_backend)
        self.application.register_backend(START, compute_backend)
        self.application.register_backend(STOP, compute_backend)
        self.application.register_backend(RESTART, compute_backend)
        self.application.register_backend(SUSPEND, compute_backend)

        self.application.register_backend(NETWORK, network_backend)
        self.application.register_backend(UP, network_backend)
        self.application.register_backend(DOWN, network_backend)

        self.application.register_backend(STORAGE, storage_backend)
        self.application.register_backend(ONLINE, storage_backend)
        self.application.register_backend(OFFLINE, storage_backend)
        self.application.register_backend(BACKUP, storage_backend)
        self.application.register_backend(SNAPSHOT, storage_backend)
        self.application.register_backend(RESIZE, storage_backend)

        self.application.register_backend(IPNETWORK, ipnetwork_backend)
        self.application.register_backend(IPNETWORKINTERFACE,
                                          ipnetworking_backend)

        self.application.register_backend(STORAGELINK, storage_link_backend)
        self.application.register_backend(NETWORKINTERFACE,
                                          networkinterface_backend)

        self.application.register_backend(TCP, TCPBackend())
