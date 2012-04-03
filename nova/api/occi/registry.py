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

from occi import registry
from nova.api.occi.extensions import occi_future


class OCCIRegistry(registry.NonePersistentRegistry):
    '''
    Simple SSF registry for OpenStack.
    '''

    def add_resource(self, key, resource, extras):
        '''
        Ensures OpenStack keys are used as resource identifiers and sets
        user id and tenant id
        '''
        key = resource.kind.location + resource.attributes['occi.core.id']
        resource.identifier = key

        if extras:
            resource.extras = {}
            resource.extras['user_id'] = extras['nova_ctx'].user_id
            resource.extras['project_id'] = extras['nova_ctx'].project_id

        super(OCCIRegistry, self).add_resource(key, resource, extras)

    def delete_mixin(self, mixin, extras):
        import ipdb
        ipdb.set_trace()
        if hasattr(mixin, 'related') and \
                                    occi_future.SEC_GROUP in mixin.related:
            be = self.get_backend(mixin, extras)
            be.destroy(mixin, extras)

        super(OCCIRegistry, self).delete_mixin(mixin, extras)

    def set_backend(self, category, backend, extras):
        '''
        Assigns user id and tenant id to user defined mixins
        '''
        if extras:
            category.extras = {}
            category.extras['user_id'] = extras['nova_ctx'].user_id
            category.extras['project_id'] = extras['nova_ctx'].project_id

        if hasattr(category, 'related') and \
                                    occi_future.SEC_GROUP in category.related:
            be = occi_future.SecurityGroupBackend()
            backend = be
            be.init_sec_group(category, extras)

        super(OCCIRegistry, self).set_backend(category, backend, extras)

    def get_categories(self, extras):
        result = []
        context = self._get_ctx(extras)
        for item in self.BACKENDS.keys():
            if item.extras == None:
                # core occi categories that visible to all
                result.append(item)
            elif context is not None and self._is_auth(context, item):
                # categories visible to this user!
                result.append(item)
            else:
                continue

        return result

    def _is_auth(self, context, item):
        return \
            (context.user_id == item.extras['user_id']) and \
            (context.project_id == item.extras['project_id'])

    def _get_ctx(self, extras):
        context = None
        if extras:
            context = extras['nova_ctx']
        return context

    def get_category(self, path, extras):
        context = self._get_ctx(extras)

        for category in self.BACKENDS.keys():
            if category.extras == None and category.location == path:
                return category
            elif category.extras is not None \
                and self._is_auth(context, category) \
                and category.location == path:
                return category
        return None

    def get_resource(self, key, extras):
        context = self._get_ctx(extras)

        resource = self.RESOURCES[key]

        if resource.extras == None:
            return resource
        elif resource.extras is not None and self._is_auth(context, resource):
            return resource

    def get_resource_keys(self, extras):
        import ipdb
        ipdb.set_trace()
        return self.RESOURCES.keys()
