import os
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

import requests

from simple_vm_client.bibigrid_connector.bibigrid_connector import BibigridConnector
from simple_vm_client.ttypes import ClusterInfo, ClusterInstance

HOST = "example.com"
PORT = 8080
HTTPS = True
MODES = ["mode1", "mode2"]
MASTER_WITH_PUBLIC_IP = False
LOCAL_DNS_LOOKUP = False
NETWORK = "my_network"
SUB_NETWORK = "my_sub_network"
PRODUCTION = True
DEFAULT_CLUSTER_INFO = ClusterInfo(
    group_id="fake_group_id",
    network_id="fake_network_id",
    public_ip="fake_public_ip",
    subnet_id="fake_subnet_id",
    user="fake_user",
    inst_counter=42,
    cluster_id="fake_cluster_id",
    key_name="fake_key_name",
)
DEFAULT_MASTER_INSTANCE = ClusterInstance(image="master_image", type="master_flavor")
DEFAULT_WORKER_INSTANCES = [
    ClusterInstance(image="worker_flavor", count=3, type="worker_flavor")
]


class TestBibigridConnector(unittest.TestCase):
    @patch(
        "simple_vm_client.bibigrid_connector.bibigrid_connector.BibigridConnector.is_bibigrid_available"
    )
    def setUp(self, mock_is_bibigrid_available):
        self.fake_config = f"""
         bibigrid:
           host: {HOST}
           port: {PORT}
           https: {HTTPS}
           modes: {MODES}
           use_master_with_public_ip: {MASTER_WITH_PUBLIC_IP}
           localDnsLookup: {LOCAL_DNS_LOOKUP}
           ansibleGalaxyRoles:
             - role1
             - role2

         openstack:
           network: {NETWORK}
           sub_network: {SUB_NETWORK}

         production: {PRODUCTION}
         """
        self.fake_config_file = tempfile.NamedTemporaryFile(
            mode="w+", suffix=".yml", delete=False
        )
        self.fake_config_file.write(self.fake_config)
        self.fake_config_file.close()
        mock_is_bibigrid_available.return_value = True
        self.connector = BibigridConnector(config_file=self.fake_config_file.name)

    def tearDown(self):
        # Clean up: Remove the temporary file
        os.remove(self.fake_config_file.name)

    @patch(
        "simple_vm_client.bibigrid_connector.bibigrid_connector.BibigridConnector.is_bibigrid_available"
    )
    def test_load_config_yml(self, mock_is_bibigrid_available):
        # Instantiate BibigridConnector with the fake config
        self.connector.load_config_yml(self.fake_config_file.name)
        self.assertEqual(self.connector._BIBIGRID_HOST, HOST)
        self.assertEqual(self.connector._BIBIGRID_PORT, PORT)
        self.assertEqual(self.connector._BIBIGRID_USE_HTTPS, HTTPS)
        self.assertEqual(self.connector._BIBIGRID_MODES, MODES)
        self.assertEqual(
            self.connector._BIBIGRID_USE_MASTER_WITH_PUBLIC_IP, MASTER_WITH_PUBLIC_IP
        )
        self.assertEqual(self.connector._BIBIGRID_LOCAL_DNS_LOOKUP, LOCAL_DNS_LOOKUP)
        self.assertEqual(self.connector._BIBIGRID_ANSIBLE_ROLES, ["role1", "role2"])
        self.assertEqual(self.connector._NETWORK, NETWORK)
        self.assertEqual(self.connector._SUB_NETWORK, SUB_NETWORK)
        self.assertEqual(self.connector._PRODUCTION, PRODUCTION)

        # Check the generated URLs
        self.assertEqual(
            self.connector._BIBIGRID_URL, "https://example.com:8080/bibigrid/"
        )
        self.assertEqual(self.connector._BIBIGRID_EP, "https://example.com:8080")

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    def test_is_bibigrid_available_when_url_not_set(self, mock_logger_info):
        # Arrange
        self.connector._BIBIGRID_EP = ""

        # Act
        result = self.connector.is_bibigrid_available()

        # Assert
        mock_logger_info.assert_any_call("Checking if Bibigrid is available")
        mock_logger_info.assert_any_call("Bibigrid Url is not set")
        self.assertFalse(result)

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.get")
    def test_is_bibigrid_available_when_request_succeeds(
        self, mock_get, mock_logger_info
    ):
        # Arrange
        mock_get.return_value = Mock(status_code=200)

        # Act
        result = self.connector.is_bibigrid_available()
        mock_logger_info.assert_any_call("Checking if Bibigrid is available")

        # Assert
        self.assertTrue(result)
        mock_get.assert_called_once_with(f"{self.connector._BIBIGRID_EP}/server/health")

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.error")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.get")
    def test_is_bibigrid_available_when_request_wrong_status_code(
        self, mock_get, mock_logger_error, mock_logger_info
    ):
        # Arrange
        mock_get.return_value = Mock(status_code=500)

        # Act
        result = self.connector.is_bibigrid_available()
        mock_logger_info.assert_any_call("Checking if Bibigrid is available")

        # Assert
        self.assertFalse(result)
        mock_get.assert_called_once_with(f"{self.connector._BIBIGRID_EP}/server/health")
        mock_logger_error.assert_called_once_with("Bibigrid returned status code 500")

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.error")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.get")
    def test_is_bibigrid_available_when_request_exception(
        self, mock_get, mock_logger_error, mock_logger_info
    ):
        # Arrange
        mock_get.side_effect = requests.RequestException("Could not connect")

        # Act
        result = self.connector.is_bibigrid_available()
        mock_logger_info.assert_any_call("Checking if Bibigrid is available")

        # Assert
        self.assertFalse(result)
        mock_get.assert_called_once_with(f"{self.connector._BIBIGRID_EP}/server/health")
        mock_logger_error.assert_called_once_with(
            "Error while checking Bibigrid availability", exc_info=True
        )

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.delete")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    def test_terminate_cluster(self, mock_logger_info, mock_delete):
        # Arrange
        cluster_id = "fake_cluster_id"

        expected_url = f"{self.connector._BIBIGRID_URL}terminate/{cluster_id}"
        expected_headers = {"content-Type": "application/json"}
        expected_body = {"mode": "openstack"}
        expected_response = {"fake_key": "fake_value"}

        mock_delete.return_value = MagicMock(json=lambda: expected_response)

        # Act
        result = self.connector.terminate_cluster(cluster_id)

        # Assert
        mock_delete.assert_called_once_with(
            url=expected_url,
            json=expected_body,
            headers=expected_headers,
            verify=self.connector._PRODUCTION,
        )
        mock_logger_info.assert_any_call(f"Terminate cluster: {cluster_id}")
        mock_logger_info.assert_any_call(expected_response)
        self.assertEqual(result, expected_response)

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.post")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    def test_start_cluster(self, mock_logger_info, mock_post):
        public_key = "fake_public_key"

        user = "fake_user"

        # Mock the response from the requests.post call
        mock_post.return_value.json.return_value = {"fake": "response"}

        # Call the method to test
        result = self.connector.start_cluster(
            public_key=public_key,
            master_instance=DEFAULT_MASTER_INSTANCE,
            worker_instances=DEFAULT_WORKER_INSTANCES,
            user=user,
        )
        wI = []
        for wk in DEFAULT_WORKER_INSTANCES:
            wI.append(wk.__dict__)
        body = {
            "mode": "openstack",
            "subnet": self.connector._SUB_NETWORK,
            "sshPublicKeys": [public_key],
            "user": user,
            "sshUser": "ubuntu",
            "masterInstance": DEFAULT_MASTER_INSTANCE.__dict__,
            "workerInstances": wI,
            "useMasterWithPublicIp": self.connector._BIBIGRID_USE_MASTER_WITH_PUBLIC_IP,
            "ansibleGalaxyRoles": self.connector._BIBIGRID_ANSIBLE_ROLES,
            "localDNSLookup": self.connector._BIBIGRID_LOCAL_DNS_LOOKUP,
        }
        for mode in self.connector._BIBIGRID_MODES:
            body.update({mode: True})

        # Assertions
        mock_post.assert_called_once_with(
            url=self.connector._BIBIGRID_URL + "create",
            json=body,
            headers={"content-Type": "application/json"},
            verify=self.connector._PRODUCTION,
        )
        args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["sshPublicKeys"], [public_key])
        self.assertEqual(kwargs["json"]["user"], user)
        self.assertIn("masterInstance", kwargs["json"])
        self.assertIn("workerInstances", kwargs["json"])
        self.assertIn("useMasterWithPublicIp", kwargs["json"])
        self.assertIn("ansibleGalaxyRoles", kwargs["json"])
        self.assertIn("localDNSLookup", kwargs["json"])
        self.assertIn("openstack", kwargs["json"]["mode"])

        self.assertEqual(result, {"fake": "response"})

        for wk in DEFAULT_WORKER_INSTANCES:
            mock_logger_info.assert_any_call(wk)
        mock_logger_info.assert_any_call({"fake": "response"})

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.get")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    def test_get_clusters_info(self, mock_logger_info, mock_get):
        # Mock the response from the requests.get call
        mock_response = MagicMock()
        mock_response.json.return_value = {"info": [{"cluster-id": "fake_cluster_id"}]}
        mock_get.return_value = mock_response

        # Call the method to test
        result = self.connector.get_clusters_info()
        headers = {"content-Type": "application/json"}
        body = {"mode": "openstack"}

        mock_get.assert_called_once_with(
            url=self.connector._BIBIGRID_URL + "list",
            json=body,
            headers=headers,
            verify=self.connector._PRODUCTION,
        )

        # Assertions

        self.assertEqual(result, [{"cluster-id": "fake_cluster_id"}])
        mock_logger_info.assert_called_once_with("Get clusters info")

    @patch.object(BibigridConnector, "get_clusters_info")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    def test_get_cluster_info_none(self, mock_logger_info, mock_get_clusters_info):
        mock_get_clusters_info.return_value = []
        result = self.connector.get_cluster_info("fake_cluster_id")
        mock_logger_info.assert_any_call("Get Cluster info from fake_cluster_id")
        self.assertIsNone(result)

    @patch.object(BibigridConnector, "get_clusters_info")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    def test_get_cluster_info(self, mock_logger_info, mock_get_clusters_info):
        # Mock the response from get_clusters_info
        mock_get_clusters_info.return_value = [
            {
                "cluster-id": "fake_cluster_id",
                "group-id": "fake_group_id",
                "network-id": "fake_network_id",
                "public-ip": "fake_public_ip",
                "subnet-id": "fake_subnet_id",
                "user": "fake_user",
                "# inst": 1,
                "key name": "fake_key_name",
            }
        ]

        # Call the method to test
        result = self.connector.get_cluster_info("fake_cluster_id")

        # Assertions
        mock_get_clusters_info.assert_called_once()
        self.assertEqual(
            result,
            ClusterInfo(
                group_id="fake_group_id",
                network_id="fake_network_id",
                public_ip="fake_public_ip",
                subnet_id="fake_subnet_id",
                user="fake_user",
                inst_counter=1,
                cluster_id="fake_cluster_id",
                key_name="fake_key_name",
            ),
        )
        mock_logger_info.assert_any_call("Get Cluster info from fake_cluster_id")
        mock_logger_info.assert_any_call(f"Cluster fake_cluster_id info: {result} ")

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.get")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    def test_get_cluster_status(self, mock_logger_info, mock_requests_get):
        # Arrange
        cluster_id = "123"

        # Mock the response from requests.get
        response_data = {"log": "Some log", "msg": "Some message"}
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response

        # Act
        result = self.connector.get_cluster_status(cluster_id)

        # Assert
        mock_requests_get.assert_called_once_with(
            url=f"{self.connector._BIBIGRID_URL}info/{cluster_id}",
            json={"mode": "openstack"},
            headers={"content-Type": "application/json"},
            verify=self.connector._PRODUCTION,
        )
        mock_response.json.assert_called_once()
        mock_response.raise_for_status.assert_called_once()
        mock_logger_info.assert_called_with(
            f"Cluster {cluster_id} status: {response_data}"
        )
        self.assertEqual(result, response_data)

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.get")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.exception")
    def test_get_cluster_status_with_exception(
        self, mock_logger_exception, mock_logger_info, mock_requests_get
    ):
        # Arrange
        cluster_id = "123"
        mock_requests_get.side_effect = requests.RequestException("Could not connect")
        # Act
        result = self.connector.get_cluster_status(cluster_id)

        self.assertEqual(result, {"error": "Could not connect"})
        mock_logger_exception.assert_called_once_with(
            "Error while getting Cluster status"
        )
