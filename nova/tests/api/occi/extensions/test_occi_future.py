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
from nova import db
from nova import flags
from nova import test

from nova.api.occi.extensions import occi_future
from nova.api.occi import registry
from nova.scheduler import driver as scheduler_driver
from nova.tests.api import occi

from occi.core_model import Entity


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


class TestOcciSecurityGroupBackend(test.TestCase):

    def setUp(self):
        super(TestOcciSecurityGroupBackend, self).setUp()

        # create sec context
        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id,
                                              self.project_id,
                                              is_admin=True)

        # OCCI related setup
        self.category = occi_future.UserSecurityGroupMixin(
                term='my_grp',
                scheme='http://www.mystuff.com/mygroup#',
                related=[occi_future.SEC_GROUP],
                attributes=None,
                location='/security/my_grp/')

        self.extras = {'nova_ctx': self.context,
                       'registry': registry.OCCIRegistry()}

        self.class_under_test = occi_future.SecurityGroupBackend()

    #---------------------------------------------------------- Test for succes

    def test_create_for_success(self):
        self.class_under_test.init_sec_group(self.category, self.extras)
#
#    def test_retrieve_for_success(self):
#        self.class_under_test.retrieve(self.entity, self.extras)

#    def test_update_for_success(self):
#        self.fail('To be implemented...')
#
#    def test_replace_for_success(self):
#        self.fail('To be implemented...')
#
    def test_delete_for_success(self):
        self.stubs.Set(db, 'security_group_get_by_name',
                       occi.fake_db_security_group_get_by_name)
        self.stubs.Set(db, 'security_group_in_use',
                       occi.fake_db_security_group_in_use)

        self.class_under_test.destroy(self.category, self.extras)

#    def test_action_for_success(self):


#    #-------------------------------------------------------- Test for Failure
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
#    #--------------------------------------------------------- Test for Sanity
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

class TestOcciSecurityRuleBackend(test.TestCase):

    def setUp(self):
        super(TestOcciSecurityRuleBackend, self).setUp()

        # create sec context
        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id,
                                              self.project_id,
                                              is_admin=True)

        # OCCI related setup
        self.category = occi_future.UserSecurityGroupMixin(
                term='my_grp',
                scheme='http://www.mystuff.com/mygroup#',
                related=[occi_future.SEC_GROUP],
                attributes=None,
                location='/security/my_grp/')

        self.entity = Entity("123", 'A test entity', None,
                             [self.category])
        self.entity.attributes['occi.core.id'] = '123123123'
        self.entity.attributes['occi.network.security.protocol'] = 'tcp'
        self.entity.attributes['occi.network.security.to'] = '22'
        self.entity.attributes['occi.network.security.from'] = '22'
        self.entity.attributes['occi.network.security.range'] = '0.0.0.0/24'
        self.entity.links = []
        self.extras = {'nova_ctx': self.context,
                       'registry': registry.OCCIRegistry()}

        self.class_under_test = occi_future.SecurityRuleBackend()

    #---------------------------------------------------------- Test for succes

    def test_create_for_success(self):
        self.stubs.Set(db, 'security_group_get_by_name',
                       occi.fake_db_security_group_get_by_name)
        self.class_under_test.create(self.entity, self.extras)

    def test_delete_for_success(self):
        self.stubs.Set(db, 'security_group_rule_get',
                       occi.fake_db_security_group_rule_get)
        self.stubs.Set(db, 'security_group_get',
                       occi.fake_db_security_group_get)
        self.stubs.Set(db, 'security_group_rule_destroy',
                       occi.fake_db_security_group_rule_destroy)
        self.stubs.Set(compute.API, 'trigger_security_group_rules_refresh',
                       occi.fake_compute_trigger_security_group_rules_refresh)

        self.class_under_test.delete(self.entity, self.extras)

#    #-------------------------------------------------------- Test for Failure
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
#    #--------------------------------------------------------- Test for Sanity
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
