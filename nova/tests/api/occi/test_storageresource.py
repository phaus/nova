'''
Created on Jan 11, 2012

@author: openstack
'''

from nova import context
from nova import test
from nova import flags
from nova import image
from nova import rpc

from nova.image import fake

from nova.api.occi.storage import storageresource
from nova.api.occi.compute import templates
from nova.api.occi import registry
from nova.network import api as net_api
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


class TestOcciStorageResource(test.TestCase):

    def setUp(self):
        super(TestOcciStorageResource, self).setUp()

        # create sec context
        self.user_id = 'fake'
        self.project_id = 'fake'
        self.context = context.RequestContext(self.user_id,
                                              self.project_id,
                                              is_admin=True)

        self.stubs.Set(registry.OCCIRegistry, 'get_resource',
                       occi.fake_get_resource)
        from nova import volume
        self.stubs.Set(volume.API, 'get', occi.fake_storage_get)
        self.stubs.Set(volume.API, 'delete', occi.fake_storage_delete)

        # OCCI related setup
        self.entity = Entity("123", 'A test entity', None, [])
        self.entity.attributes['occi.storage.size'] = '1.0'
        self.entity.attributes['occi.core.id'] = '321'
        self.reg = registry.OCCIRegistry()
        self.extras = {'nova_ctx': self.context,
                       'registry': self.reg}

        self.class_under_test = storageresource.StorageBackend()

    #---------------------------------------------------------- Test for succes

    def test_create_for_success(self):
        '''
        Try to create an OCCI entity.
        '''
        self.class_under_test.create(self.entity, self.extras)

    def test_retrieve_for_success(self):
        self.class_under_test.retrieve(self.entity, self.extras)
#
#    def test_update_for_success(self):
#        self.fail('To be implemented...')
#
#    def test_replace_for_success(self):
#        self.fail('To be implemented...')

    def test_delete_for_success(self):
        self.class_under_test.delete(self.entity, self.extras)
#
#    def test_action_for_success(self):
#        self.fail('To be implemented...')
#
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
