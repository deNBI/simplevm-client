import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import requests
from openstack.compute.v2.server import Server
from openstack.test import fakes

from simple_vm_client.forc_connector.forc_connector import ForcConnector
from simple_vm_client.ttypes import (
    Backend,
    BackendNotFoundException,
    DefaultException,
    PlaybookNotFoundException,
    TemplateNotFoundException,
)
from simple_vm_client.util.state_enums import VmTaskStates

FORC_BACKEND_URL = "https://proxy-dev.bi.denbi.de:5000/"
FORC_ACCESS_URL = "https://proxy-dev.bi.denbi.de/"
GITHUB_REPO = "https://github.com/deNBI/resenvs/archive/refs/heads/staging.zip"
FORC_SECRUITY_GROUP_ID = "9a08eecc-d9a5-405b-aeda-9d4180fc94d6"
REDIS_HOST = "redis_host"
REDIS_PORT = 6379
FORC_API_KEY = "unit_test-key"
CONFIG_DATA = f"""
                redis:
                  host: {REDIS_HOST}
                  port: {REDIS_PORT}
                  password: ""
                forc:
                  FORC_BACKEND_URL: {FORC_BACKEND_URL}
                  forc_access_url: {FORC_ACCESS_URL}
                  github_playbooks_repo: {GITHUB_REPO}
                  forc_security_group_id: {FORC_SECRUITY_GROUP_ID}
            """


