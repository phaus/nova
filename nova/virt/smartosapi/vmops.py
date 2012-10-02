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
from nova.virt import images
from nova.openstack.common import jsonutils

LOG = logging.getLogger(__name__)

class SmartOSOps(object):

     def __init__(self):
       	 print "alloa"

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
     def check_image_exists_locally(self, image_uuid):
         # make this more robust (imgadm show..) but imgadm has to work then...
         db_file = "/var/db/imgadm/%s.json" % image_uuid
         LOG.debug("Testing: %s" % db_file)
         return os.path.exists(db_file)

     def ensure_image_created(self, context, image_uuid, image_size, zone, user_id, tenant_id):
         #   1. download image from glance
 	 # 2. create ZFS fs: zfs create -V <img size> zones/<UUID>
 	 # 3. dd if=<download location> of=zones/<UUID>
 	 # 4. save manifest to /var/db/imgadm/<UUID>.json
         # 5. remove temp download

	 image_temp_target = "/tmp/%s-tmp-img" % image_uuid
         if not self.check_image_exists_locally(image_uuid):
             LOG.debug("Fetching image from glance")
             images.fetch_to_raw(context, image_uuid, image_temp_target, user_id, tenant_id)
             # Decide wether image is smartos zone or kvm disk
             if zone:
                 LOG.debug("Doing the -zone- thing")
                 manifest_file = "/tmp/%s-manifest.json" % image_uuid
                 with open(manifest_file, 'w') as f:
                     f.write(jsonutils.dumps(self.create_zone_manifest(image_uuid, image_size)))
                 utils.execute("imgadm","install","-m", manifest_file, "-f",image_temp_target)
                 #utils.delete_if_exists(manifest_file)
             else:
                 LOG.debug("Doing the -KVM- thing")
                 # Get the actual file sizse from file (the image might have been converted from qcow2 to raw)
                 # and thus become bigger
                 image_size_in_mb = (int(os.path.getsize(image_temp_target)) / 1024 / 1024) + 1
	         #utils.execute("zfs","create","zones/%s" % image_uuid)
                 utils.execute("zfs","create","-V","%sM" % image_size_in_mb,"zones/%s" % image_uuid)
                 utils.execute("dd","if=%s" % image_temp_target, "of=/dev/zvol/rdsk/zones/%s" % image_uuid)
                 utils.execute("zfs", "snapshot", "zones/%s@dataset" % image_uuid)
                 manifest_file = "/var/db/imgadm/%s.json" % image_uuid
                 with open(manifest_file, 'w') as f:
                     f.write(jsonutils.dumps(self.create_manifest(image_uuid, image_size)))
                 #utils.execute("imgadm","install","-m", manifest_file, "-f",image_temp_target)

         #utils.delete_if_exists(image_temp_target)

     def create_zone_manifest(self, image_uuid, image_size):
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
  "uuid": image_uuid,
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


     def create_manifest(self, image_uuid, image_size):
         # Create based on image_meta
         return {
  "name": "cirros",
  "version": "1.6.3",
  "type": "zvol",
  "description": "Base template to build other templates on",
  "published_at": "2012-05-02T15:15:24.139Z",
  "os": "linux",
  "image_size": image_size,
  "files": [
    {
      "path": "cirros",
      "sha1": "bdc60b8f3746d786003fe10031a8231abcbf21de",
      "size": image_size,
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
  "uuid": image_uuid,
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

     def spawn(self, context, instance, image_meta, network_info,
              block_device_mapping=None):
         """Create VM instance."""

         LOG.debug("-- HXO --")
         LOG.debug(repr(image_meta))
         LOG.debug(repr(network_info))
         LOG.debug("-- HXO --")
         (network, nics) = network_info[0]
         image_id = str(uuid.UUID(image_meta['id']))
         image_size =image_meta['size']
         # TODO: Actually check key and value
         zone = image_meta['properties'].has_key('zone') and image_meta['properties']['zone'] == 'true'
         LOG.debug("-- HXO: zone %s" % zone)
         self.ensure_image_created(context, image_id, image_size, zone, instance['user_id'], instance['project_id'])
         startinfo = {}
         if zone:
             startinfo = {
	"brand": "joyent",
		"hostname": (instance['server_name'] or instance['uuid']),
		#"nowait": True,
                "max_physical_memory": instance['memory_mb'],
                "dataset_uuid": image_id,
                #"dataset_uuid": "f9e4be48-9466-11e1-bc41-9f993f5dff36",
		"internal_metadata": {
		   "created_by_openstack": True,
		},
		"vcpus": instance['vcpus'],
		"uuid": instance['uuid'],
	        "owner_uuid": instance['project_id'],
      "nics": [
        {
          "nic_tag": "admin",
	  "ip": nics["ips"][0]["ip"],
	  "netmask": nics["ips"][0]["netmask"],
	  "gateway": nics["ips"][0]["gateway"]
	}
      ]
    }
         else:
             startinfo = {
  "brand": "kvm",
  "default-gateway": "192.168.2.1",
  "resolvers": [
    "208.67.222.222",
    "8.8.4.4"
  ],
  "ram": instance['memory_mb'],
  "vcpus": instance['vcpus'],
		"uuid": instance['uuid'],
  "nics": [
    {
      "nic_tag": "admin",
      "ip": nics["ips"][0]["ip"],
      "netmask": nics["ips"][0]["netmask"],
      "gateway": nics["ips"][0]["gateway"],
      "model": "virtio",
      "primary": True
    }
  ],
  "disks": [
    {
      "image_uuid": image_id,
      "boot": True,
      "model": "virtio",
      "size": image_size
    }
  ]
}
         LOG.debug("-- HXO -- booting")
         machine_file =  "/tmp/machine-%s.json" % instance['uuid']
         with open(machine_file, "w") as f:
             f.write(jsonutils.dumps(startinfo))

         utils.execute("vmadm","create", "-f", machine_file)
         LOG.debug("-- HXO -- done booting")

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


