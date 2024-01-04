import os
import random
import socket
import tempfile
import unittest
from unittest import mock
from unittest.mock import MagicMock, call, patch

from openstack.block_storage.v3 import volume
from openstack.block_storage.v3.limits import Limit
from openstack.block_storage.v3.volume import Volume
from openstack.cloud import OpenStackCloudException
from openstack.compute.v2 import flavor, keypair, limits, server
from openstack.compute.v2.server import Server
from openstack.exceptions import ConflictException, ResourceFailure, ResourceNotFound
from openstack.image.v2 import image
from openstack.image.v2 import image as image_module
from openstack.network.v2 import security_group, security_group_rule
from openstack.network.v2.network import Network
from openstack.test import fakes
from oslo_utils import encodeutils

from simple_vm_client.forc_connector.template.template import (
    ResearchEnvironmentMetadata,
)
from simple_vm_client.util.state_enums import VmStates, VmTaskStates

from .openstack_connector.openstack_connector import OpenStackConnector
from .ttypes import (
    DefaultException,
    FlavorNotFoundException,
    ImageNotFoundException,
    OpenStackConflictException,
    ResourceNotAvailableException,
    ServerNotFoundException,
    SnapshotNotFoundException,
    VolumeNotFoundException,
)

METADATA_EXAMPLE_NO_FORC = ResearchEnvironmentMetadata(
    template_name="example_template",
    port="8080",
    wiki_link="https://example.com/wiki",
    description="Example template for testing",
    title="Example Template",
    community_driven=True,
    logo_url="https://example.com/logo.png",
    info_url="https://example.com/info",
    securitygroup_name="example_group",
    securitygroup_description="Example security group",
    securitygroup_ssh=True,
    direction="inbound",
    protocol="tcp",
    information_for_display="Some information",
    needs_forc_support=False,
    min_ram=2,
    min_cores=1,
    is_maintained=True,
    forc_versions=["1.0.0", "2.0.0"],
    incompatible_versions=["3.0.0"],
)

METADATA_EXAMPLE = ResearchEnvironmentMetadata(
    template_name="example_template",
    port="8080",
    wiki_link="https://example.com/wiki",
    description="Example template for testing",
    title="Example Template",
    community_driven=True,
    logo_url="https://example.com/logo.png",
    info_url="https://example.com/info",
    securitygroup_name="example_group",
    securitygroup_description="Example security group",
    securitygroup_ssh=True,
    direction="inbound",
    protocol="tcp",
    information_for_display="Some information",
    needs_forc_support=True,
    min_ram=2,
    min_cores=1,
    is_maintained=True,
    forc_versions=["1.0.0", "2.0.0"],
    incompatible_versions=["3.0.0"],
)
EXPECTED_IMAGE = image_module.Image(
    id="image_id_2",
    status="active",
    name="image_2",
    metadata={"os_version": "22.04", "os_distro": "ubuntu"},
    tags=["portalclient"],
)
INACTIVE_IMAGE = image_module.Image(
    id="image_inactive",
    status="building",
    name="image_inactive",
    metadata={"os_version": "22.04", "os_distro": "ubuntu"},
    tags=["portalclient"],
)

IMAGES = [
    image_module.Image(
        id="image_id_1",
        status="inactive",
        name="image_1",
        metadata={"os_version": "22.04", "os_distro": "ubuntu"},
        tags=["portalclient"],
    ),
    EXPECTED_IMAGE,
    image_module.Image(
        id="image_id_3",
        status="active",
        name="image_3",
        metadata={"os_version": "22.04", "os_distro": "centos"},
        tags=["portalclient"],
    ),
    INACTIVE_IMAGE,
]
PORT_CALCULATION = "30000 + x + y * 256"
DEFAULT_SECURITY_GROUPS = ["defaultSimpleVM"]
CONFIG_DATA = f"""
            openstack:
              gateway_ip: "192.168.1.1"
              network: "my_network"
              sub_network: "my_sub_network"
              cloud_site: "my_cloud_site"
              ssh_port_calculation: {PORT_CALCULATION}
              udp_port_calculation: {PORT_CALCULATION}
              gateway_security_group_id: "security_group_id"
            production: true
            forc:
              forc_security_group_id: "forc_security_group_id"
            """


