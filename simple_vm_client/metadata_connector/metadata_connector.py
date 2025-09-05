import json
import os
from urllib.parse import urljoin

import requests
import yaml

from simple_vm_client.ttypes import VirtualMachineServerMetadata
from simple_vm_client.util.logger import setup_custom_logger
from simple_vm_client.util.thrift_converter import thrift_to_dict

logger = setup_custom_logger(__name__)


class MetadataConnector:
    def __init__(self, config_file: str):
        logger.info("Initializing Metadata Connector")
        self.session = requests.Session()
        self.ACTIVATED = False
        self.METADATA_WRITE_TOKEN = None
        self.METADATA_BASE_URL = None
        self.load_config_yml(config_file)
        self.is_metadata_server_available()

    def load_config_yml(self, config_file: str) -> None:
        logger.info(f"Loading config file: {config_file}")
        with open(config_file, "r") as ymlfile:
            cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

            if "metadata_server" not in cfg:
                logger.warning("Metadata server configuration not found. Skipping.")
                return

            metadata_cfg = cfg["metadata_server"]
            if not metadata_cfg.get("activated", False):
                logger.info(
                    "Metadata server config available but deactivated. Skipping."
                )
                return

            self.METADATA_USE_HTTPS = metadata_cfg.get("use_https", False)
            self.METADATA_SERVER_HOST = metadata_cfg.get("host")
            self.METADATA_SERVER_PORT = metadata_cfg.get("port")

            if not self.METADATA_SERVER_HOST or not self.METADATA_SERVER_PORT:
                logger.error("Host or port missing in metadata server configuration!")
                return

            scheme = "https" if self.METADATA_USE_HTTPS else "http"
            self.METADATA_BASE_URL = (
                f"{scheme}://{self.METADATA_SERVER_HOST}:{self.METADATA_SERVER_PORT}/"
            )

            logger.info("Metadata configuration loaded")
            self.ACTIVATED = True

        self.load_env_config()

    def load_env_config(self):
        token = os.environ.get("METADATA_WRITE_TOKEN")
        if not token:
            logger.error("Environment variable METADATA_WRITE_TOKEN is missing!")
            self.ACTIVATED = False
            return

        self.METADATA_WRITE_TOKEN = token
        self.session.headers.update({"X-Auth-Token": self.METADATA_WRITE_TOKEN})
        logger.info("Metadata environment configuration loaded")

    def remove_metadata(self, ip: str) -> bool:
        if not self.ACTIVATED:
            logger.info("Metadata server not activated. Skipping.")
            return False

        logger.info(f"Removing metadata for {ip}")
        remove_metadata_url = urljoin(self.METADATA_BASE_URL, f"metadata/{ip}")

        try:
            response = self.session.delete(remove_metadata_url, timeout=(30, 30))
            response.raise_for_status()
            logger.info(f"Metadata removed successfully for {ip}")
            return True
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error while removing metadata for {ip}: {e}")
        except requests.exceptions.Timeout:
            logger.error(f"Timeout while removing metadata for {ip}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to remove metadata for {ip}: {e}")
        return False

    def _serialize_metadata(self, metadata: VirtualMachineServerMetadata) -> str:
        try:
            metadata_dict = thrift_to_dict(metadata)
            return json.dumps(metadata_dict)
        except Exception as e:
            logger.error(f"Failed to serialize metadata: {e}")
            raise

    def set_metadata(self, ip: str, metadata: VirtualMachineServerMetadata) -> bool:
        if not ip:
            logger.error("IP address not provided, cannot set metadata.")
            return False
        if not self.ACTIVATED:
            logger.info("Metadata server not activated. Skipping.")
            return False

        logger.info(f"Setting metadata for {ip}")
        set_metadata_url = urljoin(self.METADATA_BASE_URL, f"metadata/{ip}")

        try:
            serialized_data = self._serialize_metadata(metadata)
            response = self.session.post(
                set_metadata_url,
                data=serialized_data,
                timeout=(30, 30),
                headers={"Content-Type": "application/json"},
            )
            response.raise_for_status()
            logger.info(f"Metadata set successfully for {ip}")
            return True
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error while setting metadata for {ip}: {e}")
        except requests.exceptions.Timeout:
            logger.error(f"Timeout while setting metadata for {ip}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to set metadata for {ip}: {e}")
        return False

    def is_metadata_server_available(self) -> bool:
        logger.info("Checking metadata server health...")

        if not self.ACTIVATED:
            logger.info("Metadata server not activated. Skipping health check.")
            return False

        health_url = urljoin(self.METADATA_BASE_URL, "health")

        try:
            response = self.session.get(health_url, timeout=(30, 30))
            response.raise_for_status()
            logger.info(f"Metadata health check successful: {response.json()}")
            return True
        except requests.exceptions.Timeout:
            logger.error("Timeout during metadata server health check")
        except requests.exceptions.RequestException as e:
            logger.error(f"Health check failed: {e}")
        return False
