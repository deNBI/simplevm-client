import unittest
from unittest.mock import MagicMock, patch

import redis

from simple_vm_client.forc_connector.playbook.playbook import Playbook
from simple_vm_client.ttypes import CondaPackage
from simple_vm_client.util.state_enums import VmTaskStates

DEFAULT_IP = "192.168.0.4"
DEFAULT_PORT = 9090
DEFAULT_RESEARCH_ENVIRONMENT_TEMPLATE = "vscode"
DEFAULT_RESEARCH_ENVIRONMENT_VERSION = "v3"
DEFAULT_CONDA_PACKAGES = [
    CondaPackage(name="conda1", version="1.0.0"),
    CondaPackage(name="conda2", version="2.0.0"),
]
DEFAULT_APT_PACKAGES = ["curl", "mosh"]
DEFAULT_PRIVATE_KEY = "a04f5f781e4b492d812c1dd3c7cb951f"
DEFAULT_PUBLIC_KEY = "public_key"
DEFAULT_CLOUD_SITE = "Bielefeld"
DEFAULT_BASE_URL = "https://localhost.base_url"
DEFAULT_POOL = MagicMock(spec=redis.ConnectionPool)


class TestPlaybook(unittest.TestCase):
    def init_playbook(self):
        with patch.object(Playbook, "__init__", lambda x, y, z: None):
            playbook = Playbook(None, None)
        return playbook

    @patch("simple_vm_client.forc_connector.playbook.playbook.TemporaryDirectory")
    @patch("simple_vm_client.forc_connector.playbook.playbook.redis.Redis")
    def test_cleanup(self, mock_redis, mock_temporary_directory):
        # Arrange
        openstack_id = "your_openstack_id"
        mock_temporary_directory_instance = MagicMock()
        mock_temporary_directory.return_value = mock_temporary_directory_instance
        mock_redis_instance = MagicMock(spec=redis.StrictRedis)
        mock_redis_instance.delete.return_value = None
        mock_redis.return_value = mock_redis_instance

        instance = self.init_playbook()
        instance.redis = mock_redis_instance
        instance.directory = mock_temporary_directory_instance

        # Act
        instance.cleanup(openstack_id)

        # Assert
        mock_temporary_directory_instance.cleanup.assert_called_once()
        mock_redis_instance.delete.assert_called_once_with(openstack_id)

    @patch("simple_vm_client.forc_connector.playbook.playbook.NamedTemporaryFile")
    @patch("simple_vm_client.forc_connector.playbook.playbook.NamedTemporaryFile")
    def test_get_logs(self, mock_log_file_stdout, mock_log_file_stderr):
        # Arrange
        instance = self.init_playbook()

        # Configure mock behavior for log files
        stdout_content = "This is a sample stdout log."
        stderr_content = "This is a sample stderr log."

        # Mocking log files
        mock_log_file_stdout_instance = MagicMock()
        mock_log_file_stdout_instance.readlines.return_value = (
            stdout_content.splitlines()
        )
        mock_log_file_stdout.return_value = mock_log_file_stdout_instance

        mock_log_file_stderr_instance = MagicMock()
        mock_log_file_stderr_instance.readlines.return_value = (
            stderr_content.splitlines()
        )
        mock_log_file_stderr.return_value = mock_log_file_stderr_instance
        instance.stderr = ""
        instance.stdout = ""
        instance.log_file_stderr = mock_log_file_stderr_instance
        instance.log_file_stdout = mock_log_file_stdout_instance
        instance.returncode = 0

        # Act
        returncode, stdout, stderr = instance.get_logs()

        # Assert
        mock_log_file_stdout_instance.seek.assert_called_with(0, 0)
        mock_log_file_stdout_instance.readlines.assert_called_with()

        mock_log_file_stderr_instance.seek.assert_called_with(0, 0)
        mock_log_file_stderr_instance.readlines.assert_called_with()
        self.assertEqual(returncode, instance.returncode)
        self.assertEqual(stdout, stdout_content)
        self.assertEqual(stderr, stderr_content)

    @patch("simple_vm_client.forc_connector.playbook.playbook.Playbook.cleanup")
    @patch("simple_vm_client.forc_connector.playbook.playbook.Playbook.get_logs")
    @patch("simple_vm_client.forc_connector.playbook.playbook.redis.Redis")
    @patch("simple_vm_client.forc_connector.playbook.playbook.subprocess.Popen")
    def test_stop(self, mock_popen, mock_redis, mock_get_logs, mock_cleanup):
        # Arrange
        instance = self.init_playbook()
        openstack_id = "your_openstack_id"
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        mock_get_logs.return_value = 0, "Stderr", "Stdout"
        instance.redis = mock_redis
        instance.directory = MagicMock()
        instance.process = mock_process

        # Act
        instance.stop(openstack_id)

        # Assert
        mock_process.terminate.assert_called_once()
        mock_get_logs.assert_called_once()
        mock_redis.hset.assert_called_once_with(
            name=f"pb_logs_{openstack_id}",
            mapping={
                "returncode": mock_get_logs.return_value[0],
                "stdout": mock_get_logs.return_value[1],
                "stderr": mock_get_logs.return_value[2],
            },
        )
        mock_cleanup.assert_called_once_with(openstack_id)

    @patch("simple_vm_client.forc_connector.playbook.playbook.logger")
    def test_check_status_in_progress(self, mock_logger):
        # Arrange
        openstack_id = "your_openstack_id"

        instance = self.init_playbook()

        mock_process = MagicMock()
        mock_process.poll.return_value = None

        instance.process = mock_process

        # Act
        result = instance.check_status(openstack_id)

        # Assert
        mock_logger.info.assert_any_call(f"Check Status Playbook for VM {openstack_id}")
        mock_logger.info.assert_any_call(f"Status Playbook for VM {openstack_id}: None")
        mock_logger.info.assert_any_call(
            f"Playbook for (openstack_id) {openstack_id} still in progress."
        )
        self.assertEqual(result, 3)

    @patch("simple_vm_client.forc_connector.playbook.playbook.logger")
    def test_check_status_failed(self, mock_logger):
        # Arrange
        openstack_id = "your_openstack_id"

        instance = self.init_playbook()
        mock_process = MagicMock()
        mock_process.poll.return_value = 1
        mock_redis_instance = MagicMock(spec=redis.StrictRedis)

        instance.redis = mock_redis_instance

        instance.process = mock_process

        # Act
        result = instance.check_status(openstack_id)

        # Assert

        mock_logger.info.assert_any_call(f"Check Status Playbook for VM {openstack_id}")
        mock_logger.info.assert_any_call(f"Status Playbook for VM {openstack_id}: 1")
        mock_redis_instance.hset.assert_called_once_with(
            openstack_id, "status", VmTaskStates.PLAYBOOK_FAILED.value
        )
        mock_logger.info.assert_any_call(
            f"Playbook for (openstack_id) {openstack_id} has failed."
        )
        self.assertEqual(result, 1)

    @patch("simple_vm_client.forc_connector.playbook.playbook.logger")
    def test_check_status_success(self, mock_logger):
        # Arrange
        openstack_id = "your_openstack_id"

        instance = self.init_playbook()
        mock_process = MagicMock()
        mock_process.poll.return_value = 0
        mock_redis_instance = MagicMock(spec=redis.StrictRedis)

        instance.redis = mock_redis_instance

        instance.process = mock_process

        # Act
        result = instance.check_status(openstack_id)

        # Assert

        mock_logger.info.assert_any_call(f"Check Status Playbook for VM {openstack_id}")
        mock_logger.info.assert_any_call(f"Status Playbook for VM {openstack_id}: 0")
        mock_redis_instance.hset.assert_called_once_with(
            openstack_id, "status", VmTaskStates.PLAYBOOK_SUCCESSFUL.value
        )
        mock_logger.info.assert_any_call(
            f"Playbook for (openstack_id) {openstack_id} is successful."
        )
        self.assertEqual(result, 0)
