import os
from urllib.parse import urljoin

import requests
import yaml

from simple_vm_client.util.logger import setup_custom_logger

logger = setup_custom_logger(__name__)


class MetadataConnector:
    def __init__(self, config_file: str):
        logger.info("Initializing Metadata Connector")
        self.load_config_yml(config_file)

    def load_config_yml(self, config_file: str) -> None:
        logger.info(f"Load config file openstack config - {config_file}")
        with open(config_file, "r") as ymlfile:
            cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
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
            self.METADATA_SERVER_HOST = cfg["metadata_server"]["host"]
            self.METADATA_SERVER_PORT = cfg["metadata_server"]["port"]
            self.METADATA_BASE_URL = (
                f"{self.METADATA_SERVER_HOST}:{self.METADATA_SERVER_PORT}/"
            )

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
                    "x_auth_token": self.METADATA_SERVER_TOKEN,
                },
                verify=False,
            )
            response.raise_for_status()
            logger.info(f"Metadata removed successfully for {ip}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to remove metadata for {ip}: {e}")

    def set_metadata(self, ip: str, metadata: dict):
        if not self.ACTIVATED:
            logger.info("Metadata Server not activated. Skipping.")
            return

        logger.info(f"Setting Metadata for {ip}")
        set_metadata_url = urljoin(self.METADATA_BASE_URL, f"metadata/{ip}")

        try:
            response = requests.post(
                set_metadata_url,
                json=metadata,
                timeout=(30, 30),
                headers={
                    "x_auth_token": self.METADATA_SERVER_TOKEN,
                },
                verify=False,
            )
            response.raise_for_status()
            logger.info(f"Metadata set successfully for {ip}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to set metadata for {ip}: {e}")

    def health_check(self):
        if not self.ACTIVATED:
            logger.info("Metadata Server not activated. Skipping.")
            return

        logger.info("Metadata Server checking health...")
        health_url = urljoin(self.METADATA_BASE_URL, "health")

        try:
            response = requests.get(
                health_url,
                timeout=(30, 30),
                verify=False,
            )
            response.raise_for_status()
            logger.info(f"Metadata Health Check --- {response.json()}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Health check failed: {e}")
