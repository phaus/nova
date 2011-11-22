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

from webob import exc

from base_controller import BaseController

from occi import workflow

from nova.api.openstack import wsgi


class Controller(BaseController):
    """ The query API base controller class for the OCCI API """
    def __init__(self):
        super(Controller, self).__init__()
        print "init me!\n"
    
    def get(self, req):
        # retrieve (filter)
        try:
            
            categories, attributes = self.parse_filter(req)
            result = workflow.filter_categories(categories, self.registry)
            self.render_categories(req, result)
            
        except AttributeError as attr:
            raise exc.HTTPBadRequest(explanation=str(attr)) #HTTPError(400, str(attr))
    
    def index(self, req):
        print "index me!\n"
        msg = "index me!\n"
        raise exc.HTTPNotImplemented(explanation=msg)
    
    def detail(self, req):
        print "detail me!\n"
        msg = "detail me!\n"
        raise exc.HTTPNotImplemented(explanation=msg)
    
    def show(self, req):
        print "show me!\n"
        msg = "show me!\n"
        raise exc.HTTPNotImplemented(explanation=msg)
    
    def create(self, req):
        print "create me!\n"
        msg = "create me!\n"
        raise exc.HTTPNotImplemented(explanation=msg)
    
    def action(self, req):
        print "action me!\n"
        msg = "action me!\n"
        raise exc.HTTPNotImplemented(explanation=msg)
    
    def delete(self, req):
        print "delete me!\n"
        msg = "delete me!\n"
        raise exc.HTTPNotImplemented(explanation=msg)


def create_controller():
    return wsgi.Resource(Controller())