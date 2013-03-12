# coding=utf-8
# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright (c) 2012 Hendrik Volkmer, Thijs Metsch
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

from nova.virt import images

from nova.openstack.common import log as logging
from nova.openstack.common import jsonutils

LOG = logging.getLogger(__name__)


class Image(object):

    def __init__(self, context, image_id, image_size, user_id, tenant_id):
        self.context = context
        self.image_uuid = image_id
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.image_size = image_size

    def uuid(self):
        return self.image_uuid

    def size(self):
        return self.image_size

    def ensure_created(self):
        self.image_temp_target = "/tmp/%s-tmp-img" % self.image_uuid
        if not self.check_image_exists_locally():
            LOG.debug("Fetching image from glance")
            images.fetch_to_raw(self.context, self.image_uuid,
                self.image_temp_target, self.user_id, self.tenant_id)
            self.register_image()

    def check_image_exists_locally(self):
        # TODO: make this more robust (imgadm show..) but imgadm has to work
        # then...
        db_file = "/var/db/imgadm/%s.json" % self.image_uuid
        LOG.debug("Testing: %s" % db_file)
        return os.path.exists(db_file)

    def write_manifest_file(self, manifest_file):
        with open(manifest_file, 'w') as f:
            f.write(jsonutils.dumps(self.create_manifest()))
