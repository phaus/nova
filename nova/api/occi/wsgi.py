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


from nova import image
from nova import log
from nova import wsgi
from nova.api.occi import backends
from nova.api.occi import extensions
from nova.compute import instance_types
from nova.image import glance

from occi import wsgi as occi_wsgi
from occi.extensions import infrastructure

LOG = log.getLogger('nova.api.occi.wsgi')


class OCCIApplication(occi_wsgi.Application, wsgi.Application):
    '''
    Adapter which 'translates' represents a nova WSGI application into and OCCI
    WSGI application.
    '''

    def __init__(self):
        '''
        Initialize the WSGI OCCI application.
        '''
        super(OCCIApplication, self).__init__(
                                registry=extensions.OpenStackOCCIRegistry())

        # setup the occi service...
        self._setup_occi_service()

        # register openstack instance types (flavours)
        self._register_resource_mixins(backends.ResourceMixinBackend())

        # register extensions to the basic occi entities
        self._register_occi_extensions()

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
        # TODO(dizz) this is not optimal
        self._register_os_mixins(backends.OsMixinBackend(), nova_ctx)
        return self._call_occi(environ, response, nova_ctx=nova_ctx)

    def _setup_occi_service(self):
        '''
        Register the OCCI backends within the OCCI WSGI application.
        '''
        LOG.info('Registering OCCI backends with web app.')
        compute_backend = backends.ComputeBackend()
        network_backend = backends.NetworkBackend()
        storage_backend = backends.StorageBackend()
        ipnetwork_backend = backends.IpNetworkBackend()
        ipnetworking_backend = backends.IpNetworkInterfaceBackend()
        storage_link_backend = backends.StorageLinkBackend()
        networkinterface_backend = backends.NetworkInterfaceBackend()

        # register kinds with backends
        self.register_backend(infrastructure.COMPUTE, compute_backend)
        self.register_backend(infrastructure.START, compute_backend)
        self.register_backend(infrastructure.STOP, compute_backend)
        self.register_backend(infrastructure.RESTART, compute_backend)
        self.register_backend(infrastructure.SUSPEND, compute_backend)

        self.register_backend(infrastructure.NETWORK, network_backend)
        self.register_backend(infrastructure.UP, network_backend)
        self.register_backend(infrastructure.DOWN, network_backend)

        self.register_backend(infrastructure.STORAGE, storage_backend)
        self.register_backend(infrastructure.ONLINE, storage_backend)
        self.register_backend(infrastructure.OFFLINE, storage_backend)
        self.register_backend(infrastructure.BACKUP, storage_backend)
        self.register_backend(infrastructure.SNAPSHOT, storage_backend)
        self.register_backend(infrastructure.RESIZE, storage_backend)

        self.register_backend(infrastructure.IPNETWORK, ipnetwork_backend)
        self.register_backend(infrastructure.IPNETWORKINTERFACE,
                                          ipnetworking_backend)

        self.register_backend(infrastructure.STORAGELINK, storage_link_backend)
        self.register_backend(infrastructure.NETWORKINTERFACE,
                                          networkinterface_backend)

    def _register_resource_mixins(self, resource_mixin_backend):
        '''
        Register the resource resource templates to which the user has access.
        '''
        template_schema = 'http://schemas.openstack.org/template/resource#'
        resource_schema = \
                    'http://schemas.ogf.org/occi/infrastructure#resource_tpl'

        os_flavours = instance_types.get_all_types()

        for itype in os_flavours:
            resource_template = extensions.ResourceTemplate(term=itype,
                scheme=template_schema,
                related=[resource_schema],
                attributes=os_flavours[itype],
                title='This is an openstack ' + itype + ' flavor.',
                location=itype)
            LOG.debug('Regsitering an OpeStack flavour/instance type as: ' + \
                                                        str(resource_template))
            #TODO(dizz) - no check is done to see if the template is exists
            self.register_backend(resource_template, resource_mixin_backend)

    def _register_os_mixins(self, os_mixin_backend, context):
        '''
        Register the os mixins from information retrieved frrom glance.
        '''
        template_schema = 'http://schemas.openstack.org/template/os#'
        os_schema = 'http://schemas.ogf.org/occi/infrastructure#os_tpl'

        images = []
        try:
            #this is a HTTP call out to the image service
            image_service = image.get_default_image_service()
            images = image_service.detail(context)
        except glance.glance_exception as ge:
            raise ge

        # assert len(images) > 0
        for img in images:
            os_template = extensions.OsTemplate(term=img['name'],
                                    scheme=template_schema, \
                os_id=img['id'], related=[os_schema], \
                attributes=None, title='This is an OS ' + img['name'] + \
                                            ' image', location=img['name'])
            LOG.debug('Registering an OS image type as: ' + str(os_template))
            self.register_backend(os_template, os_mixin_backend)

    def _register_occi_extensions(self):
        '''
        Register some other OCCI extensions.
        '''
        # TODO(dizz) scan all classes in extensions.py and load dynamically
        self.register_backend(extensions.TCP, extensions.TCPBackend())
