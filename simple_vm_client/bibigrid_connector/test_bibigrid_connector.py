import os
import tempfile
import unittest
from unittest.mock import MagicMock, Mock, patch

import requests

from simple_vm_client.bibigrid_connector.bibigrid_connector import BibigridConnector
from simple_vm_client.ttypes import (
    ClusterInfo,
    ClusterInstance,
    ClusterInstanceMetadata,
    ClusterMessage,
    ClusterState,
    ClusterVolume,
)

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
    message="fake_message",
    cluster_id="fake_cluster_id",
    ready=False,
)
DEFAULT_WORKER_INSTANCES = [
    ClusterInstance(image="worker_flavor", type="worker_flavor", volumes=[])
]
GATEWAY_IP = "192.168.0.1"
INTERNAL_GATEWAY_IP = "192.168.0.2"
METADATA = ClusterInstanceMetadata(user_id="123", project_id="345", project_name="TEST")
SHARED_VOLUME = ClusterVolume(
    openstack_id="abcd",
    permanent=True,
    exists=True,
    size=50,
    type="ext4",
    mount_path="/vol/spool",
)
DEFAULT_MASTER_INSTANCE = ClusterInstance(
    image="master_image", type="master_flavor", volumes=[SHARED_VOLUME]
)

PORT_FUNCTION = "30000 + 256 * oct3 + oct4"

