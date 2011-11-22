import tornado.wsgi
import webob

from occi.web import QueryHandler, ResourceHandler, CollectionHandler
from occi.registry import Registry, NonePersistentRegistry
from occi.protocol.html_rendering import HTMLRendering
from occi.protocol.occi_rendering import TextOcciRendering, \
    TextPlainRendering, TextUriListRendering
from occi.extensions.infrastructure import START, STOP, SUSPEND, RESTART, UP, \
    DOWN, ONLINE, BACKUP, SNAPSHOT, RESIZE, OFFLINE, NETWORK, \
    NETWORKINTERFACE, COMPUTE, STORAGE, IPNETWORK, IPNETWORKINTERFACE, \
    STORAGELINK
from occi.backend import KindBackend, ActionBackend, MixinBackend
from backends import ComputeBackend, StorageBackend, NetworkBackend, \
    IpNetworkBackend, IpNetworkInterfaceBackend, StorageLinkBackend, \
    NetworkInterfaceBackend

from nova import wsgi


class OCCIApplication(wsgi.Application):
    
    def __init__(self, registry=None):
        
        if registry is None:
            self.registry = NonePersistentRegistry()
        elif isinstance(registry, Registry):
            self.registry = registry
        else:
            raise AttributeError('Registry needs to derive from abstract' \
                                 ' class \'Registry\'')
        
        self._setup_registry()
        
        # Not necessary to externalise these URLs
        self.application = tornado.wsgi.WSGIApplication([
            (r"/-/", QueryHandler, dict(registry=self.registry)),
            (r"/.well-known/org/ogf/occi/-/", QueryHandler, 
                                            dict(registry=self.registry)),
            (r"(.*)/", CollectionHandler, dict(registry=self.registry)),
            (r"(.*)", ResourceHandler, dict(registry=self.registry)),
        ])

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        '''
        
        Deals with incoming requests and outgoing responses
        
        Takes the incoming request, sends it on to the OCCI WSGI application,
        which finds the appropriate backend for it and then executes the
        request. The backend then is responsible for the return content.
        
        req -- a WSGI request supplied by a HTTP client
        '''
        res = req.get_response(self.application)
        return res
    
    def _setup_registry(self):
        
        # setup up content handlers
        self.registry.set_renderer('text/occi',
                                   TextOcciRendering(self.registry))
        self.registry.set_renderer('text/plain',
                                   TextPlainRendering(self.registry))
        self.registry.set_renderer('text/uri-list',
                                   TextUriListRendering(self.registry))
        self.registry.set_renderer('text/html', HTMLRendering(self.registry))
        
        # setup backends
        COMPUTE_BACKEND = ComputeBackend()
        NETWORK_BACKEND = NetworkBackend()
        STORAGE_BACKEND = StorageBackend()
        IPNETWORK_BACKEND = IpNetworkBackend()
        IPNETWORKINTERFACE_BACKEND = IpNetworkInterfaceBackend()
        STORAGE_LINK_BACKEND = StorageLinkBackend()
        NETWORKINTERFACE_BACKEND = NetworkInterfaceBackend()
    
        # register kinds with backends
        # TODO all of these Kinds statically set their endpoints.
        #      These endpoints should be set externally.
        self._register_backend(COMPUTE, COMPUTE_BACKEND)
        self._register_backend(START, COMPUTE_BACKEND)
        self._register_backend(STOP, COMPUTE_BACKEND)
        self._register_backend(RESTART, COMPUTE_BACKEND)
        self._register_backend(SUSPEND, COMPUTE_BACKEND)
    
        self._register_backend(NETWORK, NETWORK_BACKEND)
        self._register_backend(UP, NETWORK_BACKEND)
        self._register_backend(DOWN, NETWORK_BACKEND)
    
        self._register_backend(STORAGE, STORAGE_BACKEND)
        self._register_backend(ONLINE, STORAGE_BACKEND)
        self._register_backend(OFFLINE, STORAGE_BACKEND)
        self._register_backend(BACKUP, STORAGE_BACKEND)
        self._register_backend(SNAPSHOT, STORAGE_BACKEND)
        self._register_backend(RESIZE, STORAGE_BACKEND)
    
        self._register_backend(IPNETWORK, IPNETWORK_BACKEND)
        self._register_backend(IPNETWORKINTERFACE, IPNETWORKINTERFACE_BACKEND)
    
        self._register_backend(STORAGELINK, STORAGE_LINK_BACKEND)
        self._register_backend(NETWORKINTERFACE, NETWORKINTERFACE_BACKEND)

    def _register_backend(self, category, backend):
        '''
        Register a backend.

        Verifies that correct 'parent' backends are used.

        category -- The category the backend defines.
        backend -- The backend which handles the given category.
        '''
        allow = False
        if repr(category) == 'kind' and isinstance(backend, KindBackend):
            allow = True
        elif repr(category) == 'mixin' and isinstance(backend, MixinBackend):
            allow = True
        elif repr(category) == 'action' and isinstance(backend, ActionBackend):
            allow = True

        if allow:
            self.registry.set_backend(category, backend)
        else:
            raise AttributeError('Backends handling kinds need to derive' \
                                 ' from KindBackend; Backends handling' \
                                 ' actions need to derive from' \
                                 ' ActionBackend and backends handling' \
                                 ' mixins need to derive from MixinBackend.')