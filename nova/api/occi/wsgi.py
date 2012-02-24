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
from nova import flags
from nova.openstack.common import cfg
from nova.network import api as network_api
from nova import context
from nova.api.openstack import extensions as os_extensions
from nova.api.occi import backends
from nova.api.occi import extensions
from nova.api.occi.compute import computeresource
from nova.api.occi.network import networklink
from nova.api.occi.network import networkresource
from nova.api.occi.storage import storagelink
from nova.api.occi.storage import storageresource
from nova.compute import instance_types

from occi import registry
from occi import wsgi as occi_wsgi
from occi.core_model import Resource
from occi.extensions import infrastructure

#Hi I'm a logger, use me! :-)
LOG = log.getLogger('nova.api.occi.wsgi')

#Setup options
occi_opts = [
             cfg.BoolOpt("show_default_net_config",
                default=False,
                help="Whether to show the default network config to clients"),
             cfg.BoolOpt("filter_kernel_and_ram_images",
                default=True,
                help="Whether to show the Kernel and RAM images to clients"),
             ]
FLAGS = flags.FLAGS
FLAGS.register_opts(occi_opts)

class OpenStackOCCIRegistry(registry.NonePersistentRegistry):

    def add_resource(self, key, resource):
        '''
        Make sure OS keys get used!
        '''
        key = resource.kind.location + resource.attributes['occi.core.id']
        resource.identifier = key
        registry.NonePersistentRegistry.add_resource(self, key, resource)


class OCCIApplication(occi_wsgi.Application, wsgi.Application):
    '''
    Adapter which 'translates' represents a nova WSGI application 
    into and OCCI WSGI application.
    '''

    def __init__(self):
        '''
        Initialize the WSGI OCCI application.
        '''
        super(OCCIApplication, self).__init__(
                                registry=OpenStackOCCIRegistry())

        # setup the occi service...
        self._setup_occi_service()

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
        
        # query for correct project_id based on auth token?
        # There are multiple options here:
        #  1. extract project_id from URL e.g.:
        #     create compute: POST /compute/1/
        #  2. supply project_id as a URL parameter e.g.:
        #     create compute: POST /compute/query?project_id=1
        #  3. Use a mixin
        #  4. Use a HTTP header e.g.:
        #     X-Project-Id: 1
        #  Or....
        #  Just use the openstack header! Ya ha ha ha!
        
        #L8R this might be pushed into the context middleware
        nova_ctx.project_id = environ.get('HTTP_X_AUTH_PROJECT_ID', None)
        if nova_ctx.project_id == None:
            LOG.error('No project ID header was supplied in the request')
        
        # register openstack images
        self._register_os_mixins(backends.OsMixinBackend(), nova_ctx)
        # register openstack instance types (flavours)
        self._register_resource_mixins(backends.ResourceMixinBackend())
        
        return self._call_occi(environ, response, nova_ctx=nova_ctx, \
                                                        registry=self.registry)


    def _setup_occi_service(self):
        '''
        Register the OCCI backends within the OCCI WSGI application.
        '''
        LOG.info('Registering OCCI backends with web app.')

        compute_backend = computeresource.ComputeBackend()
        network_backend = networkresource.NetworkBackend()
        storage_backend = storageresource.StorageBackend()
        ipnetwork_backend = networkresource.IpNetworkBackend()
        ipnetworking_backend = networklink.IpNetworkInterfaceBackend()
        storage_link_backend = storagelink.StorageLinkBackend()
        networkinterface_backend = networklink.NetworkInterfaceBackend()
        admin_password_backend = extensions.AdminPasswordBackend()
        key_pair_backend = extensions.KeyPairBackend()

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
        
        # OS-OCCI Action extensions 
        self.register_backend(extensions.OS_CHG_PWD, compute_backend)
        self.register_backend(extensions.OS_REVERT_RESIZE, compute_backend)
        self.register_backend(extensions.OS_CONFIRM_RESIZE, compute_backend)
        self.register_backend(extensions.OS_CREATE_IMAGE, compute_backend)
     
        # OS-OCCI Mixin extensions
        self.register_backend(extensions.ADMIN_PWD_EXT, admin_password_backend)
        self.register_backend(extensions.KEY_PAIR_EXT, key_pair_backend)
        
        #This must be done as by default OpenStack has a default network
        # to which all new VM instances are attached.
        LOG.info('Registering default network with web app.')
        self._register_default_network()


    def _register_default_network(self, name='DEFAULT_NETWORK'):
        default_network = Resource(name, infrastructure.NETWORK, \
                            [infrastructure.IPNETWORK], [],
                            'This is the network all VMs are attached to.',
                            'Default Network')
        
        show_default_net_config = FLAGS.get("show_default_net_config", False)
        
        if show_default_net_config:
            default_network.attributes = {
                    'occi.core.id': name,
                    
                    'occi.network.vlan': '',
                    'occi.network.label': 'public',
                    'occi.network.state': 'up',
                    
                    'occi.network.address': '',
                    'occi.network.gateway': '',
                    'occi.network.allocation': ''
            }
        else:
            # get values from API. right now they reflect default
            
            context = context.get_admin_context()
            authorize = os_extensions.extension_authorizer(
                                                        'compute', 'networks')
            authorize(context)
            
            self.network_api = network_api.API()
            networks = self.network_api.get_all(context)
            
            if networks > 0:
                LOG.warn('There is more that one network.')
                LOG.warn('Current implmentation assumes only one.')
                LOG.warn('Using the first network: id' + networks[0]['id'])
            
            default_network.attributes = {
                    'occi.core.id': name,
                    
                    'occi.network.vlan': '',
                    'occi.network.label': 'public',
                    'occi.network.state': 'up',
                    
                    'occi.network.address': networks[0]['cidr'],
                    'occi.network.gateway': networks[0]['gateway'],
                    'occi.network.allocation': 'dhcp'
            }
        
        self.registry.add_resource(name, default_network)


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
                attributes=self._get_resource_attributes(os_flavours[itype]),
                title='This is an openstack ' + itype + ' flavor.',
                location='/' + itype + '/')
            LOG.debug('Regsitering an OpenStack flavour/instance type as: ' + \
                                                        str(resource_template))
            
            self.register_backend(resource_template, resource_mixin_backend)
    
    
    def _get_resource_attributes(self, attrs):
        
