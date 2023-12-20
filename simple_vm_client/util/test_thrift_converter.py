import unittest

from openstack.block_storage.v2.snapshot import Snapshot as OpenStackVolumeSnapshot
from openstack.block_storage.v3.volume import Volume as OpenStackVolume
from openstack.compute.v2.flavor import Flavor as OpenStackFlavor
from openstack.compute.v2.server import Server as OpenStackServer
from openstack.image.v2.image import Image as OpenStackImage
from openstack.test import fakes

from simple_vm_client.ttypes import VM, Flavor, Image, Snapshot, Volume
from simple_vm_client.util import thrift_converter


class TestThriftConverter(unittest.TestCase):
    def test_os_to_thrift_image(self):
        openstack_image = fakes.generate_fake_resource(OpenStackImage)
        result_image = thrift_converter.os_to_thrift_image(
            openstack_image=openstack_image
        )
        properties = openstack_image.get("properties")
        if not properties:
            properties = {}
        self.assertIsInstance(result_image, Image)
        self.assertEqual(result_image.name, openstack_image.name)
        self.assertEqual(result_image.min_disk, openstack_image.min_disk)
        self.assertEqual(result_image.min_ram, openstack_image.min_ram)
        self.assertEqual(result_image.status, openstack_image.status)
        self.assertEqual(result_image.created_at, openstack_image.created_at)
        self.assertEqual(result_image.updated_at, openstack_image.updated_at)
        self.assertEqual(result_image.os_version, openstack_image.os_version)
        self.assertEqual(result_image.openstack_id, openstack_image.id)
        self.assertEqual(result_image.description, properties.get("description", ""))
        self.assertEqual(result_image.tags, openstack_image.tags)
        self.assertFalse(result_image.is_snapshot)

    def test_os_to_thrift_images(self):
        openstack_images: list[OpenStackImage] = list(
            fakes.generate_fake_resources(OpenStackImage, count=3)
        )
        result_images: list[Image] = thrift_converter.os_to_thrift_images(
            openstack_images=openstack_images
        )
        self.assertEqual(len(result_images), len(openstack_images))
        for result_image, openstack_image in zip(result_images, openstack_images):
            properties = openstack_image.get("properties")
            if not properties:
                properties = {}
            self.assertIsInstance(result_image, Image)
            self.assertEqual(result_image.name, openstack_image.name)
            self.assertEqual(result_image.min_disk, openstack_image.min_disk)
            self.assertEqual(result_image.min_ram, openstack_image.min_ram)
            self.assertEqual(result_image.status, openstack_image.status)
            self.assertEqual(result_image.created_at, openstack_image.created_at)
            self.assertEqual(result_image.updated_at, openstack_image.updated_at)
            self.assertEqual(result_image.os_version, openstack_image.os_version)
            self.assertEqual(result_image.openstack_id, openstack_image.id)
            self.assertEqual(
                result_image.description, properties.get("description", "")
            )
            self.assertEqual(result_image.tags, openstack_image.tags)
            self.assertFalse(result_image.is_snapshot)

    def test_os_to_thrift_flavor(self):
        openstack_flavor: OpenStackFlavor = fakes.generate_fake_resource(
            OpenStackFlavor
        )
        result_flavor: Flavor = thrift_converter.os_to_thrift_flavor(
            openstack_flavor=openstack_flavor
        )
        self.assertIsInstance(result_flavor, Flavor)
        self.assertEqual(result_flavor.vcpus, openstack_flavor.vcpus)
        self.assertEqual(result_flavor.ram, openstack_flavor.ram)
        self.assertEqual(result_flavor.disk, openstack_flavor.disk)
        self.assertEqual(result_flavor.name, openstack_flavor.name)
        self.assertEqual(result_flavor.ephemeral_disk, openstack_flavor.ephemeral)
        self.assertEqual(result_flavor.description, openstack_flavor.description or "")

    def test_os_to_thrift_flavors(self):
        openstack_flavors: list[OpenStackFlavor] = list(
            fakes.generate_fake_resources(OpenStackFlavor, count=3)
        )
        result_flavors: list[Flavor] = thrift_converter.os_to_thrift_flavors(
            openstack_flavors=openstack_flavors
        )
        self.assertEqual(len(result_flavors), len(openstack_flavors))
        for result_flavor, openstack_flavor in zip(result_flavors, openstack_flavors):
            self.assertIsInstance(result_flavor, Flavor)
            self.assertEqual(result_flavor.vcpus, openstack_flavor.vcpus)
            self.assertEqual(result_flavor.ram, openstack_flavor.ram)
            self.assertEqual(result_flavor.disk, openstack_flavor.disk)
            self.assertEqual(result_flavor.name, openstack_flavor.name)
            self.assertEqual(result_flavor.ephemeral_disk, openstack_flavor.ephemeral)
            self.assertEqual(
                result_flavor.description, openstack_flavor.description or ""
            )

    def test_os_to_thrift_volume(self):
        openstack_volume: OpenStackVolume = fakes.generate_fake_resource(
            OpenStackVolume
        )
        result_volume: Volume = thrift_converter.os_to_thrift_volume(
            openstack_volume=openstack_volume
        )

        if isinstance(openstack_volume.get("attachments"), list):
            device = openstack_volume.attachments[0]["device"]
            server_id = openstack_volume.attachments[0]["server_id"]
        else:
            device = None
            server_id = None
        self.assertIsInstance(result_volume, Volume)
        self.assertEqual(result_volume.status, openstack_volume.status)
        self.assertEqual(result_volume.id, openstack_volume.id)
        self.assertEqual(result_volume.name, openstack_volume.name)
        self.assertEqual(result_volume.description, openstack_volume.description)
        self.assertEqual(result_volume.size, openstack_volume.size)
        self.assertEqual(result_volume.device, device)
        self.assertEqual(result_volume.server_id, server_id)

    def test_os_to_thrift_volume_snapshot(self):
        openstack_volume_snapshot: OpenStackVolumeSnapshot = (
            fakes.generate_fake_resource(OpenStackVolumeSnapshot)
        )
        result_volume_snapshot: Snapshot = (
            thrift_converter.os_to_thrift_volume_snapshot(
                openstack_snapshot=openstack_volume_snapshot
            )
        )
        self.assertIsInstance(result_volume_snapshot, Snapshot)
        self.assertEqual(
            result_volume_snapshot.status, openstack_volume_snapshot.status
        )
        self.assertEqual(result_volume_snapshot.id, openstack_volume_snapshot.id)
        self.assertEqual(result_volume_snapshot.name, openstack_volume_snapshot.name)
        self.assertEqual(
            result_volume_snapshot.description, openstack_volume_snapshot.description
        )
        self.assertEqual(
            result_volume_snapshot.created_at, openstack_volume_snapshot.created_at
        )
        self.assertEqual(result_volume_snapshot.size, openstack_volume_snapshot.size)
        self.assertEqual(
            result_volume_snapshot.volume_id, openstack_volume_snapshot.volume_id
        )

    def test_os_to_thrift_server(self):
        openstack_server = fakes.generate_fake_resource(OpenStackServer)
        openstack_flavor: OpenStackFlavor = fakes.generate_fake_resource(
            OpenStackFlavor
        )
        openstack_image = fakes.generate_fake_resource(OpenStackImage)

        openstack_server.flavor = openstack_flavor
        openstack_server.image = openstack_image

        result_server: VM = thrift_converter.os_to_thrift_server(
            openstack_server=openstack_server
        )
        self.assertIsInstance(result_server, VM)
        self.assertIsInstance(result_server.flavor, Flavor)
        self.assertIsInstance(result_server.image, Image)
        self.assertEqual(result_server.metadata, openstack_server.metadata)
        self.assertEqual(result_server.project_id, openstack_server.project_id)
        self.assertEqual(result_server.keyname, openstack_server.key_name)
        self.assertEqual(result_server.name, openstack_server.name)
        self.assertEqual(result_server.created_at, openstack_server.created_at)
        self.assertEqual(result_server.task_state, openstack_server.task_state)
        self.assertEqual(result_server.vm_state, openstack_server.vm_state)

    def test_os_to_thrift_servers(self):
        openstack_servers: list[OpenStackFlavor] = list(
            fakes.generate_fake_resources(OpenStackServer, count=3)
        )
        for openstack_server in openstack_servers:
            openstack_flavor: OpenStackFlavor = fakes.generate_fake_resource(
                OpenStackFlavor
            )
            openstack_image = fakes.generate_fake_resource(OpenStackImage)

            openstack_server.flavor = openstack_flavor
            openstack_server.image = openstack_image

        result_servers: VM = thrift_converter.os_to_thrift_servers(
            openstack_servers=openstack_servers
        )
        self.assertEqual(len(result_servers), len(openstack_servers))


if __name__ == "__main__":
    unittest.main()
