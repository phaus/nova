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
from nova.compute import instance_types
from nova.network import api as net_api
from nova.api.occi import extensions
from nova.api.occi import registry
from nova.api.occi.extensions import occi_future
from nova.api.occi.compute import templates
from nova.api.occi.compute import computeresource
from nova.api.occi.network import networklink
from nova.api.occi.network import networkresource
from nova.api.occi.storage import storagelink
from nova.api.occi.storage import storageresource

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

MIXIN_BACKEND = backend.MixinBackend()


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
                                registry=registry.OCCIRegistry())
#        self.compute_api = API()
        self.net_manager = FLAGS.get("net_manager", "nova")
        self.no_default_network = True
        self._register_occi_infra()
        self._register_occi_extensions()

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

        storage_backend = storageresource.StorageBackend()
        storage_link_backend = storagelink.StorageLinkBackend()

        # register kinds with backends
        self.register_backend(infrastructure.COMPUTE, compute_backend)
        self.register_backend(infrastructure.START, compute_backend)
        self.register_backend(infrastructure.STOP, compute_backend)
        self.register_backend(infrastructure.RESTART, compute_backend)
        self.register_backend(infrastructure.SUSPEND, compute_backend)
        self.register_backend(templates.OS_TEMPLATE, MIXIN_BACKEND)
        self.register_backend(templates.RES_TEMPLATE, MIXIN_BACKEND)

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
        extras = {'nova_ctx': environ['nova.context']}

        # When the API boots the network services may not be started.
        # The call to the service is a sync RPC over rabbitmq and will block.
        # We must register the network only once and once all services are
        # available. Hence we perform the registration once here.
        if self.no_default_network:
            self._register_default_network()

        # register/refresh openstack images
        self._refresh_os_mixins(extras)
        # register/refresh openstack instance types (flavours)
        self._refresh_resource_mixins(extras)
        # register/refresh the openstack security groups as Mixins
        self._refresh_security_mixins(extras)
        # register/refresh the openstack floating IP pools as Mixins
        self._refresh_floating_ip_pool_mixins(extras)

        return self._call_occi(environ, response, nova_ctx=extras['nova_ctx'],
                                                        registry=self.registry)

    def _register_default_network(self):
        '''
        By default nova attaches a compute resource to a network.
        In the OCCI model this is represented as a Network resource.
        This method constructs that Network resource.
        '''
        #TODO(dizz): verify behaviour with quantum backend
        #      i.e. cover the case where there are > 1 networks
        name = 'DEFAULT_NETWORK'
        LOG.info('Registering default network with web app.')
        show_default_net_config = FLAGS.get("show_default_net_config", False)

        net_attrs = {
            'occi.core.id': name,
            'occi.network.vlan': '',
            'occi.network.label': 'public',
            'occi.network.state': 'up',
            'occi.network.address': '',
            'occi.network.gateway': '',
            'occi.network.allocation': '',
        }

        if not show_default_net_config:
            net_attrs = self._get_net_info(net_attrs)

        default_network = core_model.Resource(name, infrastructure.NETWORK, \
                        [infrastructure.IPNETWORK], [],
                        'This is the network all VMs are attached to.',
                        'Default Network')
        default_network.attributes = net_attrs

        self.registry.add_resource(name, default_network, None)

        self.no_default_network = False

    def _get_net_info(self, net_attrs):
        ctx = context.get_admin_context()

        network_api = net_api.API()
        networks = network_api.get_all(ctx)

        if len(networks) > 1:
            LOG.warn('There is more that one network.')
            LOG.warn('Using the first network: id' \
                                                + str(networks[0]['id']))

        net_attrs['occi.network.address'] = networks[0]['cidr']
        net_attrs['occi.network.label'] = 'public'
        net_attrs['occi.network.state'] = 'up'
        net_attrs['occi.network.gateway'] = networks[0]['gateway'],
        net_attrs['occi.network.allocation'] = 'dhcp'

        return net_attrs

    def _refresh_os_mixins(self, extras):
        '''
        Register images as OsTemplate mixins from
        information retrieved from glance (shared and user-specific).
        '''
        template_schema = 'http://schemas.openstack.org/template/os#'
        image_service = image.get_default_image_service()

        images = image_service.detail(extras['nova_ctx'])
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
                                scheme=template_schema,
                                os_id=img['id'],
                                related=[templates.OS_TEMPLATE],
                                attributes=None,
                                title='This is an OS ' + img['name'] + \
                                                            ' VM image',
                                location='/' + img['name'] + '/')

            LOG.debug('Registering an OS image type as: ' \
                                                    + str(os_template))

            try:
                self.registry.get_backend(os_template, extras)
            except AttributeError:
                self.register_backend(os_template, MIXIN_BACKEND)

    def _refresh_resource_mixins(self, extras):
        '''
        Register the flavors as ResourceTemplates to which the user has access.
        '''
        template_schema = 'http://schemas.openstack.org/template/resource#'
        os_flavours = instance_types.get_all_types()

        for itype in os_flavours:
            resource_template = templates.ResourceTemplate(
                term=itype,
                scheme=template_schema,
                related=[templates.RES_TEMPLATE],
                attributes=self._get_resource_attributes(os_flavours[itype]),
                title='This is an openstack ' + itype + ' flavor.',
                location='/' + itype + '/')
            LOG.debug('Registering an OpenStack flavour/instance type as: ' + \
                                                        str(resource_template))

            try:
                self.registry.get_backend(resource_template, extras)
            except AttributeError:
                self.register_backend(resource_template, MIXIN_BACKEND)

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

        #This is hardcoded atm - might be good to have it configurable
        attrs = {
                 'occi.compute.cores': 'immutable',
                 'occi.compute.memory': 'immutable',
                 'org.openstack.compute.swap': 'immutable',
                 'org.openstack.compute.storage.root': 'immutable',
                 'org.openstack.compute.storage.ephemeral': 'immutable',
                 }
        return attrs

    def _refresh_security_mixins(self, extras):
        '''
        Registers security groups as security mixins
        '''
        # ensures that preexisting openstack security groups are
        # added and only once.
        # collect these and add them to an exclusion list so they're
        # not created again when listing non-user-defined sec. groups
        excld_grps = []
        for cat in self.registry.get_categories(extras):
            if isinstance(cat, core_model.Mixin) and \
                                    occi_future.SEC_GROUP in cat.related:
                excld_grps.append(cat.term)

        groups = db.security_group_get_by_project(extras['nova_ctx'],
                                                extras['nova_ctx'].project_id)
        for group in groups:
            if group['name'] not in excld_grps:
                sec_mix = occi_future.UserSecurityGroupMixin(
                term=group['name'],
                scheme=
                'http://schemas.openstack.org/infrastructure/security/group#',
                related=[occi_future.SEC_GROUP],
                attributes=None,
                title=group['name'],
                location='/security/' + group['name'] + '/')
                try:
                    self.registry.get_backend(sec_mix, extras)
                except AttributeError:
                    self.register_backend(sec_mix, MIXIN_BACKEND)

    def _refresh_floating_ip_pool_mixins(self, extras):

        network_api = net_api.API()
        pools = network_api.get_floating_ip_pools(extras['nova_ctx'])

        for pool in pools:
            pool_mixin = core_model.Mixin(
         term=pool['name'],
         scheme='http://schemas.openstack.org/instance/network/pool/floating#',
         related=[],
         attributes=None,
         title="This is a floating IP pool",
         location='/network/pool/floating/')
            try:
                self.registry.get_backend(pool_mixin, extras)
            except AttributeError:
                self.register_backend(pool_mixin, MIXIN_BACKEND)
