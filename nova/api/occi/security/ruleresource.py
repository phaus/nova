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

import random

from nova import log as logging
from nova import db
from occi import backend


#Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.securityrule')


class SecurityRuleBackend(backend.KindBackend):

    def create(self, entity, extras):
        # the group to add the rule to must exist
        # in OCCI-speak this means the mixin must be supplied with the request
        
        LOG.info('Creating a network security rule')
        
        sec_mixin_present = 0
        
        for mixin in entity.mixins:
            if mixin.scheme == 'http://schemas.ogf.org/occi/infrastructure/security/group#':
                sec_mixin_present = sec_mixin_present + 1
                sec_mixin = mixin
                break
        if not sec_mixin_present:
            raise Exception()
        if sec_mixin_present > 1:
            raise Exception()

        #TODO: validation of values
        sg_rule = {}
        sg_rule['id'] = random.randrange(0, 99999999) 
        entity.attributes['occi.core.id'] = str(sg_rule['id'])
        sg_rule['parent_group_id'] = sec_mixin.sec_grp_id
        sg_rule['protocol'] = (entity.attributes['occi.network.security.protocol']).lower()
        sg_rule['from_port'] = entity.attributes['occi.network.security.to']
        sg_rule['to_port'] = entity.attributes['occi.network.security.from']
        cidr = entity.attributes['occi.network.security.range']
        sg_rule['cidr'] = cidr if len(cidr) > 0 else '0.0.0.0/0'
        sg_rule['group'] = {}
        
#        if self._security_group_rule_exists(security_group, values):
#            msg = _('This rule already exists in group %s') % parent_group_id
#            raise exc.HTTPBadRequest(explanation=msg)

        db.security_group_rule_create(extras['nova_ctx'], sg_rule)

    
    def delete(self, entity, extras):
        
        LOG.info('Deleting a network security rule')
        #db.security_group_rule_destroy(extras['nova_ctx'],
        #                               entity.attributes['occi.core.id'])
        
#        self.compute_api.ensure_default_security_group(context)
#        try:
#            id = int(id)
#            rule = db.security_group_rule_get(context, id)
#        except ValueError:
#            msg = _("Rule id is not integer")
#            raise exc.HTTPBadRequest(explanation=msg)
#        except exception.NotFound:
#            msg = _("Rule (%s) not found") % id
#            raise exc.HTTPNotFound(explanation=msg)
#
#        group_id = rule.parent_group_id
#        self.compute_api.ensure_default_security_group(context)
#        security_group = db.security_group_get(context, group_id)
#
#        msg = _("Revoke security group ingress %s")
#        LOG.audit(msg, security_group['name'], context=context)
#
        
#        self.sgh.trigger_security_group_rule_destroy_refresh(
#            context, [rule['id']])
#        self.compute_api.trigger_security_group_rules_refresh(context,
#                                    security_group_id=security_group['id'])
        
        
