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

import subprocess
import os
import uuid
from subprocess import Popen, PIPE, STDOUT
from nova.openstack.common import log as logging
from nova import utils

from nova.openstack.common import jsonutils

from nova.virt.smartosapi.zone_image import ZoneImage
from nova.virt.smartosapi.kvm_image import KVMImage

from nova.virt.smartosapi.zone_driver import ZoneDriver
from nova.virt.smartosapi.kvm_driver import KVMDriver

LOG = logging.getLogger(__name__)

class SmartOSOps(object):


    def list_instances(self):
        return []

    def get_info(self, instance):
        # TODO: Replace with real request to data instead of dummy values
        (state, max_mem, mem, num_cpu, cpu_time) = ('running',512,512,1,12)
        return {'state': state,
             'max_mem': max_mem,
             'mem': mem,
             'num_cpu': num_cpu,
             'cpu_time': cpu_time}

    def get_image_handler_and_driver(self, context, image_meta, instance, nics):
        zone = image_meta['properties'].has_key('zone') and image_meta['properties']['zone'] == 'true'
        LOG.debug("-- HXO: zone %s" % zone)
        image_id = str(uuid.UUID(image_meta['id']))
        image = None
        driver = None
        # TODO: This certainly could be made nicer using some idiomatic python magic
        if zone:
            image = ZoneImage(context, image_id, image_meta['size'], instance['user_id'], instance['project_id'])
            driver = ZoneDriver(instance, image, nics)
        else:
            image = KVMImage(context, image_id, image_meta['size'], instance['user_id'], instance['project_id'])
            driver = KVMDriver(instance, image, nics)
        return (image, driver)

    def spawn(self, context, instance, image_meta, network_info,
         block_device_mapping=None):
        """Create VM instance."""

        LOG.debug("-- HXO --")
        LOG.debug(repr(image_meta))
        LOG.debug(repr(network_info))
        LOG.debug("-- HXO --")

        (network, nics) = network_info[0]
        (image, driver) = self.get_image_handler_and_driver(context, image_meta, instance, nics)
        image.ensure_created()
        driver.boot()

    def plug_vifs(self, instance, network_info):
        """Plug VIFs into networks."""
        print network_info

    def unplug_vifs(self, instance, network_info):
        """Unplug VIFs from networks."""
        print network_info

    def destroy(self, instance, network_info):
        (exists,stderr) =  utils.execute("vmadm","lookup","uuid=%s" % instance['uuid'])
        if len(exists) > 0:
            utils.execute("vmadm", "delete", instance['uuid'])
            #if kvm_vm:
            #    image_uuid =
            #    utils.execute("zfs","destroy","zones/%s@%s-disk0" % (image_uuid, instance_uuid)
        LOG.debug("Deleted %s" % instance['uuid'])
