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

from nova import image
from occi import core_model
from occi.extensions import infrastructure

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

def fake_get_floating_ip_pools(meh, context):
    return [{'name': 'test1'}, {'name': 'test2'}, ]

def fake_get_instance_nw_info(meh, ctx, instance):
    return []

def fake_get_resource(meh, key, extras):
    name = 'DEFAULT_NETWORK'

    net_attrs = {
        'occi.core.id': name,
        'occi.network.vlan': '',
        'occi.network.label': 'public',
        'occi.network.state': 'up',
        'occi.network.address': '',
        'occi.network.gateway': '',
        'occi.network.allocation': '',
    }

    default_network = core_model.Resource(name, infrastructure.NETWORK, \
                        [infrastructure.IPNETWORK], [],
                        'This is the network all VMs are attached to.',
                        'Default Network')

    default_network.attributes = net_attrs

    return default_network

def fake_security_group_get_by_project(ctx, proj_id):
    return [{'name':'grp1'}, {'name':'grp2'}]

def fake_compute_get(meh, ct, uid):
    instance = {}
    instance['vm_state'] = 'active'
    return instance

def fake_compute_occi_get(meh, entity, extras):
    entity = core_model.Entity("123", 'A test entity', None, [])
    entity.attributes['occi.core.id'] = '123-123-123'
    entity.links = []
    entity.actions = [infrastructure.START,
                          infrastructure.STOP,
                          infrastructure.SUSPEND, \
                          infrastructure.RESTART]
    return entity

def fake_compute_delete(meh, ctx, vol):
    pass

def fake_compute_unpause(meh, context, instance):
    pass

def fake_compute_resume(meh, context, instance):
    pass

def fake_compute_suspend(meh, context, instance):
    pass

def fake_compute_reboot(meh, context, instance, type):
    pass

def fake_compute_pause(meh, context, instance):
    pass

def fake_storage_get(meh, ct, uid):
    instance = {}
    instance['id'] = '321321'
    instance['size'] = '1.0'
    instance['status'] = 'available'
    return instance

def fake_storage_delete(meh, ctx, vol):
    pass
