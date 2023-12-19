import unittest
from unittest.mock import MagicMock, patch
from openstack_connector.openstack_connector import OpenStackConnector
from openstack.test import fakes
from openstack.compute.v2 import limits
from openstack.compute.v2.image import Image
from openstack.block_storage.v3.limits import Limit
from openstack.image.v2 import image as image_module
from ttypes import ImageNotFoundException

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


class TestOpenStackConnector(unittest.TestCase):

    def setUp(self):
        # Create an instance of YourClass with a mocked openstack_connection
        self.mock_openstack_connection = MagicMock()
        with patch.object(OpenStackConnector, "__init__", lambda x, y, z: None):
            self.openstack_connector = OpenStackConnector(None, None)
            self.openstack_connector.openstack_connection = self.mock_openstack_connection

    def test_get_image(self):
        self.mock_openstack_connection.get_image.return_value = EXPECTED_IMAGE
        result = self.openstack_connector.get_image(EXPECTED_IMAGE.id)
        self.assertEqual(result, EXPECTED_IMAGE)

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


if __name__ == "__main__":
    unittest.main()
