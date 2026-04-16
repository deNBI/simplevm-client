"""Flavor Resource Exporter Connector.

This connector fetches flavor resource data from an external endpoint
that returns JSON data about available flavors.
"""

import json
from typing import Optional

import requests

from simple_vm_client.ttypes import FlavorResource
from simple_vm_client.util.logger import setup_custom_logger

logger = setup_custom_logger(__name__)


class FlavorResourceExporterConnector:
    """Connector for fetching flavor resource data from an external exporter endpoint."""

    def __init__(self, config_file: str):
        """Initialize the connector with configuration.

        Args:
            config_file: Path to the YAML configuration file.
        """
        logger.info("Initializing Flavor Resource Exporter Connector")

        self.config: dict = {}
        self.endpoint_url: str = ""
        self.timeout: int = 30
        self.enabled: bool = False

        self.load_config(config_file=config_file)

    def load_config(self, config_file: str) -> None:
        """Load configuration from YAML file.

        Args:
            config_file: Path to the YAML configuration file.
        """
        logger.info("Loading config file: Flavor Resource Exporter")

        try:
            import yaml
        except ImportError:
            logger.error("PyYAML is required for configuration loading")
            return

        try:
            with open(config_file, "r") as ymlfile:
                cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

                resource_config = cfg.get("flavor_resource_exporter", {})
                self.enabled = resource_config.get("activated", False)

                if not self.enabled:
                    logger.info("Flavor Resource Exporter is deactivated")
                    return

                self.endpoint_url = resource_config.get("endpoint_url", "")
                self.timeout = resource_config.get("timeout", 30)

                if not self.endpoint_url:
                    logger.warning(
                        "Flavor Resource Exporter enabled but no endpoint_url configured"
                    )

                logger.info(
                    f"Flavor Resource Exporter configured with endpoint: {self.endpoint_url}"
                )

        except FileNotFoundError:
            logger.error(f"Config file not found: {config_file}")
        except Exception as e:
            logger.error(f"Error loading config: {e}")

    def fetch_flavor_resources(self) -> list[FlavorResource]:
        """Fetch flavor resources from the external endpoint.

        Returns:
            List of FlavorResource objects.
        """
        if not self.enabled:
            logger.info("Flavor Resource Exporter is disabled")
            return []

        if not self.endpoint_url:
            logger.error("No endpoint URL configured")
            return []

        logger.info(f"Fetching flavor resources from: {self.endpoint_url}")

        try:
            response = requests.get(
                self.endpoint_url,
                timeout=(self.timeout, self.timeout),
            )
            response.raise_for_status()

            data = response.json()
            logger.info(f"Received {len(data)} flavor resources")

            # Handle both single object and list responses
            if isinstance(data, dict):
                if "results" in data:
                    data = data["results"]
                else:
                    data = [data]

            flavor_resources = []
            for item in data:
                flavor_resource = self._parse_flavor_resource(item)
                if flavor_resource:
                    flavor_resources.append(flavor_resource)

            logger.info(f"Parsed {len(flavor_resources)} flavor resources")
            return flavor_resources

        except requests.Timeout as e:
            logger.error(f"Request to flavor resource endpoint timed out: {e}")
            return []
        except requests.RequestException as e:
            logger.error(f"Error fetching flavor resources: {e}")
            return []
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON response: {e}")
            return []
        except Exception as e:
            logger.exception(f"Unexpected error fetching flavor resources: {e}")
            return []

    def _parse_flavor_resource(self, data: dict) -> Optional[FlavorResource]:
        """Parse a single flavor resource from JSON data.

        Args:
            data: Dictionary containing flavor resource data.

        Returns:
            FlavorResource object or None if parsing fails.
        """
        try:
            # Required fields
            flavor_id = data.get("id", "")
            name = data.get("name", "")
            available = data.get("available", 0)
            total = data.get("total", 0)
            cores = data.get("cores", 0)
            mem = data.get("mem", 0)
            resource_type = data.get("type", "")

            # Optional fields
            gpu_type = data.get("gpu_type")
            gpu_count = data.get("gpu_count")
            root_disk = data.get("root_disk")
            ephemeral_disk = data.get("ephemeral_disk")

            return FlavorResource(
                id=str(flavor_id),
                name=str(name),
                available=int(available),
                total=int(total),
                cores=int(cores),
                mem=int(mem),
                type=str(resource_type),
                gpu_type=str(gpu_type) if gpu_type else None,
                gpu_count=int(gpu_count) if gpu_count is not None else None,
                root_disk=int(root_disk) if root_disk is not None else None,
                ephemeral_disk=(
                    int(ephemeral_disk) if ephemeral_disk is not None else None
                ),
            )

        except (TypeError, ValueError) as e:
            logger.error(f"Error parsing flavor resource: {e}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error parsing flavor resource: {e}")
            return None

    def is_available(self) -> bool:
        """Check if the flavor resource exporter is available.

        Returns:
            True if configured and enabled, False otherwise.
        """
        return self.enabled and bool(self.endpoint_url)
