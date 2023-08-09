import requests
import yaml
from ttypes import ClusterInfo, ClusterInstance
from util.logger import setup_custom_logger

logger = setup_custom_logger(__name__)


class BibigridConnector:
    def __init__(self, config_file: str):
        logger.info("Initializing Bibigrid Connector")

        self._BIBIGRID_URL: str = ""
        self._BIBIGRID_MODES: str = ""
        self._BIBIGRID_HOST: str = ""
        self._BIBIGRID_PORT: str = ""
        self._BIBIGRID_ANSIBLE_ROLES = []
        self._BIBIGRID_LOCAL_DNS_LOOKUP = False
        self._BIBIGRID_USE_MASTER_WITH_PUBLIC_IP: bool = False
        self._PRODUCTION_bool = True
        self.load_config_yml(config_file=config_file)

    def load_config_yml(self, config_file: str) -> None:
        with open(config_file, "r") as ymlfile:
            cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

            bibigrid_cfg = cfg["bibigrid"]
            self._BIBIGRID_HOST = bibigrid_cfg["host"]
            self._BIBIGRID_PORT = bibigrid_cfg["port"]
            self._BIBIGRID_USE_HTTPS = bibigrid_cfg.get("https", False)
            self._BIBIGRID_MODES = bibigrid_cfg["modes"]
            self._BIBIGRID_USE_MASTER_WITH_PUBLIC_IP = bibigrid_cfg.get(
                "use_master_with_public_ip", False
            )
            self._BIBIGRID_LOCAL_DNS_LOOKUP = bibigrid_cfg.get("localDnsLookup", False)
            self._BIBIGRID_ANSIBLE_ROLES = bibigrid_cfg.get("ansibleGalaxyRoles", [])

            openstack_cfg = cfg["openstack"]
            self._NETWORK = openstack_cfg["network"]
            self._SUB_NETWORK = openstack_cfg["sub_network"]
            self._PRODUCTION = cfg["production"]

            protocol = "https" if self._BIBIGRID_USE_HTTPS else "http"
            self._BIBIGRID_URL = (
                f"{protocol}://{self._BIBIGRID_HOST}:{self._BIBIGRID_PORT}/bibigrid/"
            )
            self._BIBIGRID_EP = (
                f"{protocol}://{self._BIBIGRID_HOST}:{self._BIBIGRID_PORT}"
            )

            logger.info("Config loaded: Bibigrid")
            self.is_bibigrid_available()

    def get_cluster_status(self, cluster_id: str) -> dict[str, str]:
        logger.info(f"Get Cluster {cluster_id} status")
        headers = {"content-Type": "application/json"}
        body = {"mode": "openstack"}
        request_url = self._BIBIGRID_URL + "info/" + cluster_id
        response = requests.get(
            url=request_url,
            json=body,
            headers=headers,
            verify=self._PRODUCTION,
        )
        logger.info(f"Cluster {cluster_id} status: {str(response.content)} ")
        json_resp: dict[str, str] = response.json(strict=False)
        try:
            json_resp["log"] = str(json_resp["log"])
        except Exception:
            logger.info(f"No Logs for Cluster - {cluster_id}")
        try:
            json_resp["msg"] = str(json_resp["msg"])
        except Exception:
            logger.info(f"No msg for Cluster - {cluster_id}")

        return json_resp

    def get_cluster_info(self, cluster_id: str) -> ClusterInfo:
        logger.info(f"Get Cluster info from {cluster_id}")
        infos: list[dict[str, str]] = self.get_clusters_info()
        for info in infos:
            if info["cluster-id"] == cluster_id:
                cluster_info = ClusterInfo(
                    launch_date=info["launch_date"],
                    group_id=info["group-id"],
                    network_id=info["network-id"],
                    public_ip=info["public-ip"],
                    subnet_id=info["subnet-id"],
                    user=info["user"],
                    inst_counter=info["# inst"],
                    cluster_id=info["cluster-id"],
                    key_name=info["key name"],
                )
                logger.info(f"Cluster {cluster_id} info: {cluster_info} ")

                return cluster_info
        return None

    def get_clusters_info(self) -> list[dict[str, str]]:
        logger.info("Get clusters info")
        headers = {"content-Type": "application/json"}
        body = {"mode": "openstack"}
        request_url = self._BIBIGRID_URL + "list"
        response = requests.get(
            url=request_url,
            json=body,
            headers=headers,
            verify=self._PRODUCTION,
        )
        infos: list[dict[str, str]] = response.json()["info"]
        return infos

    def is_bibigrid_available(self) -> bool:
        logger.info("Checking if Bibigrid is available")

        if not self._BIBIGRID_EP:
            logger.info("Bibigrid Url is not set")
            return False

        try:
            response = requests.get(self._BIBIGRID_EP + "/server/health")
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx and 5xx)

            if response.status_code == 200:
                logger.info("Bibigrid Server is available")
                return True
            else:
                logger.error(f"Bibigrid returned status code {response.status_code}")
                return False

        except requests.RequestException as e:
            logger.exception("Error while checking Bibigrid availability")
            return False

    def terminate_cluster(self, cluster_id: str) -> dict[str, str]:
        logger.info(f"Terminate cluster: {cluster_id}")
        headers = {"content-Type": "application/json"}
        body = {"mode": "openstack"}
        response: dict[str, str] = requests.delete(
            url=f"{self._BIBIGRID_URL}terminate/{cluster_id}",
            json=body,
            headers=headers,
            verify=self._PRODUCTION,
        ).json()
        logger.info(response)
        return response

    def start_cluster(
        self,
        public_key: str,
        master_instance: ClusterInstance,
        worker_instances: list[ClusterInstance],
        user: str,
    ) -> dict[str, str]:
        logger.info(
            f"Start Cluster:\n\tmaster_instance: {master_instance}\n\tworker_instances:{worker_instances}\n\tuser:{user}"
        )
        wI = []
        for wk in worker_instances:
            logger.info(wk)
            wI.append(wk)
        headers = {"content-Type": "application/json"}
        body = {
            "mode": "openstack",
            "subnet": self._SUB_NETWORK,
            "sshPublicKeys": [public_key],
            "user": user,
            "sshUser": "ubuntu",
            "masterInstance": master_instance,
            "workerInstances": wI,
            "useMasterWithPublicIp": self._BIBIGRID_USE_MASTER_WITH_PUBLIC_IP,
            "ansibleGalaxyRoles": self._BIBIGRID_ANSIBLE_ROLES,
            "localDNSLookup": self._BIBIGRID_LOCAL_DNS_LOOKUP,
        }
        for mode in self._BIBIGRID_MODES:
            body.update({mode: True})
        request_url = self._BIBIGRID_URL + "create"
        response: dict[str, str] = requests.post(
            url=request_url,
            json=body,
            headers=headers,
            verify=self._PRODUCTION,
        ).json()
        logger.info(response)
        return response
