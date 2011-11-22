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

import sys

import webob

from occi import VERSION, workflow
from occi.registry import NonePersistentRegistry as NonPersistentRegistry

CONTENT_TYPE = 'Content-Type'
ACCEPT = 'Accept'

class BaseController(object):
    
    def __init__(self):
        # This ensures that at least one registry is loaded in case initialize
        # is not called for some reason...
        self.registry = NonPersistentRegistry()
        
    def extract_http_data(self, req):
        '''
        Extracts all necessary information from the HTTP envelop. Minimize the
        data which is carried around inside of the service. Also ensures that
        the names are always equal - When deployed in Apache the names of the
        Headers change.
        '''
        heads = {}
        headers = req.headers
        if 'Category' in headers:
            heads['Category'] = headers['Category']
        if 'X-Occi-Attribute' in headers:
            heads['X-OCCI-Attribute'] = headers['X-Occi-Attribute']
        if 'X-Occi-Location' in headers:
            heads['X-OCCI-Location'] = headers['X-Occi-Location']
        if 'Link' in headers:
            heads['Link'] = headers['Link']
        if req.body is not '':
            body = req.body.strip()
        else:
            body = ''

        return heads, body
    
    def get_renderer(self, req, content_type):
        '''
        Returns the proper rendering parser.

        content_type -- String with either either Content-Type or Accept.
        '''
        try:
            return self.registry.get_renderer(req.headers[content_type])
        except KeyError:
            return self.registry.get_renderer(self.registry.get_default_type())
    
    def parse_action(self, req):
        '''
        Retrieves the Action which was given in the request.
        '''
        headers, body = self.extract_http_data(req)
        rendering = self.get_renderer(req, CONTENT_TYPE)

        action = rendering.to_action(headers, body)

        return action
    
    def parse_filter(self, req):
        '''
        Retrieve any attributes or categories which where provided in the
        request for filtering.
        '''
        headers, body = self.extract_http_data(req)

        attr = 'X-OCCI-Attribute'
        if  attr not in headers and 'Category' not in headers and body == '':
            return [], {}

        rendering = self.get_renderer(req, CONTENT_TYPE)

        categories, attributes = rendering.get_filters(headers, body)

        return categories, attributes
    
    def parse_entity(self, req, def_kind=None):
        '''
        Retrieves the entity which was rendered within the request.

        def_kind -- Indicates if the request can be incomplete (False).
        '''
        headers, body = self.extract_http_data(req)
        rendering = self.get_renderer(req, CONTENT_TYPE)

        entity = rendering.to_entity(headers, body, def_kind)

        return entity
    
    def parse_entities(self, req):
        '''
        Retrieves a set of entities which was rendered within the request.
        '''
        headers, body = self.extract_http_data(req)
        rendering = self.get_renderer(req, CONTENT_TYPE)

        entities = rendering.to_entities(headers, body)

        return entities
    
    def parse_mixins(self, req):
        '''
        Retrieves a mixin from a request.
        '''
        headers, body = self.extract_http_data(req)
        rendering = self.get_renderer(req, CONTENT_TYPE)

        mixin = rendering.to_mixins(headers, body)

        return mixin
    
    #---------- WILL NOT WORK AS-IS ------------------
    
    def response(self, status, mime_type, headers, body='OK'):
        '''
        Will create a response and send it to the client.

        status -- The status code.
        mime_type -- Sets the Content-Type of the response.
        headers -- The HTTP headers.
        body -- The text for the body (default: ok).
        '''
        
        response = webob.Response()
        
        
        self.set_header('Server', VERSION)
        self.set_header('Content-Type', mime_type)
        self.set_status(status)
        if headers is not None:
            for item in headers.keys():
                self._headers[item] = headers[item]
        self.write(body)
        self.finish('\n')
        
    def render_entity(self, entity):
        '''
        Renders a single entity to the client.

        entity -- The entity which should be rendered.
        '''
        rendering = self.get_renderer(ACCEPT)

        headers, body = rendering.from_entity(entity)

        self.response(200, rendering.mime_type, headers, body)
        
    def render_entities(self, entities, key):
        '''
        Renders a list of entities to the client.

        entities -- The entities which should be rendered.
        '''
        rendering = self.get_renderer(ACCEPT)

        headers, body = rendering.from_entities(entities, key)

        self.response(200, rendering.mime_type, headers, body)
        
    def render_categories(self, req, categories):
        '''
        Renders a list of categories to the client.

        categories -- The categories which should be rendered.
        '''
        rendering = self.get_renderer(req, ACCEPT)

        headers, body = rendering.from_categories(categories)
    
        #self.response(200, rendering.mime_type, headers, body)
