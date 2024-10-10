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
        self.load_config_yml(config_file)
        self.is_metadata_server_available()

    def load_config_yml(self, config_file: str) -> None:
        logger.info(f"Load config file openstack config - {config_file}")
        with open(config_file, "r") as ymlfile:
            cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
            logger.info("Config file loaded")
            if "metadata_server" not in cfg:
                logger.info("Metadata Server configuration not found. Skipping.")
                self.ACTIVATED = False
                return
            if not cfg["metadata_server"].get("activated", False):
                logger.info(
                    "Metadata Server Config available but deactivated. Skipping.."
                )
                self.ACTIVATED = False
                return
            self.ACTIVATED = True
            self.METADATA_USE_HTTPS = cfg["metadata_server"].get("use_https", False)
            self.METADATA_SERVER_HOST = cfg["metadata_server"]["host"]
            self.METADATA_SERVER_PORT = cfg["metadata_server"]["port"]
            if self.METADATA_USE_HTTPS:
                self.METADATA_BASE_URL = (
                    f"https://{self.METADATA_SERVER_HOST}:{self.METADATA_SERVER_PORT}/"
                )
            else:
                self.METADATA_BASE_URL = (
                    f"http://{self.METADATA_SERVER_HOST}:{self.METADATA_SERVER_PORT}/"
                )
        logger.info("Metadata Config Loaded")
        self.load_env_config()

    def load_env_config(self):
        required_keys = [
            "METADATA_SERVER_TOKEN",
        ]
        missing_keys = [key for key in required_keys if key not in os.environ]
        if missing_keys:
            missing_keys_str = ", ".join(missing_keys)
            logger.error(
                f"MetadataServer missing keys {missing_keys_str} not provided in env!"
            )
        self.METADATA_SERVER_TOKEN = os.environ.get("METADATA_SERVER_TOKEN")
        logger.info("Metadata Environment loaded")

    def remove_metadata(self, ip: str):
        if not self.ACTIVATED:
            logger.info("Metadata Server not activated. Skipping.")
            return

        logger.info(f"Removing Metadata for: {ip}")
        remove_metadata_url = urljoin(self.METADATA_BASE_URL, f"metadata/{ip}")

        try:
            response = requests.delete(
                remove_metadata_url,
                timeout=(30, 30),
                headers={
                    "X-Auth-Token": self.METADATA_SERVER_TOKEN,
                }
            )
            response.raise_for_status()
            logger.info(f"Metadata removed successfully for {ip}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to remove metadata for {ip}: {e}")

    def _serialize_metadata(self, metadata: VirtualMachineServerMetadata) -> str:
        metadata_dict = thrift_to_dict(metadata)
        return json.dumps(metadata_dict)

    def set_metadata(self, ip: str, metadata: VirtualMachineServerMetadata):
        if not ip:
            return
        if not self.ACTIVATED:
            logger.info("Metadata Server not activated. Skipping.")
            return

        logger.info(f"Setting Metadata for {ip}")
        set_metadata_url = urljoin(self.METADATA_BASE_URL, f"metadata/{ip}")
        try:
            serialized_data = self._serialize_metadata(metadata=metadata)
            response = requests.post(
                set_metadata_url,
                data=serialized_data,
                timeout=(30, 30),
                headers={
                    "X-Auth-Token": self.METADATA_SERVER_TOKEN,
                    "Content-Type": "application/json",
                },
                verify=False,
            )
            response.raise_for_status()
            logger.info(f"Metadata set successfully for {ip}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to set metadata for {ip}: {e}")

    def is_metadata_server_available(self):
        logger.info("Metadata Server checking health...")

        if not self.ACTIVATED:
            logger.info("Metadata Server not activated. Skipping.")
            return False

        health_url = urljoin(self.METADATA_BASE_URL, "health")

        try:
            response = requests.get(
                health_url,
                timeout=(30, 30)
            )
            response.raise_for_status()
            logger.info(f"Metadata Health Check --- {response.json()}")
            return True
        except requests.exceptions.RequestException as e:
            logger.error(f"Health check failed: {e}")
            return False
