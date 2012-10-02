# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2012 Hendrik Volkmer
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

from nova.openstack.common import log as logging
from nova.openstack.common import jsonutils
from nova import utils

LOG = logging.getLogger(__name__)

class VmDriver(object):

    def __init__(self, instance, image, nics):
        self.instance = instance
        self.image_id = image.uuid()
        self.image_size = image.size()
        self.nics = nics

    def boot(self):
        LOG.debug("-- HXO -- booting")
        # TODO: Writing to the filesystem should be made optional (for debugging only)
        # later on. vmadm supports STDIN
        machine_file =  "/tmp/machine-%s.json" % self.instance['uuid']
        with open(machine_file, "w") as f:
            f.write(jsonutils.dumps(self.startinfo()))
        utils.execute("vmadm","create", "-f", machine_file)
        LOG.debug("-- HXO -- done booting")