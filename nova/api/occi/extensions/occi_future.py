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

import random

from nova import log as logging
from nova import db
from nova import utils
from nova import flags
from nova.compute import API

from occi import core_model
from occi import backend

# TODO: Remove SSH Console and VNC Console once URI support is added to pyssf

#Hi I'm a logger, use me! :-)
LOG = logging.getLogger('nova.api.occi.backends.securityrule')

FLAGS = flags.FLAGS


####################### OCCI Candidate Spec Additions ########################
def get_extensions():
    return [
            {
             'categories': [CONSOLE_LINK, SSH_CONSOLE, VNC_CONSOLE],
             'handler': backend.KindBackend()
            },
            {
             'categories': [SEC_RULE],
             'handler': SecurityRuleBackend()
            },
           ]

# Console Link Extension
CONSOLE_LINK = core_model.Kind(
                        'http://schemas.ogf.org/infrastructure/compute#',
                        'console',
                        [core_model.Link.kind],
                        None,
                        'This is a link to the VMs console',
                        None,
                        '/compute/consolelink/')

# SSH Console Kind Extension
SSH_CONSOLE_ATTRIBUTES = {'org.openstack.compute.console.ssh': '', }
SSH_CONSOLE = core_model.Kind(
                'http://schemas.openstack.org/occi/infrastructure/compute#',
                'ssh_console',
                None,
                None,
                'SSH console kind',
                SSH_CONSOLE_ATTRIBUTES,
                '/compute/console/ssh/')


# VNC Console Kind Extension
VNC_CONSOLE_ATTRIBUTES = {'org.openstack.compute.console.vnc': '', }
VNC_CONSOLE = core_model.Kind(
                'http://schemas.openstack.org/occi/infrastructure/compute#',
                'vnc_console',
                None,
                None,
                'VNC console kind',
                VNC_CONSOLE_ATTRIBUTES,
                '/compute/console/vnc/')


# Network security rule extension to specify firewall rules
SEC_RULE_ATTRIBUTES = {
                       'occi.network.security.protocol': '',
                       'occi.network.security.to': '',
                       'occi.network.security.from': '',
                       'occi.network.security.range': '',
                       }
SEC_RULE = core_model.Kind(
        'http://schemas.openstack.org/occi/infrastructure/network/security#',
        'rule',
        [core_model.Resource.kind],
        None,
        'Network security rule kind',
        SEC_RULE_ATTRIBUTES,
        '/network/security/rule/')

# Network security rule group
SEC_GROUP = core_model.Mixin(\
    'http://schemas.ogf.org/occi/infrastructure/security/group#',
    'group', attributes=None)


# An extended Mixin, an extension
class SecurityGroupMixin(core_model.Mixin):
    def __init__(self, scheme, term, sec_grp_id, related=None, actions=None,
                 title='', attributes=None, location=None):
        super(SecurityGroupMixin, self).__init__(scheme, term, related,
                                                 actions, title,
                                                 attributes, location)
        self.sec_grp_id = sec_grp_id


class SecurityRuleBackend(backend.KindBackend):

    def __init__(self):
        super(SecurityRuleBackend, self).__init__()
        self.compute_api = API()
        self.sgh = utils.import_object(FLAGS.security_group_handler)

    def _make_sec_rule(self, entity, sec_mixin):
        '''
        Create and validate a security rule.
        '''
        sg_rule = {}
        sg_rule['id'] = random.randrange(0, 99999999)
        entity.attributes['occi.core.id'] = str(sg_rule['id'])
        sg_rule['parent_group_id'] = sec_mixin.sec_grp_id
        prot = entity.attributes['occi.network.security.protocol'].lower()
        if prot in ('tcp', 'udp', 'icmp'):
            sg_rule['protocol'] = prot
        else:
            raise Exception()
        from_p = entity.attributes['occi.network.security.to']
        if (type(from_p) is int) and from_p > 0 and from_p <= 65535:
            sg_rule['from_port'] = from_p
        else:
            raise Exception()
        to_p = entity.attributes['occi.network.security.to']
        if (type(to_p) is int) and to_p > 0 and to_p <= 65535:
            sg_rule['to_port'] = to_p
        else:
            raise Exception()
        if from_p > to_p:
            raise Exception()
        cidr = entity.attributes['occi.network.security.range']
        if len(cidr) > 0:
            cidr = '0.0.0.0/0'
        if utils.is_valid_cidr(cidr):
            sg_rule['cidr'] = cidr
        else:
            raise Exception()
        sg_rule['group'] = {}
        return sg_rule

    def _get_sec_group(self, extras, sec_mixin):
        '''
        Retreive the security group associated with the security mixin.
        '''
        try:
            parent_group_id = int(sec_mixin.sec_grp_id)
            security_group = db.security_group_get(extras['nova_ctx'], \
                                                            parent_group_id)
        except Exception:
            # Error with ID, cannot find group
            raise Exception()
        return security_group

    def create(self, entity, extras):
        '''
        creates a security rule
        the group to add the rule to must exist
        in OCCI-speak this means the mixin must be supplied with the request
        '''
        LOG.info('Creating a network security rule')

        sec_mixin = self._get_sec_mixin(entity)
        security_group = self._get_sec_group(extras, sec_mixin)
        sg_rule = self._make_sec_rule(entity, sec_mixin)

        if self._security_group_rule_exists(security_group, sg_rule):
            #This rule already exists in group
            raise Exception()

        db.security_group_rule_create(extras['nova_ctx'], sg_rule)

    def _get_sec_mixin(self, entity):
        '''
        Get the security mixin of the supplied entity.
        '''
        sec_mixin_present = 0
        mixin = None
        for mixin in entity.mixins:
            if mixin.scheme == \
                'http://schemas.ogf.org/occi/infrastructure/security/group#':
                sec_mixin_present = sec_mixin_present + 1
                break
        if not sec_mixin_present:
            raise Exception()
        if sec_mixin_present > 1:
            raise Exception()

        #TODO: ensure that an OpenStack sec group matches the mixin
        # if not, create one.

        return mixin

    def _security_group_rule_exists(self, security_group, values):
        # Taken directly from security_groups.py
        """Indicates whether the specified rule values are already
           defined in the given security group.
        """
        for rule in security_group.rules:
            is_duplicate = True
            keys = ('group_id', 'cidr', 'from_port', 'to_port', 'protocol')
            for key in keys:
                if rule.get(key) != values.get(key):
                    is_duplicate = False
                    break
            if is_duplicate:
                return True
        return False

    def delete(self, entity, extras):
        '''
        Deletes the security rule
        '''
        LOG.info('Deleting a network security rule')
        self.compute_api.ensure_default_security_group(extras['nova_ctx'])
        try:
            rule = db.security_group_rule_get(extras['nova_ctx'],
                                        int(entity.attributes['occi.core.id']))
        except Exception:
            raise Exception()

        group_id = rule.parent_group_id
        self.compute_api.ensure_default_security_group(extras['nova_ctx'])
        security_group = db.security_group_get(extras['nova_ctx'], group_id)

        db.security_group_rule_destroy(extras['nova_ctx'], rule['id'])
        self.sgh.trigger_security_group_rule_destroy_refresh(
            extras['nova_ctx'], [rule['id']])
        self.compute_api.trigger_security_group_rules_refresh(
                                                        extras['nova_ctx'],
                                    security_group_id=security_group['id'])
