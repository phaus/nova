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

from nova.virt.smartosapi.vm_driver import VmDriver

class KVMDriver(VmDriver):

	def startinfo(self):
		return {
           "brand": "kvm",
           "default-gateway": "192.168.2.1",
           "resolvers": [
             "208.67.222.222",
             "8.8.4.4"
             ],
	           "ram": self.instance['memory_mb'],
	           "vcpus": self.instance['vcpus'],
	           "uuid": self.instance['uuid'],
	           "nics": [
             {
               "nic_tag": "admin",
               "ip": self.nics["ips"][0]["ip"],
               "netmask": self.nics["ips"][0]["netmask"],
               "gateway": self.nics["ips"][0]["gateway"],
               "model": "virtio",
               "primary": True
               }
             ],
           "disks": [
             {
               "image_uuid": self.image_id,
               "boot": True,
               "model": "virtio",
               "size": self.image_size
               }
             ]
           }