HEADERS = {"Content-Type": "application/json"}


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
           sub_network: {SUB_NETWORK}

           ansibleGalaxyRoles:
             - role1
             - role2

         openstack:
           network: {NETWORK}
           gateway_ip: {GATEWAY_IP}
           internal_gateway_ip: {INTERNAL_GATEWAY_IP}
           ssh_port_calculation: {PORT_FUNCTION}
           udp_port_calculation: {PORT_FUNCTION}

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
        self.assertEqual(self.connector._GATEWAY_IP, INTERNAL_GATEWAY_IP),
        self.assertEqual(self.connector._PORT_FUNCTION, PORT_FUNCTION)
        self.assertEqual(
            self.connector._BIBIGRID_USE_MASTER_WITH_PUBLIC_IP, MASTER_WITH_PUBLIC_IP
        )
        self.assertEqual(self.connector._BIBIGRID_LOCAL_DNS_LOOKUP, LOCAL_DNS_LOOKUP)
        self.assertEqual(self.connector._BIBIGRID_ANSIBLE_ROLES, ["role1", "role2"])
        self.assertEqual(self.connector._NETWORK, NETWORK)
        self.assertEqual(self.connector._SUB_NETWORK, SUB_NETWORK)
        self.assertEqual(self.connector._PRODUCTION, PRODUCTION)

        # Check the generated URLs

        self.assertEqual(self.connector._BIBIGRID_EP, "https://example.com:8080")

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    def test_is_bibigrid_available_when_url_not_set(self, mock_logger_info):
        # Arrange
        self.connector._BIBIGRID_EP = ""

        # Act
        result = self.connector.is_bibigrid_available()

        self.assertFalse(result)

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.get")
    def test_is_bibigrid_available_when_request_succeeds(self, mock_get):
        # Arrange
        mock_get.return_value = Mock(status_code=200)

        # Act
        result = self.connector.is_bibigrid_available()

        # Assert
        self.assertTrue(result)
        mock_get.assert_called_once_with(
            url=f"{self.connector._BIBIGRID_EP}/bibigrid/requirements",
            headers=HEADERS,
            verify=self.connector._PRODUCTION,
        )

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.get")
    def test_is_bibigrid_available_when_request_wrong_status_code(
        self,
        mock_get,
    ):
        # Arrange
        mock_get.return_value = Mock(status_code=500)

        # Act
        result = self.connector.is_bibigrid_available()

        # Assert
        self.assertFalse(result)
        mock_get.assert_called_once_with(
            url=f"{self.connector._BIBIGRID_EP}/bibigrid/requirements",
            headers=HEADERS,
            verify=self.connector._PRODUCTION,
        )

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.get")
    def test_is_bibigrid_available_when_request_exception(self, mock_get):
        # Arrange
        mock_get.side_effect = requests.RequestException("Could not connect")

        # Act
        result = self.connector.is_bibigrid_available()

        # Assert
        self.assertFalse(result)
        mock_get.assert_called_once_with(
            url=f"{self.connector._BIBIGRID_EP}/bibigrid/requirements",
            headers=HEADERS,
            verify=self.connector._PRODUCTION,
        )

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.delete")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    def test_terminate_cluster(self, mock_logger_info, mock_delete):
        # Arrange
        cluster_id = "fake_cluster_id"

        expected_url = f"{self.connector._BIBIGRID_EP}/bibigrid/terminate/{cluster_id}"
        expected_response = {"fake_key": "fake_value"}

        mock_delete.return_value = MagicMock(json=lambda: expected_response)

        # Act
        result = self.connector.terminate_cluster(cluster_id)

        # Assert
        mock_delete.assert_called_once_with(
            url=expected_url,
            headers=HEADERS,
            verify=self.connector._PRODUCTION,
        )
        mock_logger_info.assert_any_call(f"Terminate cluster: {cluster_id}")
        mock_logger_info.assert_any_call(expected_response)
        self.assertEqual(result, expected_response)

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.post")
    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.logger.info")
    def test_start_cluster(self, mock_logger_info, mock_post):
        public_key = "fake_public_key"

        # Mock the response from the requests.post call
        mock_post.return_value.json.return_value = {
            "cluster_id": "123",
            "message": "started",
        }

        # Call the method to test
        result = self.connector.start_cluster(
            public_keys=[public_key],
            master_instance=DEFAULT_MASTER_INSTANCE,
            worker_instances=DEFAULT_WORKER_INSTANCES,
            metadata=METADATA,
        )
        wI = []
        for wk in DEFAULT_WORKER_INSTANCES:
            wkvars = vars(wk)
            wkvars.update({"onDemand": False})

            wI.append(wkvars)

        master_instance = vars(DEFAULT_MASTER_INSTANCE)
        master_instance.update(
            {
                "volumes": [
                    {
                        "id": SHARED_VOLUME.openstack_id,
                        "size": SHARED_VOLUME.size,
                        "mountPoint": SHARED_VOLUME.mount_path,
                        "exists": SHARED_VOLUME.exists,
                        "permanent": SHARED_VOLUME.permanent,
                    }
                ]
            }
        )

        body = [
            {
                "infrastructure": "openstack",
                "cloud": "openstack",
                "sshTimeout": 30,
                "useMasterAsCompute": False,
                "useMasterWithPublicIP": False,
                "dontUploadCredentials": True,
                "noAllPartition": True,
                "gateway": {"ip": INTERNAL_GATEWAY_IP, "portFunction": PORT_FUNCTION},
                "masterInstance": {
                    "type": master_instance["type"],
                    "image": master_instance["image"],
                    "volumes": master_instance["volumes"],
                },
                "nfs": True,
                "workerInstances": wI,
                "sshUser": "ubuntu",
                "subnet": self.connector._SUB_NETWORK,
                "network": "",
                "waitForServices": ["de.NBI_Bielefeld_environment.service"],
                "sshPublicKeys": [public_key],
                "securityGroups": ["defaultSimpleVM"],
                "meta": vars(METADATA),
            }
        ]
        full_body = {"configurations": body}

        # Assertions
        mock_post.assert_called_once_with(
            url=self.connector._BIBIGRID_EP + "/bibigrid/create",
            headers=HEADERS,
            json=full_body,
            verify=self.connector._PRODUCTION,
        )

        self.assertEqual(result, ClusterMessage(cluster_id="123", message="started"))

    @patch("simple_vm_client.bibigrid_connector.bibigrid_connector.requests.get")
    def test_get_cluster_state(self, mock_requests_get):
        # Arrange
        cluster_id = "123"

        # Mock the response from requests.get
        response_data = vars(
            ClusterState(
                cluster_id=cluster_id,
                message="test",
                state="tmp",
                ssh_user="ubuntu",
                floating_ip=None,
                last_changed=None,
            )
        )
        mock_response = MagicMock()
        mock_response.json.return_value = response_data
        mock_response.raise_for_status.return_value = None
        mock_requests_get.return_value = mock_response
        mock_requests_get.return_value.status_code = 200

        # Act
        result = self.connector.get_cluster_state(cluster_id)

        # Assert
        mock_requests_get.assert_called_once_with(
            url=f"{self.connector._BIBIGRID_EP}/bibigrid/state/{cluster_id}",
            headers=HEADERS,
            verify=self.connector._PRODUCTION,
        )
        mock_response.json.assert_called_once()
        mock_response.raise_for_status.assert_called_once()
        self.assertEqual(result, ClusterState(**response_data))
