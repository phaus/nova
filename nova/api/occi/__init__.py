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

"""
WSGI middleware for OpenStack API controllers.
"""

import routes
import webob.dec
import webob.exc

from nova.api.occi import compute
from nova.api.openstack import faults
from nova.api.openstack import wsgi

from nova import flags
from nova import log as logging
from nova import wsgi as base_wsgi


LOG = logging.getLogger('nova.api.occi')
#FLAGS = flags.FLAGS
#flags.DEFINE_bool('allow_admin_api',
#    False,
#    'When True, this API service will accept admin operations.')
#flags.DEFINE_bool('allow_instance_snapshots',
#    True,
#    'When True, this API service will permit instance snapshot operations.')


class FaultWrapper(base_wsgi.Middleware):
    """Calls down the middleware stack, making exceptions into faults."""

    @webob.dec.wsgify(RequestClass=wsgi.Request)
    def __call__(self, req):
        try:
            return req.get_response(self.application)
        except Exception as ex:
            LOG.exception(_("Caught error: %s"), unicode(ex))
            exc = webob.exc.HTTPInternalServerError()
            return faults.Fault(exc)


class APIMapper(routes.Mapper):
    def routematch(self, url=None, environ=None):
        if url is "":
            result = self._match("", environ)
            return result[0], result[1]
        return routes.Mapper.routematch(self, url, environ)

# Not needed
#class ProjectMapper(APIMapper):
#
#    def resource(self, member_name, collection_name, **kwargs):
#        if not ('parent_resource' in kwargs):
#            kwargs['path_prefix'] = '{project_id}/'
#        else:
#            parent_resource = kwargs['parent_resource']
#            p_collection = parent_resource['collection_name']
#            p_member = parent_resource['member_name']
#            kwargs['path_prefix'] = '{project_id}/%s/:%s_id' % (p_collection,
#                                                               p_member)
#        routes.Mapper.resource(self, member_name,
#                                     collection_name,
#                                     **kwargs)


class APIRouter(base_wsgi.Router):
    """
    Routes requests on the OCCI API to the appropriate controller
    and method.
    """

    @classmethod
    def factory(cls, global_config, **local_config):
        """Simple paste factory, :class:`nova.wsgi.Router` doesn't have one"""
        return cls()

    def __init__(self, ext_mgr=None):
        self.server_members = {}
        #mapper = ProjectMapper()
        #AE: we don't need the project mapper
        mapper = APIMapper()
        self._setup_routes(mapper)
        super(APIRouter, self).__init__(mapper)

    def _setup_routes(self, mapper):
        LOG.debug("setting up occi compute route: /compute")
        mapper.connect("occi", "/compute",
                    controller=compute.create_controller(), action='show')
        LOG.debug("done setting up occi route")
