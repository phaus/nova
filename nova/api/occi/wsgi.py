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

from extensions import TCP, TCPBackend, OsTemplate, ResourceTemplate
#    DEFAULT_RESOURCE_TEMPLATE_SCHEME, \
#    OCCI_RESOURCE_TEMPLATE_SCHEME, DEFAULT_OS_TEMPLATE_SCHEME,\
#    OCCI_OS_TEMPLATE_SCHEME

from glance.common import exception as glance_exception
from nova import wsgi
from nova import context
from nova.compute import instance_types
import nova.image as image

from nova.api.occi.backends import ComputeBackend, NetworkBackend, \
    StorageBackend, IpNetworkBackend, IpNetworkInterfaceBackend, \
    StorageLinkBackend, NetworkInterfaceBackend, ResourceMixinBackend, \
    OsMixinBackend
from occi.extensions.infrastructure import COMPUTE, START, STOP, RESTART, \
    SUSPEND, NETWORK, UP, DOWN, STORAGE, ONLINE, OFFLINE, BACKUP, SNAPSHOT, \
    RESIZE, IPNETWORK, IPNETWORKINTERFACE, STORAGELINK, NETWORKINTERFACE
from occi.wsgi import Application

import logging

LOG = logging.getLogger('nova.api.occi.wsgi')


class OCCIApplication(Application, wsgi.Application):
    '''
    Adapter which 'translates' represents a nova WSGI application into and OCCI
    WSGI application.
    '''
    
    def __init__(self):
        '''
        Initialize the WSGI OCCI application.
        '''
        
        Application.__init__(self)
        
        self.application = Application()
        self.image_service = image.get_default_image_service()
        self.context = context.get_admin_context()
        self._setup_occi_service()

    def __call__(self, environ, response):
        '''
        Will be called as defined by WSGI.        
        Deals with incoming requests and outgoing responses

        Takes the incoming request, sends it on to the OCCI WSGI application,
        which finds the appropriate backend for it and then executes the
        request. The backend then is responsible for the return content.

        environ -- The environ.
        response -- The response.

        '''
        nova_ctx = environ['nova.context']
        return self._call_occi(environ, response, nova_ctx=nova_ctx)

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

        # register openstack resource templates
        # TODO each of these calls need to be authenticated
        # TODO need to pass admin credentials
        self._register_resource_mixins(ResourceMixinBackend())
        self._register_os_mixins(OsMixinBackend())
        
        # register extensions to the basic occi entities
        self._register_occi_extensions()
        
    def _register_resource_mixins(self, resource_mixin_backend):
        
        DEFAULT_RESOURCE_TEMPLATE_SCHEME = 'http://schemas.openstack.org/template/resource#'
        OCCI_RESOURCE_TEMPLATE_SCHEME = 'http://schemas.ogf.org/occi/infrastructure#resource_tpl'
        
        os_flavours = instance_types.get_all_types()
        
        assert len(os_flavours) > 0
        for itype in os_flavours:
            resourceTemplate = ResourceTemplate(term=itype, scheme=DEFAULT_RESOURCE_TEMPLATE_SCHEME, \
                related=[OCCI_RESOURCE_TEMPLATE_SCHEME], attributes=os_flavours[itype], \
                title='This is an openstack ' + itype + ' flavor.', location=itype)
            self.application.register_backend(resourceTemplate, resource_mixin_backend)
    
    def _register_os_mixins(self, os_mixin_backend):

        DEFAULT_OS_TEMPLATE_SCHEME = 'http://schemas.openstack.org/template/os#'
        OCCI_OS_TEMPLATE_SCHEME = 'http://schemas.ogf.org/occi/infrastructure#os_tpl'
                
        try:
            #this is a HTTP call out to glance
            images = self.image_service.detail(self.context)
        except glance_exception.GlanceException as ge:
            raise ge
        
        assert len(images) > 0
        for image in images:
            osTemplate = OsTemplate(term=image['name'], scheme=DEFAULT_OS_TEMPLATE_SCHEME, \
                os_id=image['id'], related=[OCCI_OS_TEMPLATE_SCHEME], \
                attributes=None, title='This is an OS ' + image['name'] + ' image', location=image['name'])
            self.application.register_backend(osTemplate, os_mixin_backend)
            
    def _register_occi_extensions(self):
        #TODO scan all classes in extensions.py and load dynamically
        self.application.register_backend(TCP, TCPBackend())
