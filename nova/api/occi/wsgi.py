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

from nova import context
from nova import image
from nova import log
from nova import wsgi
from nova import flags
from nova import db
from nova.openstack.common import cfg
from nova.compute import API
from nova.compute import instance_types
from nova.network import api as net_api
from nova.api.openstack import extensions as os_extensions
from nova.api.occi import extensions
from nova.api.occi.extensions import occi_future
from nova.api.occi.compute import templates
from nova.api.occi.compute import computeresource
from nova.api.occi.network import networklink
from nova.api.occi.network import networkresource
from nova.api.occi.storage import storagelink
from nova.api.occi.storage import storageresource

from occi import registry
from occi import core_model
from occi import backend
from occi import wsgi as occi_wsgi
from occi.extensions import infrastructure


#Hi I'm a logger, use me! :-)
LOG = log.getLogger('nova.api.occi.wsgi')

#Setup options
OCCI_OPTS = [
             cfg.BoolOpt("show_default_net_config",
                default=False,
                help="Show the default network configuration to clients"),
             cfg.BoolOpt("filter_kernel_and_ram_images",
                default=True,
                help="Whether to show the Kernel and RAM images to clients"),
             cfg.StrOpt("net_manager",
                        default="nova", #also quantum
                        help="The network manager to use with the OCCI API."),
             ]
FLAGS = flags.FLAGS
FLAGS.register_opts(OCCI_OPTS)


class OpenStackOCCIRegistry(registry.NonePersistentRegistry):
    '''
    Simple SSF registry for OpenStack.
    '''

    def add_resource(self, key, resource):
        '''
        Ensures OpenStack keys are used as resource identifiers
        '''
        key = resource.kind.location + resource.attributes['occi.core.id']
        resource.identifier = key
        registry.NonePersistentRegistry.add_resource(self, key, resource)


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
                                registry=OpenStackOCCIRegistry())
        self.compute_api = API()
        self.net_manager = FLAGS.get("net_manager", "nova")
        self.no_default_network = True
        self._setup_occi_service()
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
        #L8R: this might be pushed into the context middleware
        nova_ctx.project_id = environ.get('HTTP_X_AUTH_TENANT_ID', None)

        if nova_ctx.project_id == None:
            LOG.error('No tenant ID header was supplied in the request')

        # When the API boots the network services may not be started.
        # The call to the service is a sync RPC over rabbitmq and will block.
        # We must register the network only once and once all services are
        # available. Hence we perform the registration once here.
        if self.no_default_network:
            self._register_default_network()

        # register/refresh openstack images
        self._register_os_mixins(backend.MixinBackend(), nova_ctx)
        # register/refresh openstack instance types (flavours)
        self._register_resource_mixins(backend.MixinBackend())
        # register/refresh the openstack security groups as Mixins
        self._register_security_mixins(nova_ctx)

        return self._call_occi(environ, response, nova_ctx=nova_ctx,
                                                        registry=self.registry)

    def _setup_occi_service(self):
        '''
        Register the OCCI backends within the OCCI WSGI application.
        '''
        LOG.info('Registering OCCI backends with web app.')

        self._register_occi_infra()
        self._register_occi_extensions()

        #This must be done as by default OpenStack has a default network
        # to which all new VM instances are attached.

    def _register_default_network(self, name='DEFAULT_NETWORK'):
        '''
        By default nova attaches a compute resource to a network.
        In the OCCI model this is represented as a Network resource.
        This method constructs that Network resource.
        '''
        #L8R: verify behaviour with quantum backend
        #      i.e. cover the case where there are > 1 networks
        LOG.info('Registering default network with web app.')
        show_default_net_config = FLAGS.get("show_default_net_config", False)

        net_attrs = {}

        if show_default_net_config:
            net_attrs = {
                    'occi.core.id': name,

                    'occi.network.vlan': '',
                    'occi.network.label': 'public',
                    'occi.network.state': 'up',

                    'occi.network.address': '',
                    'occi.network.gateway': '',
                    'occi.network.allocation': ''
            }
        else:
            ctx = context.get_admin_context()
            authorize = os_extensions.extension_authorizer('compute',
                                                                    'networks')
            authorize(ctx)

            network_api = net_api.API()
            networks = network_api.get_all(ctx)

            if len(networks) > 1:
                LOG.warn('There is more that one network.')
                LOG.warn('Current implmentation assumes only one.')
                LOG.warn('Using the first network: id' \
                                                    + str(networks[0]['id']))

            net_attrs = {
                    'occi.core.id': name,
#                    'occi.core.id': networks[0]['uuid'],
                    'occi.network.vlan': '',
                    'occi.network.label': 'public',
                    'occi.network.state': 'up',

                    'occi.network.address': networks[0]['cidr'],
                    'occi.network.gateway': networks[0]['gateway'],
                    'occi.network.allocation': 'dhcp'
            }
