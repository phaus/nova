'''
Created on Jan 11, 2012

@author: openstack
'''

from nova import image
from nova import test
from nova import wsgi
from nova.api.occi import wsgi as occi_wsgi
from nova.api.occi import extensions
from nova.tests.api import occi


class TestOcciWsgiApp(test.TestCase):

    def setUp(self):
        super(TestOcciWsgiApp, self).setUp()

        # setup img service...
        self.stubs.Set(image, 'get_default_image_service',
                       occi.fake_get_default_image_service)

    #--------------------------------------------------------- Test for success

    def test_occi_app_for_success(self):
        '''
        test constructor...
        '''
        occi_wsgi.OCCIApplication()

    #--------------------------------------------------------- Test for failure

    #---------------------------------------------------------- Test for sanity

    def test_occi_app_for_sanity(self):
        '''
        test for sanity...
        '''
        app = occi_wsgi.OCCIApplication()
        self.assertTrue(isinstance(app, wsgi.Application),
                        'OCCI WSGI app needs to be derived frrom wsgi.App')

        # check if all resource mixins are present...
        i = 0
        types = ['m1.xlarge', 'm1.medium', 'm1.tiny', 'm1.small', 'm1.large']
        for mixin in app.registry.get_categories():
            if isinstance(mixin, extensions.ResourceTemplate):
                self.assertTrue(mixin.term in types)
                scheme = 'http://schemas.openstack.org/template/resource#'
                self.assertEquals(scheme, mixin.scheme)
                i += 1
        self.assertTrue(i, len(types))

        # make a call so OS templates get filled
        environ = {'SERVER_NAME': 'localhost',
                   'SERVER_PORT': '8080',
                   'PATH_INFO': '/',
                   'REQUEST_METHOD': 'GET',
                   'nova.context': None}
        app(environ, occi.fake_response)

        # check for OS mixins...
        i = 0
        images = ['fakeimage7', 'fakeimage6', 'fakeimage123456']
        for mixin in app.registry.get_categories():
            if isinstance(mixin, extensions.OsTemplate):
                self.assertTrue(mixin.term in images)
                scheme = 'http://schemas.openstack.org/template/os#'
                self.assertEquals(scheme, mixin.scheme)
                i += 1
        self.assertTrue(i, len(images))
