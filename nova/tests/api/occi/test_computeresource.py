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
from nova import compute
from nova import flags
from nova import image
from nova import rpc
from nova import test

from nova.image import fake
from nova.api.occi.compute import computeresource
from nova.api.occi.compute import templates
from nova.api.occi import registry
from nova.network import api as net_api
from nova.scheduler import driver as scheduler_driver
from nova.tests.api import occi

from occi.core_model import Entity
from occi.extensions import infrastructure


FLAGS = flags.FLAGS

def fake_rpc_cast(context, topic, msg, do_cast=True):
    '''
    The RPC cast wrapper so scheduler returns instances...
    '''
    if topic == FLAGS.scheduler_topic and \
            msg['method'] == 'run_instance':
        request_spec = msg['args']['request_spec']
        scheduler = scheduler_driver.Scheduler
        num_instances = request_spec.get('num_instances', 1)
        instances = []
        for x in xrange(num_instances):
            instance = scheduler().create_instance_db_entry(
                    context, request_spec)
            encoded = scheduler_driver.encode_instance(instance)
            instances.append(encoded)
        return instances
    else:
        pass


class TestOcciComputeResource(test.TestCase):

    def setUp(self):
        super(TestOcciComputeResource, self).setUp()

        # create sec context
        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id,
                                              self.project_id,
                                              is_admin=True)

        # setup image service...
        self.stubs.Set(image, 'get_image_service', occi.fake_get_image_service)
        self.stubs.Set(fake._FakeImageService, 'show', occi.fake_show)
        self.stubs.Set(rpc, 'cast', fake_rpc_cast)
        self.stubs.Set(net_api.API, 'get_instance_nw_info',
                       occi.fake_get_instance_nw_info)
        self.stubs.Set(registry.OCCIRegistry, 'get_resource',
                       occi.fake_get_resource)
        self.stubs.Set(compute.API, 'get', occi.fake_compute_get)
        self.stubs.Set(compute.API, 'delete', occi.fake_storage_delete)

        # OCCI related setup
        self.os_template = templates.OsTemplate(
                                'http://schemas.openstack.org/template/os#',
                                'foo', '1')
        self.resource_template = templates.ResourceTemplate(
                            'http://schemas.openstack.org/template/resource#',
                            'm1.small')

        self.entity = Entity("123", 'A test entity', None,
                             [self.os_template, self.resource_template])
        self.entity.attributes['occi.core.id'] = '123-123-123'
        self.entity.links = []
        self.extras = {'nova_ctx': self.context,
                       'registry': registry.OCCIRegistry()}

        self.class_under_test = computeresource.ComputeBackend()

    #---------------------------------------------------------- Test for succes

    def test_create_for_success(self):
        '''
        Try to create an OCCI entity.
        '''
        self.class_under_test.create(self.entity, self.extras)

    def test_retrieve_for_success(self):
        self.class_under_test.retrieve(self.entity, self.extras)

#    def test_update_for_success(self):
#        self.fail('To be implemented...')
#
#    def test_replace_for_success(self):
#        self.fail('To be implemented...')

    def test_delete_for_success(self):
        self.class_under_test.delete(self.entity, self.extras)

    def test_action_for_success(self):
        self.stubs.Set(computeresource.ComputeBackend, 'retrieve',
                                                occi.fake_compute_occi_get)
        self.stubs.Set(compute.API, 'unpause', occi.fake_compute_unpause)
        self.stubs.Set(compute.API, 'resume', occi.fake_compute_resume)
        self.stubs.Set(compute.API, 'suspend', occi.fake_compute_suspend)
        self.stubs.Set(compute.API, 'reboot', occi.fake_compute_reboot)
        self.stubs.Set(compute.API, 'pause', occi.fake_compute_pause)


        self.entity.attributes['occi.compute.state'] = 'inactive'
        self.entity.actions = [infrastructure.START]
        self.class_under_test.action(self.entity, infrastructure.START,
                                                                self.extras)

        self.entity.attributes['occi.compute.state'] = 'active'
        self.entity.actions = [infrastructure.STOP]
        self.class_under_test.action(self.entity, infrastructure.STOP,
                                                                self.extras)

        self.entity.attributes['occi.compute.state'] = 'active'
        self.entity.attributes['method'] = 'graceful'
        self.entity.actions = [infrastructure.RESTART]
        self.class_under_test.action(self.entity, infrastructure.RESTART,
                                                                self.extras)

        self.entity.attributes['occi.compute.state'] = 'active'
        self.entity.actions = [infrastructure.SUSPEND]
        self.class_under_test.action(self.entity, infrastructure.SUSPEND,
                                                                self.extras)

        self.stubs.UnsetAll()

#    #--------------------------------------------------------- Test for Failure
#
#    def test_create_for_failure(self):
#        self.fail('To be implemented...')
#
#    def test_retrieve_for_failure(self):
#        self.fail('To be implemented...')
#
#    def test_update_for_failure(self):
#        self.fail('To be implemented...')
#
#    def test_replace_for_failure(self):
#        self.fail('To be implemented...')
#
#    def test_delete_for_failure(self):
#        self.fail('To be implemented...')
#
#    def test_action_for_failure(self):
#        self.fail('To be implemented...')
#
#    #---------------------------------------------------------- Test for Sanity
#
#    def test_create_for_sanity(self):
#        self.fail('To be implemented...')
#
#    def test_retrieve_for_sanity(self):
#        self.fail('To be implemented...')
#
#    def test_update_for_sanity(self):
#        self.fail('To be implemented...')
#
#    def test_replace_for_sanity(self):
#        self.fail('To be implemented...')
#
#    def test_delete_for_sanity(self):
#        self.fail('To be implemented...')
#
#    def test_action_for_sanity(self):
#        self.fail('To be implemented...')
