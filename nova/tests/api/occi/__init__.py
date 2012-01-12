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

from nova import image


def fake_get_image_service(context, image_href):
    '''
    Make sure fake image service is used.
    '''
    tmp = image.fake.FakeImageService(), image_href
    return tmp


def fake_get_default_image_service():
    '''
    Fake get default image_service...
    '''
    return image.fake.FakeImageService()


def fake_show(meh, context, id):
    '''
    Returns a single image...
    '''
    return {'id': id,
            'container_format': 'ami',
            'properties': {
                           'kernel_id': id,
                           'ramdisk_id': id}
            }

def fake_response(arg0, arg1):
    '''
    Fake WSGI response method
    '''
    pass
