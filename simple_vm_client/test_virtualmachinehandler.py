import unittest
from unittest.mock import MagicMock, patch

from openstack.block_storage.v2 import volume
from openstack.block_storage.v2.snapshot import Snapshot
from openstack.compute.v2 import flavor, server
from openstack.image.v2 import image
from openstack.test import fakes

from simple_vm_client.VirtualMachineHandler import VirtualMachineHandler

IMAGES_LIST = list(fakes.generate_fake_resources(image.Image, 3))
IMAGE = fakes.generate_fake_resource(image.Image)
FLAVORS_LIST = list(fakes.generate_fake_resources(image.Image, 3))
FLAVOR = fakes.generate_fake_resource(flavor.Flavor)
SERVER_LIST = list(fakes.generate_fake_resources(server.Server, 3))
SERVER = fakes.generate_fake_resource(server.Server)
VOLUME_LIST = list(fakes.generate_fake_resources(volume.Volume, 3))
VOLUME = fakes.generate_fake_resource(volume.Volume)
VOL_SNAP = fakes.generate_fake_resource(Snapshot)
OPENSTACK_ID = "vm_id"
METADATA = {"data": "data"}
BIBIGIRD_ID = "Bibigrid_id"
NAME = "UnitTest"
USERNAME = "username"
DESCRIPTION = "desc"
STORAGE = 5


