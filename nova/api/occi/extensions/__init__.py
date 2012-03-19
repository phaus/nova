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


from nova import log as logging

import os


LOG = logging.getLogger('nova.api.occi.extensions')
EXTENSIONS = []
PKG = locals()['__package__']
FILE = locals()['__file__']


def load_extensions():
    pth = FILE.rpartition(os.sep)
    pth = pth[0] + pth[1]

    mods_to_load = []
    #walkthrough the extensions directory
    for _, _, filenames in os.walk(pth):
        for filename in filenames:
            if filename.endswith('.py') \
                and not filename.startswith('__init__'):
                mods_to_load.append(filename.split('.py')[0])

    #import and collect extension instances
    LOG.info('Loading the following extensions...')
    for mod in mods_to_load:
        pkg = PKG
        exec('from %s import %s' % (pkg, mod))
        extn = eval(mod).get_extensions()
        EXTENSIONS.append(extn)
        LOG.info(extn)

load_extensions()
