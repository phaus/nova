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
        COMPUTE_BACKEND = ComputeBackend()
        NETWORK_BACKEND = NetworkBackend()
        STORAGE_BACKEND = StorageBackend()
        IPNETWORK_BACKEND = IpNetworkBackend()
        IPNETWORKINTERFACE_BACKEND = IpNetworkInterfaceBackend()
        STORAGE_LINK_BACKEND = StorageLinkBackend()
        NETWORKINTERFACE_BACKEND = NetworkInterfaceBackend()

        # register kinds with backends
        self.application.register_backend(COMPUTE, COMPUTE_BACKEND)
        self.application.register_backend(START, COMPUTE_BACKEND)
        self.application.register_backend(STOP, COMPUTE_BACKEND)
        self.application.register_backend(RESTART, COMPUTE_BACKEND)
        self.application.register_backend(SUSPEND, COMPUTE_BACKEND)

        self.application.register_backend(NETWORK, NETWORK_BACKEND)
        self.application.register_backend(UP, NETWORK_BACKEND)
        self.application.register_backend(DOWN, NETWORK_BACKEND)

        self.application.register_backend(STORAGE, STORAGE_BACKEND)
        self.application.register_backend(ONLINE, STORAGE_BACKEND)
        self.application.register_backend(OFFLINE, STORAGE_BACKEND)
        self.application.register_backend(BACKUP, STORAGE_BACKEND)
        self.application.register_backend(SNAPSHOT, STORAGE_BACKEND)
        self.application.register_backend(RESIZE, STORAGE_BACKEND)

        self.application.register_backend(IPNETWORK, IPNETWORK_BACKEND)
        self.application.register_backend(IPNETWORKINTERFACE,
                                          IPNETWORKINTERFACE_BACKEND)

        self.application.register_backend(STORAGELINK, STORAGE_LINK_BACKEND)
        self.application.register_backend(NETWORKINTERFACE,
                                          NETWORKINTERFACE_BACKEND)