import tempfile

import requests
import yaml

from simple_vm_client.ttypes import (
    ClusterInfo,
    ClusterInstance,
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
        self._PRODUCTION_bool = True
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
        request_url = f"{self._BIBIGRID_EP}/bibigrid/log/"

        try:
            response = requests.get(
                url=request_url,
                params={"cluster_id": cluster_id},
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

    def get_cluster_state(self, cluster_id: str) -> ClusterInfo:
        logger.info(f"Get Cluster state from {cluster_id}")
        request_url = self._BIBIGRID_EP + f"/bibigrid/state/"
        headers = {"content-Type": "application/json"}
        response = requests.get(
            url=request_url,
            params={"cluster_id": cluster_id},
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
        request_url = self._BIBIGRID_EP + "/bibigrid/ready/"
        headers = {"content-Type": "application/json"}
        response = requests.get(
            url=request_url,
            params={"cluster_id": cluster_id},
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
        return True

    # logger.info("Checking if Bibigrid is available")

    # if not self._BIBIGRID_EP:
    #   logger.info("Bibigrid Url is not set")
    #  return False

    # try:
    #   response = requests.get(self._BIBIGRID_EP + "/server/health")
    #  response.raise_for_status()  # Raise an exception for HTTP errors (4xx and 5xx)

    # if response.status_code == 200:
    #    logger.info("Bibigrid Server is available")
    #   return True
    # else:
    #   logger.error(f"Bibigrid returned status code {response.status_code}")
    #  return False

    # except requests.RequestException:
    #   logger.exception("Error while checking Bibigrid availability")
    #  return False

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
    ) -> ClusterMessage:
        logger.info(
            f"Start Cluster:\n\tmaster_instance: {master_instance}\n\tworker_instances:{worker_instances}\n"
        )

        # Prepare worker instances in the required format
        worker_config = []
        for wk in worker_instances:
            logger.info(wk)
            worker_config.append(
                {
                    "type": wk.type,  # Ensure `ClusterInstance` has these attributes
                    "image": wk.image,  # and modify as needed to reflect actual structure
                    "count": wk.count,  # Example attributes
                    "onDemand": False,
                }
            )

        # Create configuration matching the required YAML structure
        body = [
            {
                "infrastructure": "openstack",
                "cloud": "openstack",
                "sshTimeout": 10,
                "useMasterAsCompute": False,
                "useMasterWithPublicIP": self._BIBIGRID_USE_MASTER_WITH_PUBLIC_IP,
                # "nfsShares": ["/vol/permanent"],
                "dontUploadCredentials": True,
                "gateway": {
                    "ip": "129.70.51.75",
                    "portFunction": "30000 + 256 * oct3 + oct4",  # Example formula
                },
                "masterInstance": {
                    "type": master_instance.type,  # Example attribute
                    "image": master_instance.image,  # Example attribute
                },
                "workerInstances": worker_config,
                "sshUser": "ubuntu",
                "subnet": self._SUB_NETWORK,
                "waitForServices": ["de.NBI_Bielefeld_environment.service"],
               # "sshPublicKeys": public_keys
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