#        import ipdb
#        ipdb.set_trace()
        
#        test_attrs = {
#                      'root_gb': 10, 'name': 'm1.medium',
#                      'deleted': False, 'created_at': None,
#                      'ephemeral_gb': 40, 'updated_at': None,
#                      'memory_mb': 4096, 'vcpus': 2, 'flavorid': '3',
#                      'swap': 0L, 'rxtx_factor': 1.0,
#                      'extra_specs': {}, 'deleted_at': None,
#                      'vcpu_weight': None, 'id': 1L
#                      }
#        
#        test_attrs['root_gb']
#        test_attrs['ephemeral_gb']
#        test_attrs['memory_mb']
#        test_attrs['vcpus']
#        test_attrs['swap']
        
        #This is hardcoded atm - might be good to have it configurable
        attrs = { 
                 'occi.compute.cores': 'immutable',
                 'occi.compute.memory': 'immutable',
                 'org.openstack.compute.swap': 'immutable',
                 'org.openstack.compute.storage.root': 'immutable',
                 'org.openstack.compute.storage.ephemeral': 'immutable',
                 }
        return attrs
       

    def _register_os_mixins(self, os_mixin_backend, context):
        '''
        Register the os mixins from information retrieved frrom glance.
        '''
        template_schema = 'http://schemas.openstack.org/template/os#'
        os_schema = 'http://schemas.ogf.org/occi/infrastructure#os_tpl'

        image_service = image.get_default_image_service()
        images = image_service.detail(context)

        # L8R: now the API allows users to supply RAM and Kernel images
        filter_kernel_and_ram_images = \
                                FLAGS.get("filter_kernel_and_ram_images", True)

        for img in images:
            #If the image is a kernel or ram one 
            # and we're not to filter them out then register it.
            if ((img['container_format'] or img['disk_format']) \
                    in ('ari', 'aki')) and filter_kernel_and_ram_images:
                LOG.warn('Not registering kernel/RAM image.')
                continue 

            os_template = extensions.OsTemplate(
                                term=img['name'],
                                scheme=template_schema, \
                                os_id=img['id'], related=[os_schema], \
                                attributes=None,
                                title='This is an OS ' + img['name'] + \
                                                            ' VM image',
	                            location='/' + img['name'] + '/')
            
            LOG.debug('Registering an OS image type as: ' \
                                                    + str(os_template))
            self.register_backend(os_template, os_mixin_backend)


    def _register_occi_extensions(self):
        '''
        Register some other OCCI extensions.
        '''
        # self.register_backend(extensions.TCP, extensions.TCPBackend())
        pass