class TestForcConnector(unittest.TestCase):
    @patch("simple_vm_client.forc_connector.forc_connector.redis.ConnectionPool")
    @patch("simple_vm_client.forc_connector.forc_connector.redis.Redis")
    @patch("simple_vm_client.forc_connector.forc_connector.Template")
    def setUp(self, mock_template, mock_redis, mock_connection_pool):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_file.write(CONFIG_DATA)

        self.forc_connector = ForcConnector(config_file=temp_file.name)
        os.remove(temp_file.name)

    @patch("simple_vm_client.forc_connector.forc_connector.redis.ConnectionPool")
    @patch("simple_vm_client.forc_connector.forc_connector.redis.Redis")
    @patch("simple_vm_client.forc_connector.forc_connector.Template")
    @patch.dict(
        os.environ,
        {
            "FORC_API_KEY": FORC_API_KEY,
        },
    )
    def test_init(self, mock_template, mock_redis, mock_connection_pool):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_file.write(CONFIG_DATA)
        ForcConnector(temp_file.name)
        os.remove(temp_file.name)

        mock_template.assert_called_with(
            github_playbook_repo=GITHUB_REPO,
            FORC_BACKEND_URL=FORC_BACKEND_URL,
            forc_api_key=FORC_API_KEY,
        )
        mock_connection_pool.assert_called_with(host=REDIS_HOST, port=REDIS_PORT)
        mock_redis.assert_called_with(
            connection_pool=mock_connection_pool.return_value, charset="utf-8"
        )

    def test_load_config(self):
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as temp_file:
            temp_file.write(CONFIG_DATA)

        self.forc_connector.load_config(config_file=temp_file.name)
        os.remove(temp_file.name)
        self.assertEqual(self.forc_connector.FORC_BACKEND_URL, FORC_BACKEND_URL)
        self.assertEqual(self.forc_connector.FORC_ACCESS_URL, FORC_ACCESS_URL)
        self.assertEqual(self.forc_connector.GITHUB_PLAYBOOKS_REPO, GITHUB_REPO)
        self.assertEqual(self.forc_connector.REDIS_HOST, REDIS_HOST)
        self.assertEqual(self.forc_connector.REDIS_PORT, REDIS_PORT)

    @patch("simple_vm_client.forc_connector.forc_connector.redis.ConnectionPool")
    @patch("simple_vm_client.forc_connector.forc_connector.redis.Redis")
    @patch("simple_vm_client.forc_connector.forc_connector.logger.info")
    @patch("simple_vm_client.forc_connector.forc_connector.logger.error")
    def test_connect_to_redis(
        self, mock_logger_error, mock_logger_info, mock_redis, mock_redis_pool
    ):
        self.forc_connector.connect_to_redis()
        mock_redis_pool.assert_any_call(
            host=self.forc_connector.REDIS_HOST, port=self.forc_connector.REDIS_PORT
        )
        mock_redis.asser_called_once_with(
            connection_pool=self.forc_connector.redis_pool, charset="utf-8"
        )
        self.forc_connector.redis_connection.ping.return_value = True
        self.forc_connector.redis_connection.ping.assert_any_call()
        mock_logger_info.assert_any_call("Redis connection created!")
        self.forc_connector.redis_connection.ping.return_value = False
        self.forc_connector.connect_to_redis()
        mock_logger_error.assert_any_call("Could not connect to redis!")

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_users_from_backend(self, mock_get):
        backend_id = "backend_id"
        get_url = f"{self.forc_connector.FORC_BACKEND_URL}users/{backend_id}"
        return_value = MagicMock(status_code=200, body={"data"})
        return_value.json.return_value = "data"
        mock_get.return_value = return_value
        result = self.forc_connector.get_users_from_backend(backend_id)
        mock_get.assert_called_once_with(
            get_url,
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )
        self.assertEqual(result, ["data"])

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_users_from_backend_401(self, mock_get):
        backend_id = "backend_id"
        get_url = f"{self.forc_connector.FORC_BACKEND_URL}users/{backend_id}"
        return_value = MagicMock(status_code=401, body={"data"})
        mock_get.return_value = return_value
        result = self.forc_connector.get_users_from_backend(backend_id)
        mock_get.assert_called_once_with(
            get_url,
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )
        self.assertEqual(result, ["Error: 401"])

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_users_from_backend_timeout(self, mock_get):
        backend_id = "backend_id"
        get_url = f"{self.forc_connector.FORC_BACKEND_URL}users/{backend_id}"
        mock_get.side_effect = requests.Timeout("UNit Test")

        result = self.forc_connector.get_users_from_backend(backend_id)
        mock_get.assert_called_once_with(
            get_url,
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )
        self.assertEqual(result, [])

    @patch("simple_vm_client.forc_connector.forc_connector.requests.delete")
    def test_delete_user_from_backend(self, mock_delete):
        backend_id = "backend_id"
        user_id = "user_id"
        delete_url = f"{self.forc_connector.FORC_BACKEND_URL}users/{backend_id}"
        user_info = {"user": user_id}

        return_value = MagicMock(status_code=200)
        return_value.json.return_value = {"data": "success"}
        mock_delete.return_value = return_value

        result = self.forc_connector.delete_user_from_backend(backend_id, user_id)

        mock_delete.assert_called_once_with(
            delete_url,
            json=user_info,
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

        self.assertEqual(result, {"data": "success"})

    @patch("simple_vm_client.forc_connector.forc_connector.requests.delete")
    def test_delete_user_from_backend_timeout(self, mock_delete):
        backend_id = "backend_id"
        user_id = "user_id"
        delete_url = f"{self.forc_connector.FORC_BACKEND_URL}users/{backend_id}"
        user_info = {"user": user_id}

        mock_delete.side_effect = requests.Timeout("Unit Test Timeout")

        result = self.forc_connector.delete_user_from_backend(backend_id, user_id)

        mock_delete.assert_called_once_with(
            delete_url,
            json=user_info,
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

        self.assertEqual(result, {"Error": "Timeout."})

    @patch("simple_vm_client.forc_connector.forc_connector.requests.delete")
    def test_delete_user_from_backend_exception(self, mock_delete):
        backend_id = "backend_id"
        user_id = "user_id"
        delete_url = f"{self.forc_connector.FORC_BACKEND_URL}users/{backend_id}"
        user_info = {"user": user_id}

        mock_delete.side_effect = Exception("Unit Test Exception")

        with self.assertRaises(BackendNotFoundException):
            self.forc_connector.delete_user_from_backend(backend_id, user_id)

        mock_delete.assert_called_once_with(
            delete_url,
            json=user_info,
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

    @patch("simple_vm_client.forc_connector.forc_connector.requests.delete")
    @patch("simple_vm_client.forc_connector.forc_connector.json")
    def test_delete_backend_not_found_json(self, mock_json, mock_delete):
        backend_id = "backend_id"
        return_value = MagicMock(status_code=404)
        return_value.json.return_value = {"data": "success"}
        mock_json.dumps.side_effect = ValueError()
        mock_delete.return_value = return_value

        with self.assertRaises(BackendNotFoundException):
            self.forc_connector.delete_backend(backend_id)

    @patch("simple_vm_client.forc_connector.forc_connector.requests.delete")
    def test_delete_backend(self, mock_delete):
        backend_id = "backend_id"
        delete_url = f"{self.forc_connector.FORC_BACKEND_URL}backends/{backend_id}"

        return_value = MagicMock(status_code=200)
        return_value.json.return_value = {"data": "success"}
        mock_delete.return_value = return_value

        self.forc_connector.delete_backend(backend_id)

        mock_delete.assert_called_once_with(
            delete_url,
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

    @patch("simple_vm_client.forc_connector.forc_connector.requests.delete")
    def test_delete_backend_not_found(self, mock_delete):
        backend_id = "backend_id"
        delete_url = f"{self.forc_connector.FORC_BACKEND_URL}backends/{backend_id}"

        return_value = MagicMock(status_code=404)
        return_value.json.return_value = {"error": "Backend not found"}
        mock_delete.return_value = return_value

        with self.assertRaises(BackendNotFoundException):
            self.forc_connector.delete_backend(backend_id)

        mock_delete.assert_called_once_with(
            delete_url,
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

    @patch("simple_vm_client.forc_connector.forc_connector.requests.delete")
    def test_delete_backend_server_error(self, mock_delete):
        backend_id = "backend_id"
        delete_url = f"{self.forc_connector.FORC_BACKEND_URL}backends/{backend_id}"

        return_value = MagicMock(status_code=500)
        return_value.json.return_value = {"error": "Internal Server Error"}
        mock_delete.return_value = return_value

        with self.assertRaises(BackendNotFoundException) as context:
            self.forc_connector.delete_backend(backend_id)

        mock_delete.assert_called_once_with(
            delete_url,
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

    @patch("simple_vm_client.forc_connector.forc_connector.requests.delete")
    def test_delete_backend_timeout(self, mock_delete):
        backend_id = "backend_id"
        delete_url = f"{self.forc_connector.FORC_BACKEND_URL}backends/{backend_id}"

        mock_delete.side_effect = requests.Timeout("Unit Test Timeout")

        with self.assertRaises(DefaultException) as context:
            self.forc_connector.delete_backend(backend_id)

        mock_delete.assert_called_once_with(
            delete_url,
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

    @patch("simple_vm_client.forc_connector.forc_connector.requests.post")
    def test_add_user_to_backend_backend_not_found(self, mock_post):
        mock_response = MagicMock()

        mock_response.json.side_effect = Exception()
        mock_post.return_value = mock_response
        with self.assertRaises(BackendNotFoundException):
            self.forc_connector.add_user_to_backend(backend_id="test", user_id="test")

    @patch("simple_vm_client.forc_connector.forc_connector.requests.post")
    def test_add_user_to_backend(self, mock_post):
        # Create an instance of your class
        # Mock the response from requests.post
        mock_response = MagicMock()
        mock_response.json.return_value = {"key": "value"}
        mock_post.return_value = mock_response

        # Call the method you want to test
        result = self.forc_connector.add_user_to_backend(
            backend_id="backend_id", user_id="user_id"
        )

        # Assertions
        mock_post.assert_called_once_with(
            f"{self.forc_connector.FORC_BACKEND_URL}users/backend_id",
            json={"user": "user_id"},
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )
        self.assertEqual(result, {"key": "value"})

    @patch("simple_vm_client.forc_connector.forc_connector.requests.post")
    def test_add_user_to_backend_timeout(self, mock_post):
        mock_post.side_effect = requests.Timeout("Unit Test")

        result = self.forc_connector.add_user_to_backend(
            backend_id="backend_id", user_id="user_id"
        )

        mock_post.assert_called_once_with(
            f"{self.forc_connector.FORC_BACKEND_URL}users/backend_id",
            json={"user": "user_id"},
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )
        self.assertEqual(result, {"Error": "Timeout."})

    @patch("simple_vm_client.forc_connector.forc_connector.requests.post")
    def test_add_user_to_backend_exception(self, mock_post):
        mock_post.side_effect = Exception("Unit Test")

        with self.assertRaises(BackendNotFoundException):
            self.forc_connector.add_user_to_backend(
                backend_id="backend_id", user_id="user_id"
            )

        mock_post.assert_called_once_with(
            f"{self.forc_connector.FORC_BACKEND_URL}users/backend_id",
            json={"user": "user_id"},
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

    def test_has_forc(self):
        result = self.forc_connector.has_forc()
        self.assertEqual(result, self.forc_connector.FORC_BACKEND_URL is not None)

    def test_get_FORC_BACKEND_URL(self):
        result = self.forc_connector.get_FORC_BACKEND_URL()

        self.assertEqual(result, self.forc_connector.FORC_BACKEND_URL)

    def test_get_forc_access_url(self):
        result = self.forc_connector.get_forc_access_url()

        self.assertEqual(result, self.forc_connector.FORC_ACCESS_URL)

    @patch.dict(
        os.environ,
        {
            "FORC_API_KEY": FORC_API_KEY,
        },
    )
    def test_load_env(self):
        self.forc_connector.load_env()
        self.assertEqual(FORC_API_KEY, self.forc_connector.FORC_API_KEY)

    def test_set_vm_wait_for_playbook(self):
        openstack_id = "openstack_id"
        private_key = "priv"
        name = "name"
        self.forc_connector.set_vm_wait_for_playbook(
            openstack_id=openstack_id, private_key=private_key, name=name
        )
        self.forc_connector.redis_connection.hset.assert_called_once_with(
            name=openstack_id,
            mapping=dict(
                key=private_key,
                name=name,
                status=VmTaskStates.PREPARE_PLAYBOOK_BUILD.value,
            ),
        )

    def test_get_playbook_status(self):
        fake_server = fakes.generate_fake_resource(Server)
        fake_server.task_state = None
        fake_playbook = MagicMock()
        self.forc_connector._active_playbooks[fake_server.id] = fake_playbook
        self.forc_connector.redis_connection.exists.return_value = 1
        self.forc_connector.redis_connection.hget.return_value = (
            VmTaskStates.PREPARE_PLAYBOOK_BUILD.value.encode("utf-8")
        )
        result = self.forc_connector.get_playbook_status(server=fake_server)
        self.assertEqual(result.task_state, VmTaskStates.PREPARE_PLAYBOOK_BUILD.value)
        self.forc_connector.redis_connection.hget.return_value = (
            VmTaskStates.BUILD_PLAYBOOK.value.encode("utf-8")
        )
        result = self.forc_connector.get_playbook_status(server=fake_server)
        self.assertEqual(result.task_state, VmTaskStates.BUILD_PLAYBOOK.value)
        self.forc_connector.redis_connection.hget.return_value = (
            VmTaskStates.PLAYBOOK_FAILED.value.encode("utf-8")
        )
        result = self.forc_connector.get_playbook_status(server=fake_server)
        self.assertEqual(result.task_state, VmTaskStates.PLAYBOOK_FAILED.value)
        self.forc_connector.redis_connection.hget.return_value = (
            VmTaskStates.PLAYBOOK_SUCCESSFUL.value.encode("utf-8")
        )
        result = self.forc_connector.get_playbook_status(server=fake_server)
        self.assertEqual(result.task_state, VmTaskStates.PLAYBOOK_SUCCESSFUL.value)

    @patch("simple_vm_client.forc_connector.forc_connector.Playbook")
    def test_create_and_deploy_playbook(self, mock_playbook):
        key = "key"
        openstack_id = "openstack_id"
        playbook_mock = MagicMock()
        mock_playbook.return_value = playbook_mock

        self.forc_connector.redis_connection.hget.return_value = key.encode("utf-8")
        res = self.forc_connector.create_and_deploy_playbook(
            public_key=key,
            research_environment_template="vscode",
            create_only_backend=False,
            conda_packages=[],
            apt_packages=[],
            openstack_id=openstack_id,
            port=80,
            ip="192.168.0.1",
            cloud_site="Bielefeld",
            base_url="base_url",
        )
        self.forc_connector.redis_connection.hset.assert_called_once_with(
            openstack_id, "status", VmTaskStates.BUILD_PLAYBOOK.value
        )
        self.assertEqual(res, 0)
        active_play = self.forc_connector._active_playbooks[openstack_id]
        self.assertEqual(active_play, playbook_mock)

    @patch("simple_vm_client.forc_connector.forc_connector.requests.post")
    @patch("simple_vm_client.forc_connector.forc_connector.Backend")
    def test_create_backend(self, mock_backend, mock_post):
        # Arrange
        owner = "test_owner"
        user_key_url = "test_key_url"
        template = "test_template"
        upstream_url = "test_upstream_url"
        self.forc_connector.template.get_template_version_for.return_value = (
            "test_version"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": 1,
            "owner": owner,
            "location_url": "test_location_url",
            "template": template,
            "template_version": "test_version",
        }
        mock_post.return_value = mock_response

        # Act
        result = self.forc_connector.create_backend(
            owner, user_key_url, template, upstream_url
        )

        # Assert
        mock_post.assert_called_once_with(
            f"{self.forc_connector.FORC_BACKEND_URL}backends",
            json={
                "owner": owner,
                "user_key_url": user_key_url,
                "template": template,
                "template_version": "test_version",
                "upstream_url": upstream_url,
            },
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

        mock_response.json.assert_called_once()
        mock_backend.assert_called_once_with(
            id=1,
            owner=owner,
            location_url="test_location_url",
            template=template,
            template_version="test_version",
        )

        self.assertEqual(result, mock_backend.return_value)

    @patch(
        "simple_vm_client.forc_connector.forc_connector.requests.post",
        side_effect=requests.Timeout,
    )
    def test_create_backend_timeout(self, mock_post):
        # Arrange
        owner = "test_owner"
        user_key_url = "test_key_url"
        template = "test_template"
        upstream_url = "test_upstream_url"

        # Act & Assert
        with self.assertRaises(DefaultException):
            self.forc_connector.create_backend(
                owner, user_key_url, template, upstream_url
            )

        mock_post.assert_called_once()

    @patch(
        "simple_vm_client.forc_connector.forc_connector.requests.post",
        side_effect=Exception("Test error"),
    )
    def test_create_backend_exception(self, mock_post):
        # Arrange
        owner = "test_owner"
        user_key_url = "test_key_url"
        template = "test_template"
        upstream_url = "test_upstream_url"

        # Act & Assert
        with self.assertRaises(DefaultException):
            self.forc_connector.create_backend(
                owner, user_key_url, template, upstream_url
            )

        mock_post.assert_called_once()

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_backends(self, mock_get):
        # Arrange

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": 1,
                "owner": "test_owner",
                "location_url": "test_location_url",
                "template": "test_template",
                "template_version": "test_version",
            },
            {
                "id": 2,
                "owner": "another_owner",
                "location_url": "another_location_url",
                "template": "another_template",
                "template_version": "another_version",
            },
        ]
        mock_get.return_value = mock_response

        # Act
        result = self.forc_connector.get_backends()

        # Assert
        mock_get.assert_called_once_with(
            f"{self.forc_connector.FORC_BACKEND_URL}backends",
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

        mock_response.json.assert_called_once()

        expected_backends = [
            Backend(
                id=1,
                owner="test_owner",
                location_url="test_location_url",
                template="test_template",
                template_version="test_version",
            ),
            Backend(
                id=2,
                owner="another_owner",
                location_url="another_location_url",
                template="another_template",
                template_version="another_version",
            ),
        ]

        self.assertEqual(result, expected_backends)

    @patch(
        "simple_vm_client.forc_connector.forc_connector.requests.get",
        side_effect=requests.Timeout,
    )
    def test_get_backends_timeout(self, mock_get):
        # Arrange

        # Act & Assert
        with self.assertRaises(DefaultException):
            self.forc_connector.get_backends()

        mock_get.assert_called_once()

    def test_is_playbook_active(self) -> bool:
        openstack_id = "openstack_id"
        self.forc_connector.is_playbook_active(openstack_id=openstack_id)
        self.forc_connector.redis_connection.exists.assert_called_once_with(
            openstack_id
        )

    def test_get_playbook_logs(self):
        openstack_id = "openstack_id"
        self.forc_connector.redis_connection.exists.return_value = 1
        playbook_mock = MagicMock()
        playbook_mock.get_logs.return_value = "status", "stdout", "stderr"
        self.forc_connector._active_playbooks = {openstack_id: playbook_mock}
        self.forc_connector.get_playbook_logs(openstack_id=openstack_id)
        self.forc_connector.redis_connection.exists.assert_called_once_with(
            openstack_id
        )
        playbook_mock.get_logs.assert_called_once()
        playbook_mock.cleanup.assert_called_once()

    def test_get_playbook_logs_no_playbook(self):
        openstack_id = "openstack_id"
        with self.assertRaises(PlaybookNotFoundException):
            self.forc_connector.get_playbook_logs(openstack_id=openstack_id)
        self.forc_connector.redis_connection.exists.assert_called_once_with(
            openstack_id
        )

    def test_create_backend_template_exc(self):
        self.forc_connector.template.get_template_version_for.return_value = None
        with self.assertRaises(TemplateNotFoundException):
            self.forc_connector.create_backend(
                owner="dede",
                user_key_url="dede",
                template="not_found",
                upstream_url="de",
            )

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_backend_sexc(self, mock_get):
        mock_response = MagicMock(status_code=401)
        mock_get.return_value = mock_response
        with self.assertRaises(DefaultException):
            self.forc_connector.get_backends()

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_backends_by_template_exc(self, mock_get):
        mock_response = MagicMock(status_code=401)
        mock_get.return_value = mock_response
        with self.assertRaises(DefaultException):
            self.forc_connector.get_backends_by_template(template="ds")

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_backends_by_template(self, mock_get):
        # Arrange
        template = "test_template"

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": 1,
                "owner": "test_owner",
                "location_url": "test_location_url",
                "template": template,
                "template_version": "test_version",
            },
            {
                "id": 2,
                "owner": "another_owner",
                "location_url": "another_location_url",
                "template": template,
                "template_version": "another_version",
            },
        ]
        mock_get.return_value = mock_response

        # Act
        result = self.forc_connector.get_backends_by_template(template)

        # Assert
        mock_get.assert_called_once_with(
            f"{self.forc_connector.FORC_BACKEND_URL}backends/byTemplate/{template}",
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

        mock_response.json.assert_called_once()

        expected_backends = [
            Backend(
                id=1,
                owner="test_owner",
                location_url="test_location_url",
                template=template,
                template_version="test_version",
            ),
            Backend(
                id=2,
                owner="another_owner",
                location_url="another_location_url",
                template=template,
                template_version="another_version",
            ),
        ]

        self.assertEqual(result, expected_backends)

    @patch(
        "simple_vm_client.forc_connector.forc_connector.requests.get",
        side_effect=requests.Timeout,
    )
    def test_get_backends_by_template_timeout(self, mock_get):
        # Arrange
        template = "test_template"

        # Act & Assert
        with self.assertRaises(DefaultException):
            self.forc_connector.get_backends_by_template(template)

        mock_get.assert_called_once()

    def test_get_metadata_by_research_environment(self):
        metadata_Mock = MagicMock()
        res_env = "testres"

        return_value = {res_env: metadata_Mock}
        template_mock = MagicMock()
        template_mock.loaded_research_env_metadata = {res_env: metadata_Mock}
        self.forc_connector.template = template_mock
        self.forc_connector.template.loaded_research_env_metadata = return_value
        res = self.forc_connector.get_metadata_by_research_environment(
            research_environment=res_env
        )
        self.assertEqual(metadata_Mock, res)

    def test_get_metadata_by_research_environment_none(self):
        res_env = "testres"
        template_mock = MagicMock()
        template_mock.loaded_research_env_metadata = None
        res = self.forc_connector.get_metadata_by_research_environment(
            research_environment=res_env
        )
        self.assertEqual(res, None)

    def test_get_metadata_by_research_environment_none_two(self):
        metadata_Mock = MagicMock()

        template_mock = MagicMock()
        template_mock.loaded_research_env_metadata = {"dede": metadata_Mock}
        self.forc_connector.template = template_mock
        res = self.forc_connector.get_metadata_by_research_environment(
            research_environment="user_key_url"
        )
        self.assertEqual(None, None)

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_backend_by_id_exc(self, mock_get):
        backend_id = "your_backend_id"
        mock_response = MagicMock()
        mock_response.json.side_effect = Exception()
        mock_get.return_value = mock_response

        with self.assertRaises(Exception):
            self.forc_connector.get_backend_by_id(backend_id)

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_backend_by_id(self, mock_get):
        backend_id = "your_backend_id"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": backend_id,
            "owner": "owner",
            "location_url": "location_url",
            "template": "template",
            "template_version": "template_version",
        }
        mock_get.return_value = mock_response

        result = self.forc_connector.get_backend_by_id(backend_id)

        mock_get.assert_called_once_with(
            f"{self.forc_connector.FORC_BACKEND_URL}backends/{backend_id}",
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

        expected_backend = Backend(
            id=backend_id,
            owner="owner",
            location_url="location_url",
            template="template",
            template_version="template_version",
        )

        self.assertEqual(result, expected_backend)

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_backend_by_id_timeout(self, mock_get):
        backend_id = "your_backend_id"
        mock_get.side_effect = requests.Timeout("Unit Test Timeout")

        with self.assertRaises(DefaultException) as context:
            self.forc_connector.get_backend_by_id(backend_id)

        self.assertIn("Unit Test Timeout", str(context.exception))

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_backends_by_owner_default_exc(self, mock_get):
        mock_response = MagicMock(status_code=401)
        mock_get.return_value = mock_response
        with self.assertRaises(DefaultException):
            self.forc_connector.get_backends_by_owner(owner="user")

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_backends_by_owner(self, mock_get):
        owner = "your_owner"
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "id": "backend_id_1",
                "owner": owner,
                "location_url": "location_url_1",
                "template": "template_1",
                "template_version": "template_version_1",
            },
            {
                "id": "backend_id_2",
                "owner": owner,
                "location_url": "location_url_2",
                "template": "template_2",
                "template_version": "template_version_2",
            },
        ]
        mock_get.return_value = mock_response

        result = self.forc_connector.get_backends_by_owner(owner)

        mock_get.assert_called_once_with(
            f"{self.forc_connector.FORC_BACKEND_URL}backends/byOwner/{owner}",
            timeout=(30, 30),
            headers={"X-API-KEY": self.forc_connector.FORC_API_KEY},
            verify=True,
        )

        expected_backends = [
            Backend(
                id="backend_id_1",
                owner=owner,
                location_url="location_url_1",
                template="template_1",
                template_version="template_version_1",
            ),
            Backend(
                id="backend_id_2",
                owner=owner,
                location_url="location_url_2",
                template="template_2",
                template_version="template_version_2",
            ),
        ]

        self.assertEqual(result, expected_backends)

    @patch("simple_vm_client.forc_connector.forc_connector.requests.get")
    def test_get_backends_by_owner_timeout(self, mock_get):
        owner = "your_owner"
        mock_get.side_effect = requests.Timeout("Unit Test Timeout")

        with self.assertRaises(DefaultException) as context:
            self.forc_connector.get_backends_by_owner(owner)

        self.assertIn("Unit Test Timeout", str(context.exception))