class TestOpenStackConnector(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env_patcher = mock.patch.dict(
            os.environ,
            {
                "OS_AUTH_URL": "https://example.com",
                "OS_USERNAME": "username",
                "OS_PASSWORD": "password",
                "OS_PROJECT_NAME": "project_name",
                "OS_PROJECT_ID": "project_id",
                "OS_USER_DOMAIN_NAME": "user_domain",
                "OS_PROJECT_DOMAIN_ID": "project_domain_id",
                "USE_APPLICATION_CREDENTIALS": "False",
            },
        )
        cls.env_patcher.start()

        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()

        cls.env_patcher.stop()

    def setUp(self):
        # Create an instance of YourClass with a mocked openstack_connection
        self.mock_openstack_connection = MagicMock()
        with patch.object(OpenStackConnector, "__init__", lambda x, y, z: None):
            self.openstack_connector = OpenStackConnector(None, None)
            self.openstack_connector.openstack_connection = (
                self.mock_openstack_connection
            )
            self.openstack_connector.DEFAULT_SECURITY_GROUPS = DEFAULT_SECURITY_GROUPS
            self.openstack_connector.DEACTIVATE_UPGRADES_SCRIPT = (
                self.openstack_connector.create_deactivate_update_script()
            )
            self.openstack_connector.GATEWAY_SECURITY_GROUP_ID = (
                "dedasdasdasdadew1231231"
            )
            with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
                temp_file.write(CONFIG_DATA)

            # Call the load_config_yml method with the temporary file path
            self.openstack_connector.load_config_yml(temp_file.name)

            # Assert that the configuration attributes are set correctly

    def init_openstack_connector(self):
        with patch.object(OpenStackConnector, "__init__", lambda x, y, z: None):
            openstack_connector = OpenStackConnector(None, None)
            openstack_connector.openstack_connection = self.mock_openstack_connection
            openstack_connector.DEFAULT_SECURITY_GROUPS = DEFAULT_SECURITY_GROUPS

        return openstack_connector

    def test_load_config_yml(self):
        # Create a temporary YAML file with sample configuration
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_file.write(CONFIG_DATA)

        # Call the load_config_yml method with the temporary file path
        self.openstack_connector.load_config_yml(temp_file.name)
        os.remove(temp_file.name)
        # Assert that the configuration attributes are set correctly
        self.assertEqual(self.openstack_connector.GATEWAY_IP, "192.168.1.1")
        self.assertEqual(self.openstack_connector.NETWORK, "my_network")
        self.assertEqual(self.openstack_connector.SUB_NETWORK, "my_sub_network")
        self.assertTrue(self.openstack_connector.PRODUCTION)
        self.assertEqual(self.openstack_connector.CLOUD_SITE, "my_cloud_site")
        self.assertEqual(
            self.openstack_connector.SSH_PORT_CALCULATION, PORT_CALCULATION
        )
        self.assertEqual(
            self.openstack_connector.UDP_PORT_CALCULATION, PORT_CALCULATION
        )
        self.assertEqual(
            self.openstack_connector.FORC_SECURITY_GROUP_ID, "forc_security_group_id"
        )

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger")
    def test_load_env_config_username_password(self, mock_logger):
        openstack_connector = self.init_openstack_connector()

        # Call the load_env_config method
        openstack_connector.load_env_config()

        # Assert that attributes are set correctly
        self.assertEqual(openstack_connector.AUTH_URL, "https://example.com")
        self.assertFalse(openstack_connector.USE_APPLICATION_CREDENTIALS)
        self.assertEqual(openstack_connector.USERNAME, "username")
        self.assertEqual(openstack_connector.PASSWORD, "password")
        self.assertEqual(openstack_connector.PROJECT_NAME, "project_name")
        self.assertEqual(openstack_connector.PROJECT_ID, "project_id")
        self.assertEqual(openstack_connector.USER_DOMAIN_NAME, "user_domain")
        self.assertEqual(openstack_connector.PROJECT_DOMAIN_ID, "project_domain_id")

        # Assert that logger.info was called with the expected message
        mock_logger.info.assert_called_once_with("Load environment config: OpenStack")

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger")
    @patch.dict(
        os.environ,
        {
            "OS_AUTH_URL": "https://example.com",
            "USE_APPLICATION_CREDENTIALS": "True",
            "OS_APPLICATION_CREDENTIAL_ID": "app_cred_id",
            "OS_APPLICATION_CREDENTIAL_SECRET": "app_cred_secret",
        },
    )
    def test_load_env_config_application_credentials(self, mock_logger):
        # Create an instance of OpenStackConnector
        openstack_connector = self.init_openstack_connector()

        # Call the load_env_config method
        openstack_connector.load_env_config()

        # Assert that attributes are set correctly for application credentials
        self.assertEqual(openstack_connector.AUTH_URL, "https://example.com")
        self.assertTrue(openstack_connector.USE_APPLICATION_CREDENTIALS)
        self.assertEqual(openstack_connector.APPLICATION_CREDENTIAL_ID, "app_cred_id")
        self.assertEqual(
            openstack_connector.APPLICATION_CREDENTIAL_SECRET, "app_cred_secret"
        )

        # Assert that logger.info was called with the expected messages
        expected_calls = [
            call("Load environment config: OpenStack"),
            call("APPLICATION CREDENTIALS will be used!"),
        ]
        mock_logger.info.assert_has_calls(expected_calls, any_order=False)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger")
    @patch.dict(os.environ, {"OS_AUTH_URL": ""})
    def test_load_env_config_missing_os_auth_url(self, mock_logger):
        openstack_connector = self.init_openstack_connector()

        # Mock sys.exit to capture the exit status
        with patch("sys.exit") as mock_exit:
            # Call the load_env_config method
            openstack_connector.load_env_config()
        # Assert that logger.error was called with the expected message
        mock_logger.error.assert_called_once_with("OS_AUTH_URL not provided in env!")

        # Assert that sys.exit was called with status code 1
        mock_exit.assert_called_once_with(1)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger")
    @patch.dict(os.environ, {"USE_APPLICATION_CREDENTIALS": "True"})
    def test_load_env_config_missing_app_cred_vars(self, mock_logger):
        # Create an instance of OpenStackConnector
        openstack_connector = self.init_openstack_connector()

        # Mock sys.exit to capture the exit status
        with patch("sys.exit") as mock_exit:
            # Call the load_env_config method
            openstack_connector.load_env_config()

        # Assert that logger.error was called with the expected message
        expected_error_message = "Usage of Application Credentials enabled - but OS_APPLICATION_CREDENTIAL_ID not provided in env!"
        mock_logger.error.assert_called_once_with(expected_error_message)

        # Assert that sys.exit was called with status code 1
        mock_exit.assert_called_once_with(1)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger")
    @patch.dict(
        os.environ,
        {
            "USE_APPLICATION_CREDENTIALS": "False",
            "OS_USERNAME": "test_username",
            "OS_PASSWORD": "test_password",
            "OS_PROJECT_NAME": "test_project_name",
            "OS_PROJECT_ID": "test_project_id",
            "OS_USER_DOMAIN_NAME": "test_user_domain",
            "OS_PROJECT_DOMAIN_ID": "test_project_domain",
        },
    )
    def test_load_env_config_missing_username_password_vars(self, mock_logger):
        # Create an instance of OpenStackConnector using the helper method
        openstack_connector = self.init_openstack_connector()

        # Remove required environment variables
        del os.environ["OS_USERNAME"]
        del os.environ["OS_PASSWORD"]

        # Mock sys.exit to capture the exit status
        with patch("sys.exit") as mock_exit:
            # Call the load_env_config method
            openstack_connector.load_env_config()

        # Assert that logger.error was called with the expected message
        expected_error_message = "Usage of Username/Password enabled - but keys OS_USERNAME, OS_PASSWORD not provided in env!"
        mock_logger.error.assert_called_once_with(expected_error_message)

        # Assert that sys.exit was called with status code 1
        mock_exit.assert_called_once_with(1)

    def test_get_default_security_groups(self):
        # Call the _get_default_security_groups method
        default_security_groups = (
            self.openstack_connector._get_default_security_groups()
        )

        # Assert that the returned list is a copy of the DEFAULT_SECURITY_GROUPS attribute
        self.assertEqual(
            default_security_groups, self.openstack_connector.DEFAULT_SECURITY_GROUPS
        )

        # Assert that modifying the returned list does not affect the DEFAULT_SECURITY_GROUPS attribute
        default_security_groups.append("new_security_group")
        self.assertNotEqual(
            default_security_groups, self.openstack_connector.DEFAULT_SECURITY_GROUPS
        )

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_image(self, mock_logger_info):
        self.mock_openstack_connection.get_image.return_value = EXPECTED_IMAGE
        result = self.openstack_connector.get_image(EXPECTED_IMAGE.id)
        mock_logger_info.assert_called_once_with(f"Get Image {EXPECTED_IMAGE.id}")
        self.assertEqual(result, EXPECTED_IMAGE)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_image_not_found_exception(self, mock_logger_info):
        # Configure the mock_openstack_connection.get_image to return None
        self.mock_openstack_connection.get_image.return_value = None

        # Configure the ImageNotFoundException to be raised
        with self.assertRaises(ImageNotFoundException) as context:
            # Call the method with an image ID that will not be found
            self.openstack_connector.get_image("nonexistent_id", ignore_not_found=False)
        mock_logger_info.assert_called_once_with("Get Image nonexistent_id")

        # Assert that the exception contains the expected message and image ID
        self.assertEqual(context.exception.message, "Image nonexistent_id not found!")

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_image_not_active_exception(self, mock_logger_info):
        # Configure the mock_openstack_connection.get_image to return the not active image
        self.mock_openstack_connection.get_image.return_value = INACTIVE_IMAGE
        # Configure the ImageNotFoundException to be raised
        with self.assertRaises(ImageNotFoundException) as context:
            # Call the method with the not active image ID and set ignore_not_active to False
            self.openstack_connector.get_image(
                name_or_id=INACTIVE_IMAGE.name, ignore_not_active=False
            )
        mock_logger_info.assert_called_once_with(f"Get Image {INACTIVE_IMAGE.name}")

        # Assert that the exception contains the expected message and image ID
        self.assertEqual(
            context.exception.message,
            f"Image {INACTIVE_IMAGE.name} found but not active!",
        )

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_images(self, mock_logger_info):
        # Configure the mock_openstack_connection.image.images to return the fake images
        self.mock_openstack_connection.image.images.return_value = IMAGES

        # Call the method
        result = self.openstack_connector.get_images()
        mock_logger_info.assert_any_call("Get Images")
        image_names = [image.name for image in IMAGES]

        mock_logger_info.assert_any_call(f"Found  images - {image_names}")

        # Assert that the method returns the expected result
        self.assertEqual(result, IMAGES)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_private_images(self, mock_logger_info):
        # Configure the mock_openstack_connection.image.images to return the fake images
        self.mock_openstack_connection.image.images.return_value = IMAGES

        # Call the method
        result = self.openstack_connector.get_private_images()
        mock_logger_info.assert_any_call("Get private images")
        image_names = [image.name for image in IMAGES]

        mock_logger_info.assert_any_call(f"Found private images - {image_names}")

        # Assert that the method returns the expected result
        self.assertEqual(result, IMAGES)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_active_image_by_os_version(self, mock_logger_info):
        # Generate a set of fake images with different properties
        os_version = "22.04"

        # Configure the mock_openstack_connection.list_images to return the fake images
        self.mock_openstack_connection.list_images.return_value = IMAGES

        # Call the method with specific os_version and os_distro
        result = self.openstack_connector.get_active_image_by_os_version(
            os_version=os_version, os_distro="ubuntu"
        )
        mock_logger_info.assert_called_with(
            f"Get active Image by os-version: {os_version}"
        )

        # Assert that the method returns the expected image
        self.assertEqual(result, EXPECTED_IMAGE)
        result = self.openstack_connector.get_active_image_by_os_version(
            os_version=os_version, os_distro=None
        )
        self.assertEqual(result, EXPECTED_IMAGE)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_active_image_by_os_version_not_found_exception(self, mock_logger_info):
        # Configure the mock_openstack_connection.list_images to return an empty list
        self.mock_openstack_connection.list_images.return_value = []
        os_version = "nonexistent_version"

        # Configure the ImageNotFoundException to be raised
        with self.assertRaises(ImageNotFoundException) as context:
            # Call the method with an os_version and os_distro that won't find a matching image
            self.openstack_connector.get_active_image_by_os_version(
                os_version, "nonexistent_distro"
            )
        mock_logger_info.assert_called_with(
            f"Get active Image by os-version: {os_version}"
        )

        # Assert that the exception contains the expected message
        self.assertEqual(
            context.exception.message,
            "Old Image was deactivated! No image with os_version:nonexistent_version and os_distro:nonexistent_distro found!",
        )

    def test_replace_inactive_image(self):
        # Generate a fake image with status 'something other than active'

        self.mock_openstack_connection.list_images.return_value = IMAGES

        # Configure the mock_openstack_connection.get_image to return the inactive image
        self.mock_openstack_connection.get_image.return_value = INACTIVE_IMAGE

        # Call the method with the inactive image ID and set replace_inactive to True
        result = self.openstack_connector.get_image(
            "inactive_id", replace_inactive=True
        )

        # Assert that the method returns the replacement image
        self.assertEqual(result, EXPECTED_IMAGE)

    def test_get_limits(self):
        compute_limits = fakes.generate_fake_resource(limits.AbsoluteLimits)
        volume_limits = fakes.generate_fake_resource(Limit)
        compute_copy = {}
        for key in compute_limits.keys():
            compute_copy[key] = random.randint(0, 10000)

        absolute_volume = volume_limits["absolute"]
        for key in absolute_volume.keys():
            volume_limits["absolute"][key] = random.randint(0, 10000)
        self.openstack_connector.openstack_connection.get_compute_limits.return_value = (
            compute_copy
        )
        self.openstack_connector.openstack_connection.get_volume_limits.return_value = (
            volume_limits
        )
        self.openstack_connector.get_limits()

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.error")
    def test_create_server(self, mock_logger_error, mock_logger_info):
        # Prepare test data
        name = "test_server"
        image_id = "test_image_id"
        flavor_id = "test_flavor_id"
        network_id = "test_network_id"
        userdata = "test_userdata"
        key_name = "test_key"
        metadata = {"key1": "value1", "key2": "value2"}
        security_groups = ["group1", "group2"]

        # Mock the create_server method to return a fake server object
        fake_server = Server(**{"id": "fake_server_id", "name": name})
        self.mock_openstack_connection.create_server.return_value = fake_server

        # Call the create_server method
        result = self.openstack_connector.create_server(
            name,
            image_id,
            flavor_id,
            network_id,
            userdata,
            key_name,
            metadata,
            security_groups,
        )

        # Check if the method logs the correct information
        mock_logger_info.assert_called_once_with(
            f"Create Server:\n\tname: {name}\n\timage_id:{image_id}\n\tflavor_id:{flavor_id}\n\tmetadata:{metadata}"
        )

        # Check if the create_server method on openstack_connection was called with the expected parameters
        self.mock_openstack_connection.create_server.assert_called_once_with(
            name=name,
            image=image_id,
            flavor=flavor_id,
            network=[network_id],
            userdata=userdata,
            key_name=key_name,
            meta=metadata,
            security_groups=security_groups,
        )

        # Check if the method returns the fake server object
        self.assertEqual(result, fake_server)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_get_volume(self, mock_logger_exception, mock_logger_info):
        # Prepare test data
        name_or_id = "test_volume_id"

        # Mock the get_volume method to return a fake volume object
        fake_volume = Volume(**{"id": "fake_volume_id", "name": "test_volume"})
        self.mock_openstack_connection.get_volume.return_value = fake_volume

        # Call the get_volume method
        result = self.openstack_connector.get_volume(name_or_id)

        # Check if the method logs the correct information
        mock_logger_info.assert_called_once_with(f"Get Volume {name_or_id}")

        # Check if the get_volume method on openstack_connection was called with the expected parameters
        self.mock_openstack_connection.get_volume.assert_called_once_with(
            name_or_id=name_or_id
        )

        # Check if the method returns the fake volume object
        self.assertEqual(result, fake_volume)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_get_volume_exception(self, mock_logger_exception):
        # Prepare test data
        name_or_id = "non_existing_volume_id"

        # Mock the get_volume method to return None
        self.mock_openstack_connection.get_volume.return_value = None

        # Call the get_volume method and expect a VolumeNotFoundException
        with self.assertRaises(
            Exception
        ):  # Replace Exception with the actual exception type
            self.openstack_connector.get_volume(name_or_id)

        # Check if the method logs the correct exception information
        mock_logger_exception.assert_called_once_with(f"No Volume with id {name_or_id}")

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_delete_volume(self, mock_logger_exception, mock_logger_info):
        # Prepare test data
        volume_id = "test_volume_id"

        # Mock the delete_volume method to avoid actual deletion in the test
        self.mock_openstack_connection.delete_volume.side_effect = [
            None,  # No exception case
            ResourceNotFound(
                message="Volume not found"
            ),  # VolumeNotFoundException case
            ConflictException(
                message="Delete volume failed"
            ),  # OpenStackCloudException case
            OpenStackCloudException(
                message="Some other exception"
            ),  # DefaultException case
        ]

        # Call the delete_volume method for different scenarios
        # 1. No exception
        self.openstack_connector.delete_volume(volume_id)
        mock_logger_info.assert_called_once_with(f"Delete Volume {volume_id}")
        mock_logger_exception.assert_not_called()

        # 2. ResourceNotFound, expect VolumeNotFoundException
        with self.assertRaises(
            VolumeNotFoundException
        ):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume(volume_id)
        mock_logger_exception.assert_called_with(f"No Volume with id {volume_id}")

        # 3. ConflictException, expect OpenStackCloudException
        with self.assertRaises(
            OpenStackCloudException
        ):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume(volume_id)
        mock_logger_exception.assert_called_with(f"Delete volume: {volume_id}) failed!")

        # 4. OpenStackCloudException, expect DefaultException
        with self.assertRaises(
            DefaultException
        ):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume(volume_id)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.error")
    def test_create_volume_snapshot(self, mock_logger_error, mock_logger_info):
        # Prepare test data
        volume_id = "test_volume_id"
        snapshot_name = "test_snapshot"
        snapshot_description = "Test snapshot description"

        # Mock the create_volume_snapshot method to avoid actual creation in the test
        self.mock_openstack_connection.create_volume_snapshot.side_effect = [
            {"id": "snapshot_id"},  # No exception case
            ResourceNotFound(
                message="Volume not found"
            ),  # VolumeNotFoundException case
            OpenStackCloudException(
                message="Some other exception"
            ),  # DefaultException case
        ]

        # Call the create_volume_snapshot method for different scenarios
        # 1. No exception
        snapshot_id = self.openstack_connector.create_volume_snapshot(
            volume_id, snapshot_name, snapshot_description
        )
        self.assertEqual(snapshot_id, "snapshot_id")
        mock_logger_info.assert_called_once_with(
            f"Create Snapshot for Volume {volume_id}"
        )

        # 2. ResourceNotFound, expect VolumeNotFoundException
        with self.assertRaises(VolumeNotFoundException):
            self.openstack_connector.create_volume_snapshot(
                volume_id, snapshot_name, snapshot_description
            )
        mock_logger_error.assert_called_with(f"No Volume with id {volume_id}")

        # 3. OpenStackCloudException, expect DefaultException
        with self.assertRaises(DefaultException):
            self.openstack_connector.create_volume_snapshot(
                volume_id, snapshot_name, snapshot_description
            )

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_get_volume_snapshot(self, mock_logger_exception, mock_logger_info):
        # Prepare test data
        snapshot_id = "test_snapshot_id"

        # Mock the get_volume_snapshot method to avoid actual retrieval in the test
        self.mock_openstack_connection.get_volume_snapshot.side_effect = [
            {"id": snapshot_id},  # No exception case
            None,  # VolumeNotFoundException case
        ]

        # Call the get_volume_snapshot method for different scenarios
        # 1. No exception
        snapshot = self.openstack_connector.get_volume_snapshot(snapshot_id)
        self.assertEqual(snapshot["id"], snapshot_id)
        mock_logger_info.assert_called_once_with(f"Get volume Snapshot {snapshot_id}")

        # 2. None returned, expect VolumeNotFoundException
        with self.assertRaises(VolumeNotFoundException):
            self.openstack_connector.get_volume_snapshot(snapshot_id)
        mock_logger_exception.assert_called_with(
            f"No volume Snapshot with id {snapshot_id}"
        )

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_delete_volume_snapshot(self, mock_logger_exception, mock_logger_info):
        # Prepare test data
        snapshot_id = "test_snapshot_id"

        # Mock the delete_volume_snapshot method to avoid actual deletion in the test
        self.mock_openstack_connection.delete_volume_snapshot.side_effect = [
            None,  # No exception case
            ResourceNotFound(
                message="Snapshot not found"
            ),  # SnapshotNotFoundException case
            ConflictException(
                message="Delete snapshot failed"
            ),  # OpenStackCloudException case
            OpenStackCloudException(
                message="Some other exception"
            ),  # DefaultException case
        ]

        # Call the delete_volume_snapshot method for different scenarios
        # 1. No exception
        self.openstack_connector.delete_volume_snapshot(snapshot_id)
        mock_logger_info.assert_called_once_with(
            f"Delete volume Snapshot {snapshot_id}"
        )

        # 2. ResourceNotFound, expect SnapshotNotFoundException
        with self.assertRaises(
            SnapshotNotFoundException
        ):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume_snapshot(snapshot_id)
        mock_logger_exception.assert_called_with(f"Snapshot not found: {snapshot_id}")

        # 3. ConflictException, expect OpenStackCloudException
        with self.assertRaises(
            OpenStackCloudException
        ):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume_snapshot(snapshot_id)
        mock_logger_exception.assert_called_with(
            f"Delete volume snapshot: {snapshot_id}) failed!"
        )

        # 4. OpenStackCloudException, expect DefaultException
        with self.assertRaises(
            DefaultException
        ):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume_snapshot(snapshot_id)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_servers(self, mock_logger_info):
        # Prepare test data
        expected_servers = fakes.generate_fake_resources(server.Server, count=3)

        # Mock the list_servers method to simulate fetching servers
        self.mock_openstack_connection.list_servers.return_value = expected_servers

        # Call the get_servers method
        result_servers = self.openstack_connector.get_servers()

        # Assertions
        self.assertEqual(result_servers, expected_servers)
        mock_logger_info.assert_called_once_with("Get servers")

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.error")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_servers_by_ids(
        self, mock_logger_info, mock_logger_exception, mock_logger_error
    ):
        # Prepare test data
        server_ids = ["id1", "id2", "id3", "id4"]
        expected_servers = [Server(id="id1"), Server(id="id2")]

        # Mock the get_server_by_id method to simulate fetching servers
        self.mock_openstack_connection.get_server_by_id.side_effect = [
            expected_servers[0],  # Server found
            expected_servers[1],  # Server found
            None,  # Server not found
            Exception,
        ]

        # Call the get_servers_by_ids method
        result_servers = self.openstack_connector.get_servers_by_ids(server_ids)

        # Assertions
        self.assertEqual(result_servers, expected_servers)  # Exclude the None case
        mock_logger_info.assert_any_call(f"Get Servers by IDS : {server_ids}")
        mock_logger_info.assert_any_call("Get server id1")
        mock_logger_info.assert_any_call("Get server id2")
        mock_logger_info.assert_any_call("Get server id3")
        mock_logger_info.assert_any_call("Get server id4")
        mock_logger_error.assert_called_once_with("Requested VM id3 not found!")
        mock_logger_exception.assert_called_once_with("Requested VM id4 not found!\n ")

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_attach_volume_to_server(self, mock_logger_info, mock_logger_exception):
        # Prepare test data
        expected_attachment = {
            "device": "/dev/vdb"
        }  # Replace with actual attachment details
        expected_server = fakes.generate_fake_resource(server.Server)
        expected_volume = fakes.generate_fake_resource(volume.Volume)
        openstack_id = expected_server.id
        volume_id = expected_volume.id

        # Mock the get_server and get_volume methods
        self.mock_openstack_connection.attach_volume.return_value = expected_attachment
        self.mock_openstack_connection.get_server_by_id.return_value = (
            expected_server  # Replace with actual Server instance
        )
        self.mock_openstack_connection.get_volume.return_value = (
            expected_volume  # Replace with actual Volume instance
        )

        # Call the attach_volume_to_server method
        result_attachment = self.openstack_connector.attach_volume_to_server(
            openstack_id, volume_id
        )

        # Assertions
        self.assertEqual(result_attachment, expected_attachment)
        mock_logger_info.assert_called_with(
            f"Attaching volume {volume_id} to virtualmachine {openstack_id}"
        )
        self.mock_openstack_connection.get_server_by_id.assert_called_once_with(
            id=openstack_id
        )
        self.mock_openstack_connection.get_volume.assert_called_once_with(
            name_or_id=volume_id
        )
        self.mock_openstack_connection.attach_volume.assert_called_once_with(
            server=expected_server, volume=expected_volume
        )

        # Test exception case
        self.mock_openstack_connection.attach_volume.side_effect = ConflictException(
            message="Conflict error"
        )
        with self.assertRaises(OpenStackConflictException):
            self.openstack_connector.attach_volume_to_server(openstack_id, volume_id)
        mock_logger_exception.assert_called_once_with(
            f"Trying to attach volume {volume_id} to vm {openstack_id} error failed!",
            exc_info=True,
        )

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_detach_volume(self, mock_logger_info, mock_logger_exception):
        # Prepare test data
        expected_server = fakes.generate_fake_resource(server.Server)
        expected_volume = fakes.generate_fake_resource(volume.Volume)
        server_id = expected_server.id
        volume_id = expected_volume.id

        # Mock the get_volume, get_server, and detach_volume methods
        self.mock_openstack_connection.get_volume.return_value = (
            expected_volume  # Replace with actual Volume instance
        )
        self.mock_openstack_connection.get_server_by_id.return_value = (
            expected_server  # Replace with actual Server instance
        )
        # Call the detach_volume method
        self.openstack_connector.detach_volume(volume_id, server_id)

        # Assertions
        mock_logger_info.assert_any_call(
            f"Delete Volume Attachment  {volume_id} - {server_id}"
        )
        self.mock_openstack_connection.get_volume.assert_called_once_with(
            name_or_id=volume_id
        )
        self.mock_openstack_connection.get_server_by_id.assert_called_once_with(
            id=server_id
        )
        self.mock_openstack_connection.detach_volume.assert_called_once_with(
            volume=expected_volume, server=expected_server
        )

        # Test exception case
        self.mock_openstack_connection.detach_volume.side_effect = ConflictException(
            message="Conflict error"
        )
        with self.assertRaises(OpenStackConflictException):
            self.openstack_connector.detach_volume(volume_id, server_id)
        mock_logger_exception.assert_called_once_with(
            f"Delete volume attachment (server: {server_id} volume: {volume_id}) failed!"
        )

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_resize_volume(self, mock_logger_info, mock_logger_exception):
        # Prepare test data
        expected_volume = fakes.generate_fake_resource(volume.Volume)
        volume_id = expected_volume.id
        size = 100

        # Mock the extend_volume method
        self.mock_openstack_connection.block_storage.extend_volume.side_effect = [
            None,  # No exception case
            ResourceNotFound(message="Volume not found"),
            # VolumeNotFoundException case
            OpenStackCloudException(message="Resize error"),
        ]  # DefaultException case

        # Call the resize_volume method for different scenarios
        # 1. No exception
        self.openstack_connector.resize_volume(volume_id, size)
        mock_logger_info.assert_called_once_with(
            f"Extend volume {volume_id} to size {size}"
        )

        # 2. ResourceNotFound, expect VolumeNotFoundException
        with self.assertRaises(VolumeNotFoundException):
            self.openstack_connector.resize_volume(volume_id, size)

        # 3. OpenStackCloudException, expect DefaultException
        with self.assertRaises(DefaultException):
            self.openstack_connector.resize_volume(volume_id, size)

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_create_volume(self, mock_logger_info, mock_logger_exception):
        # Prepare test data
        volume_name = "test_volume"
        volume_storage = 100
        metadata = {"key": "value"}

        # Mock the create_volume method
        self.mock_openstack_connection.block_storage.create_volume.side_effect = [
            Volume(id="volume_id"),  # Successful case
            ResourceFailure(
                message="Volume creation failed"
            ),  # ResourceNotAvailableException case
        ]

        # Call the create_volume method for different scenarios
        # 1. Successful case
        result_volume = self.openstack_connector.create_volume(
            volume_name, volume_storage, metadata
        )
        mock_logger_info.assert_called_once_with(
            f"Creating volume with {volume_storage} GB storage"
        )
        self.assertIsInstance(result_volume, Volume)

        # 2. ResourceFailure, expect ResourceNotAvailableException
        with self.assertRaises(ResourceNotAvailableException):
            self.openstack_connector.create_volume(
                volume_name, volume_storage, metadata
            )
        mock_logger_exception.assert_called_once_with(
            f"Trying to create volume with {volume_storage} GB  failed", exc_info=True
        )

    def test_network_not_found(self):
        self.openstack_connector.openstack_connection.network.find_network.return_value = (
            None
        )
        with self.assertRaises(Exception):
            self.openstack_connector.get_network()

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_get_network(self, mock_logger_exception):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_file.write(CONFIG_DATA)

        # Call the load_config_yml method with the temporary file path
        self.openstack_connector.load_config_yml(temp_file.name)

        # Mock the find_network method
        self.mock_openstack_connection.network.find_network.return_value = Network(
            id="my_network"
        )

        # Call the get_network method
        result_network = self.openstack_connector.get_network()

        # Assertions
        self.assertIsInstance(result_network, Network)
        self.assertEqual(result_network.id, "my_network")
        self.mock_openstack_connection.network.find_network.assert_called_once_with(
            self.openstack_connector.NETWORK
        )
        mock_logger_exception.assert_not_called()  # Ensure no exception is logged

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_import_existing_keypair(self, mock_logger_info, mock_logger_exception):
        # Mock the get_keypair method for existing keypair
        existing_keypair = fakes.generate_fake_resource(keypair.Keypair)

        self.mock_openstack_connection.get_keypair.return_value = existing_keypair

        # Call the import_keypair method for an existing keypair
        result_keypair = self.openstack_connector.import_keypair(
            keyname=existing_keypair.name, public_key=existing_keypair.public_key
        )

        # Assertions for existing keypair
        self.assertEqual(result_keypair, existing_keypair)
        self.mock_openstack_connection.get_keypair.assert_called_once_with(
            name_or_id=existing_keypair.name
        )
        mock_logger_info.assert_called_once_with(f"Get Keypair {existing_keypair.name}")
        self.mock_openstack_connection.create_keypair.assert_not_called()
        self.mock_openstack_connection.delete_keypair.assert_not_called()
        mock_logger_exception.assert_not_called()

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_import_non_existing_keypair(self, mock_logger_info, mock_logger_exception):
        # Mock the get_keypair method for non-existing keypair
        new_keypair = fakes.generate_fake_resource(keypair.Keypair)

        self.mock_openstack_connection.get_keypair.return_value = None
        self.mock_openstack_connection.create_keypair.return_value = new_keypair

        # Call the import_keypair method for a new keypair
        result_keypair = self.openstack_connector.import_keypair(
            keyname=new_keypair.name, public_key=new_keypair.public_key
        )

        # Assertions for new keypair
        self.assertEqual(result_keypair, new_keypair)

        self.mock_openstack_connection.get_keypair.assert_called_with(
            name_or_id=new_keypair.name
        )
        self.mock_openstack_connection.create_keypair.assert_called_once_with(
            name=new_keypair.name, public_key=new_keypair.public_key
        )
        mock_logger_info.assert_called_with(f"Create Keypair {new_keypair.name}")
        self.mock_openstack_connection.delete_keypair.assert_not_called()
        mock_logger_exception.assert_not_called()

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_import_changed_keypair(self, mock_logger_info, mock_logger_exception):
        # Mock the get_keypair method for keypair with changed public_key
        changed_keypair = fakes.generate_fake_resource(keypair.Keypair)
        old_keypair = fakes.generate_fake_resource(keypair.Keypair)
        changed_keypair.name = old_keypair.name

        self.mock_openstack_connection.get_keypair.return_value = old_keypair
        self.mock_openstack_connection.create_keypair.return_value = changed_keypair

        # Call the import_keypair method for a keypair with changed public_key
        result_keypair = self.openstack_connector.import_keypair(
            keyname=changed_keypair.name, public_key=changed_keypair.public_key
        )

        # Assertions for keypair with changed public_key
        self.assertEqual(result_keypair, changed_keypair)
        self.mock_openstack_connection.get_keypair.assert_called_with(
            name_or_id=changed_keypair.name
        )
        self.mock_openstack_connection.create_keypair.assert_called_once_with(
            name=changed_keypair.name, public_key=changed_keypair.public_key
        )
        self.mock_openstack_connection.delete_keypair.assert_called_once_with(
            name=changed_keypair.name
        )
        mock_logger_info.assert_any_call(f"Delete keypair: {changed_keypair.name}")
        mock_logger_info.assert_any_call(
            f"Key {changed_keypair.name} has changed. Replace old Key"
        )
        mock_logger_exception.assert_not_called()

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_import_same_keypair(self, mock_logger_info, mock_logger_exception):
        # Mock the get_keypair method for keypair with same public_key
        same_keypair = fakes.generate_fake_resource(keypair.Keypair)

        self.mock_openstack_connection.get_keypair.return_value = same_keypair

        # Call the import_keypair method for a keypair with same public_key
        result_keypair = self.openstack_connector.import_keypair(
            keyname=same_keypair.name, public_key=same_keypair.public_key
        )

        # Assertions for keypair with same public_key
        self.assertEqual(result_keypair, same_keypair)
        self.mock_openstack_connection.get_keypair.assert_called_with(
            name_or_id=same_keypair.name
        )
        self.mock_openstack_connection.create_keypair.assert_not_called()
        self.mock_openstack_connection.delete_keypair.assert_not_called()
        mock_logger_info.assert_called_with(f"Get Keypair {same_keypair.name}")
        mock_logger_exception.assert_not_called()

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_create_add_keys_script(self, mock_logger_info):
        # Prepare test data
        keys = ["key1", "key2", "key3"]

        # Call the create_add_keys_script method
        result_script = self.openstack_connector.create_add_keys_script(keys)

        # Assertions
        expected_script_content = '#!/bin/bash\ndeclare -a keys_to_add=("key1" "key2" "key3" )\necho "Found keys: ${#keys_to_add[*]}"\nfor ix in ${!keys_to_add[*]}\ndo\n    printf "\\n%s" "${keys_to_add[$ix]}" >> /home/ubuntu/.ssh/authorized_keys\n\ndone\n'
        expected_script_content = encodeutils.safe_encode(
            expected_script_content.encode("utf-8")
        )

        # Additional assertions
        mock_logger_info.assert_called_once_with("create add key script")

        # Check that the real script content matches the expected content
        self.assertEqual(result_script, expected_script_content)

    @patch("simple_vm_client.openstack_connector.openstack_connector.socket.socket")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_netcat(self, mock_logger_info, mock_socket):
        # Replace with the actual host and port
        host = "example.com"
        port = 22

        # Mock the connect_ex method to simulate the connection result
        mock_socket.return_value.connect_ex.return_value = 0

        # Call the netcat method
        result = self.openstack_connector.netcat(host, port)

        # Assertions
        self.assertTrue(result)  # Adjust based on your logic
        mock_logger_info.assert_any_call(f"Checking SSH Connection {host}:{port}")
        mock_socket.assert_called_once_with(socket.AF_INET, socket.SOCK_STREAM)
        mock_socket.return_value.settimeout.assert_called_once_with(5)
        mock_socket.return_value.connect_ex.assert_called_once_with((host, port))
        mock_logger_info.assert_any_call(
            f"Checking SSH Connection {host}:{port} Result = 0"
        )

    def test_get_flavor_exception(self):
        self.openstack_connector.openstack_connection.get_flavor.return_value = None
        with self.assertRaises(FlavorNotFoundException):
            self.openstack_connector.get_flavor("not_found")

    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_flavor(self, mock_logger_info):
        # Replace with the actual flavor name or ID
        expected_flavor = fakes.generate_fake_resource(flavor.Flavor)

        # Mock the get_flavor method to simulate fetching a flavor
        self.mock_openstack_connection.get_flavor.return_value = expected_flavor

        # Call the get_flavor method
        result_flavor = self.openstack_connector.get_flavor(expected_flavor.name)

        # Assertions
        self.assertEqual(result_flavor, expected_flavor)
        mock_logger_info.assert_called_with(f"Get flavor {expected_flavor.name}")
        self.mock_openstack_connection.get_flavor.assert_called_once_with(
            name_or_id=expected_flavor.name, get_extra=True
        )

    @mock.patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_flavors(self, mock_logger_info):
        # Replace with the actual flavors you want to simulate
        expected_flavors = list(fakes.generate_fake_resources(flavor.Flavor, count=3))

        # Mock the list_flavors method to simulate fetching flavors
        self.mock_openstack_connection.list_flavors.return_value = expected_flavors

        # Call the get_flavors method
        result_flavors = self.openstack_connector.get_flavors()

        # Assertions
        self.assertEqual(result_flavors, expected_flavors)
        mock_logger_info.assert_any_call("Get Flavors")
        mock_logger_info.assert_any_call([flav["name"] for flav in expected_flavors])

        self.mock_openstack_connection.list_flavors.assert_called_once_with(
            get_extra=True
        )

    @mock.patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_servers_by_bibigrid_id(self, mock_logger_info):
        # Replace with the actual Bibigrid ID you want to test
        bibigrid_id = "your_bibigrid_id"

        # Replace with the actual servers you want to simulate
        expected_servers = list(fakes.generate_fake_resources(flavor.Flavor, count=3))

        # Mock the list_servers method to simulate fetching servers
        self.mock_openstack_connection.list_servers.return_value = expected_servers

        # Call the get_servers_by_bibigrid_id method
        result_servers = self.openstack_connector.get_servers_by_bibigrid_id(
            bibigrid_id
        )

        # Assertions
        self.assertEqual(result_servers, expected_servers)
        mock_logger_info.assert_called_with(
            f"Get Servery by Bibigrid id: {bibigrid_id}"
        )
        self.mock_openstack_connection.list_servers.assert_called_once_with(
            filters={"bibigrid_id": bibigrid_id, "name": bibigrid_id}
        )

    @mock.patch(
        "simple_vm_client.openstack_connector.openstack_connector.logger.exception"
    )
    @mock.patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_create_snapshot(self, mock_logger_info, mock_logger_exception):
        # Replace with the actual parameters you want to test
        openstack_id = "your_openstack_id"
        name = "your_snapshot_name"
        username = "your_username"
        base_tags = ["tag1", "tag2"]
        description = "your_description"
        new_snapshot = fakes.generate_fake_resource(image.Image)

        # Mock the create_image_snapshot and image.add_tag methods
        self.mock_openstack_connection.create_image_snapshot.return_value = new_snapshot
        self.mock_openstack_connection.image.add_tag.return_value = None

        # Case 1: No exception
        result_snapshot_id = self.openstack_connector.create_snapshot(
            openstack_id, name, username, base_tags, description
        )
        self.assertEqual(result_snapshot_id, new_snapshot.id)

        # Case 2: ConflictException
        self.mock_openstack_connection.create_image_snapshot.side_effect = (
            ConflictException(message="Conflict")
        )
        with self.assertRaises(OpenStackConflictException):
            self.openstack_connector.create_snapshot(
                openstack_id, name, username, base_tags, description
            )
        mock_logger_exception.assert_called_once_with(
            "Create snapshot your_openstack_id failed!"
        )

        # Case 3: OpenStackCloudException
        self.mock_openstack_connection.create_image_snapshot.side_effect = (
            OpenStackCloudException(message="Cloud Exception")
        )
        with self.assertRaises(DefaultException):
            self.openstack_connector.create_snapshot(
                openstack_id, name, username, base_tags, description
            )

    def test_delete_image_not_found(self):
        self.openstack_connector.openstack_connection.get_image.return_value = None
        with self.assertRaises(Exception):
            self.openstack_connector.delete_image("not_found")

    @mock.patch(
        "simple_vm_client.openstack_connector.openstack_connector.logger.exception"
    )
    @mock.patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_delete_image(self, mock_logger_info, mock_logger_exception):
        # Replace with the actual image_id you want to test
        fake_image = fakes.generate_fake_resource(image.Image)

        # Mock the get_image and compute.delete_image methods
        self.mock_openstack_connection.get_image.return_value = fake_image
        self.mock_openstack_connection.compute.delete_image.return_value = None

        # Case 1: No exception
        self.openstack_connector.delete_image(fake_image.id)
        mock_logger_info.assert_any_call(f"Delete Image {fake_image.id}")
        self.mock_openstack_connection.compute.delete_image.assert_called_once_with(
            fake_image.id
        )

        # Case 2: Other exceptions
        self.mock_openstack_connection.get_image.side_effect = Exception("Some error")
        with self.assertRaises(DefaultException):
            self.openstack_connector.delete_image(fake_image.id)
        mock_logger_exception.assert_called_once_with(
            f"Delete Image {fake_image.id} failed!"
        )

    @mock.patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_get_public_images(self, mock_logger_info):
        # Replace with the actual public images you want to test
        images = list(fakes.generate_fake_resources(image.Image, count=3))
        images[2].visibility = "private"

        # Mock the image.images() method with filters and extra_info
        self.mock_openstack_connection.image.images.return_value = images[:2]

        # Call the get_public_images method
        result_images = self.openstack_connector.get_public_images()

        # Assertions
        self.assertEqual(result_images, images[:2])  # Exclude the private image
        mock_logger_info.assert_any_call("Get public images")

    @patch.object(OpenStackConnector, "get_image")
    @patch.object(OpenStackConnector, "get_flavor")
    @patch.object(OpenStackConnector, "get_network")
    @patch.object(OpenStackConnector, "create_server")
    @mock.patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_add_cluster_machine(
        self,
        mock_logger_info,
        mock_create_server,
        mock_get_network,
        mock_get_flavor,
        mock_get_image,
    ):
        # Arrange
        cluster_id = "123"
        cluster_user = "user1"
        cluster_group_id = ["group1", "group2"]
        image_name = "image1"
        flavor_name = "flavor1"
        name = "machine1"
        key_name = "key1"
        batch_idx = 1
        worker_idx = 2

        # Mock responses from get_image, get_flavor, and get_network
        mock_image = MagicMock()
        mock_get_image.return_value = mock_image

        mock_flavor = MagicMock()
        mock_get_flavor.return_value = mock_flavor

        mock_network = MagicMock()
        mock_get_network.return_value = mock_network

        # Mock response from create_server
        mock_server = {"id": "server123"}
        mock_create_server.return_value = mock_server

        # Act
        result = self.openstack_connector.add_cluster_machine(
            cluster_id,
            cluster_user,
            cluster_group_id,
            image_name,
            flavor_name,
            name,
            key_name,
            batch_idx,
            worker_idx,
        )

        # Assert
        mock_get_image.assert_called_once_with(
            name_or_id=image_name, replace_inactive=True
        )
        mock_get_flavor.assert_called_once_with(name_or_id=flavor_name)
        mock_get_network.assert_called_once()
        mock_create_server.assert_called_once_with(
            name=name,
            image_id=mock_image.id,
            flavor_id=mock_flavor.id,
            network_id=mock_network.id,
            userdata=self.openstack_connector.DEACTIVATE_UPGRADES_SCRIPT,
            key_name=key_name,
            metadata={
                "bibigrid-id": cluster_id,
                "user": cluster_user,
                "worker-batch": str(batch_idx),
                "name": name,
                "worker-index": str(worker_idx),
            },
            security_groups=cluster_group_id,
        )
        mock_logger_info.assert_any_call(f"Add machine to {cluster_id}")

        mock_logger_info.assert_any_call(f"Created cluster machine:{mock_server['id']}")
        self.assertEqual(result, mock_server["id"])

    def test_add_udp_security_group_existing_group(self):
        # Test when an existing UDP security group is found
        server = fakes.generate_fake_resource(Server)
        sec_group = fakes.generate_fake_resource(security_group.SecurityGroup)
        sec_group.name = server.name + "_udp"
        # Mocking an existing security group
        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            sec_group
        )
        # Mocking server security groups
        self.openstack_connector.openstack_connection.list_server_security_groups.return_value = [
            sec_group
        ]

        # Call the method
        self.openstack_connector.add_udp_security_group(server.id)

        # Assertions
        self.openstack_connector.openstack_connection.compute.add_security_group_to_server.assert_called_once_with(
            server=server.id, security_group=sec_group
        )

    @patch.object(OpenStackConnector, "get_vm_ports")
    @patch.object(OpenStackConnector, "create_security_group")
    @mock.patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_add_udp_security_group_new_group(
        self, mock_logger_info, mock_create_security_group, mock_get_vm_ports
    ):
        # Test when a new UDP security group needs to be created

        server = fakes.generate_fake_resource(Server)
        sec_group = fakes.generate_fake_resource(security_group.SecurityGroup)
        sec_group.name = server.name + "_udp"
        udp_port = 30001

        # Mocking a non-existing security group
        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            None
        )
        self.openstack_connector.openstack_connection.get_server_by_id.return_value = (
            server
        )
        # Mocking VM ports
        mock_get_vm_ports.return_value = {"udp": udp_port}
        mock_create_security_group.return_value = sec_group
        self.openstack_connector.get_vm_ports = mock_get_vm_ports
        self.openstack_connector.create_security_group = mock_create_security_group

        # Call the method
        self.openstack_connector.add_udp_security_group(server.id)
        self.openstack_connector.openstack_connection.get_server_by_id.assert_called_once_with(
            id=server.id
        )

        # Assertions
        mock_create_security_group.assert_called_once_with(
            name=sec_group.name,
            udp_port=udp_port,
            udp=True,
            ssh=False,
            description="UDP",
        )
        self.openstack_connector.openstack_connection.compute.add_security_group_to_server.assert_called_once_with(
            server=server.id, security_group=sec_group
        )
        mock_logger_info.assert_any_call(
            f"Setting up UDP security group for {server.id}"
        )
        mock_logger_info.assert_any_call(
            (f"Add security group {sec_group.id} to server {server.id}")
        )

    @mock.patch("simple_vm_client.openstack_connector.openstack_connector.logger.info")
    def test_add_udp_security_group_already_added(self, mock_logger_info):
        # Test when an existing UDP security group is found
        server = fakes.generate_fake_resource(Server)

        sec_group = fakes.generate_fake_resource(security_group.SecurityGroup)
        sec_group.name = server.name + "_udp"

        # Mocking an existing security group
        self.openstack_connector.openstack_connection.get_server_by_id.return_value = (
            server
        )
        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            sec_group
        )
        # Mocking server security groups
        self.openstack_connector.openstack_connection.list_server_security_groups.return_value = [
            sec_group
        ]
        self.openstack_connector.add_udp_security_group(server.id)
        self.openstack_connector.openstack_connection.add_security_group_to_server.assert_not_called()
        mock_logger_info.assert_any_call(
            f"Setting up UDP security group for {server.id}"
        )
        mock_logger_info.assert_any_call(
            f"UDP Security group with name {sec_group.name} already exists."
        )

        mock_logger_info.assert_any_call(
            f"UDP Security group with name {sec_group.name} already added to server."
        )

    @patch.object(OpenStackConnector, "_get_security_groups_starting_machine")
    @patch.object(OpenStackConnector, "_get_volumes_machines_start")
    @patch.object(OpenStackConnector, "create_userdata")
    @patch.object(OpenStackConnector, "delete_keypair")
    def test_start_server_with_playbook(
        self,
        mock_delete_keypair,
        mock_create_userdata,
        mock_get_volumes,
        mock_get_security_groups_starting_machine,
    ):
        server = fakes.generate_fake_resource(Server)
        server_keypair = fakes.generate_fake_resource(keypair.Keypair)
        fake_image = fakes.generate_fake_resource(image.Image)
        fake_image.status = "active"
        fake_flavor = fakes.generate_fake_resource(flavor.Flavor)
        fake_network = fakes.generate_fake_resource(Network)

        # Set up mocks
        self.openstack_connector.openstack_connection.create_server.return_value = (
            server
        )
        self.openstack_connector.openstack_connection.create_keypair.return_value = (
            server_keypair
        )
        mock_get_security_groups_starting_machine.return_value = ["sg1", "sg2"]
        self.openstack_connector.openstack_connection.get_image.return_value = (
            fake_image
        )
        self.openstack_connector.openstack_connection.get_flavor.return_value = (
            fake_flavor
        )
        self.openstack_connector.openstack_connection.network.find_network.return_value = (
            fake_network
        )
        mock_get_volumes.return_value = ["volume1", "volume2"]
        mock_create_userdata.return_value = "userdata"

        # Set necessary input parameters
        flavor_name = fake_flavor.name
        image_name = fake_image.name
        servername = server.name
        metadata = {"project_name": "mock_project", "project_id": "mock_project_id"}
        research_environment_metadata = MagicMock()
        volume_ids_path_new = [
            {"openstack_id": "volume_id1"},
            {"openstack_id": "volume_id2"},
        ]
        volume_ids_path_attach = [{"openstack_id": "volume_id3"}]
        additional_keys = ["key1", "key2"]
        additional_security_group_ids = ["sg3", "sg4"]

        # Call the method
        result = self.openstack_connector.start_server_with_playbook(
            flavor_name,
            image_name,
            servername,
            metadata,
            research_environment_metadata,
            volume_ids_path_new,
            volume_ids_path_attach,
            additional_keys,
            additional_security_group_ids,
        )

        # Assertions
        self.openstack_connector.openstack_connection.create_server.assert_called_once_with(
            name=server.name,
            image=fake_image.id,
            flavor=fake_flavor.id,
            network=[fake_network.id],
            key_name=servername,
            meta=metadata,
            volumes=["volume1", "volume2"],
            userdata="userdata",
            security_groups=["sg1", "sg2"],
        )

        mock_create_userdata.assert_called_once_with(
            volume_ids_path_new=volume_ids_path_new,
            volume_ids_path_attach=volume_ids_path_attach,
            additional_keys=additional_keys,
        )

        mock_get_security_groups_starting_machine.assert_called_once_with(
            additional_security_group_ids=additional_security_group_ids,
            project_name="mock_project",
            project_id="mock_project_id",
            research_environment_metadata=research_environment_metadata,
        )

        self.openstack_connector.openstack_connection.create_keypair.assert_called_once_with(
            name=servername
        )

        mock_get_volumes.assert_called_once_with(
            volume_ids_path_new=volume_ids_path_new,
            volume_ids_path_attach=volume_ids_path_attach,
        )

        mock_delete_keypair.assert_called_once_with(key_name=server_keypair.name)

        # Check the result
        self.assertEqual(result, (server.id, server_keypair.private_key))

    @patch.object(OpenStackConnector, "_get_security_groups_starting_machine")
    @patch.object(OpenStackConnector, "_get_volumes_machines_start")
    @patch.object(OpenStackConnector, "create_userdata")
    @patch.object(OpenStackConnector, "delete_keypair")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_start_server_with_playbook_exception(
        self,
        mock_logger_exception,
        mock_delete_keypair,
        mock_create_userdata,
        mock_get_volumes,
        mock_get_security_groups_starting_machine,
    ):
        server = fakes.generate_fake_resource(Server)
        server_keypair = fakes.generate_fake_resource(keypair.Keypair)
        fake_image = fakes.generate_fake_resource(image.Image)
        fake_image.status = "active"
        fake_flavor = fakes.generate_fake_resource(flavor.Flavor)
        fake_network = fakes.generate_fake_resource(Network)

        # Set up mocks
        self.openstack_connector.openstack_connection.create_server.return_value = (
            server
        )
        self.openstack_connector.openstack_connection.create_keypair.return_value = (
            server_keypair
        )
        mock_get_security_groups_starting_machine.return_value = ["sg1", "sg2"]
        self.openstack_connector.openstack_connection.get_image.return_value = (
            fake_image
        )
        self.openstack_connector.openstack_connection.get_flavor.return_value = (
            fake_flavor
        )
        self.openstack_connector.openstack_connection.network.find_network.return_value = (
            fake_network
        )
        mock_get_volumes.side_effect = OpenStackCloudException("Unit Test Error")
        flavor_name = fake_flavor.name
        image_name = fake_image.name
        servername = server.name
        metadata = {"project_name": "mock_project", "project_id": "mock_project_id"}
        research_environment_metadata = MagicMock()
        volume_ids_path_new = [
            {"openstack_id": "volume_id1"},
            {"openstack_id": "volume_id2"},
        ]
        volume_ids_path_attach = [{"openstack_id": "volume_id3"}]
        additional_keys = ["key1", "key2"]
        additional_security_group_ids = ["sg3", "sg4"]

        with self.assertRaises(DefaultException):
            self.openstack_connector.start_server_with_playbook(
                flavor_name,
                image_name,
                servername,
                metadata,
                research_environment_metadata,
                volume_ids_path_new,
                volume_ids_path_attach,
                additional_keys,
                additional_security_group_ids,
            )
        mock_delete_keypair.assert_called_once_with(key_name=server_keypair.name)
        mock_logger_exception.assert_called_once_with(
            (f"Start Server {servername} error")
        )

    @patch.object(OpenStackConnector, "_get_default_security_groups")
    @patch.object(
        OpenStackConnector, "get_or_create_research_environment_security_group"
    )
    @patch.object(OpenStackConnector, "get_or_create_project_security_group")
    def test_get_security_groups_starting_machine(
        self,
        mock_get_project_sg,
        mock_get_research_env_sg,
        mock_get_default_security_groups,
    ):
        # Set up mocks
        fake_default_security_group = fakes.generate_fake_resource(
            security_group.SecurityGroup
        )
        fake_project_security_group = fakes.generate_fake_resource(
            security_group.SecurityGroup
        )
        mock_get_default_security_groups.return_value = [fake_default_security_group.id]
        mock_get_research_env_sg.return_value = "research_env_sg"
        mock_get_project_sg.return_value = fake_project_security_group.id
        self.openstack_connector.openstack_connection.get_security_group.side_effect = [
            {"id": "additional_sg1"},
            {"id": "additional_sg2"},
        ]
        # Set necessary input parameters
        additional_security_group_ids = ["additional_sg1", "additional_sg2"]
        project_name = "mock_project"
        project_id = "mock_project_id"
        research_environment_metadata = MagicMock()

        # Call the method
        result = self.openstack_connector._get_security_groups_starting_machine(
            additional_security_group_ids,
            project_name,
            project_id,
            research_environment_metadata,
        )

        # Assertions
        mock_get_default_security_groups.assert_called_once()

        mock_get_research_env_sg.assert_called_once_with(
            resenv_metadata=research_environment_metadata
        )
        mock_get_project_sg.assert_called_once_with(
            project_name=project_name, project_id=project_id
        )

        self.openstack_connector.openstack_connection.get_security_group.assert_has_calls(
            [call(name_or_id="additional_sg1"), call(name_or_id="additional_sg2")]
        )
        # Check the result
        expected_result = [
            "research_env_sg",
            fake_default_security_group.id,
            fake_project_security_group.id,
            "additional_sg1",
            "additional_sg2",
        ]
        self.assertCountEqual(result, expected_result)

    def test_get_volumes_machines_start(self):
        fake_vol_1 = fakes.generate_fake_resource(volume.Volume)
        fake_vol_2 = fakes.generate_fake_resource(volume.Volume)

        # Set up mock
        self.openstack_connector.openstack_connection.get_volume.side_effect = [
            fake_vol_1,
            fake_vol_2,
        ]

        # Set necessary input parameters
        volume_ids_path_new = [{"openstack_id": fake_vol_1.id}]
        volume_ids_path_attach = [{"openstack_id": fake_vol_2.id}]

        # Call the method
        result = self.openstack_connector._get_volumes_machines_start(
            volume_ids_path_new, volume_ids_path_attach
        )

        # Assertions
        self.openstack_connector.openstack_connection.get_volume.assert_has_calls(
            [call(name_or_id=fake_vol_1.id), call(name_or_id=fake_vol_2.id)]
        )

        # Check the result
        expected_result = [fake_vol_1, fake_vol_2]
        self.assertEqual(result, expected_result)
        volume_ids_path_new = []
        volume_ids_path_attach = []

        # Call the method
        result = self.openstack_connector._get_volumes_machines_start(
            volume_ids_path_new, volume_ids_path_attach
        )

        # Assertions
        self.openstack_connector.openstack_connection.get_volume.assert_has_calls([])

        # Check the result
        expected_result = []
        self.assertEqual(result, expected_result)

    @patch.object(OpenStackConnector, "_get_security_groups_starting_machine")
    @patch.object(OpenStackConnector, "_get_volumes_machines_start")
    @patch.object(OpenStackConnector, "create_userdata")
    @patch.object(OpenStackConnector, "delete_keypair")
    def test_start_server(
        self,
        mock_delete_keypair,
        mock_create_userdata,
        mock_get_volumes,
        mock_get_security_groups_starting_machine,
    ):
        server = fakes.generate_fake_resource(Server)
        server_keypair = fakes.generate_fake_resource(keypair.Keypair)
        server_keypair.name = server.name + "_mock_project"
        fake_image = fakes.generate_fake_resource(image.Image)
        fake_image.status = "active"
        fake_flavor = fakes.generate_fake_resource(flavor.Flavor)
        fake_network = fakes.generate_fake_resource(Network)

        # Set up mocks
        self.openstack_connector.openstack_connection.create_server.return_value = (
            server
        )
        self.openstack_connector.openstack_connection.create_keypair.return_value = (
            server_keypair
        )
        mock_get_security_groups_starting_machine.return_value = ["sg1", "sg2"]
        self.openstack_connector.openstack_connection.get_image.return_value = (
            fake_image
        )
        self.openstack_connector.openstack_connection.get_flavor.return_value = (
            fake_flavor
        )
        self.openstack_connector.openstack_connection.network.find_network.return_value = (
            fake_network
        )
        self.openstack_connector.openstack_connection.compute.find_keypair.return_value = (
            server_keypair
        )
        self.openstack_connector.openstack_connection.compute.get_keypair.return_value = (
            server_keypair
        )

        mock_get_volumes.return_value = ["volume1", "volume2"]
        mock_create_userdata.return_value = "userdata"

        # Set necessary input parameters
        flavor_name = fake_flavor.name
        image_name = fake_image.name
        servername = server.name
        metadata = {"project_name": "mock_project", "project_id": "mock_project_id"}
        research_environment_metadata = MagicMock()
        volume_ids_path_new = [
            {"openstack_id": "volume_id1"},
            {"openstack_id": "volume_id2"},
        ]
        volume_ids_path_attach = [{"openstack_id": "volume_id3"}]
        additional_keys = ["key1", "key2"]
        additional_security_group_ids = ["sg3", "sg4"]
        public_key = "public_key"

        # Call the method
        result = self.openstack_connector.start_server(
            flavor_name=flavor_name,
            image_name=image_name,
            servername=servername,
            metadata=metadata,
            research_environment_metadata=research_environment_metadata,
            volume_ids_path_new=volume_ids_path_new,
            volume_ids_path_attach=volume_ids_path_attach,
            additional_keys=additional_keys,
            additional_security_group_ids=additional_security_group_ids,
            public_key=public_key,
        )

        # Assertions
        self.openstack_connector.openstack_connection.create_server.assert_called_once_with(
            name=server.name,
            image=fake_image.id,
            flavor=fake_flavor.id,
            network=[fake_network.id],
            key_name=server_keypair.name,
            meta=metadata,
            volumes=["volume1", "volume2"],
            userdata="userdata",
            security_groups=["sg1", "sg2"],
        )

        mock_create_userdata.assert_called_once_with(
            volume_ids_path_new=volume_ids_path_new,
            volume_ids_path_attach=volume_ids_path_attach,
            additional_keys=additional_keys,
        )

        mock_get_security_groups_starting_machine.assert_called_once_with(
            additional_security_group_ids=additional_security_group_ids,
            project_name="mock_project",
            project_id="mock_project_id",
            research_environment_metadata=research_environment_metadata,
        )

        self.openstack_connector.openstack_connection.create_keypair.assert_called_once_with(
            name=server_keypair.name, public_key=public_key
        )

        mock_get_volumes.assert_called_once_with(
            volume_ids_path_new=volume_ids_path_new,
            volume_ids_path_attach=volume_ids_path_attach,
        )

        self.openstack_connector.openstack_connection.get_keypair.assert_called_once_with(
            name_or_id=server_keypair.name
        )
        mock_delete_keypair.assert_any_call(key_name=server_keypair.name)

        # Check the result
        self.assertEqual(result, server.id)

    @patch.object(OpenStackConnector, "_get_security_groups_starting_machine")
    @patch.object(OpenStackConnector, "_get_volumes_machines_start")
    @patch.object(OpenStackConnector, "create_userdata")
    @patch.object(OpenStackConnector, "delete_keypair")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_start_server_exception(
        self,
        mock_logger_exception,
        mock_delete_keypair,
        mock_create_userdata,
        mock_get_volumes,
        mock_get_security_groups_starting_machine,
    ):
        server = fakes.generate_fake_resource(Server)
        server_keypair = fakes.generate_fake_resource(keypair.Keypair)
        fake_image = fakes.generate_fake_resource(image.Image)
        fake_image.status = "active"
        fake_flavor = fakes.generate_fake_resource(flavor.Flavor)
        fake_network = fakes.generate_fake_resource(Network)
        public_key = "public_key"

        # Set up mocks
        self.openstack_connector.openstack_connection.create_server.return_value = (
            server
        )
        self.openstack_connector.openstack_connection.create_keypair.return_value = (
            server_keypair
        )
        mock_get_security_groups_starting_machine.return_value = ["sg1", "sg2"]
        self.openstack_connector.openstack_connection.get_image.return_value = (
            fake_image
        )
        self.openstack_connector.openstack_connection.get_flavor.return_value = (
            fake_flavor
        )
        self.openstack_connector.openstack_connection.network.find_network.return_value = (
            fake_network
        )
        mock_get_volumes.side_effect = OpenStackCloudException("Unit Test Error")
        flavor_name = fake_flavor.name
        image_name = fake_image.name
        servername = server.name
        metadata = {"project_name": "mock_project", "project_id": "mock_project_id"}
        research_environment_metadata = MagicMock()
        volume_ids_path_new = [
            {"openstack_id": "volume_id1"},
            {"openstack_id": "volume_id2"},
        ]
        volume_ids_path_attach = [{"openstack_id": "volume_id3"}]
        additional_keys = ["key1", "key2"]
        additional_security_group_ids = ["sg3", "sg4"]

        with self.assertRaises(DefaultException):
            self.openstack_connector.start_server(
                flavor_name=flavor_name,
                image_name=image_name,
                servername=servername,
                metadata=metadata,
                research_environment_metadata=research_environment_metadata,
                volume_ids_path_new=volume_ids_path_new,
                volume_ids_path_attach=volume_ids_path_attach,
                additional_keys=additional_keys,
                additional_security_group_ids=additional_security_group_ids,
                public_key=public_key,
            )
        mock_logger_exception.assert_any_call((f"Start Server {servername} error"))

    @patch.object(OpenStackConnector, "create_add_keys_script")
    @patch.object(OpenStackConnector, "create_mount_init_script")
    def test_create_userdata(
        self, mock_create_mount_init_script, mock_create_add_keys_script
    ):
        # Set up mocks
        mock_create_add_keys_script.return_value = b"mock_add_keys_script"
        mock_create_mount_init_script.return_value = b"mock_mount_script"

        # Set necessary input parameters
        volume_ids_path_new = [{"openstack_id": "volume_id_new"}]
        volume_ids_path_attach = [{"openstack_id": "volume_id_attach"}]
        additional_keys = ["key1", "key2"]

        # Call the method
        result = self.openstack_connector.create_userdata(
            volume_ids_path_new, volume_ids_path_attach, additional_keys
        )

        # Assertions
        mock_create_add_keys_script.assert_called_once_with(keys=additional_keys)
        mock_create_mount_init_script.assert_called_once_with(
            new_volumes=volume_ids_path_new, attach_volumes=volume_ids_path_attach
        )

        # Check the result
        expected_result = (
            b"mock_add_keys_script\n"
            + b"#!/bin/bash\npasswd -u ubuntu\n"
            + b"\nmock_mount_script"
        )
        self.assertEqual(result, expected_result)

    @patch.object(OpenStackConnector, "get_server")
    @patch("simple_vm_client.openstack_connector.openstack_connector.sympy.symbols")
    @patch("simple_vm_client.openstack_connector.openstack_connector.sympy.sympify")
    def test_get_vm_ports(self, mock_sympify, mock_symbols, mock_get_server):
        # Set up mocks
        mock_server = fakes.generate_fake_resource(server.Server)
        mock_server["private_v4"] = "192.168.1.2"

        mock_get_server.return_value = mock_server
        mock_sympify.return_value.evalf.return_value = (
            30258  # Replace with expected values
        )
        mock_symbols.side_effect = ["x", "y"]

        # Call the method
        result = self.openstack_connector.get_vm_ports(mock_server.id)

        # Assertions
        mock_get_server.assert_called_once_with(openstack_id=mock_server.id)
        mock_symbols.assert_any_call("x")
        mock_symbols.assert_any_call("y")

        mock_sympify.assert_called_with(self.openstack_connector.SSH_PORT_CALCULATION)
        mock_sympify.return_value.evalf.assert_called_with(subs={"x": 2, "y": 1})

        # Check the result
        expected_result = {
            "port": "30258",
            "udp": "30258",
        }  # Replace with expected values
        self.assertEqual(result, expected_result)

    @patch.object(OpenStackConnector, "get_server")
    @patch.object(OpenStackConnector, "_validate_server_for_deletion")
    @patch.object(OpenStackConnector, "_remove_security_groups_from_server")
    def test_delete_server_successful(
        self, mock_remove_security_groups, mock_validate_server, mock_get_server
    ):
        # Arrange
        mock_server = fakes.generate_fake_resource(server.Server)

        mock_get_server.return_value = mock_server
        # Act
        self.openstack_connector.delete_server(mock_server.id)

        # Assert
        mock_get_server.assert_called_once_with(openstack_id=mock_server.id)
        mock_validate_server.assert_called_once_with(server=mock_server)
        mock_remove_security_groups.assert_called_once_with(server=mock_server)
        self.openstack_connector.openstack_connection.compute.delete_server.assert_called_once_with(
            mock_server.id, force=True
        )

    @patch.object(OpenStackConnector, "get_server")
    def test_delete_server_exception(self, mock_get_server):
        # Arrange
        mock_server = fakes.generate_fake_resource(server.Server)
        # Mocking the necessary methods to raise a ConflictException
        mock_get_server.side_effect = ConflictException("Conflict")
        # Act

        # Act and Assert
        with self.assertRaises(OpenStackConflictException):
            self.openstack_connector.delete_server(mock_server.id)

        mock_get_server.assert_called_once_with(openstack_id=mock_server.id)
        self.openstack_connector.openstack_connection.compute.delete_server.assert_not_called()

    @patch.object(OpenStackConnector, "get_server")
    def test_delete_server_not_found_exception(self, mock_get_server):
        # Arrange
        # Mocking the necessary methods to raise a ConflictException
        server_id = "not_found"
        mock_get_server.return_value = None
        # Act

        # Act and Assert
        with self.assertRaises(ServerNotFoundException):
            self.openstack_connector.delete_server(server_id)

        mock_get_server.assert_called_once_with(openstack_id=server_id)
        self.openstack_connector.openstack_connection.compute.delete_server.assert_not_called()

    def test_validate_server_for_deletion(self):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)

        # Act
        self.openstack_connector._validate_server_for_deletion(server_mock)

        # Assert
        # No exceptions should be raised if the server is found
        self.assertTrue(True)

    def test_validate_server_for_deletion_conflict_exception(self):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)
        server_mock.task_state = "image_pending_upload"
        with self.assertRaises(ConflictException):
            # Act
            self.openstack_connector._validate_server_for_deletion(server_mock)

    def test_remove_security_groups_from_server_no_security_groups(self):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)
        server_mock.security_groups = None

        # Act
        self.openstack_connector._remove_security_groups_from_server(server_mock)

        # Assert
        # The method should not raise any exceptions if there are no security groups
        self.assertTrue(True)

    @patch.object(OpenStackConnector, "is_security_group_in_use")
    def test_remove_security_groups_from_server_with_security_groups(
        self, mock_is_security_group_in_use
    ):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)
        fake_groups = list(
            fakes.generate_fake_resources(security_group.SecurityGroup, count=4)
        )
        fake_groups[2].name = "bibigrid-sec"
        server_mock.security_groups = fake_groups
        self.openstack_connector.openstack_connection.get_security_group.side_effect = (
            fake_groups
        )
        mock_is_security_group_in_use.side_effect = [False, False, True, True]

        # Act
        self.openstack_connector._remove_security_groups_from_server(server_mock)

        for group in fake_groups:
            self.openstack_connector.openstack_connection.compute.remove_security_group_from_server.assert_any_call(
                server=server_mock, security_group=group
            )

        with self.assertRaises(AssertionError):
            self.openstack_connector.openstack_connection.delete_security_group.assert_any_call(
                fake_groups[2]
            )
            self.openstack_connector.openstack_connection.delete_security_group.assert_any_call(
                fake_groups[3]
            )

        for group in fake_groups[:2]:
            self.openstack_connector.openstack_connection.delete_security_group.assert_any_call(
                group
            )

    @patch.object(OpenStackConnector, "get_server")
    def test_stop_server_success(self, mock_get_server):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)
        mock_get_server.return_value = server_mock
        # Act
        self.openstack_connector.stop_server(openstack_id="some_openstack_id")

        # Assert
        # Ensure the stop_server method is called with the correct server
        self.openstack_connector.openstack_connection.compute.stop_server.assert_called_once_with(
            server_mock
        )

    @patch.object(OpenStackConnector, "get_server")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_stop_server_conflict_exception(
        self, mock_logger_exception, mock_get_server
    ):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)
        mock_get_server.return_value = server_mock
        self.openstack_connector.openstack_connection.compute.stop_server.side_effect = ConflictException(
            "Unit Test"
        )
        # Act
        with self.assertRaises(OpenStackConflictException):
            self.openstack_connector.stop_server(openstack_id="some_openstack_id")
        mock_logger_exception.assert_called_once_with(
            "Stop Server some_openstack_id failed!"
        )

    @patch.object(OpenStackConnector, "get_server")
    def test_reboot_server_success(self, mock_get_server):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)
        mock_get_server.return_value = server_mock
        # Act
        self.openstack_connector.reboot_server(server_mock.id, "SOFT")

        # Assert
        # Ensure the stop_server method is called with the correct server
        self.openstack_connector.openstack_connection.compute.reboot_server.assert_called_once_with(
            server_mock, "SOFT"
        )

    @patch.object(OpenStackConnector, "get_server")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_reboot_server_conflict_exception(
        self, mock_logger_exception, mock_get_server
    ):
        self.openstack_connector.openstack_connection.compute.reboot_server.side_effect = ConflictException(
            "Unit Test"
        )
        # Act
        with self.assertRaises(OpenStackConflictException):
            self.openstack_connector.reboot_server("some_openstack_id", "SOFT")
        mock_logger_exception.assert_called_once_with(
            "Reboot Server some_openstack_id failed!"
        )

    @patch.object(OpenStackConnector, "get_server")
    def test_reboot_soft_server(self, mock_get_server):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)
        mock_get_server.return_value = server_mock
        self.openstack_connector.reboot_soft_server(server_mock.id)
        self.openstack_connector.openstack_connection.compute.reboot_server.assert_called_once_with(
            server_mock, "SOFT"
        )

    @patch.object(OpenStackConnector, "get_server")
    def test_reboot_hard_server(self, mock_get_server):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)
        mock_get_server.return_value = server_mock
        self.openstack_connector.reboot_hard_server(server_mock.id)
        self.openstack_connector.openstack_connection.compute.reboot_server.assert_called_once_with(
            server_mock, "HARD"
        )

    @patch.object(OpenStackConnector, "get_server")
    def test_resume_server_success(self, mock_get_server):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)
        mock_get_server.return_value = server_mock
        # Act
        self.openstack_connector.resume_server(server_mock.id)

        # Assert
        # Ensure the stop_server method is called with the correct server
        self.openstack_connector.openstack_connection.compute.start_server.assert_called_once_with(
            server_mock
        )

    @patch.object(OpenStackConnector, "get_server")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_resume_server_conflict_exception(
        self, mock_logger_exception, mock_get_server
    ):
        self.openstack_connector.openstack_connection.compute.start_server.side_effect = ConflictException(
            "Unit Test"
        )
        # Act
        with self.assertRaises(OpenStackConflictException):
            self.openstack_connector.resume_server("some_openstack_id")
        mock_logger_exception.assert_called_once_with(
            "Resume Server some_openstack_id failed!"
        )

    @patch.object(OpenStackConnector, "_calculate_vm_ports")
    @patch.object(OpenStackConnector, "get_image")
    @patch.object(OpenStackConnector, "get_flavor")
    @patch.object(OpenStackConnector, "netcat")
    def test_get_server(
        self, mock_netcat, mock_get_flavor, mock_get_image, mock_calculate_ports
    ):
        # Arrange
        openstack_id = "your_openstack_id"
        server_mock = fakes.generate_fake_resource(server.Server)
        server_mock.vm_state = VmStates.ACTIVE.value
        image_mock = fakes.generate_fake_resource(image.Image)
        server_mock.image = image_mock
        flavor_mock = fakes.generate_fake_resource(flavor.Flavor)
        server_mock.flavor = flavor_mock

        # Mocking the methods and attributes
        self.openstack_connector.openstack_connection.get_server_by_id.return_value = (
            server_mock
        )
        mock_get_image.return_value = image_mock
        mock_get_flavor.return_value = flavor_mock
        mock_calculate_ports.return_value = (30111, 30111)
        mock_netcat.return_value = True  # Assuming SSH connection is successful

        # Act
        self.openstack_connector.get_server(openstack_id)

        # Assert
        self.openstack_connector.openstack_connection.get_server_by_id.assert_called_once_with(
            id=openstack_id
        )
        mock_calculate_ports.assert_called_once_with(server=server_mock)
        mock_netcat.assert_called_once_with(
            host=self.openstack_connector.GATEWAY_IP, port=30111
        )
        mock_get_image.assert_called_once_with(
            name_or_id=image_mock.id,
            ignore_not_active=True,
            ignore_not_found=True,
        )
        mock_get_flavor.assert_called_once_with(name_or_id=flavor_mock.id)
        mock_netcat.return_value = False  # Assuming SSH connection is successful
        # Act
        result_server = self.openstack_connector.get_server(openstack_id)
        self.assertEqual(
            result_server.task_state, VmTaskStates.CHECKING_SSH_CONNECTION.value
        )

    def test_get_server_not_found(self):
        self.openstack_connector.openstack_connection.get_server_by_id.return_value = (
            None
        )

        with self.assertRaises(ServerNotFoundException):
            self.openstack_connector.get_server("someid")

    def test_get_server_openstack_exception(self):
        self.openstack_connector.openstack_connection.get_server_by_id.side_effect = (
            OpenStackCloudException("UNit Test")
        )

        with self.assertRaises(DefaultException):
            self.openstack_connector.get_server("someid")

    @patch.object(OpenStackConnector, "get_server")
    def test_set_server_metadata_success(self, mock_get_server):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)
        mock_get_server.return_value = server_mock
        metadata = {"data": "123"}
        # Act
        self.openstack_connector.set_server_metadata(server_mock.id, metadata)

        # Assert
        # Ensure the stop_server method is called with the correct server
        self.openstack_connector.openstack_connection.compute.set_server_metadata.assert_called_once_with(
            server_mock, metadata
        )

    @patch.object(OpenStackConnector, "get_server")
    def test_set_server_metadata_exception(self, mock_get_server):
        # Arrange
        server_mock = fakes.generate_fake_resource(server.Server)
        mock_get_server.return_value = server_mock
        metadata = {"data": "123"}
        self.openstack_connector.openstack_connection.compute.set_server_metadata.side_effect = OpenStackCloudException(
            "Unit Tests"
        )
        # Act
        with self.assertRaises(DefaultException):
            self.openstack_connector.set_server_metadata(server_mock.id, metadata)

    @patch.object(OpenStackConnector, "get_server")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_reboot_server_conflict_exception(
        self, mock_logger_exception, mock_get_server
    ):
        self.openstack_connector.openstack_connection.compute.reboot_server.side_effect = ConflictException(
            "Unit Test"
        )
        # Act
        with self.assertRaises(OpenStackConflictException):
            self.openstack_connector.reboot_server("some_openstack_id", "SOFT")
        mock_logger_exception.assert_called_once_with(
            f"Reboot Server some_openstack_id failed!"
        )

    def test_exist_server_true(self):
        server_mock = fakes.generate_fake_resource(server.Server)

        self.openstack_connector.openstack_connection.compute.find_server.return_value = (
            server_mock
        )

        result = self.openstack_connector.exist_server(server_mock.name)
        self.assertTrue(result)

    def test_exist_server_false(self):
        server_mock = fakes.generate_fake_resource(server.Server)

        self.openstack_connector.openstack_connection.compute.find_server.return_value = (
            None
        )

        result = self.openstack_connector.exist_server(server_mock.name)
        self.assertFalse(result)

    def test_get_or_create_project_security_group_exists(self):
        # Mock the get_security_group method to simulate an existing security group
        existing_security_group = fakes.generate_fake_resource(
            security_group.SecurityGroup
        )

        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            existing_security_group
        )

        # Call the method
        result = self.openstack_connector.get_or_create_project_security_group(
            "project_name", "project_id"
        )

        # Assertions
        self.assertEqual(result, existing_security_group.id)
        self.openstack_connector.openstack_connection.create_security_group.assert_not_called()

    def test_get_or_create_project_security_group_create_new(self):
        # Mock the get_security_group method to simulate a non-existing security group
        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            None
        )

        # Mock the create_security_group method to simulate creating a new security group
        new_security_group = fakes.generate_fake_resource(security_group.SecurityGroup)
        self.openstack_connector.openstack_connection.create_security_group.return_value = (
            new_security_group
        )

        # Call the method
        result = self.openstack_connector.get_or_create_project_security_group(
            "project_name", "project_id"
        )

        # Assertions
        self.assertEqual(result, new_security_group.id)
        self.openstack_connector.openstack_connection.create_security_group.assert_called_once()

    def test_get_or_create_vm_security_group_exist(self):
        # Mock the get_security_group method to simulate an existing security group
        existing_security_group = fakes.generate_fake_resource(
            security_group.SecurityGroup
        )

        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            existing_security_group
        )

        # Call the method
        result = self.openstack_connector.get_or_create_vm_security_group("server_id")

        # Assertions
        self.assertEqual(result, existing_security_group.id)
        self.openstack_connector.openstack_connection.create_security_group.assert_not_called()

    def test_get_or_create_vm_security_group_create_new(self):
        # Mock the get_security_group method to simulate a non-existing security group
        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            None
        )

        # Mock the create_security_group method to simulate creating a new security group
        new_security_group = fakes.generate_fake_resource(security_group.SecurityGroup)
        self.openstack_connector.openstack_connection.create_security_group.return_value = (
            new_security_group
        )

        # Call the method
        result = self.openstack_connector.get_or_create_vm_security_group(
            "openstack_id"
        )

        # Assertions
        self.assertEqual(result, new_security_group.id)
        self.openstack_connector.openstack_connection.create_security_group.assert_called_once()

    def test_get_or_create_research_environment_security_group_exist(self):
        # Mock the get_security_group method to simulate an existing security group
        existing_security_group = fakes.generate_fake_resource(
            security_group.SecurityGroup
        )

        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            existing_security_group
        )

        # Call the method
        result = (
            self.openstack_connector.get_or_create_research_environment_security_group(
                resenv_metadata=METADATA_EXAMPLE
            )
        )

        # Assertions
        self.assertEqual(result, existing_security_group.id)
        self.openstack_connector.openstack_connection.create_security_group.assert_not_called()

    def test_get_or_create_research_environment_no_forc_support(self):
        # Mock the get_security_group method to simulate a non-existing security group
        self.openstack_connector.get_or_create_research_environment_security_group(
            resenv_metadata=METADATA_EXAMPLE_NO_FORC
        )
        self.openstack_connector.openstack_connection.get_security_group.assert_not_called()

    def test_get_or_create_research_environment_security_group_new(self):
        # Mock the get_security_group method to simulate a non-existing security group
        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            None
        )

        # Mock the create_security_group method to simulate creating a new security group
        new_security_group = fakes.generate_fake_resource(security_group.SecurityGroup)
        self.openstack_connector.openstack_connection.create_security_group.return_value = (
            new_security_group
        )

        # Call the method
        result = (
            self.openstack_connector.get_or_create_research_environment_security_group(
                resenv_metadata=METADATA_EXAMPLE
            )
        )

        # Assertions
        self.assertEqual(result, new_security_group.id)
        self.openstack_connector.openstack_connection.create_security_group.assert_called_once()

    def test_is_security_group_in_use_instances(self):
        # Mock the compute.servers method to simulate instances using the security group
        instances = [{"id": "instance_id", "name": "instance_name"}]
        self.openstack_connector.openstack_connection.compute.servers = MagicMock(
            return_value=instances
        )

        # Call the method
        result = self.openstack_connector.is_security_group_in_use("security_group_id")

        # Assertions
        self.assertTrue(result)

    def test_is_security_group_in_use_ports(self):
        # Mock the network.ports method to simulate ports associated with the security group
        ports = [{"id": "port_id", "name": "port_name"}]
        self.openstack_connector.openstack_connection.compute.servers.return_value = []
        self.openstack_connector.openstack_connection.network.ports.return_value = ports

        # Call the method
        result = self.openstack_connector.is_security_group_in_use("security_group_id")

        # Assertions
        self.assertTrue(result)

    def test_is_security_group_in_use_load_balancers(self):
        # Mock the network.load_balancers method to simulate load balancers associated with the security group
        load_balancers = [{"id": "lb_id", "name": "lb_name"}]
        self.openstack_connector.openstack_connection.compute.servers.return_value = []
        self.openstack_connector.openstack_connection.network.ports.return_value = []

        self.openstack_connector.openstack_connection.network.load_balancers.return_value = [
            1,
            2,
        ]

        # Call the method
        result = self.openstack_connector.is_security_group_in_use("security_group_id")

        # Assertions
        self.assertTrue(result)

    def test_is_security_group_not_in_use(self):
        # Mock both compute.servers and network.ports methods to simulate no usage of the security group
        self.openstack_connector.openstack_connection.compute.servers = MagicMock(
            return_value=[]
        )
        self.openstack_connector.openstack_connection.network.ports = MagicMock(
            return_value=[]
        )
        self.openstack_connector.openstack_connection.network.load_balancers = (
            MagicMock(return_value=[])
        )

        # Call the method
        result = self.openstack_connector.is_security_group_in_use("security_group_id")

        # Assertions
        self.assertFalse(result)

    def test_create_security_group_exist(self):
        fake_sg = fakes.generate_fake_resource(security_group.SecurityGroup)
        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            fake_sg
        )
        # Call the method
        result = self.openstack_connector.create_security_group(
            name=fake_sg.name,
            udp_port=1234,
            ssh=True,
            udp=True,
            description=fake_sg.description,
            research_environment_metadata=METADATA_EXAMPLE,
        )
        self.assertEqual(result, fake_sg)

    def test_create_security_group(self):
        # Mock the get_security_group method to simulate non-existing security group
        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            None
        )

        # Mock the create_security_group method to return a fake SecurityGroup
        fake_sg = fakes.generate_fake_resource(security_group.SecurityGroup)
        self.openstack_connector.openstack_connection.create_security_group.return_value = (
            fake_sg
        )

        # Call the method
        result = self.openstack_connector.create_security_group(
            name=fake_sg.name,
            udp_port=1234,
            ssh=True,
            udp=True,
            description=fake_sg.description,
            research_environment_metadata=METADATA_EXAMPLE,
        )

        # Assertions
        self.assertEqual(result, fake_sg)
        self.openstack_connector.openstack_connection.create_security_group.assert_called_once_with(
            name=fake_sg.name, description=fake_sg.description
        )
        self.openstack_connector.openstack_connection.create_security_group_rule.assert_any_call(
            direction="ingress",
            protocol="udp",
            port_range_max=1234,
            port_range_min=1234,
            secgroup_name_or_id=fake_sg.id,
            remote_group_id=self.openstack_connector.GATEWAY_SECURITY_GROUP_ID,
        )
        self.openstack_connector.openstack_connection.create_security_group_rule.assert_any_call(
            direction="ingress",
            protocol="udp",
            ethertype="IPv6",
            port_range_max=1234,
            port_range_min=1234,
            secgroup_name_or_id=fake_sg.id,
            remote_group_id=self.openstack_connector.GATEWAY_SECURITY_GROUP_ID,
        )

        self.openstack_connector.openstack_connection.create_security_group_rule.assert_any_call(
            direction="ingress",
            protocol="tcp",
            port_range_max=22,
            port_range_min=22,
            secgroup_name_or_id=fake_sg.id,
            remote_group_id=self.openstack_connector.GATEWAY_SECURITY_GROUP_ID,
        )
        self.openstack_connector.openstack_connection.create_security_group_rule.assert_any_call(
            direction="ingress",
            protocol="tcp",
            ethertype="IPv6",
            port_range_max=22,
            port_range_min=22,
            secgroup_name_or_id=fake_sg.id,
            remote_group_id=self.openstack_connector.GATEWAY_SECURITY_GROUP_ID,
        )

    def test_open_port_range_for_vm_in_project_exception(self):
        with self.assertRaises(DefaultException):
            self.openstack_connector.open_port_range_for_vm_in_project(
                range_start=1000,
                range_stop=1000,
                openstack_id="wewqeq",
                ethertype="IPV7",
                protocol="TCP",
            )

    @patch.object(OpenStackConnector, "get_or_create_project_security_group")
    @patch.object(OpenStackConnector, "get_or_create_vm_security_group")
    @patch.object(OpenStackConnector, "get_server")
    @patch("simple_vm_client.openstack_connector.openstack_connector.logger.exception")
    def test_open_port_range_for_vm_in_project_conflict_exception(
        self, mock_logger_exception, mock_get_server, mock_get_vm_sg, mock_get_proj_sg
    ):
        fake_server = fakes.generate_fake_resource(server.Server)

        fake_project_sg = fakes.generate_fake_resource(security_group.SecurityGroup)
        fake_vm_sg = fakes.generate_fake_resource(security_group.SecurityGroup)
        fake_sg_rule = fakes.generate_fake_resource(
            security_group_rule.SecurityGroupRule
        )
        fake_server.security_groups = [fake_vm_sg, fake_project_sg]
        fake_server.metadata = {
            "project_name": "fake_project",
            "project_id": "fake_project_id",
        }
        mock_get_server.return_value = fake_server
        self.openstack_connector.openstack_connection.create_security_group_rule.return_value = (
            fake_sg_rule
        )

        self.openstack_connector.openstack_connection.create_security_group_rule.side_effect = ConflictException(
            "Unit Test"
        )
        with self.assertRaises(OpenStackConflictException):
            self.openstack_connector.open_port_range_for_vm_in_project(
                range_start=1000, range_stop=1000, openstack_id="test"
            )
        mock_logger_exception.assert_called_once_with(
            f"Could not create security group rule for instance test"
        )

    @patch.object(OpenStackConnector, "get_or_create_project_security_group")
    @patch.object(OpenStackConnector, "get_or_create_vm_security_group")
    @patch.object(OpenStackConnector, "get_server")
    def test_open_port_range_for_vm_in_project(
        self,
        mock_get_server,
        mock_get_vm_sg,
        mock_get_proj_sg,
    ):
        # Mock the get_server_by_id method to return a fake Server
        fake_server = fakes.generate_fake_resource(server.Server)

        fake_project_sg = fakes.generate_fake_resource(security_group.SecurityGroup)
        fake_vm_sg = fakes.generate_fake_resource(security_group.SecurityGroup)
        fake_sg_rule = fakes.generate_fake_resource(
            security_group_rule.SecurityGroupRule
        )
        fake_server.security_groups = [fake_vm_sg, fake_project_sg]
        fake_server.metadata = {
            "project_name": "fake_project",
            "project_id": "fake_project_id",
        }
        mock_get_server.return_value = fake_server

        # Mock the get_or_create_project_security_group method to return a fake security group ID
        mock_get_proj_sg.return_value = fake_project_sg.id

        # Mock the get_or_create_vm_security_group method to return a fake security group ID
        mock_get_vm_sg.return_value = fake_vm_sg.id

        # Mock the create_security_group_rule method to return a fake security group rule
        self.openstack_connector.openstack_connection.create_security_group_rule.return_value = (
            fake_sg_rule
        )

        # Call the method
        result = self.openstack_connector.open_port_range_for_vm_in_project(
            range_start=1000,
            range_stop=2000,
            openstack_id=fake_server.id,
            ethertype="IPv4",
            protocol="TCP",
        )

        # Assertions
        self.assertEqual(fake_sg_rule, fake_sg_rule)
        mock_get_server.assert_called_once_with(openstack_id=fake_server.id)
        mock_get_proj_sg.assert_called_once_with(
            project_name="fake_project", project_id="fake_project_id"
        )
        mock_get_vm_sg.assert_called_once_with(openstack_id=fake_server.id)
        self.openstack_connector.openstack_connection.add_server_security_groups.assert_called_once_with(
            server=fake_server, security_groups=[fake_vm_sg.id]
        )

    def test_create_or_get_default_ssh_security_group_exists(self):
        # Mock the get_security_group method to simulate an existing security group
        existing_security_group = fakes.generate_fake_resource(
            security_group.SecurityGroup
        )

        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            existing_security_group
        )

        # Call the method
        result = self.openstack_connector.create_or_get_default_ssh_security_group()

        # Assertions
        self.assertEqual(result.id, existing_security_group.id)
        self.openstack_connector.openstack_connection.create_security_group.assert_not_called()

    def test_create_or_get_default_ssh_security_group_create_new(self):
        # Mock the get_security_group method to simulate a non-existing security group
        self.openstack_connector.openstack_connection.get_security_group.return_value = (
            None
        )

        # Mock the create_security_group method to simulate creating a new security group
        new_security_group = fakes.generate_fake_resource(security_group.SecurityGroup)
        self.openstack_connector.openstack_connection.create_security_group.return_value = (
            new_security_group
        )

        # Call the method
        result = self.openstack_connector.create_or_get_default_ssh_security_group()

        # Assertions
        self.assertEqual(result.id, new_security_group.id)
        self.openstack_connector.openstack_connection.create_security_group.assert_called_once()

    @patch("simple_vm_client.openstack_connector.openstack_connector.os.path.dirname")
    @patch("simple_vm_client.openstack_connector.openstack_connector.os.path.abspath")
    @patch("simple_vm_client.openstack_connector.openstack_connector.os.path.join")
    @patch(
        "simple_vm_client.openstack_connector.openstack_connector.open",
        new_callable=unittest.mock.mock_open,
        read_data="mock_script_content",
    )
    def test_create_mount_init_script(
        self, mock_open, mock_join, mock_abspath, mock_dirname
    ):
        # Mock the relevant parts for os.path operations
        mock_abspath.return_value = "/mock/absolute/path"
        mock_dirname.return_value = "/mock/directory"
        mock_join.return_value = "/mock/join/path"

        # Call the method with sample volume data
        result = self.openstack_connector.create_mount_init_script(
            new_volumes=[{"openstack_id": "vol_id_1", "path": "/path_1"}],
            attach_volumes=[{"openstack_id": "vol_id_2", "path": "/path_2"}],
        )

        # Assertions
        self.assertEqual(result, b"mock_script_content")
        mock_open.assert_called_once_with("/mock/join/path", "r")
        mock_open().read.assert_called_once()

    def test_create_mount_init_script_no_volumes(self):
        result = self.openstack_connector.create_mount_init_script(
            new_volumes=None, attach_volumes=None
        )
        self.assertEqual(result, "")

    def test_create_mount_init_script_no_new_volumes(self):
        result = self.openstack_connector.create_mount_init_script(
            new_volumes=None,
            attach_volumes=[{"openstack_id": "vol_id_1", "path": "/path_1"}],
        )
        self.assertIn(b"vol_id_1", result)

    def test_create_mount_init_script_no_attach_volumes(self):
        result = self.openstack_connector.create_mount_init_script(
            new_volumes=[{"openstack_id": "vol_id_2", "path": "/path_2"}],
            attach_volumes=None,
        )
        self.assertIn(b"vol_id_2", result)

    def test_delete_security_group_rule_sucess(self):
        self.openstack_connector.openstack_connection.delete_security_group_rule.return_value = (
            True
        )
        self.openstack_connector.delete_security_group_rule("rule_id")
        self.openstack_connector.openstack_connection.delete_security_group_rule.assert_called_once_with(
            rule_id="rule_id"
        )

    def test_delete_security_group_rule_failure(self):
        self.openstack_connector.openstack_connection.delete_security_group_rule.return_value = (
            False
        )
        with self.assertRaises(DefaultException):
            self.openstack_connector.delete_security_group_rule("rule_id")
            self.openstack_connector.openstack_connection.delete_security_group_rule.assert_called_once_with(
                rule_id="rule_id"
            )

    def test_get_gateway_ip(self):
        result = self.openstack_connector.get_gateway_ip()
        self.assertEqual(result, {"gateway_ip": self.openstack_connector.GATEWAY_IP})

    def test_get_calculation_values(self):
        result = self.openstack_connector.get_calculation_values()
        self.assertEqual(
            result,
            {
                "SSH_PORT_CALCULATION": self.openstack_connector.SSH_PORT_CALCULATION,
                "UDP_PORT_CALCULATION": self.openstack_connector.UDP_PORT_CALCULATION,
            },
        )

    def test_create_volume_by_volume_snap_exception(self):
        fake_source_volume = fakes.generate_fake_resource(volume.Volume)
        fake_result_volume = fakes.generate_fake_resource(volume.Volume)

        self.openstack_connector.openstack_connection.block_storage.create_volume.side_effect = ResourceFailure(
            "UNit Test"
        )
        with self.assertRaises(ResourceNotAvailableException):
            self.openstack_connector.create_volume_by_volume_snap(
                volume_name=fake_result_volume.name,
                metadata={"data": "data"},
                volume_snap_id=fake_source_volume.id,
            )

    def test_create_volume_by_volume_snap(self):
        fake_source_volume = fakes.generate_fake_resource(volume.Volume)
        fake_result_volume = fakes.generate_fake_resource(volume.Volume)

        self.openstack_connector.openstack_connection.block_storage.create_volume.return_value = (
            fake_result_volume
        )
        result = self.openstack_connector.create_volume_by_volume_snap(
            volume_name=fake_result_volume.name,
            metadata={"data": "data"},
            volume_snap_id=fake_source_volume.id,
        )
        self.assertEqual(result, fake_result_volume)

    def test_create_volume_by_source_volume(self):
        fake_source_volume = fakes.generate_fake_resource(volume.Volume)
        fake_result_volume = fakes.generate_fake_resource(volume.Volume)
        self.openstack_connector.openstack_connection.block_storage.create_volume.return_value = (
            fake_result_volume
        )
        result = self.openstack_connector.create_volume_by_source_volume(
            volume_name=fake_result_volume.name,
            metadata={"data": "data"},
            source_volume_id=fake_source_volume.id,
        )
        self.assertEqual(result, fake_result_volume)

    def test_create_create_volume_by_source_volume_exception(self):
        fake_source_volume = fakes.generate_fake_resource(volume.Volume)
        fake_result_volume = fakes.generate_fake_resource(volume.Volume)

        self.openstack_connector.openstack_connection.block_storage.create_volume.side_effect = ResourceFailure(
            "UNit Test"
        )
        with self.assertRaises(ResourceNotAvailableException):
            self.openstack_connector.create_volume_by_source_volume(
                volume_name=fake_result_volume.name,
                metadata={"data": "data"},
                source_volume_id=fake_source_volume.id,
            )

    @patch(
        "simple_vm_client.openstack_connector.openstack_connector.connection.Connection"
    )
    def test___init__(self, mock_authorize):
        # Mock the relevant parts for file operations and connection

        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_file.write(CONFIG_DATA)
            # Call the __init__ method
        OpenStackConnector(config_file=temp_file.name)
        os.remove(temp_file.name)
        # Assertions

        mock_authorize.assert_called_once()

    def test___init__failed_auth(self):
        # Mock the relevant parts for file operations and connection

        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_file.write(CONFIG_DATA)
            # Call the __init__ method
        with self.assertRaises(Exception):
            OpenStackConnector(config_file=temp_file.name)
        os.remove(temp_file.name)
        # Assertions

    @patch.dict(
        os.environ,
        {
            "USE_APPLICATION_CREDENTIALS": "True",
            "OS_APPLICATION_CREDENTIAL_ID": "APP_ID",
            "OS_APPLICATION_CREDENTIAL_SECRET": "APP_SECRET",
        },
    )
    @patch(
        "simple_vm_client.openstack_connector.openstack_connector.connection.Connection"
    )
    def test___init__os_creds(self, mock_authorize):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_file.write(CONFIG_DATA)
            # Call the __init__ method
        OpenStackConnector(config_file=temp_file.name)
        os.remove(temp_file.name)
        # Assertions

        mock_authorize.assert_called_once()


if __name__ == "__main__":
    unittest.main()
