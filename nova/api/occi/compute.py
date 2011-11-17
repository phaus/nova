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

import ipdb

#TODO fix to OCCI
from nova.api.openstack import wsgi
#TODO not need, just here for complete example
from nova.api.openstack import xmlutil

class HeadersSerializer(wsgi.ResponseHeadersSerializer):
    pass


class ServerXMLSerializer(xmlutil.XMLTemplateSerializer):
    pass


class ServerXMLDeserializer(wsgi.MetadataXMLDeserializer):
    pass


class Controller(object):
    """ The Compute API base controller class for the OCCI API """
    def __init__(self):
        print "init me!"
    
    def index(self):
        print "index me!"
        return "index me!"
    
    def detail(self):
        print "detail me!"
        return "detail me!"
    
    def show(self):
        ipdb.set_trace()
        print "show me!"
        return "show me!"
    
    def create(self):
        ipdb.set_trace()
        print "create me!"
        return "create me!"
    
    def action(self):
        print "action me!"
        return "action me!"
    
    def delete(self):
        print "delete me!"
        return "delete me!"


#def create_resource():
#    print "creating compute controller"
#    headers_serializer = HeadersSerializer()
#    body_serializers = {'application/xml': ServerXMLSerializer()}
#    serializer = wsgi.ResponseSerializer(body_serializers, headers_serializer)
#    body_deserializers = {'application/xml': ServerXMLDeserializer()}
#    deserializer = wsgi.RequestDeserializer(body_deserializers)
#    return wsgi.Resource(Controller(), deserializer, serializer)

def create_controller():
    return Controller()
