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

import os
from nova import utils
from nova.openstack.common import log as logging
from nova.virt.smartosapi.image import Image

LOG = logging.getLogger(__name__)

class KVMImage(Image):

    def register_image(self):
        LOG.debug("Doing the -KVM- thing")

        # Get the actual file sizse from file (the image might have been converted from qcow2 to raw)
        # and thus become bigger
        self.image_size = os.path.getsize(self.image_temp_target)
        image_size_in_mb = (int(self.image_size) / 1024 / 1024) + 1

        utils.execute("zfs","create","-V","%sM" % image_size_in_mb,"zones/%s" % self.image_uuid)
        utils.execute("dd","if=%s" % self.image_temp_target, "of=/dev/zvol/rdsk/zones/%s" % self.image_uuid)
        utils.execute("zfs", "snapshot", "zones/%s@dataset" % self.image_uuid)
        manifest_file = "/var/db/imgadm/%s.json" % self.image_uuid
        self.write_manifest_file(manifest_file)

        LOG.debug("KVM image registered at %s" % manifest_file)

        # TODO: Using imgadm does not work because of https://github.com/joyent/smartos-live/issues/110
        # utils.execute("imgadm","install","-m", manifest_file, "-f",image_temp_target)

    def create_manifest(self):
        return {
  "name": "cirros",
  "version": "1.6.3",
  "type": "zvol",
  "description": "Base template to build other templates on",
  "published_at": "2012-05-02T15:15:24.139Z",
  "os": "linux",
  "image_size": self.image_size,
  "files": [
    {
      "path": "cirros",
      "sha1": "bdc60b8f3746d786003fe10031a8231abcbf21de",
      "size": self.image_size,
      "url": "http://192.168.83.123:9292/v1/images/1415980f-9f1b-4ef6-b02b-05569bbefc17"
    }
  ],
  "requirements": {
    "networks": [
      {
        "name": "net0",
        "description": "public"
      }
    ],
    "ssh_key": True
  },
  "disk_driver": "virtio",
  "nic_driver": "virtio",
  "uuid": self.image_uuid,
  "creator_uuid": "352971aa-31ba-496c-9ade-a379feaecd52",
  "vendor_uuid": "352971aa-31ba-496c-9ade-a379feaecd52",
  "creator_name": "sdc",
  "platform_type": "smartos",
  "cloud_name": "sdc",
  "urn": "sdc:sdc:cirros:1.6.3",
  # Dynamic timestamps
  "created_at": "2012-05-02T15:15:24.139Z",
  "updated_at": "2012-05-02T15:15:24.139Z"
}