#            name = networks[0]['uuid']

        default_network = core_model.Resource(name, infrastructure.NETWORK, \
                        [infrastructure.IPNETWORK], [],
                        'This is the network all VMs are attached to.',
                        'Default Network')
        default_network.attributes = net_attrs

        self.registry.add_resource(name, default_network)

        self.no_default_network = False

    def _register_resource_mixins(self, resource_mixin_backend):
        '''
        Register the flavors as ResourceTemplates to which the user has access.
        '''
        template_schema = 'http://schemas.openstack.org/template/resource#'
        resource_schema = \
                    'http://schemas.ogf.org/occi/infrastructure#resource_tpl'

        os_flavours = instance_types.get_all_types()
        for itype in os_flavours:
            resource_template = templates.ResourceTemplate(term=itype,
                scheme=template_schema,
                related=[resource_schema],
                attributes=self._get_resource_attributes(os_flavours[itype]),
                title='This is an openstack ' + itype + ' flavor.',
                location='/' + itype + '/')
            LOG.debug('Regsitering an OpenStack flavour/instance type as: ' + \
                                                        str(resource_template))

            self.register_backend(resource_template, resource_mixin_backend)

    def _get_resource_attributes(self, attrs):
        '''
        Gets the attributes required to render occi compliant compute
        resource information.
        '''
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

    def _register_os_mixins(self, os_mixin_backend, ctx):
        '''
        Register images as OsTemplate mixins from
        information retrieved from glance (shared and user-specific).
        '''
        template_schema = 'http://schemas.openstack.org/template/os#'
        os_schema = 'http://schemas.ogf.org/occi/infrastructure#os_tpl'

        image_service = image.get_default_image_service()

        # L8R: now the API allows users to supply RAM and Kernel images
        # can this filter be done via the glance filters?
        # filters = {'container_format': 'saving', 'disk_format': ''}
        # ovf, bare, ami
        # raw, vhd, vmdk, vdi, iso, qcow2, ami
        # not aki, ari
        # note possibly large list where there are many images
        images = image_service.detail(ctx)
        filter_kernel_and_ram_images = \
                                FLAGS.get("filter_kernel_and_ram_images", True)

        for img in images:
            # If the image is a kernel or ram one
            # and we're not to filter them out then register it.
            if ((img['container_format'] or img['disk_format']) \
                    in ('ari', 'aki')) and filter_kernel_and_ram_images:
                LOG.warn('Not registering kernel/RAM image.')
                continue

            os_template = templates.OsTemplate(
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

    def _register_security_mixins(self, ctx):
        '''
        Registers security groups as security mixins
        '''
        # get a listing of all security groups for the user
        # map a security group to a mixin
        # when a security mixin is supplied with the provision request
        # that's the security group to use with the VM

        self.compute_api.ensure_default_security_group(ctx)
        groups = db.security_group_get_by_project(ctx, ctx.project_id)

        for group in groups:
            sec_grp_id = group.id
            g_name = group.name
            if g_name.strip().find(' ') >= 0:
                raise Exception()

            sec_mix = occi_future.SecurityGroupMixin(
                term=g_name,
                scheme=
                'http://schemas.openstack.org/infrastructure/security/group#',
                sec_grp_id=sec_grp_id,
                related=[occi_future.SEC_GROUP],
                attributes=None,
                title=group.name,
                location='/' + group.name + '/')

            self.register_backend(sec_mix, backend.MixinBackend())

    def _register_occi_infra(self):
        '''
        Registers the OCCI infrastructure resources to ensure compliance
        with GFD184
        '''
        compute_backend = computeresource.ComputeBackend()

        if self.net_manager == "quantum":
            network_backend = networkresource.QuantumNetworkBackend()
        elif self.net_manager == "nova":
            network_backend = networkresource.NetworkBackend()
            networkinterface_backend = networklink.NetworkInterfaceBackend()
            ipnetwork_backend = networkresource.IpNetworkBackend()
            ipnetworking_backend = networklink.IpNetworkInterfaceBackend()
        else: raise Exception()

        storage_backend = storageresource.StorageBackend()
        storage_link_backend = storagelink.StorageLinkBackend()
#        sec_rule_backend = ruleresource.SecurityRuleBackend()
#        os_actions_backend = os_actions.OsComputeActionBackend()

        # register kinds with backends
        self.register_backend(infrastructure.COMPUTE, compute_backend)
        self.register_backend(infrastructure.START, compute_backend)
        self.register_backend(infrastructure.STOP, compute_backend)
        self.register_backend(infrastructure.RESTART, compute_backend)
        self.register_backend(infrastructure.SUSPEND, compute_backend)

        self.register_backend(infrastructure.NETWORK, network_backend)
        self.register_backend(infrastructure.UP, network_backend)
        self.register_backend(infrastructure.DOWN, network_backend)
        self.register_backend(infrastructure.NETWORKINTERFACE,
                                          networkinterface_backend)
        self.register_backend(infrastructure.IPNETWORK, ipnetwork_backend)
        self.register_backend(infrastructure.IPNETWORKINTERFACE,
                                          ipnetworking_backend)

        self.register_backend(infrastructure.STORAGE, storage_backend)
        self.register_backend(infrastructure.ONLINE, storage_backend)
        self.register_backend(infrastructure.OFFLINE, storage_backend)
        self.register_backend(infrastructure.BACKUP, storage_backend)
        self.register_backend(infrastructure.SNAPSHOT, storage_backend)
        self.register_backend(infrastructure.RESIZE, storage_backend)
        self.register_backend(infrastructure.STORAGELINK, storage_link_backend)

    def _register_occi_extensions(self):
        '''
        Register OCCI extensions contained within the 'extension' package.
        '''
        #EXTENSIONS is a list of hasmaps. The hashmap contains the handler.
        #The hashmap contains a list of categories to be handled by the handler
        for extn in extensions.EXTENSIONS:
            #miaow! kittens, kittens, kittens!
            for ext in extn:
                for cat in ext['categories']:
                    self.register_backend(cat, ext['handler'])
