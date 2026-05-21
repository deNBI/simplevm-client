"""Tests for FlavorResourceExporterConnector."""

import os
import unittest
from unittest.mock import MagicMock, patch

from simple_vm_client.flavor_resource_exporter_connector.flavor_resource_exporter_connector import (
    FlavorResourceExporterConnector,
)
from simple_vm_client.ttypes import FlavorResource


class TestFlavorResourceExporterConnector(unittest.TestCase):
    """Test cases for FlavorResourceExporterConnector."""

    def setUp(self):
        """Set up test fixtures."""
        # Clean up env vars before each test
        for key in [
            "FLAVOR_RESOURCE_EXPORTER_USERNAME",
            "FLAVOR_RESOURCE_EXPORTER_PASSWORD",
            "FLAVOR_RESOURCE_EXPORTER_ENDPOINT_URL",
        ]:
            os.environ.pop(key, None)

    @patch("builtins.open")
    @patch("yaml.load")
    def test_init_disabled_without_credentials(self, mock_yaml_load, mock_open):
        """Test that connector is disabled when no credentials are set."""
        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com",
            }
        }

        connector = FlavorResourceExporterConnector("config.yml")
        self.assertFalse(connector.enabled)

    @patch("builtins.open")
    @patch("yaml.load")
    def test_init_enabled_with_credentials(self, mock_yaml_load, mock_open):
        """Test that connector is enabled when credentials are set."""
        os.environ["FLAVOR_RESOURCE_EXPORTER_USERNAME"] = "testuser"
        os.environ["FLAVOR_RESOURCE_EXPORTER_PASSWORD"] = "testpass"

        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com",
                "timeout": 60,
            }
        }

        connector = FlavorResourceExporterConnector("config.yml")
        self.assertTrue(connector.enabled)
        self.assertEqual(connector.username, "testuser")
        self.assertEqual(connector.password, "testpass")
        self.assertEqual(connector.endpoint_url, "http://example.com")
        self.assertEqual(connector.timeout, 60)

    @patch("builtins.open")
    @patch("yaml.load")
    def test_fetch_flavor_resources_disabled(self, mock_yaml_load, mock_open):
        """Test that fetch returns empty list when disabled."""
        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": False,
                "endpoint_url": "http://example.com",
            }
        }

        connector = FlavorResourceExporterConnector("config.yml")
        result = connector.fetch_flavor_resources()
        self.assertEqual(result, [])

    @patch("requests.Session.get")
    @patch("builtins.open")
    @patch("yaml.load")
    def test_fetch_flavor_resources_success(self, mock_yaml_load, mock_open, mock_get):
        """Test successful fetch of flavor resources."""
        os.environ["FLAVOR_RESOURCE_EXPORTER_USERNAME"] = "testuser"
        os.environ["FLAVOR_RESOURCE_EXPORTER_PASSWORD"] = "testpass"

        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com/flavors",
            }
        }

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": "e50ca5a2-df1c-4d8e-bbff-c383083ac411",
                "name": "de.NBI GPU P100 medium",
                "available": 1,
                "total": 10,
                "cores": 14,
                "mem": 65535,
                "type": "gpu",
                "gpu_type": "P100",
                "gpu_count": 1,
                "root_disk": 50,
                "ephemeral_disk": 0,
            }
        ]
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        connector = FlavorResourceExporterConnector("config.yml")
        result = connector.fetch_flavor_resources()

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], FlavorResource)
        self.assertEqual(result[0].id, "e50ca5a2-df1c-4d8e-bbff-c383083ac411")
        self.assertEqual(result[0].name, "de.NBI GPU P100 medium")
        self.assertEqual(result[0].available, 1)
        self.assertEqual(result[0].total, 10)
        self.assertEqual(result[0].cores, 14)
        self.assertEqual(result[0].mem, 65535)
        self.assertEqual(result[0].type, "gpu")
        self.assertEqual(result[0].gpu_type, "P100")
        self.assertEqual(result[0].gpu_count, 1)
        self.assertEqual(result[0].root_disk, 50)
        self.assertEqual(result[0].ephemeral_disk, 0)

    @patch("requests.Session.get")
    @patch("builtins.open")
    @patch("yaml.load")
    def test_fetch_flavor_resources_with_auth(
        self, mock_yaml_load, mock_open, mock_get
    ):
        """Test that requests are made with Basic Auth when credentials are set."""
        os.environ["FLAVOR_RESOURCE_EXPORTER_USERNAME"] = "testuser"
        os.environ["FLAVOR_RESOURCE_EXPORTER_PASSWORD"] = "testpass"

        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com/flavors",
            }
        }

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        connector = FlavorResourceExporterConnector("config.yml")
        connector.fetch_flavor_resources()

        mock_get.assert_called_once()
        assert connector.session.auth.username == "testuser"
        assert connector.session.auth.password == "testpass"

    @patch("builtins.open")
    @patch("yaml.load")
    def test_fetch_flavor_resources_no_endpoint(self, mock_yaml_load, mock_open):
        """Test that fetch returns empty list when no endpoint is configured."""
        os.environ["FLAVOR_RESOURCE_EXPORTER_USERNAME"] = "testuser"
        os.environ["FLAVOR_RESOURCE_EXPORTER_PASSWORD"] = "testpass"

        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
            }
        }

        connector = FlavorResourceExporterConnector("config.yml")
        result = connector.fetch_flavor_resources()
        self.assertEqual(result, [])

    @patch("builtins.open")
    @patch("yaml.load")
    def test_is_available(self, mock_yaml_load, mock_open):
        """Test is_available method."""
        os.environ["FLAVOR_RESOURCE_EXPORTER_USERNAME"] = "testuser"
        os.environ["FLAVOR_RESOURCE_EXPORTER_PASSWORD"] = "testpass"

        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com",
            }
        }

        connector = FlavorResourceExporterConnector("config.yml")
        self.assertTrue(connector.is_available())

    @patch("builtins.open")
    @patch("yaml.load")
    def test_is_available_missing_username(self, mock_yaml_load, mock_open):
        """Test is_available returns False when username is missing."""
        os.environ.pop("FLAVOR_RESOURCE_EXPORTER_USERNAME", None)
        os.environ["FLAVOR_RESOURCE_EXPORTER_PASSWORD"] = "testpass"

        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com",
            }
        }

        connector = FlavorResourceExporterConnector("config.yml")
        self.assertFalse(connector.is_available())

    @patch("builtins.open")
    @patch("yaml.load")
    def test_init_enabled_without_basic_auth(self, mock_yaml_load, mock_open):
        """Test that connector is enabled without basic auth credentials when configured."""
        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com",
                "use_basic_auth": False,
            }
        }

        connector = FlavorResourceExporterConnector("config.yml")
        self.assertTrue(connector.enabled)
        self.assertFalse(connector.use_basic_auth)
        self.assertTrue(connector.is_available())

    @patch("requests.Session.get")
    @patch("builtins.open")
    @patch("yaml.load")
    def test_fetch_flavor_resources_no_auth(self, mock_yaml_load, mock_open, mock_get):
        """Test fetching resources without basic auth when configured."""
        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com/flavors",
                "use_basic_auth": False,
            }
        }

        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        connector = FlavorResourceExporterConnector("config.yml")
        connector.fetch_flavor_resources()

        mock_get.assert_called_once()
        self.assertIsNone(connector.session.auth)

    @patch("builtins.open")
    @patch("yaml.load")
    def test_is_available_without_basic_auth(self, mock_yaml_load, mock_open):
        """Test is_available returns True when basic auth is disabled and connector is configured."""
        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com",
                "use_basic_auth": False,
            }
        }

        connector = FlavorResourceExporterConnector("config.yml")
        self.assertTrue(connector.is_available())

    @patch("builtins.open")
    @patch("yaml.load")
    def test_is_available_missing_password(self, mock_yaml_load, mock_open):
        """Test is_available returns False when password is missing."""
        os.environ["FLAVOR_RESOURCE_EXPORTER_USERNAME"] = "testuser"
        os.environ.pop("FLAVOR_RESOURCE_EXPORTER_PASSWORD", None)

        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com",
            }
        }

        connector = FlavorResourceExporterConnector("config.yml")
        self.assertFalse(connector.is_available())

    @patch("requests.Session.get")
    @patch("builtins.open")
    @patch("yaml.load")
    def test_fetch_flavor_resources_pagination(
        self, mock_yaml_load, mock_open, mock_get
    ):
        """Test handling of paginated response with 'results' key."""
        os.environ["FLAVOR_RESOURCE_EXPORTER_USERNAME"] = "testuser"
        os.environ["FLAVOR_RESOURCE_EXPORTER_PASSWORD"] = "testpass"

        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com/flavors",
            }
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {
                    "id": "id1",
                    "name": "Flavor 1",
                    "available": 2,
                    "total": 5,
                    "cores": 4,
                    "mem": 8192,
                    "type": "cpu",
                },
                {
                    "id": "id2",
                    "name": "Flavor 2",
                    "available": 1,
                    "total": 3,
                    "cores": 8,
                    "mem": 16384,
                    "type": "cpu",
                },
            ]
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        connector = FlavorResourceExporterConnector("config.yml")
        result = connector.fetch_flavor_resources()

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].name, "Flavor 1")
        self.assertEqual(result[1].name, "Flavor 2")

    @patch("requests.Session.get")
    @patch("builtins.open")
    @patch("yaml.load")
    def test_fetch_flavor_resources_single_object(
        self, mock_yaml_load, mock_open, mock_get
    ):
        """Test handling of single object response."""
        os.environ["FLAVOR_RESOURCE_EXPORTER_USERNAME"] = "testuser"
        os.environ["FLAVOR_RESOURCE_EXPORTER_PASSWORD"] = "testpass"

        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com/flavor",
            }
        }

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "single-id",
            "name": "Single Flavor",
            "available": 1,
            "total": 1,
            "cores": 2,
            "mem": 4096,
            "type": "cpu",
        }
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        connector = FlavorResourceExporterConnector("config.yml")
        result = connector.fetch_flavor_resources()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].name, "Single Flavor")

    @patch("requests.Session.get")
    @patch("builtins.open")
    @patch("yaml.load")
    def test_fetch_flavor_resources_timeout(self, mock_yaml_load, mock_open, mock_get):
        """Test handling of request timeout."""
        os.environ["FLAVOR_RESOURCE_EXPORTER_USERNAME"] = "testuser"
        os.environ["FLAVOR_RESOURCE_EXPORTER_PASSWORD"] = "testpass"

        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com/flavors",
                "timeout": 5,
            }
        }

        mock_get.side_effect = Exception("Timeout")

        connector = FlavorResourceExporterConnector("config.yml")
        result = connector.fetch_flavor_resources()

        self.assertEqual(result, [])

    @patch("builtins.open")
    @patch("yaml.load")
    def test_parse_flavor_resource_minimal(self, mock_yaml_load, mock_open):
        """Test parsing with minimal required fields."""
        os.environ["FLAVOR_RESOURCE_EXPORTER_USERNAME"] = "testuser"
        os.environ["FLAVOR_RESOURCE_EXPORTER_PASSWORD"] = "testpass"

        mock_open.return_value.__enter__ = lambda self: self
        mock_open.return_value.__exit__ = lambda self, *args: None
        mock_open.return_value.read = lambda: "test"

        mock_yaml_load.return_value = {
            "flavor_resource_exporter": {
                "activated": True,
                "endpoint_url": "http://example.com",
            }
        }

        connector = FlavorResourceExporterConnector("config.yml")

        data = {
            "id": "test-id",
            "name": "Test Flavor",
            "available": 1,
            "total": 5,
            "cores": 4,
            "mem": 8192,
            "type": "cpu",
        }

        result = connector._parse_flavor_resource(data)
        self.assertIsInstance(result, FlavorResource)
        self.assertEqual(result.id, "test-id")
        self.assertEqual(result.name, "Test Flavor")
        self.assertIsNone(result.gpu_type)
        self.assertIsNone(result.gpu_count)
        self.assertIsNone(result.root_disk)
        self.assertIsNone(result.ephemeral_disk)
