# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2013 Nicira, Inc.
# All Rights Reserved
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
#
# @author: Aaron Rosen, Nicira Networks, Inc.

from oslo.config import cfg

from nova.openstack.common import importutils

security_group_opts = [
    cfg.StrOpt('security_group_api',
               default='nova',
               help='The full class name of the security API class'),
    cfg.StrOpt('security_group_handler',
               default='nova.network.sg.NullSecurityGroupHandler',
               help='The full class name of the security group handler class'),
]

CONF = cfg.CONF
CONF.register_opts(security_group_opts)

NOVA_DRIVER = ('nova.api.openstack.compute.contrib.security_groups.'
               'NativeNovaSecurityGroupAPI')
QUANTUM_DRIVER = ('nova.api.openstack.compute.contrib.security_groups.'
                  'NativeQuantumSecurityGroupAPI')


def get_openstack_security_group_driver():
    if CONF.security_group_api.lower() == 'nova':
        return importutils.import_object(NOVA_DRIVER)
    elif CONF.security_group_api.lower() == 'quantum':
        return importutils.import_object(QUANTUM_DRIVER)
    else:
        return importutils.import_object(CONF.security_group_api)


def get_security_group_handler():
    return importutils.import_object(CONF.security_group_handler)


def is_quantum_security_groups():
    if CONF.security_group_api.lower() == "quantum":
        return True
    else:
        return False