class TestVirtualMachineHandler(unittest.TestCase):
    @patch("simple_vm_client.VirtualMachineHandler.OpenStackConnector")
    @patch("simple_vm_client.VirtualMachineHandler.BibigridConnector")
    @patch("simple_vm_client.VirtualMachineHandler.ForcConnector")
    def setUp(self, mock_template, mock_redis, mock_connection_pool):
        self.handler = VirtualMachineHandler(config_file="config_path")

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_images(self, converter):
        self.handler.openstack_connector.get_images.return_value = IMAGES_LIST
        self.handler.get_images()
        self.handler.openstack_connector.get_images.assert_called_once()
        converter.os_to_thrift_images.assert_called_once_with(
            openstack_images=IMAGES_LIST
        )

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_image(self, converter):
        self.handler.openstack_connector.get_image.return_value = IMAGE
        self.handler.get_image("image_id")
        self.handler.openstack_connector.get_image.assert_called_once_with(
            name_or_id="image_id", ignore_not_active=False
        )
        converter.os_to_thrift_image.assert_called_once_with(openstack_image=IMAGE)

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_public_images(self, converter):
        self.handler.openstack_connector.get_public_images.return_value = IMAGES_LIST
        self.handler.get_public_images()
        self.handler.openstack_connector.get_public_images.assert_called_once_with()
        converter.os_to_thrift_images.assert_called_once_with(
            openstack_images=IMAGES_LIST
        )

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_private_images(self, converter):
        self.handler.openstack_connector.get_private_images.return_value = IMAGES_LIST
        self.handler.get_private_images()
        self.handler.openstack_connector.get_private_images.assert_called_once_with()
        converter.os_to_thrift_images.assert_called_once_with(
            openstack_images=IMAGES_LIST
        )

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_flavors(self, converter):
        self.handler.openstack_connector.get_flavors.return_value = FLAVORS_LIST
        self.handler.get_flavors()
        self.handler.openstack_connector.get_flavors.assert_called_once_with()
        converter.os_to_thrift_flavors.assert_called_once_with(
            openstack_flavors=FLAVORS_LIST
        )

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_volume(self, converter):
        self.handler.openstack_connector.get_volume.return_value = VOLUME
        self.handler.get_volume("volume_id")
        self.handler.openstack_connector.get_volume.assert_called_once_with(
            name_or_id="volume_id"
        )
        converter.os_to_thrift_volume.assert_called_once_with(openstack_volume=VOLUME)

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_volumes_by_ids(self, converter):
        self.handler.openstack_connector.get_volume.side_effect = VOLUME_LIST
        self.handler.get_volumes_by_ids([vol.id for vol in VOLUME_LIST])
        for vol in VOLUME_LIST:
            self.handler.openstack_connector.get_volume.assert_any_call(
                name_or_id=vol.id
            )
            converter.os_to_thrift_volume.assert_any_call(openstack_volume=vol)

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_resize_volume(self, converter):
        self.handler.resize_volume("id", 5)
        self.handler.openstack_connector.resize_volume.asser_called_once_with("id", 5)

    def test_get_gateway_ip(self):
        self.handler.get_gateway_ip()
        self.handler.openstack_connector.get_gateway_ip.assert_called_once()

    def test_get_calculation_values(self):
        self.handler.get_calculation_values()
        self.handler.openstack_connector.get_calculation_values.assert_called_once()

    def test_import_keypair(self):
        key_name = "key"
        pub_key = "pub"
        self.handler.import_keypair(keyname=key_name, public_key=pub_key)
        self.handler.openstack_connector.import_keypair.assert_called_once_with(
            keyname=key_name, public_key=pub_key
        )

    def test_exist_server(self) -> bool:
        name = "test"
        self.handler.exist_server(name=name)
        self.handler.openstack_connector.exist_server.assert_called_once_with(name=name)

    def test_get_vm_ports(self):
        openstack_id = "vm_id"
        self.handler.get_vm_ports(openstack_id=openstack_id)
        self.handler.openstack_connector.get_vm_ports.assert_called_once_with(
            openstack_id=openstack_id
        )

    def test_stop_server(self):
        openstack_id = "vm_id"
        self.handler.stop_server(openstack_id=openstack_id)
        self.handler.openstack_connector.stop_server.assert_called_once_with(
            openstack_id=openstack_id
        )

    def test_delete_server(self) -> None:
        self.handler.delete_server(openstack_id=OPENSTACK_ID)
        self.handler.openstack_connector.delete_server.assert_called_once_with(
            openstack_id=OPENSTACK_ID
        )

    def test_reboot_hard_server(self) -> None:
        self.handler.reboot_hard_server(openstack_id=OPENSTACK_ID)
        self.handler.openstack_connector.reboot_hard_server.assert_called_once_with(
            openstack_id=OPENSTACK_ID
        )

    def test_reboot_soft_server(self) -> None:
        self.handler.reboot_soft_server(openstack_id=OPENSTACK_ID)
        self.handler.openstack_connector.reboot_soft_server.assert_called_once_with(
            openstack_id=OPENSTACK_ID
        )

    def test_resume_server(self) -> None:
        self.handler.resume_server(openstack_id=OPENSTACK_ID)
        self.handler.openstack_connector.resume_server.assert_called_once_with(
            openstack_id=OPENSTACK_ID
        )

    def test_set_server_metadata(self):
        self.handler.set_server_metadata(openstack_id=OPENSTACK_ID, metadata=METADATA)
        self.handler.openstack_connector.set_server_metadata.assert_called_once_with(
            openstack_id=OPENSTACK_ID, metadata=METADATA
        )

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_server(self, converter):
        self.handler.openstack_connector.get_server.return_value = SERVER
        self.handler.forc_connector.get_playbook_status.return_value = SERVER

        self.handler.get_server(openstack_id=OPENSTACK_ID)
        self.handler.openstack_connector.get_server.assert_called_once_with(
            openstack_id=OPENSTACK_ID
        )
        self.handler.forc_connector.get_playbook_status.assert_called_once_with(
            server=SERVER
        )
        converter.os_to_thrift_server.assert_called_once_with(openstack_server=SERVER)

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_servers(self, converter):
        self.handler.openstack_connector.get_servers.return_value = SERVER_LIST
        self.handler.forc_connector.get_playbook_status.side_effect = SERVER_LIST
        self.handler.get_servers()
        for svr in SERVER_LIST:
            self.handler.forc_connector.get_playbook_status.assert_any_call(server=svr)

        converter.os_to_thrift_servers.assert_any_call(openstack_servers=SERVER_LIST)

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_servers_by_ids(self, converter):
        ids = [serv.id for serv in SERVER_LIST]
        self.handler.openstack_connector.get_servers_by_ids.return_value = SERVER_LIST
        self.handler.get_servers_by_ids(server_ids=ids)

        self.handler.openstack_connector.get_servers_by_ids.assert_called_once_with(
            ids=ids
        )
        converter.os_to_thrift_servers.assert_any_call(openstack_servers=SERVER_LIST)

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_servers_by_bibigrid_id(self, converter):
        self.handler.openstack_connector.get_servers_by_bibigrid_id.return_value = (
            SERVER_LIST
        )
        self.handler.get_servers_by_bibigrid_id(bibigrid_id=BIBIGIRD_ID)

        self.handler.openstack_connector.get_servers_by_bibigrid_id.assert_called_once_with(
            bibigrid_id=BIBIGIRD_ID
        )
        converter.os_to_thrift_servers.assert_called_once_with(
            openstack_servers=SERVER_LIST
        )

    def test_get_playbook_logs(self):
        self.handler.get_playbook_logs(openstack_id=OPENSTACK_ID)
        self.handler.forc_connector.get_playbook_logs.assert_called_once_with(
            openstack_id=OPENSTACK_ID
        )

    def test_has_forc(self):
        self.handler.has_forc()
        self.handler.forc_connector.has_forc.assert_called_once()

    def test_get_forc_url(self):
        self.handler.get_forc_url()
        self.handler.forc_connector.get_forc_access_url.assert_called_once()

    def test_create_snapshot(self):
        self.handler.create_snapshot(
            openstack_id=OPENSTACK_ID,
            name=NAME,
            username=USERNAME,
            base_tags=[],
            description=DESCRIPTION,
        )
        self.handler.openstack_connector.create_snapshot.assert_called_once_with(
            openstack_id=OPENSTACK_ID,
            name=NAME,
            username=USERNAME,
            base_tags=[],
            description=DESCRIPTION,
        )

    def test_delete_image(self) -> None:
        self.handler.delete_image(image_id=OPENSTACK_ID)
        self.handler.openstack_connector.delete_image.assert_called_once_with(
            image_id=OPENSTACK_ID
        )

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_create_volume(self, converter):
        self.handler.openstack_connector.create_volume.return_value = VOLUME
        self.handler.create_volume(
            volume_name=NAME, volume_storage=STORAGE, metadata=METADATA
        )
        self.handler.openstack_connector.create_volume.assert_called_once_with(
            volume_name=NAME, volume_storage=STORAGE, metadata=METADATA
        )
        converter.os_to_thrift_volume.assert_called_once_with(openstack_volume=VOLUME)

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_create_volume_by_source_volume(self, converter):
        self.handler.openstack_connector.create_volume_by_source_volume.return_value = (
            VOLUME
        )
        self.handler.create_volume_by_source_volume(
            source_volume_id=OPENSTACK_ID, volume_name=NAME, metadata=METADATA
        )
        self.handler.openstack_connector.create_volume_by_source_volume.assert_called_once_with(
            source_volume_id=OPENSTACK_ID, volume_name=NAME, metadata=METADATA
        )
        converter.os_to_thrift_volume.assert_called_once_with(openstack_volume=VOLUME)

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_create_volume_by_volume_snap(self, converter):
        self.handler.openstack_connector.create_volume_by_volume_snap.return_value = (
            VOLUME
        )
        self.handler.create_volume_by_volume_snap(
            volume_snap_id=OPENSTACK_ID, volume_name=NAME, metadata=METADATA
        )
        self.handler.openstack_connector.create_volume_by_volume_snap.assert_called_once_with(
            volume_snap_id=OPENSTACK_ID, volume_name=NAME, metadata=METADATA
        )
        converter.os_to_thrift_volume.assert_called_once_with(openstack_volume=VOLUME)

    def test_create_volume_snapshot(self):
        self.handler.create_volume_snapshot(
            volume_id=OPENSTACK_ID, name=NAME, description=DESCRIPTION
        )
        self.handler.openstack_connector.create_volume_snapshot.assert_called_once_with(
            volume_id=OPENSTACK_ID, name=NAME, description=DESCRIPTION
        )

    @patch("simple_vm_client.VirtualMachineHandler.thrift_converter")
    def test_get_volume_snapshot(self, converter):
        self.handler.openstack_connector.get_volume_snapshot.return_value = VOL_SNAP
        self.handler.get_volume_snapshot(snapshot_id=OPENSTACK_ID)
        converter.os_to_thrift_volume_snapshot.assert_called_once_with(
            openstack_snapshot=VOL_SNAP
        )

    def test_delete_volume_snapshot(self):
        self.handler.delete_volume_snapshot(snapshot_id=OPENSTACK_ID)
        self.handler.openstack_connector.delete_volume_snapshot.assert_called_once_with(
            snapshot_id=OPENSTACK_ID
        )

    def test_detach_volume(self):
        self.handler.detach_volume(volume_id=OPENSTACK_ID, server_id=OPENSTACK_ID)
        self.handler.openstack_connector.detach_volume.assert_called_once_with(
            volume_id=OPENSTACK_ID, server_id=OPENSTACK_ID
        )

    def test_delete_volume(self):
        self.handler.delete_volume(volume_id=OPENSTACK_ID)
        self.handler.openstack_connector.delete_volume.assert_called_once_with(
            volume_id=OPENSTACK_ID
        )

    def test_attach_volume_to_server(self):
        self.handler.attach_volume_to_server(
            openstack_id=OPENSTACK_ID, volume_id=OPENSTACK_ID
        )
        self.handler.openstack_connector.attach_volume_to_server.assert_called_once_with(
            openstack_id=OPENSTACK_ID, volume_id=OPENSTACK_ID
        )

    def test_get_limits(self):
        self.handler.get_limits()
        self.handler.openstack_connector.get_limits.assert_called_once()

    def test_create_backend(self):
        self.handler.create_backend(
            owner=USERNAME,
            user_key_url=USERNAME,
            template=USERNAME,
            upstream_url=USERNAME,
        )
        self.handler.forc_connector.create_backend.assert_called_once_with(
            owner=USERNAME,
            user_key_url=USERNAME,
            template=USERNAME,
            upstream_url=USERNAME,
        )

    def test_delete_backend(self):
        self.handler.delete_backend(id=OPENSTACK_ID)
        self.handler.forc_connector.delete_backend.assert_called_once_with(
            backend_id=OPENSTACK_ID
        )

    def test_get_backends(self):
        self.handler.get_backends()
        self.handler.forc_connector.get_backends.assert_called_once()

    def test_get_backends_by_owner(self):
        self.handler.get_backends_by_owner(owner=USERNAME)
        self.handler.forc_connector.get_backends_by_owner.assert_called_once_with(
            owner=USERNAME
        )

    def test_get_backends_by_template(self):
        self.handler.get_backends_by_template(template=USERNAME)
        self.handler.forc_connector.get_backends_by_template.assert_called_once_with(
            template=USERNAME
        )

    def test_get_backend_by_id(self):
        self.handler.get_backend_by_id(id=OPENSTACK_ID)
        self.handler.forc_connector.get_backend_by_id.assert_called_once_with(
            id=OPENSTACK_ID
        )

    def test_add_user_to_backend(self):
        self.handler.add_user_to_backend(backend_id=OPENSTACK_ID, user_id=USERNAME)
        self.handler.forc_connector.add_user_to_backend.assert_called_once_with(
            backend_id=OPENSTACK_ID, user_id=USERNAME
        )

    def test_get_users_from_backend(self):
        self.handler.get_users_from_backend(backend_id=OPENSTACK_ID)
        self.handler.forc_connector.get_users_from_backend.assert_called_once_with(
            backend_id=OPENSTACK_ID
        )

    def test_delete_user_from_backend(self):
        self.handler.delete_user_from_backend(backend_id=OPENSTACK_ID, user_id=USERNAME)
        self.handler.forc_connector.delete_user_from_backend.assert_called_once_with(
            backend_id=OPENSTACK_ID, user_id=USERNAME
        )

    def test_get_allowed_templates(self):
        self.handler.get_allowed_templates()
        self.handler.forc_connector.template.get_allowed_templates.assert_called_once()

    def test_delete_security_group_rule(self):
        self.handler.delete_security_group_rule(openstack_id=OPENSTACK_ID)
        self.handler.openstack_connector.delete_security_group_rule.assert_called_once_with(
            openstack_id=OPENSTACK_ID
        )

    def test_open_port_range_for_vm_in_project(self):
        self.handler.open_port_range_for_vm_in_project(
            range_start=1000, range_stop=1000, openstack_id=OPENSTACK_ID
        )
        self.handler.openstack_connector.open_port_range_for_vm_in_project.assert_called_once_with(
            range_start=1000,
            range_stop=1000,
            openstack_id=OPENSTACK_ID,
            ethertype="IPv4",
            protocol="TCP",
        )

    def test_add_udp_security_group(self):
        self.handler.add_udp_security_group(server_id=OPENSTACK_ID)
        self.handler.openstack_connector.add_udp_security_group.assert_called_once_with(
            server_id=OPENSTACK_ID
        )

    def test_start_server_with_res(self):
        self.handler.forc_connector.get_metadata_by_research_environment.return_value = (
            "res_metadata"
        )

        self.handler.start_server(
            flavor_name=FLAVOR.name,
            image_name=IMAGE.name,
            public_key="pub",
            servername=SERVER.name,
            metadata=METADATA,
            volume_ids_path_new=[],
            volume_ids_path_attach=[],
            additional_keys=[],
            research_environment="de",
            additional_security_group_ids=[],
        )
        self.handler.openstack_connector.start_server.assert_called_once_with(
            flavor_name=FLAVOR.name,
            image_name=IMAGE.name,
            public_key="pub",
            servername=SERVER.name,
            metadata=METADATA,
            volume_ids_path_new=[],
            volume_ids_path_attach=[],
            additional_keys=[],
            research_environment_metadata="res_metadata",
            additional_security_group_ids=[],
        )

    def test_start_server(self):
        self.handler.start_server(
            flavor_name=FLAVOR.name,
            image_name=IMAGE.name,
            public_key="pub",
            servername=SERVER.name,
            metadata=METADATA,
            volume_ids_path_new=[],
            volume_ids_path_attach=[],
            additional_keys=[],
            research_environment="",
            additional_security_group_ids=[],
        )
        self.handler.openstack_connector.start_server.assert_called_once_with(
            flavor_name=FLAVOR.name,
            image_name=IMAGE.name,
            public_key="pub",
            servername=SERVER.name,
            metadata=METADATA,
            volume_ids_path_new=[],
            volume_ids_path_attach=[],
            additional_keys=[],
            research_environment_metadata=None,
            additional_security_group_ids=[],
        )

    def test_start_server_with_custom_key(self):
        self.handler.openstack_connector.start_server_with_playbook.return_value = (
            SERVER.id,
            "priv",
        )
        self.handler.start_server_with_custom_key(
            flavor_name=FLAVOR.name,
            image_name=IMAGE.name,
            servername=SERVER.name,
            metadata=METADATA,
            volume_ids_path_new=[],
            volume_ids_path_attach=[],
            research_environment="",
            additional_security_group_ids=[],
        )
        self.handler.openstack_connector.start_server_with_playbook.assert_called_once_with(
            flavor_name=FLAVOR.name,
            image_name=IMAGE.name,
            servername=SERVER.name,
            metadata=METADATA,
            volume_ids_path_new=[],
            volume_ids_path_attach=[],
            additional_security_group_ids=[],
            research_environment_metadata=None,
        )
        self.handler.forc_connector.set_vm_wait_for_playbook.assert_called_once_with(
            openstack_id=SERVER.id, private_key="priv", name=SERVER.name
        )

    def test_start_server_with_custom_key_and_res(self):
        self.handler.openstack_connector.start_server_with_playbook.return_value = (
            SERVER.id,
            "priv",
        )
        self.handler.forc_connector.get_metadata_by_research_environment.return_value = (
            "res_metadata"
        )
        self.handler.start_server_with_custom_key(
            flavor_name=FLAVOR.name,
            image_name=IMAGE.name,
            servername=SERVER.name,
            metadata=METADATA,
            volume_ids_path_new=[],
            volume_ids_path_attach=[],
            research_environment="de",
            additional_security_group_ids=[],
        )
        self.handler.openstack_connector.start_server_with_playbook.assert_called_once_with(
            flavor_name=FLAVOR.name,
            image_name=IMAGE.name,
            servername=SERVER.name,
            metadata=METADATA,
            volume_ids_path_new=[],
            volume_ids_path_attach=[],
            additional_security_group_ids=[],
            research_environment_metadata="res_metadata",
        )
        self.handler.forc_connector.set_vm_wait_for_playbook.assert_called_once_with(
            openstack_id=SERVER.id, private_key="priv", name=SERVER.name
        )

    def test_create_and_deploy_playbook(self):
        self.handler.openstack_connector.get_vm_ports.return_value = {
            "port": str(20),
            "udp": str(25),
        }
        self.handler.openstack_connector.get_gateway_ip.return_value = {
            "gateway_ip": "192.168.0.1"
        }
        self.handler.openstack_connector.CLOUD_SITE = "bielefeld"

        self.handler.create_and_deploy_playbook(
            public_key="pub",
            openstack_id=OPENSTACK_ID,
            conda_packages=[],
            research_environment_template=USERNAME,
            apt_packages=[],
            create_only_backend=False,
            base_url=USERNAME,
        )

        self.handler.openstack_connector.get_vm_ports.assert_called_once_with(
            openstack_id=OPENSTACK_ID
        )
        self.handler.openstack_connector.get_gateway_ip.assert_called_once()
        self.handler.forc_connector.create_and_deploy_playbook.assert_called_once_with(
            public_key="pub",
            openstack_id=OPENSTACK_ID,
            conda_packages=[],
            research_environment_template=USERNAME,
            apt_packages=[],
            port=20,
            cloud_site="bielefeld",
            ip="192.168.0.1",
            create_only_backend=False,
            base_url=USERNAME,
        )

    def test_is_bibigrid_available(self):
        self.handler.is_bibigrid_available()
        self.handler.bibigrid_connector.is_bibigrid_available.assert_called_once()

    def test_get_cluster_info(self):
        self.handler.get_cluster_info(cluster_id=OPENSTACK_ID)
        self.handler.bibigrid_connector.get_cluster_info.assert_called_once_with(
            cluster_id=OPENSTACK_ID
        )

    def test_get_cluster_status(self):
        self.handler.get_cluster_status(cluster_id=OPENSTACK_ID)
        self.handler.bibigrid_connector.get_cluster_status.assert_called_once_with(
            cluster_id=OPENSTACK_ID
        )

    def test_start_cluster(self):
        master = MagicMock()
        worker_instances = [MagicMock()]
        self.handler.start_cluster(
            public_key="pub",
            master_instance=master,
            worker_instances=worker_instances,
            user=USERNAME,
        )
        self.handler.bibigrid_connector.start_cluster.assert_called_once_with(
            public_key="pub",
            master_instance=master,
            worker_instances=worker_instances,
            user=USERNAME,
        )

    def test_terminate_cluster(self):
        self.handler.terminate_cluster(cluster_id=OPENSTACK_ID)
        self.handler.bibigrid_connector.terminate_cluster.assert_called_once_with(
            cluster_id=OPENSTACK_ID
        )

    def test_add_cluster_machine(self):
        self.handler.add_cluster_machine(
            cluster_id=OPENSTACK_ID,
            cluster_user=USERNAME,
            cluster_group_id=["test"],
            image_name=IMAGE.name,
            flavor_name=FLAVOR.name,
            name=NAME,
            key_name=NAME,
            batch_idx=1,
            worker_idx=1,
        )
        self.handler.openstack_connector.add_cluster_machine.assert_called_once_with(
            cluster_id=OPENSTACK_ID,
            cluster_user=USERNAME,
            cluster_group_id=["test"],
            image_name=IMAGE.name,
            flavor_name=FLAVOR.name,
            name=NAME,
            key_name=NAME,
            batch_idx=1,
            worker_idx=1,
        )

    def test_keyboard_interrupt_handler_playbooks(self):
        mock_stop_a = MagicMock()
        mock_stop_b = MagicMock()
        mock_stop_c = MagicMock()

        self.handler.forc_connector._active_playbooks = {
            "a": mock_stop_a,
            "b": mock_stop_b,
            "c": mock_stop_c,
        }
        self.handler.forc_connector.redis_connection.hget.side_effect = [
            "a".encode("utf-8"),
            "b".encode("utf-8"),
            "c".encode("utf-8"),
        ]
        with self.assertRaises(SystemExit):
            self.handler.keyboard_interrupt_handler_playbooks()
        for key in self.handler.forc_connector._active_playbooks.keys():
            self.handler.openstack_connector.delete_keypair.assert_any_call(
                key_name=key
            )
            self.handler.openstack_connector.delete_server.assert_any_call(
                openstack_id=key
            )
        mock_stop_a.stop.assert_called_once()
        mock_stop_b.stop.assert_called_once()
        mock_stop_c.stop.assert_called_once()
