import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import redis

from simple_vm_client.forc_connector.playbook.playbook import CONDA, OPTIONAL, Playbook
from simple_vm_client.forc_connector.template.template import Template
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
            playbook.vars_files = []
            playbook.tasks = []
            playbook.playbooks_dir = Template.get_playbook_dir()
            playbook.returncode: int = -1
            playbook.stdout: str = ""
            playbook.stderr: str = ""
            playbook.conda_packages = []
            playbook.apt_packages = []
            playbook.always_tasks = []
            playbook.research_environment_template = None
            playbook.cloud_site = DEFAULT_CLOUD_SITE
            playbook.playbook_exec_name: str = "generic_playbook.yml"

            playbook.directory = TemporaryDirectory(dir=f"{playbook.playbooks_dir}")
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

    @patch("simple_vm_client.forc_connector.playbook.playbook.logger")
    @patch("simple_vm_client.forc_connector.playbook.playbook.subprocess.Popen")
    def test_run_it(self, mock_popen, mock_logger):
        # Arrange
        playbook = self.init_playbook()
        inventory = MagicMock()
        directory = MagicMock()
        playbook.inventory = inventory
        playbook.directory = directory
        playbook.log_file_stderr = MagicMock()
        playbook.log_file_stdout = MagicMock()

        playbook.inventory.name = "inventory_name"
        playbook.directory.name = "directory_name"
        playbook.playbook_exec_name = "playbook_exec_name"
        mock_process = MagicMock()
        mock_popen.return_value = mock_process

        # Act
        playbook.run_it()

        # Assert
        mock_logger.info.assert_called_with(
            f"Run Playbook for {playbook.playbook_exec_name} - "
            f"[['/usr/local/bin/ansible-playbook', '-v', '-i', 'inventory_name', 'directory_name/playbook_exec_name']]"
        )
        mock_popen.assert_called_once_with(
            [
                "/usr/local/bin/ansible-playbook",
                "-v",
                "-i",
                "inventory_name",
                "directory_name/playbook_exec_name",
            ],
            stdout=playbook.log_file_stdout,
            stderr=playbook.log_file_stderr,
            universal_newlines=True,
        )
        self.assertEqual(playbook.process, mock_process)

    def test_add_always_tasks_only(self):
        # Arrange
        instance = self.init_playbook()
        playbook_name = "example_playbook"
        instance.always_tasks = []

        # Act
        instance.add_always_tasks_only(playbook_name)

        # Assert
        expected_task = {
            "name": f"Running {playbook_name} tasks",
            "import_tasks": f"{playbook_name}.yml",
        }
        self.assertIn(expected_task, instance.always_tasks)

    def test_add_tasks_only(self):
        # Arrange
        instance = self.init_playbook()
        playbook_name = "example_playbook"
        instance.tasks = []

        # Act
        instance.add_tasks_only(playbook_name)

        # Assert
        expected_task = {
            "name": f"Running {playbook_name} tasks",
            "import_tasks": f"{playbook_name}.yml",
        }
        self.assertIn(expected_task, instance.tasks)

    def test_add_to_playbook_always_lists(self):
        # Arrange
        instance = self.init_playbook()
        playbook_name = "example_playbook"

        instance.vars_files = []
        instance.always_tasks = []

        # Act
        instance.add_to_playbook_always_lists(playbook_name)

        # Assert
        expected_vars_file = f"{playbook_name}_vars_file.yml"
        expected_always_task = {
            "name": f"Running {playbook_name} tasks",
            "import_tasks": f"{playbook_name}.yml",
        }
        self.assertIn(expected_vars_file, instance.vars_files)
        self.assertIn(expected_always_task, instance.always_tasks)

    @patch("simple_vm_client.forc_connector.playbook.playbook.logger")
    def test_add_to_playbook_lists(self, mock_logger):
        # Arrange
        instance = self.init_playbook()
        playbook_name_local = "example_local_playbook"
        playbook_name = "example_playbook"
        instance.vars_files = []
        instance.tasks = []

        # Act
        instance.add_to_playbook_lists(playbook_name_local, playbook_name)

        # Assert
        expected_vars_file = f"{playbook_name}_vars_file.yml"
        expected_task = {
            "name": f"Running {playbook_name_local} tasks",
            "import_tasks": f"{playbook_name_local}.yml",
        }
        mock_logger.info.assert_called_once_with(
            "Added playbook: "
            + playbook_name_local
            + ".yml"
            + ", vars file: "
            + playbook_name
            + "_vars_file.yml"
        )
        self.assertIn(expected_vars_file, instance.vars_files)
        self.assertIn(expected_task, instance.tasks)

    @patch("simple_vm_client.forc_connector.playbook.playbook.shutil.copytree")
    @patch("simple_vm_client.forc_connector.playbook.playbook.open")
    @patch("simple_vm_client.forc_connector.playbook.playbook.os.path.isfile")
    def test_copy_and_init_conda_packages(self, mock_isfile, mock_open, mock_copytree):
        # Arrange
        mock_yaml_exec = MagicMock()
        instance = self.init_playbook()
        instance.yaml_exec = mock_yaml_exec
        instance.conda_packages = DEFAULT_CONDA_PACKAGES
        instance.add_to_playbook_lists = MagicMock()
        instance.add_tasks_only = MagicMock()

        mock_tempdir = MagicMock()
        mock_tempdir.name = "/tmp/test_temp_dir"
        instance.playbooks_dir = Template.get_playbook_dir()

        instance.directory = mock_tempdir
        instance.cloud_site = "your_cloud_site"

        # Set up mock for os.path.isfile
        mock_isfile.return_value = True

        # Act
        instance.copy_and_init_conda_packages()

        # Assert
        mock_copytree.assert_called_once_with(
            f"{instance.playbooks_dir}resenvs/{CONDA}",
            mock_tempdir.name,
            dirs_exist_ok=True,
        )

        mock_open.assert_any_call(
            f"{mock_tempdir.name}/{CONDA}_vars_file.yml", mode="r"
        )
        mock_open.assert_any_call(
            f"{mock_tempdir.name}/{CONDA}_vars_file.yml", mode="w"
        )

        mock_yaml_exec.load.assert_called_once()

        mock_yaml_exec.dump.assert_called_once()

        instance.add_to_playbook_lists.assert_called_once_with(
            CONDA + "-" + instance.cloud_site, CONDA
        )

        # Check that add_tasks_only is not called
        instance.add_tasks_only.assert_not_called()

    @patch("simple_vm_client.forc_connector.playbook.playbook.shutil.copytree")
    def test_copy_and_init_conda_packages_no_conda_packages(self, mock_copytree):
        playbook = self.init_playbook()
        playbook.copy_and_init_conda_packages()
        mock_copytree.assert_not_called()

    @patch("simple_vm_client.forc_connector.playbook.playbook.shutil.copytree")
    @patch("simple_vm_client.forc_connector.playbook.playbook.open")
    @patch("simple_vm_client.forc_connector.playbook.playbook.os.path.isfile")
    @patch("simple_vm_client.forc_connector.playbook.playbook.logger.exception")
    def test_copy_and_init_conda_packages_error(
        self, mock_logger_exception, mock_is_file, mock_open, mock_copytree
    ):
        # Arrange
        mock_yaml_exec = MagicMock()

        mock_is_file.return_value = True
        instance = self.init_playbook()
        instance.yaml_exec = mock_yaml_exec
        instance.conda_packages = DEFAULT_CONDA_PACKAGES
        instance.add_to_playbook_lists = MagicMock()
        instance.add_tasks_only = MagicMock()

        mock_tempdir = MagicMock()
        mock_tempdir.name = "/tmp/test_temp_dir"
        instance.playbooks_dir = Template.get_playbook_dir()

        instance.directory = mock_tempdir
        instance.cloud_site = "your_cloud_site"

        # Set up mock for os.path.isfile
        mock_open.side_effect = IOError("Error reading file")

        # Act and Assert
        instance.copy_and_init_conda_packages()
        playbook_var_yml = f"/{CONDA}_vars_file.yml"

        mock_logger_exception.assert_called_once_with(
            f"Could not open - {instance.directory.name + playbook_var_yml}"
        )

        instance.add_to_playbook_lists.assert_not_called()

        instance.add_tasks_only.assert_called_once_with(
            CONDA + "-" + instance.cloud_site
        )

    @patch("simple_vm_client.forc_connector.playbook.playbook.shutil.copy")
    @patch(
        "simple_vm_client.forc_connector.playbook.playbook.os.path.isfile",
        return_value=True,
    )
    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    @patch("simple_vm_client.forc_connector.playbook.playbook.logger.info")
    def test_copy_and_init_apt_packages(
        self, mock_logger_info, mock_open, mock_isfile, mock_copy
    ):
        # Arrange
        instance = self.init_playbook()  # Initialize your class with appropriate values
        mock_yaml_exec = MagicMock()
        instance.yaml_exec = mock_yaml_exec

        # Mock apt_packages and other necessary attributes
        instance.apt_packages = DEFAULT_APT_PACKAGES

        # Act
        instance.copy_and_init_apt_packages()

        # Assert
        # Add your assertions based on the expected behavior of the method

        # Verify that shutil.copy is called with the correct arguments
        playbook_yml = os.path.join(
            instance.playbooks_dir, OPTIONAL + "-" + instance.cloud_site + ".yml"
        )
        mock_copy.assert_any_call(playbook_yml, instance.directory.name)
        playbook_vars_yml = os.path.join(
            instance.playbooks_dir, OPTIONAL + "_vars_file.yml"
        )

        mock_copy.assert_any_call(playbook_vars_yml, instance.directory.name)

        target_playbook_vars = os.path.join(
            instance.directory.name, OPTIONAL + "_vars_file.yml"
        )

        # Verify that open is called with the correct arguments
        mock_open.assert_any_call(target_playbook_vars, mode="r")
        mock_logger_info.assert_called_once_with(
            "Added playbook: "
            + OPTIONAL
            + "-"
            + instance.cloud_site
            + ".yml"
            + ", vars file: "
            + OPTIONAL
            + "_vars_file.yml"
        )

    @patch("simple_vm_client.forc_connector.playbook.playbook.shutil.copytree")
    def test_copy_and_init_apt_packages_no_apt_packages(self, mock_copytree):
        playbook = self.init_playbook()
        playbook.copy_and_init_apt_packages()
        mock_copytree.assert_not_called()

    @patch(
        "simple_vm_client.forc_connector.playbook.playbook.shutil.copy",
        side_effect=IOError("Error copying file"),
    )
    @patch("simple_vm_client.forc_connector.playbook.playbook.logger.exception")
    def test_copy_and_init_apt_packages_raises_io_error(
        self, mock_logger_exception, mock_copy
    ):
        # Arrange
        obj = self.init_playbook()
        obj.apt_packages = DEFAULT_APT_PACKAGES  # Set your desired apt_packages

        # Act and Assert
        obj.copy_and_init_apt_packages()
        mock_logger_exception.assert_called_once_with("Could not copy apt packages")

    @patch(
        "simple_vm_client.forc_connector.playbook.playbook.open",
        side_effect=IOError("Error copying file"),
    )
    @patch("simple_vm_client.forc_connector.playbook.playbook.logger.exception")
    def test_copy_and_init_apt_packages_raises_open_error(
        self, mock_logger_exception, mock_copy
    ):
        # Arrange
        obj = self.init_playbook()
        obj.apt_packages = DEFAULT_APT_PACKAGES  # Set your desired apt_packages
        obj.add_tasks_only = MagicMock()

        # Act and Assert
        obj.copy_and_init_apt_packages()
        mock_logger_exception.assert_called_once_with("Could not copy apt packages")
        obj.add_tasks_only.assert_called_once_with(OPTIONAL)

    @patch("simple_vm_client.forc_connector.playbook.playbook.shutil.copytree")
    @patch(
        "simple_vm_client.forc_connector.playbook.playbook.os.path.isfile",
        return_value=True,
    )  # Mocking os.path.isfile to return True
    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    @patch("simple_vm_client.forc_connector.playbook.playbook.logger.info")
    def test_copy_and_init_research_environment(
        self, mock_logger_info, mock_open, mock_isfile, mock_copytree
    ):
        # Arrange
        instance = self.init_playbook()  # Create an instance of YourClass
        mock_yaml_exec = MagicMock()
        instance.yaml_exec = mock_yaml_exec

        # Mock data and methods
        instance.research_environment_template = "template_name"
        instance.cloud_site = "cloud_site"
        instance.research_environment_template_version = "template_version"
        instance.create_only_backend = False
        instance.base_url = "base_url"

        # Act
        instance.copy_and_init_research_environment()

        # Assert
        mock_copytree.assert_called_once_with(
            f"{instance.playbooks_dir}resenvs/template_name",
            instance.directory.name,
            dirs_exist_ok=True,
        )
        mock_isfile.assert_any_call(
            f"{instance.directory.name}/template_name-cloud_site.yml"
        )
        mock_open.assert_any_call(
            f"{instance.directory.name}/template_name_vars_file.yml", mode="r"
        )
        mock_open.assert_any_call(
            f"{instance.directory.name}/template_name_vars_file.yml", mode="w"
        )
        mock_logger_info.assert_called_once_with(
            f"Added playbook: {instance.research_environment_template}-{instance.cloud_site}.yml,"
            f" vars file: {instance.research_environment_template}_vars_file.yml"
        )

    @patch("simple_vm_client.forc_connector.playbook.playbook.shutil.copytree")
    def test_copy_and_init_research_environment_no_template(self, mock_copytree):
        playbook = self.init_playbook()
        playbook.copy_and_init_research_environment()
        mock_copytree.assert_not_called()

    @patch(
        "simple_vm_client.forc_connector.playbook.playbook.open",
        side_effect=IOError("Error copying file"),
    )
    @patch("simple_vm_client.forc_connector.playbook.playbook.logger.exception")
    @patch("simple_vm_client.forc_connector.playbook.playbook.shutil.copytree")
    def test_copy_and_init_research_environment_error(
        self, mock_copy, mock_logger_exception, mock_open
    ):
        # Arrange
        obj = self.init_playbook()
        obj.research_environment_template = "template_name"
        obj.create_only_backend = False
        obj.add_tasks_only = MagicMock()

        # Act and Assert
        obj.copy_and_init_research_environment()
        mock_logger_exception.assert_called_once_with(
            "Could not copy research environment template data"
        )
        obj.add_tasks_only.assert_called_once_with(obj.research_environment_template)

    @patch("shutil.copytree")
    @patch(
        "os.path.isfile", return_value=False
    )  # Mocking os.path.isfile to return False
    @patch("shutil.copy")
    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    def test_copy_playbooks_and_init(
        self, mock_open, mock_copy, mock_copytree, mock_isfile
    ):
        playbook = self.init_playbook()
        mock_yaml_exec = MagicMock()
        playbook.yaml_exec = mock_yaml_exec
        playbook.copy_and_init_conda_packages = MagicMock()
        playbook.copy_and_init_apt_packages = MagicMock()
        playbook.copy_and_init_research_environment = MagicMock()
        playbook.copy_and_init_change_keys = MagicMock()
        playbook.copy_playbooks_and_init(public_key=DEFAULT_PUBLIC_KEY)

        playbook.copy_and_init_conda_packages.assert_called_once_with()
        playbook.copy_and_init_apt_packages.assert_called_once_with()
        playbook.copy_and_init_research_environment.assert_called_once_with()
        playbook.copy_and_init_change_keys.assert_called_once_with(
            public_key=DEFAULT_PUBLIC_KEY
        )

    patch("shutil.copy")

    @patch(
        "os.path.isfile", return_value=True
    )  # Mocking os.path.isfile to return False
    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    @patch("simple_vm_client.forc_connector.playbook.playbook.shutil.copy")
    def test_copy_and_init_change_keys(self, mock_copy, mock_open, mock_isfile):
        playbook = self.init_playbook()
        mock_yaml_exec = MagicMock()
        mock_yaml_exec.load.return_value = {"change_key_vars": {"key": None}}
        playbook.yaml_exec = mock_yaml_exec
        playbook.add_to_playbook_always_lists = MagicMock()
        key_file_mock = MagicMock()

        mock_open.side_effect = [key_file_mock, key_file_mock]

        # Act
        playbook.copy_and_init_change_keys(public_key=DEFAULT_PUBLIC_KEY)

        # Assert
        expected_copy_calls = [
            unittest.mock.call(
                "/path/to/playbooks/change_key.yml", "/path/to/directory"
            ),
            unittest.mock.call(
                "/path/to/playbooks/change_key_vars_file.yml", "/path/to/directory"
            ),
        ]
        mock_copy(expected_copy_calls, any_order=True)

        key_file = playbook.directory.name + "/change_key_vars_file.yml"

        data_ck = {"change_key_vars": {"key": None}}
        data_ck["change_key_vars"]["key"] = DEFAULT_PUBLIC_KEY.strip('"')

        mock_open.assert_any_call(key_file, mode="r"),
        mock_open.assert_any_call(key_file, mode="w")
        mock_yaml_exec.load.assert_called_once_with(key_file_mock.__enter__())
        mock_yaml_exec.dump.assert_called_once_with(data_ck, key_file_mock.__enter__())
        playbook.add_to_playbook_always_lists.assert_called_once_with("change_key")

    @patch("simple_vm_client.forc_connector.playbook.playbook.shutil.copytree")
    @patch(
        "os.path.isfile", return_value=True
    )  # Mocking os.path.isfile to return False
    @patch("shutil.copy")
    @patch("builtins.open", new_callable=unittest.mock.mock_open)
    @patch(
        "simple_vm_client.forc_connector.playbook.playbook.Playbook.copy_playbooks_and_init"
    )
    @patch("simple_vm_client.forc_connector.playbook.playbook.redis.Redis")
    def test_init(
        self,
        mock_redis,
        mock_copy_playbooks_and_init,
        mock_open,
        mock_copy,
        mock_isfile,
        mock_copytree,
    ):
        # Act
        instance = Playbook(
            ip=DEFAULT_IP,
            port=DEFAULT_PORT,
            research_environment_template=DEFAULT_RESEARCH_ENVIRONMENT_TEMPLATE,
            research_environment_template_version=DEFAULT_RESEARCH_ENVIRONMENT_VERSION,
            create_only_backend=False,
            conda_packages=DEFAULT_CONDA_PACKAGES,
            apt_packages=DEFAULT_APT_PACKAGES,
            osi_private_key=DEFAULT_PRIVATE_KEY,
            public_key=DEFAULT_PUBLIC_KEY,
            pool=DEFAULT_POOL,
            cloud_site=DEFAULT_CLOUD_SITE,
            base_url=DEFAULT_BASE_URL,
        )

        # Assert
        self.assertEqual(instance.cloud_site, DEFAULT_CLOUD_SITE)
        self.assertIsNotNone(instance.redis)
        self.assertIsNotNone(instance.yaml_exec)
        self.assertEqual(instance.conda_packages, DEFAULT_CONDA_PACKAGES)
        self.assertEqual(instance.apt_packages, DEFAULT_APT_PACKAGES)
        self.assertIsNone(instance.process)
        self.assertEqual(
            instance.research_environment_template_version,
            DEFAULT_RESEARCH_ENVIRONMENT_VERSION,
        )
        self.assertEqual(instance.create_only_backend, False)
        self.assertEqual(instance.returncode, -1)
        self.assertEqual(instance.stdout, "")
        self.assertEqual(instance.stderr, "")
        self.assertEqual(
            instance.research_environment_template,
            DEFAULT_RESEARCH_ENVIRONMENT_TEMPLATE,
        )
        self.assertEqual(instance.base_url, DEFAULT_BASE_URL)

        mock_copy_playbooks_and_init.assert_called_once()
