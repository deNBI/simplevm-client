import inspect
import os
import tempfile
import unittest
from unittest import mock
from unittest.mock import MagicMock, patch, call

from openstack.block_storage.v3.volume import Volume
from openstack.cloud import OpenStackCloudException
from openstack.exceptions import ResourceNotFound, ConflictException, ResourceFailure

from openstack_connector.openstack_connector import OpenStackConnector
from openstack.test import fakes
from openstack.compute.v2 import limits, server
from openstack.compute.v2.image import Image
from openstack.block_storage.v3.limits import Limit
from openstack.image.v2 import image as image_module
from ttypes import ImageNotFoundException, VolumeNotFoundException, DefaultException, SnapshotNotFoundException, \
    ResourceNotAvailableException
from openstack.compute import compute_service
from openstack.compute.v2.server import Server
EXPECTED_IMAGE = image_module.Image(id='image_id_2', status='active', name="image_2",
                                    metadata={'os_version': '22.04', 'os_distro': 'ubuntu'}, tags=["portalclient"])
INACTIVE_IMAGE = image_module.Image(id='image_inactive', status='building', name="image_inactive",
                                    metadata={'os_version': '22.04', 'os_distro': 'ubuntu'}, tags=["portalclient"])

IMAGES = [
    image_module.Image(id='image_id_1', status='inactive', name="image_1", metadata={'os_version': '22.04', 'os_distro': 'ubuntu'},
                       tags=["portalclient"]),
    EXPECTED_IMAGE,
    image_module.Image(id='image_id_3', status='active', name="image_3", metadata={'os_version': '22.04', 'os_distro': 'centos'},
                       tags=["portalclient"]),
    INACTIVE_IMAGE
]
DEFAULT_SECURITY_GROUPS =["defaultSimpleVM"]


