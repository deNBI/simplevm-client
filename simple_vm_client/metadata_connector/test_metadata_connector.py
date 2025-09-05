import json
from unittest.mock import MagicMock

import pytest
import requests
from metadata_connector import MetadataConnector

from simple_vm_client.ttypes import VirtualMachineServerMetadata


@pytest.fixture
def dummy_config_file(tmp_path):
    """Create a temporary YAML config file for testing."""
    config_data = {
        "metadata_server": {
            "activated": True,
            "use_https": False,
            "host": "localhost",
            "port": 1234,
        }
    }
    config_file = tmp_path / "config.yml"
    config_file.write_text(json.dumps(config_data))  # json works with yaml.safe_load
    return str(config_file)


@pytest.fixture
def connector_with_env(monkeypatch, dummy_config_file):
    """Fixture: MetadataConnector with env variable set."""
    monkeypatch.setenv("METADATA_WRITE_TOKEN", "secret-token")

    connector = MetadataConnector(dummy_config_file)
    connector.ACTIVATED = True
    connector.METADATA_BASE_URL = "http://localhost:1234/"
    connector.METADATA_WRITE_TOKEN = "secret-token"

    # Replace requests.Session with mock
    connector.session = MagicMock()
    return connector


def test_load_config_and_env(dummy_config_file, monkeypatch):
    """Test config loading and environment loading."""
    monkeypatch.setenv("METADATA_WRITE_TOKEN", "test-token")
    connector = MetadataConnector(dummy_config_file)

    assert connector.ACTIVATED is True
    assert connector.METADATA_SERVER_HOST == "localhost"
    assert connector.METADATA_SERVER_PORT == 1234
    assert connector.METADATA_BASE_URL == "http://localhost:1234/"
    assert connector.METADATA_WRITE_TOKEN == "test-token"


def test_remove_metadata_success(connector_with_env):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    connector_with_env.session.delete.return_value = mock_response

    result = connector_with_env.remove_metadata("10.0.0.1")

    assert result is True
    connector_with_env.session.delete.assert_called_once()


def test_remove_metadata_failure(connector_with_env):
    connector_with_env.session.delete.side_effect = requests.exceptions.ConnectionError(
        "boom"
    )

    result = connector_with_env.remove_metadata("10.0.0.2")

    assert result is False


def test_set_metadata_success(connector_with_env):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    connector_with_env.session.post.return_value = mock_response

    metadata = VirtualMachineServerMetadata()
    result = connector_with_env.set_metadata("10.0.0.3", metadata)

    assert result is True
    connector_with_env.session.post.assert_called_once()
    args, kwargs = connector_with_env.session.post.call_args
    assert "10.0.0.3" in args[0]
    assert kwargs["headers"]["Content-Type"] == "application/json"


def test_set_metadata_failure(connector_with_env):
    connector_with_env.session.post.side_effect = requests.exceptions.Timeout("timeout")

    metadata = VirtualMachineServerMetadata()
    result = connector_with_env.set_metadata("10.0.0.4", metadata)

    assert result is False


def test_is_metadata_server_available_success(connector_with_env):
    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"status": "ok"}
    connector_with_env.session.get.return_value = mock_response

    result = connector_with_env.is_metadata_server_available()

    assert result is True
    connector_with_env.session.get.assert_called_once()


def test_is_metadata_server_available_failure(connector_with_env):
    connector_with_env.session.get.side_effect = requests.exceptions.ConnectionError(
        "down"
    )

    result = connector_with_env.is_metadata_server_available()

    assert result is False
