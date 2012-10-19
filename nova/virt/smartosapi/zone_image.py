# coding=utf-8
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
from nova import utils
from nova.virt.smartosapi import image

LOG = logging.getLogger(__name__)


class ZoneImage(image.Image):

    def register_image(self):
        LOG.debug("Doing the -zone- thing")
        manifest_file = "/tmp/%s-manifest.json" % self.image_uuid
        self.write_manifest_file(manifest_file)
        utils.execute("imgadm", "install", "-m", manifest_file, "-f",
            self.image_temp_target)
        LOG.debug("zone image registered via %s" % manifest_file)

        #utils.delete_if_exists(manifest_file)

    def create_manifest(self):
        return {
            "name": "smartos64-xxxz",
            "version": "1.6.3",
            "type": "zone-dataset",
            "description": "Base template to build other templates on",
            "published_at": "2012-05-02T15:15:24.139Z",
            "os": "smartos",
            "files": [
              {
                "path": "smartos64-1.6.3.zfs",
                "sha1": "9df6543bc4bde6e2efc532fe37ce21bc95318397",
                "size": 47480510,
                "url": "https://datasets.joyent.com/datasets/f9e4be48-9466-11e1-bc41-9f993f5dff36/smartos64-1.6.3.zfs.bz2"
              }
            ],
            "requirements": {
              "networks": [
                {
                  "name": "net0",
                  "description": "public"
                }
              ]
            },
            "uuid": self.image_uuid,
            "creator_uuid": "352971aa-31ba-496c-9ade-a379feaecd52",
            "vendor_uuid": "352971aa-31ba-496c-9ade-a379feaecd52",
            "creator_name": "sdc",
            "platform_type": "smartos",
            "cloud_name": "sdc",
            "urn": "sdc:sdc:smartos64xxx:1.6.3",
            "created_at": "2012-05-02T15:15:24.139Z",
            "updated_at": "2012-05-02T15:15:24.139Z",
            "_url": "https://datasets.joyent.com/datasets"
              }