class TestOpenStackConnector(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.env_patcher = mock.patch.dict(os.environ, {
        "OS_AUTH_URL": "https://example.com",
        "OS_USERNAME": "username",
        "OS_PASSWORD": "password",
        "OS_PROJECT_NAME": "project_name",
        "OS_PROJECT_ID": "project_id",
        "OS_USER_DOMAIN_NAME": "user_domain",
        "OS_PROJECT_DOMAIN_ID": "project_domain_id",
        "USE_APPLICATION_CREDENTIALS": "False"}
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
            self.openstack_connector.openstack_connection = self.mock_openstack_connection
            self.openstack_connector.DEFAULT_SECURITY_GROUPS=DEFAULT_SECURITY_GROUPS

    def init_openstack_connector(self):
        with patch.object(OpenStackConnector, "__init__", lambda x, y, z: None):
            openstack_connector = OpenStackConnector(None, None)
            openstack_connector.openstack_connection = self.mock_openstack_connection
            openstack_connector.DEFAULT_SECURITY_GROUPS = DEFAULT_SECURITY_GROUPS
        return openstack_connector
    def test_load_config_yml(self):
        # Create a temporary YAML file with sample configuration
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
            temp_file.write("""
            openstack:
              gateway_ip: "192.168.1.1"
              network: "my_network"
              sub_network: "my_sub_network"
              cloud_site: "my_cloud_site"
              ssh_port_calculation: 22
              udp_port_calculation: 12345
              gateway_security_group_id: "security_group_id"
            production: true
            forc:
              forc_security_group_id: "forc_security_group_id"
            """)

        # Call the load_config_yml method with the temporary file path
        self.openstack_connector.load_config_yml(temp_file.name)

        # Assert that the configuration attributes are set correctly
        self.assertEqual(self.openstack_connector.GATEWAY_IP, "192.168.1.1")
        self.assertEqual(self.openstack_connector.NETWORK, "my_network")
        self.assertEqual(self.openstack_connector.SUB_NETWORK, "my_sub_network")
        self.assertTrue(self.openstack_connector.PRODUCTION)
        self.assertEqual(self.openstack_connector.CLOUD_SITE, "my_cloud_site")
        self.assertEqual(self.openstack_connector.SSH_PORT_CALCULATION, 22)
        self.assertEqual(self.openstack_connector.UDP_PORT_CALCULATION, 12345)
        self.assertEqual(self.openstack_connector.FORC_SECURITY_GROUP_ID, "forc_security_group_id")

    @patch('openstack_connector.openstack_connector.logger')
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

    @patch('openstack_connector.openstack_connector.logger')
    @patch.dict(os.environ, {
        "OS_AUTH_URL": "https://example.com",
        "USE_APPLICATION_CREDENTIALS": "True",
        "OS_APPLICATION_CREDENTIAL_ID": "app_cred_id",
        "OS_APPLICATION_CREDENTIAL_SECRET": "app_cred_secret"
    })
    def test_load_env_config_application_credentials(self, mock_logger):
        # Create an instance of OpenStackConnector
        openstack_connector = self.init_openstack_connector()

        # Call the load_env_config method
        openstack_connector.load_env_config()

        # Assert that attributes are set correctly for application credentials
        self.assertEqual(openstack_connector.AUTH_URL, "https://example.com")
        self.assertTrue(openstack_connector.USE_APPLICATION_CREDENTIALS)
        self.assertEqual(openstack_connector.APPLICATION_CREDENTIAL_ID, "app_cred_id")
        self.assertEqual(openstack_connector.APPLICATION_CREDENTIAL_SECRET, "app_cred_secret")

        # Assert that logger.info was called with the expected messages
        expected_calls = [
            call("Load environment config: OpenStack"),
            call("APPLICATION CREDENTIALS will be used!")
        ]
        mock_logger.info.assert_has_calls(expected_calls, any_order=False)
    @patch('openstack_connector.openstack_connector.logger')
    @patch.dict(os.environ, {
        "OS_AUTH_URL": ""})
    def test_load_env_config_missing_os_auth_url(self, mock_logger):
        openstack_connector = self.init_openstack_connector()

        # Mock sys.exit to capture the exit status
        with patch('sys.exit') as mock_exit:
            # Call the load_env_config method
            openstack_connector.load_env_config()
        # Assert that logger.error was called with the expected message
        mock_logger.error.assert_called_once_with("OS_AUTH_URL not provided in env!")

        # Assert that sys.exit was called with status code 1
        mock_exit.assert_called_once_with(1)
    @patch('openstack_connector.openstack_connector.logger')
    @patch.dict(os.environ, {"USE_APPLICATION_CREDENTIALS": "True"})
    def test_load_env_config_missing_app_cred_vars(self, mock_logger):
        # Create an instance of OpenStackConnector
        openstack_connector = self.init_openstack_connector()

        # Mock sys.exit to capture the exit status
        with patch('sys.exit') as mock_exit:
            # Call the load_env_config method
            openstack_connector.load_env_config()

        # Assert that logger.error was called with the expected message
        expected_error_message = "Usage of Application Credentials enabled - but OS_APPLICATION_CREDENTIAL_ID not provided in env!"
        mock_logger.error.assert_called_once_with(expected_error_message)

        # Assert that sys.exit was called with status code 1
        mock_exit.assert_called_once_with(1)

    @patch('openstack_connector.openstack_connector.logger')
    @patch.dict(os.environ, {
        "USE_APPLICATION_CREDENTIALS": "False",
        "OS_USERNAME": "test_username",
        "OS_PASSWORD": "test_password",
        "OS_PROJECT_NAME": "test_project_name",
        "OS_PROJECT_ID": "test_project_id",
        "OS_USER_DOMAIN_NAME": "test_user_domain",
        "OS_PROJECT_DOMAIN_ID": "test_project_domain"
    })
    def test_load_env_config_missing_username_password_vars(self, mock_logger):
        # Create an instance of OpenStackConnector using the helper method
        openstack_connector = self.init_openstack_connector()

        # Remove required environment variables
        del os.environ["OS_USERNAME"]
        del os.environ["OS_PASSWORD"]

        # Mock sys.exit to capture the exit status
        with patch('sys.exit') as mock_exit:
            # Call the load_env_config method
            openstack_connector.load_env_config()

        # Assert that logger.error was called with the expected message
        expected_error_message = "Usage of Username/Password enabled - but keys OS_USERNAME, OS_PASSWORD not provided in env!"
        mock_logger.error.assert_called_once_with(expected_error_message)

        # Assert that sys.exit was called with status code 1
        mock_exit.assert_called_once_with(1)
    def test_get_default_security_groups(self):
        # Call the _get_default_security_groups method
        default_security_groups = self.openstack_connector._get_default_security_groups()

        # Assert that the returned list is a copy of the DEFAULT_SECURITY_GROUPS attribute
        self.assertEqual(default_security_groups, self.openstack_connector.DEFAULT_SECURITY_GROUPS)

        # Assert that modifying the returned list does not affect the DEFAULT_SECURITY_GROUPS attribute
        default_security_groups.append("new_security_group")
        self.assertNotEqual(default_security_groups, self.openstack_connector.DEFAULT_SECURITY_GROUPS)

    def test_get_image(self):
        self.mock_openstack_connection.get_image.return_value = EXPECTED_IMAGE
        result = self.openstack_connector.get_image(EXPECTED_IMAGE.id)
        self.assertEqual(result, EXPECTED_IMAGE)


    def test_get_image_not_found_exception(self):
        # Configure the mock_openstack_connection.get_image to return None
        self.mock_openstack_connection.get_image.return_value = None

        # Configure the ImageNotFoundException to be raised
        with self.assertRaises(ImageNotFoundException) as context:
            # Call the method with an image ID that will not be found
            self.openstack_connector.get_image('nonexistent_id', ignore_not_found=False)

        # Assert that the exception contains the expected message and image ID
        self.assertEqual(
            context.exception.message,
            "Image nonexistent_id not found!"
        )

    def test_get_image_not_active_exception(self):
        # Configure the mock_openstack_connection.get_image to return the not active image
        self.mock_openstack_connection.get_image.return_value = INACTIVE_IMAGE
        print(f"Name: {INACTIVE_IMAGE.name}")
        # Configure the ImageNotFoundException to be raised
        with self.assertRaises(ImageNotFoundException) as context:
            # Call the method with the not active image ID and set ignore_not_active to False
            self.openstack_connector.get_image(name_or_id=INACTIVE_IMAGE.name, ignore_not_active=False)

        # Assert that the exception contains the expected message and image ID
        self.assertEqual(
            context.exception.message,
            f"Image {INACTIVE_IMAGE.name} found but not active!"
        )

    def test_get_images(self):
        # Configure the mock_openstack_connection.image.images to return the fake images
        self.mock_openstack_connection.image.images.return_value = IMAGES

        # Call the method
        result = self.openstack_connector.get_images()

        # Assert that the method returns the expected result
        self.assertEqual(result, IMAGES)

    def test_get_active_image_by_os_version(self):
        # Generate a set of fake images with different properties

        # Configure the mock_openstack_connection.list_images to return the fake images
        self.mock_openstack_connection.list_images.return_value = IMAGES

        # Call the method with specific os_version and os_distro
        result = self.openstack_connector.get_active_image_by_os_version(os_version='22.04', os_distro='ubuntu')

        # Assert that the method returns the expected image
        self.assertEqual(result, EXPECTED_IMAGE)

    def test_get_active_image_by_os_version_not_found_exception(self):
        # Configure the mock_openstack_connection.list_images to return an empty list
        self.mock_openstack_connection.list_images.return_value = []

        # Configure the ImageNotFoundException to be raised
        with self.assertRaises(ImageNotFoundException) as context:
            # Call the method with an os_version and os_distro that won't find a matching image
            self.openstack_connector.get_active_image_by_os_version('nonexistent_version', 'nonexistent_distro')

        # Assert that the exception contains the expected message
        self.assertEqual(
            context.exception.message,
            "Old Image was deactivated! No image with os_version:nonexistent_version and os_distro:nonexistent_distro found!"
        )

    def test_replace_inactive_image(self):
        # Generate a fake image with status 'something other than active'

        self.mock_openstack_connection.list_images.return_value = IMAGES

        # Configure the mock_openstack_connection.get_image to return the inactive image
        self.mock_openstack_connection.get_image.return_value = INACTIVE_IMAGE

        # Call the method with the inactive image ID and set replace_inactive to True
        result = self.openstack_connector.get_image('inactive_id', replace_inactive=True)

        # Assert that the method returns the replacement image
        self.assertEqual(result, EXPECTED_IMAGE)

    @unittest.skip("Currently not working")
    def test_get_limits(self):
        compute_limits = fakes.generate_fake_resource(limits.AbsoluteLimits)
        volume_limits = fakes.generate_fake_resource(Limit)
        self.mock_openstack_connection.get_compute_limits.return_value = compute_limits
        self.mock_openstack_connection.get_volume_limits.return_value = volume_limits
        result = self.openstack_connector.get_limits()

    @patch("openstack_connector.openstack_connector.logger.info")
    @patch("openstack_connector.openstack_connector.logger.error")
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
        print(f"test : {fake_server}")
        self.mock_openstack_connection.create_server.return_value = fake_server

        # Call the create_server method
        result = self.openstack_connector.create_server(
            name, image_id, flavor_id, network_id, userdata, key_name,
            metadata, security_groups
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

    @patch("openstack_connector.openstack_connector.logger.info")
    @patch("openstack_connector.openstack_connector.logger.exception")
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
        self.mock_openstack_connection.get_volume.assert_called_once_with(name_or_id=name_or_id)

        # Check if the method returns the fake volume object
        self.assertEqual(result, fake_volume)

    @patch("openstack_connector.openstack_connector.logger.exception")
    def test_get_volume_exception(self, mock_logger_exception):
        # Prepare test data
        name_or_id = "non_existing_volume_id"

        # Mock the get_volume method to return None
        self.mock_openstack_connection.get_volume.return_value = None

        # Call the get_volume method and expect a VolumeNotFoundException
        with self.assertRaises(Exception):  # Replace Exception with the actual exception type
            self.openstack_connector.get_volume(name_or_id)

        # Check if the method logs the correct exception information
        mock_logger_exception.assert_called_once_with(f"No Volume with id {name_or_id}")

    @patch("openstack_connector.openstack_connector.logger.info")
    @patch("openstack_connector.openstack_connector.logger.exception")
    def test_delete_volume(self, mock_logger_exception, mock_logger_info):
        # Prepare test data
        volume_id = "test_volume_id"

        # Mock the delete_volume method to avoid actual deletion in the test
        self.mock_openstack_connection.delete_volume.side_effect = [
            None,  # No exception case
            ResourceNotFound(message="Volume not found"),  # VolumeNotFoundException case
            ConflictException(message="Delete volume failed"),  # OpenStackCloudException case
            OpenStackCloudException(message="Some other exception")  # DefaultException case
        ]

        # Call the delete_volume method for different scenarios
        # 1. No exception
        self.openstack_connector.delete_volume(volume_id)
        mock_logger_info.assert_called_once_with(f"Delete Volume {volume_id}")
        mock_logger_exception.assert_not_called()

        # 2. ResourceNotFound, expect VolumeNotFoundException
        with self.assertRaises(VolumeNotFoundException):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume(volume_id)
        mock_logger_exception.assert_called_with(f"No Volume with id {volume_id}")

        # 3. ConflictException, expect OpenStackCloudException
        with self.assertRaises(OpenStackCloudException):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume(volume_id)
        mock_logger_exception.assert_called_with(f"Delete volume: {volume_id}) failed!")

        # 4. OpenStackCloudException, expect DefaultException
        with self.assertRaises(DefaultException):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume(volume_id)

    @patch("openstack_connector.openstack_connector.logger.info")
    @patch("openstack_connector.openstack_connector.logger.error")
    def test_create_volume_snapshot(self, mock_logger_error, mock_logger_info):
        # Prepare test data
        volume_id = "test_volume_id"
        snapshot_name = "test_snapshot"
        snapshot_description = "Test snapshot description"

        # Mock the create_volume_snapshot method to avoid actual creation in the test
        self.mock_openstack_connection.create_volume_snapshot.side_effect = [
            {"id": "snapshot_id"},  # No exception case
            ResourceNotFound(message="Volume not found"),  # VolumeNotFoundException case
            OpenStackCloudException(message="Some other exception")  # DefaultException case
        ]

        # Call the create_volume_snapshot method for different scenarios
        # 1. No exception
        snapshot_id = self.openstack_connector.create_volume_snapshot(
            volume_id, snapshot_name, snapshot_description
        )
        self.assertEqual(snapshot_id, "snapshot_id")
        mock_logger_info.assert_called_once_with(f"Create Snapshot for Volume {volume_id}")

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


    @patch("openstack_connector.openstack_connector.logger.info")
    @patch("openstack_connector.openstack_connector.logger.exception")
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
        mock_logger_exception.assert_called_with(f"No volume Snapshot with id {snapshot_id}")

    @patch("openstack_connector.openstack_connector.logger.info")
    @patch("openstack_connector.openstack_connector.logger.exception")
    def test_delete_volume_snapshot(self, mock_logger_exception, mock_logger_info):
        # Prepare test data
        snapshot_id = "test_snapshot_id"

        # Mock the delete_volume_snapshot method to avoid actual deletion in the test
        self.mock_openstack_connection.delete_volume_snapshot.side_effect = [
            None,  # No exception case
            ResourceNotFound(message="Snapshot not found"),  # SnapshotNotFoundException case
            ConflictException(message="Delete snapshot failed"),  # OpenStackCloudException case
            OpenStackCloudException(message="Some other exception")  # DefaultException case
        ]

        # Call the delete_volume_snapshot method for different scenarios
        # 1. No exception
        self.openstack_connector.delete_volume_snapshot(snapshot_id)
        mock_logger_info.assert_called_once_with(f"Delete volume Snapshot {snapshot_id}")

        # 2. ResourceNotFound, expect SnapshotNotFoundException
        with self.assertRaises(SnapshotNotFoundException):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume_snapshot(snapshot_id)
        mock_logger_exception.assert_called_with(f"Snapshot not found: {snapshot_id}")

        # 3. ConflictException, expect OpenStackCloudException
        with self.assertRaises(OpenStackCloudException):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume_snapshot(snapshot_id)
        mock_logger_exception.assert_called_with(f"Delete volume snapshot: {snapshot_id}) failed!")

        # 4. OpenStackCloudException, expect DefaultException
        with self.assertRaises(DefaultException):  # Replace Exception with the actual exception type
            self.openstack_connector.delete_volume_snapshot(snapshot_id)

    @patch("openstack_connector.openstack_connector.logger.info")
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
    @patch("openstack_connector.openstack_connector.logger.error")
    @patch("openstack_connector.openstack_connector.logger.exception")
    @patch("openstack_connector.openstack_connector.logger.info")
    def test_get_servers_by_ids(self, mock_logger_info, mock_logger_exception, mock_logger_error):
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
        #mock_logger_info.assert_any_call(f"Get Servers by IDS : {server_ids}")
        mock_logger_info.assert_any_call("Get server id1")
        mock_logger_info.assert_any_call("Get server id2")
        mock_logger_info.assert_any_call("Get server id3")
        mock_logger_info.assert_any_call("Get server id4")
        mock_logger_error.assert_called_once_with("Requested VM id3 not found!")
        mock_logger_exception.assert_called_once_with("Requested VM id4 not found!\n ")

if __name__ == "__main__":
    unittest.main()
