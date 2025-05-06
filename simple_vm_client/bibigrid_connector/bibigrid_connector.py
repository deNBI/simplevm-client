import requests
import yaml

from simple_vm_client.ttypes import (
    ClusterInfo,
    ClusterInstance,
    ClusterInstanceMetadata,
    ClusterLog,
    ClusterMessage,
    ClusterNotFoundException,
    ClusterState,
)
from simple_vm_client.util.logger import setup_custom_logger

logger = setup_custom_logger(__name__)


class BibigridConnector:
    def __init__(self, config_file: str):
        logger.info("Initializing Bibigrid Connector")

        self._BIBIGRID_MODES: str = ""
        self._BIBIGRID_HOST: str = ""
        self._BIBIGRID_PORT: str = ""
        self._BIBIGRID_ANSIBLE_ROLES = []
        self._BIBIGRID_LOCAL_DNS_LOOKUP = False
        self._BIBIGRID_EP = ""
        self._BIBIGRID_USE_MASTER_WITH_PUBLIC_IP: bool = False
        self._GATEWAY_IP = ""
        self._PORT_FUNCTION = ""
        self._PRODUCTION_bool = True
        self._DEFAULT_SECURITY_GROUP_NAME: str = "defaultSimpleVM"

        self.load_config_yml(config_file=config_file)

    def load_config_yml(self, config_file: str) -> None:
        with open(config_file, "r") as ymlfile:
            cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
            # Check if "bibigrid" key is present in the loaded YAML
            if "bibigrid" not in cfg:
                # Optionally, you can log a message or take other actions here
                logger.info("Bibigrid configuration not found. Skipping.")
                return

            bibigrid_cfg = cfg["bibigrid"]
            if not bibigrid_cfg.get("activated", True):
                logger.info("Bibigrid Config available but deactivated. Skipping..")
                return
            self._BIBIGRID_HOST = bibigrid_cfg["host"]
            self._BIBIGRID_PORT = bibigrid_cfg["port"]
            self._BIBIGRID_USE_HTTPS = bibigrid_cfg.get("https", False)
            self._BIBIGRID_MODES = bibigrid_cfg["modes"]
            self._BIBIGRID_USE_MASTER_WITH_PUBLIC_IP = bibigrid_cfg.get(
                "use_master_with_public_ip", False
            )
            self._SUB_NETWORK = bibigrid_cfg["sub_network"]

            self._BIBIGRID_LOCAL_DNS_LOOKUP = bibigrid_cfg.get("localDnsLookup", False)
            self._BIBIGRID_ANSIBLE_ROLES = bibigrid_cfg.get("ansibleGalaxyRoles", [])

            openstack_cfg = cfg["openstack"]
            self._NETWORK = openstack_cfg["network"]
            self._GATEWAY_IP = (
                openstack_cfg.get("internal_gateway_ip") or openstack_cfg["gateway_ip"]
            )
            self._PORT_FUNCTION = openstack_cfg["ssh_port_calculation"]
            self._PRODUCTION = cfg["production"]

            protocol = "https" if self._BIBIGRID_USE_HTTPS else "http"
            self._BIBIGRID_EP = (
                f"{protocol}://{self._BIBIGRID_HOST}:{self._BIBIGRID_PORT}"
            )

            logger.info("Config loaded: Bibigrid")
            self.is_bibigrid_available()

    def get_cluster_log(self, cluster_id: str) -> ClusterLog:
        logger.info(f"Get Cluster {cluster_id} logs...")

        headers = {"content-Type": "application/json"}
        request_url = f"{self._BIBIGRID_EP}/bibigrid/log/{cluster_id}"

        try:
            response = requests.get(
                url=request_url,
                headers=headers,
                verify=self._PRODUCTION,
            )
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx and 5xx)
            json_resp = response.json(strict=False)

            return ClusterLog(
                cluster_id=cluster_id,
                message=json_resp["message"],
                log=json_resp["log"],
            )

        except requests.RequestException as e:
            logger.exception("Error while getting Cluster status")
            return {"error": str(e)}

    def get_cluster_supported_ubuntu_os_versions(self) -> list[str]:
        """
        Retrieves the supported Ubuntu OS versions for cluster nodes.

        Returns:
            list[str]: A list of supported Ubuntu OS versions.
        """

        logger.info("Get Cluster Node requirements")

        request_url = f"{self._BIBIGRID_EP}/bibigrid/requirements"
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.get(
                url=request_url, headers=headers, verify=self._PRODUCTION
            )
            response.raise_for_status()  # Raise an exception for bad status codes
        except requests.RequestException as e:
            logger.error(f"Failed to retrieve node requirements: {e}")
            return []

        response_content = response.json()
        os_versions = (
            response_content.get("cloud_node_requirements", {})
            .get("os_distro", {})
            .get("ubuntu", {})
            .get("os_versions", [])
        )

        logger.info(f"Supported Ubuntu OS versions: {os_versions}")
        return os_versions

    def get_cluster_state(self, cluster_id: str) -> ClusterInfo:
        logger.info(f"Get Cluster state from {cluster_id}")
        request_url = f"{self._BIBIGRID_EP}/bibigrid/state/{cluster_id}"
        headers = {"content-Type": "application/json"}
        response = requests.get(
            url=request_url,
            headers=headers,
            verify=self._PRODUCTION,
        )

        if response.status_code == 200:
            response_content = response.json()
            return ClusterState(**response_content)
        else:
            raise ClusterNotFoundException(message=f"Cluster {cluster_id} not found!")

    def get_cluster_info(self, cluster_id: str) -> ClusterInfo:
        logger.info(f"Get Cluster info from {cluster_id}")
        request_url = f"{self._BIBIGRID_EP}/bibigrid/info/{cluster_id}"
        headers = {"content-Type": "application/json"}
        response = requests.get(
            url=request_url,
            headers=headers,
            verify=self._PRODUCTION,
        )

        if response.status_code == 200:
            response_content = response.json()
            return ClusterInfo(
                message=response_content["message"],
                cluster_id=cluster_id,
                ready=response_content["ready"],
            )
        else:
            raise ClusterNotFoundException(message=f"Cluster {cluster_id} not found!")

    def is_bibigrid_available(self) -> bool:
        request_url = f"{self._BIBIGRID_EP}/bibigrid/requirements"
        headers = {"Content-Type": "application/json"}

        try:
            response = requests.get(
                url=request_url, headers=headers, verify=self._PRODUCTION
            )
            response.raise_for_status()  # Raise an exception for bad status codes
        except requests.RequestException:
            return False
        return True

    def terminate_cluster(self, cluster_id: str) -> dict[str, str]:
        # TODO only needs specific config keywoards
        logger.info(f"Terminate cluster: {cluster_id}")
        headers = {"content-Type": "application/json"}
        body = {"mode": "openstack"}
        response: dict[str, str] = requests.delete(
            url=f"{self._BIBIGRID_EP}/bibigrid/terminate/{cluster_id}",
            json=body,
            headers=headers,
            verify=self._PRODUCTION,
        ).json()
        logger.info(response)
        return response

    def start_cluster(
        self,
        public_keys: list[str],
        master_instance: ClusterInstance,
        worker_instances: list[ClusterInstance],
        metadata: ClusterInstanceMetadata = None,
    ) -> ClusterMessage:
        logger.info(
            f"Start Cluster:\n\tmaster_instance: {master_instance}\n\tworker_instances:{worker_instances}\n"
        )
        # Prepare worker instances in the required format
        worker_config = []
        for wk in worker_instances:
            logger.info(wk)
            config = vars(
                wk
            ).copy()  # create a copy to avoid modifying the original object
            config["onDemand"] = False
            worker_config.append(config)
        # Create configuration matching the required YAML structure
        body = [
            {
                "infrastructure": "openstack",
                "cloud": "openstack",
                "sshTimeout": 30,
                "useMasterAsCompute": False,
                "useMasterWithPublicIP": self._BIBIGRID_USE_MASTER_WITH_PUBLIC_IP,
                "dontUploadCredentials": True,
                "noAllPartition": True,
                # todo use internal gateway if provided
                "gateway": {
                    "ip": self._GATEWAY_IP,
                    "portFunction": self._PORT_FUNCTION,
                },
                "masterInstance": {
                    "type": master_instance.type,
                    "image": master_instance.image,
                },
                "workerInstances": worker_config,
                "sshUser": "ubuntu",
                "subnet": self._SUB_NETWORK,
                "waitForServices": ["de.NBI_Bielefeld_environment.service"],
                "sshPublicKeys": public_keys,
                "securityGroups": [self._DEFAULT_SECURITY_GROUP_NAME],
                "meta": vars(metadata),
            }
        ]
        full_body = {"configurations": body}
        logger.info(full_body)
        response: dict[str, str] = requests.post(
            url=self._BIBIGRID_EP + "/bibigrid/create",
            json=full_body,
            verify=self._PRODUCTION,
        ).json()

        logger.info(response)
        return ClusterMessage(
            cluster_id=response["cluster_id"], message=response["message"]
        )
