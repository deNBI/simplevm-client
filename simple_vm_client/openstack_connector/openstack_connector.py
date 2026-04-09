from __future__ import annotations

import math
import os
import socket
import sys
import threading
import urllib
import urllib.parse
from contextlib import closing
from typing import Union
from uuid import uuid4

import sympy
import yaml
from keystoneauth1 import session
from keystoneauth1.identity import v3
from keystoneauth1.identity.v3 import application_credential
from openstack import connection
from openstack.block_storage.v2.snapshot import Snapshot
from openstack.block_storage.v3.volume import Volume
from openstack.compute.v2.flavor import Flavor
from openstack.compute.v2.image import Image
from openstack.compute.v2.keypair import Keypair
from openstack.compute.v2.server import Server
from openstack.exceptions import (
    ConflictException,
    OpenStackCloudException,
    ResourceFailure,
    ResourceNotFound,
)
from openstack.network.v2.network import Network
from openstack.network.v2.security_group import SecurityGroup
from oslo_utils import encodeutils

from simple_vm_client.forc_connector.template.template import (
    ResearchEnvironmentMetadata,
)
from simple_vm_client.ttypes import (
    DefaultException,
    FlavorNotFoundException,
    ImageNotFoundException,
    OpenStackConflictException,
    ResourceNotAvailableException,
    SecurityGroupNotFoundException,
    ServerNotFoundException,
    SnapshotNotFoundException,
    VolumeNotFoundException,
)
from simple_vm_client.util.logger import setup_custom_logger
from simple_vm_client.util.state_enums import VmStates, VmTaskStates

logger = setup_custom_logger(__name__)

BIOCONDA = "bioconda"

ALL_TEMPLATES = [BIOCONDA]
SUPPORTED_OS_VERSIONS = ["22.04", "24.04"]
lock_dict = {}
lock_access = threading.Lock()


class OpenStackConnector:
    def __init__(self, config_file: str):
        # Config FIle Data
        logger.info(
            "Initializing OpenStack connector", extra={"config_file": config_file}
        )
        self.GATEWAY_IP: str = ""
        self.INTERNAL_GATEWAY_IP: str = ""
        self.NETWORK: str = ""
        self.PRODUCTION: bool = True
        self.CLOUD_SITE: str = ""
        self.SSH_MULTIPLICATION_PORT: int = 1
        self.UDP_MULTIPLICATION_PORT: int = 10
        self.DEFAULT_SECURITY_GROUP_NAME: str = ""
        self.DEFAULT_SECURITY_GROUPS: list[str] = []

        # Environment Data
        self.USERNAME: str = ""
        self.PASSWORD: str = ""
        self.PROJECT_NAME: str = ""
        self.PROJECT_ID: str = ""
        self.USER_DOMAIN_NAME: str = ""
        self.AUTH_URL: str = ""
        self.PROJECT_DOMAIN_ID: str = ""
        self.FORC_SECURITY_GROUP_ID: str = ""
        self.APPLICATION_CREDENTIAL_ID = ""
        self.APPLICATION_CREDENTIAL_SECRET = ""
        self.USE_APPLICATION_CREDENTIALS: bool = False
        self.NOVA_MICROVERSION = "2.1"
        self.THREADS = 32

        self.load_env_config()
        logger.info(f"Loading config file: {config_file}")
        self.load_config_yml(config_file)

        try:
            # Create an authentication session
            if self.USE_APPLICATION_CREDENTIALS:
                logger.info(
                    "Using Application Credentials for OpenStack Connection",
                    extra={"auth_url": self.AUTH_URL},
                )
                auth = application_credential.ApplicationCredential(
                    auth_url=self.AUTH_URL,
                    application_credential_id=self.APPLICATION_CREDENTIAL_ID,
                    application_credential_secret=self.APPLICATION_CREDENTIAL_SECRET,
                )
                sess = session.Session(auth=auth)
                sess.session.connections_pool = True
                sess.session.connection_pool_size = math.ceil(self.THREADS * 1.20)
                self.openstack_connection = connection.Connection(session=sess)
            else:
                logger.info(
                    "Using User Credentials for OpenStack Connection",
                    extra={"auth_url": self.AUTH_URL, "project": self.PROJECT_NAME},
                )
                auth = v3.Password(
                    auth_url=self.AUTH_URL,
                    username=self.USERNAME,
                    password=self.PASSWORD,
                    project_name=self.PROJECT_NAME,
                    user_domain_name=self.USER_DOMAIN_NAME,
                    project_domain_id=self.PROJECT_DOMAIN_ID,
                )
                sess = session.Session(auth=auth)
                sess.session.connections_pool = True
                sess.session.connection_pool_size = math.ceil(self.THREADS * 1.20)
                self.openstack_connection = connection.Connection(
                    session=sess,
                    compute_api_version=self.NOVA_MICROVERSION,
                )
            self.openstack_connection.authorize()
            self.get_network()
            logger.info(
                "Connected to OpenStack",
                extra={"cloud_site": self.CLOUD_SITE, "network": self.NETWORK},
            )
            self.create_or_get_default_ssh_security_group()
        except Exception as e:
            logger.error(
                "Client failed authentication at OpenStack",
                extra={"error": str(e), "cloud_site": self.CLOUD_SITE},
                exc_info=True,
            )
            raise ConnectionError(f"Client failed authentication at OpenStack: {e}")

        self.DEACTIVATE_UPGRADES_SCRIPT = self.create_deactivate_update_script()

    def load_config_yml(self, config_file: str) -> None:
        logger.info("Loading OpenStack config file", extra={"config_file": config_file})
        with open(config_file, "r") as ymlfile:
            cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

            self.GATEWAY_IP = cfg["openstack"]["gateway_ip"]
            self.INTERNAL_GATEWAY_IP = cfg["openstack"].get("internal_gateway_ip")
            self.NETWORK = cfg["openstack"]["network"]
            self.PRODUCTION = cfg["production"]
            self.CLOUD_SITE = cfg["openstack"]["cloud_site"]
            self.SSH_PORT_CALCULATION = cfg["openstack"]["ssh_port_calculation"]
            self.UDP_PORT_CALCULATION = cfg["openstack"]["udp_port_calculation"]
            self.FORC_SECURITY_GROUP_ID = cfg["openstack"].get(
                "forc_security_group_id", None
            )
            self.THREADS = cfg["server"].get("threads", 32)

            if not self.FORC_SECURITY_GROUP_ID:
                logger.warning(
                    "No FORC security group defined - some features may be limited"
                )

            self.DEFAULT_SECURITY_GROUP_NAME = "defaultSimpleVM"
            self.DEFAULT_SECURITY_GROUPS = [self.DEFAULT_SECURITY_GROUP_NAME]
            self.GATEWAY_SECURITY_GROUP_ID = cfg["openstack"][
                "gateway_security_group_id"
            ]

            if "compute_api_version" in cfg["openstack"]:
                self.NOVA_MICROVERSION = cfg["openstack"]["compute_api_version"]
                logger.debug(
                    "Using custom compute API version",
                    extra={"api_version": self.NOVA_MICROVERSION},
                )

            logger.debug(
                "OpenStack config loaded",
                extra={
                    "cloud_site": self.CLOUD_SITE,
                    "network": self.NETWORK,
                    "gateway_ip": self.GATEWAY_IP,
                    "production": self.PRODUCTION,
                    "threads": self.THREADS,
                },
            )

    def _get_default_security_groups(self):
        return self.DEFAULT_SECURITY_GROUPS.copy()

    def load_env_config(self) -> None:
        self.AUTH_URL = os.environ.get("OS_AUTH_URL")
        if not self.AUTH_URL:
            logger.error(
                "OS_AUTH_URL environment variable is required but not set",
                exc_info=True,
            )
            sys.exit(1)

        self.USE_APPLICATION_CREDENTIALS = (
            os.environ.get("USE_APPLICATION_CREDENTIALS", "False").lower() == "true"
        )

        logger.info(
            "Loading OpenStack environment configuration",
            extra={"use_application_credentials": self.USE_APPLICATION_CREDENTIALS},
        )

        if self.USE_APPLICATION_CREDENTIALS:
            try:
                self.APPLICATION_CREDENTIAL_ID = os.environ[
                    "OS_APPLICATION_CREDENTIAL_ID"
                ]
                self.APPLICATION_CREDENTIAL_SECRET = os.environ[
                    "OS_APPLICATION_CREDENTIAL_SECRET"
                ]
                logger.info(
                    "Using Application Credentials for authentication",
                    extra={"credential_id": self.APPLICATION_CREDENTIAL_ID[:8] + "..."},
                )
                logger.debug(
                    "Application credentials loaded successfully",
                    extra={"credential_id": self.APPLICATION_CREDENTIAL_ID[:8] + "..."},
                )
            except KeyError as e:
                logger.error(
                    f"Application credentials enabled but {e.args[0]} is missing",
                    exc_info=True,
                )
                sys.exit(1)
        else:
            required_keys = [
                "OS_USERNAME",
                "OS_PASSWORD",
                "OS_PROJECT_NAME",
                "OS_PROJECT_ID",
                "OS_USER_DOMAIN_NAME",
                "OS_PROJECT_DOMAIN_ID",
            ]
            missing_keys = [key for key in required_keys if key not in os.environ]
            if missing_keys:
                logger.error(
                    "Username/Password auth enabled but missing environment variables",
                    extra={"missing_keys": missing_keys},
                )
                sys.exit(1)
            else:
                self.USERNAME = os.environ["OS_USERNAME"]
                self.PASSWORD = os.environ["OS_PASSWORD"]
                self.PROJECT_NAME = os.environ["OS_PROJECT_NAME"]
                self.PROJECT_ID = os.environ["OS_PROJECT_ID"]
                self.USER_DOMAIN_NAME = os.environ["OS_USER_DOMAIN_NAME"]
                self.PROJECT_DOMAIN_ID = os.environ["OS_PROJECT_DOMAIN_ID"]
                logger.debug(
                    "User credentials loaded",
                    extra={"username": self.USERNAME, "project": self.PROJECT_NAME},
                )

    def create_server(
        self,
        name: str,
        image_id: str,
        flavor_id: str,
        network_id: str,
        userdata: str,
        key_name: str,
        metadata: dict[str, str],
        security_groups: list[str],
    ) -> Server:
        logger.info(
            "Creating new OpenStack server",
            extra={
                "server_name": name,
                "image_id": image_id,
                "flavor_id": flavor_id,
                "network_id": network_id,
                "security_groups": security_groups,
            },
        )
        server: Server = self.openstack_connection.create_server(
            name=name,
            image=image_id,
            flavor=flavor_id,
            network=[network_id],
            userdata=userdata,
            key_name=key_name,
            meta=metadata,
            security_groups=security_groups,
            boot_from_volume=False,
        )
        logger.info(
            "OpenStack server created successfully",
            extra={"server_id": server.id, "server_name": name},
        )
        return server

    def get_volume(self, name_or_id: str) -> Volume:
        logger.debug("Fetching volume by name_or_id", extra={"name_or_id": name_or_id})
        try:
            volume: Volume = self.openstack_connection.get_volume(name_or_id=name_or_id)
            if volume is None:
                logger.warning("Volume not found", extra={"name_or_id": name_or_id})
                raise VolumeNotFoundException(
                    message=f"Volume not found: {name_or_id}", name_or_id=name_or_id
                )
            logger.debug("Volume found", extra={"volume_id": volume.id})
            return volume
        except Exception as e:
            logger.error(
                "Error fetching volume",
                extra={"name_or_id": name_or_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def delete_volume(self, volume_id: str) -> None:
        logger.info("Deleting volume", extra={"volume_id": volume_id})
        try:
            self.openstack_connection.delete_volume(name_or_id=volume_id, wait=False)
            logger.info("Volume deleted successfully", extra={"volume_id": volume_id})
        except ResourceNotFound as e:
            logger.warning(
                "Volume not found for deletion",
                extra={"volume_id": volume_id, "error": str(e)},
            )
            raise VolumeNotFoundException(message=e.message, name_or_id=volume_id)
        except ConflictException as e:
            logger.error(
                "Failed to delete volume - conflict",
                extra={"volume_id": volume_id, "error": str(e)},
                exc_info=True,
            )
            raise OpenStackCloudException(message=e.message)
        except OpenStackCloudException as e:
            logger.error(
                "Failed to delete volume",
                extra={"volume_id": volume_id, "error": str(e)},
                exc_info=True,
            )
            raise DefaultException(message=str(e))

    def create_volume_snapshot(
        self, volume_id: str, name: str, description: str
    ) -> str:
        logger.info(
            "Creating volume snapshot",
            extra={
                "volume_id": volume_id,
                "name_or_id": name,
                "description": description,
            },
        )
        try:
            volume_snapshot = self.openstack_connection.create_volume_snapshot(
                volume_id=volume_id, name=name, description=description
            )
            logger.info(
                "Volume snapshot created successfully",
                extra={"snapshot_id": volume_snapshot["id"]},
            )
            return volume_snapshot["id"]
        except ResourceNotFound as e:
            logger.error(
                "Volume not found for snapshot creation",
                extra={"volume_id": volume_id, "error": str(e)},
                exc_info=True,
            )
            raise VolumeNotFoundException(message=e.message, name_or_id=volume_id)
        except OpenStackCloudException as e:
            logger.error(
                "Failed to create volume snapshot",
                extra={"volume_id": volume_id, "error": str(e)},
                exc_info=True,
            )
            raise DefaultException(message=e.message)

    def get_volume_snapshot(self, name_or_id: str) -> Snapshot:
        logger.debug("Fetching volume snapshot", extra={"name_or_id": name_or_id})
        try:
            snapshot: Snapshot = self.openstack_connection.get_volume_snapshot(
                name_or_id=name_or_id
            )
            if snapshot is None:
                logger.warning(
                    "Volume snapshot not found", extra={"name_or_id": name_or_id}
                )
                raise VolumeNotFoundException(
                    message=f"Volume snapshot not found: {name_or_id}",
                    name_or_id=name_or_id,
                )
            logger.debug("Volume snapshot found", extra={"snapshot_id": snapshot.id})
            return snapshot
        except Exception as e:
            logger.error(
                "Error fetching volume snapshot",
                extra={"name_or_id": name_or_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def delete_volume_snapshot(self, snapshot_id: str) -> None:
        logger.info("Deleting volume snapshot", extra={"snapshot_id": snapshot_id})
        try:
            self.openstack_connection.delete_volume_snapshot(name_or_id=snapshot_id)
            logger.info(
                "Volume snapshot deleted successfully",
                extra={"snapshot_id": snapshot_id},
            )
        except ResourceNotFound as e:
            logger.warning(
                "Snapshot not found for deletion",
                extra={"snapshot_id": snapshot_id, "error": str(e)},
            )
            raise SnapshotNotFoundException(message=e.message, name_or_id=snapshot_id)
        except ConflictException as e:
            logger.error(
                "Failed to delete volume snapshot - conflict",
                extra={"snapshot_id": snapshot_id, "error": str(e)},
                exc_info=True,
            )
            raise OpenStackCloudException(message=e.message)
        except OpenStackCloudException as e:
            logger.error(
                "Failed to delete volume snapshot",
                extra={"snapshot_id": snapshot_id, "error": str(e)},
                exc_info=True,
            )
            raise DefaultException(message=str(e))

    def create_volume_by_source_volume(
        self, volume_name: str, metadata: dict[str, str], source_volume_id: str
    ) -> Volume:
        logger.info(
            "Creating volume from source volume",
            extra={"volume_name": volume_name, "source_volume_id": source_volume_id},
        )
        try:
            volume: Volume = self.openstack_connection.block_storage.create_volume(
                name=volume_name, metadata=metadata, source_volume_id=source_volume_id
            )
            logger.info(
                "Volume created from source volume",
                extra={"volume_id": volume.id, "source_volume_id": source_volume_id},
            )
            return volume
        except ResourceFailure as e:
            logger.error(
                "Failed to create volume from source volume",
                extra={"source_volume_id": source_volume_id, "error": str(e)},
                exc_info=True,
            )
            raise ResourceNotAvailableException(message=e.message)

    def create_volume_by_volume_snap(
        self, volume_name: str, metadata: dict[str, str], volume_snap_id: str
    ) -> Volume:
        logger.info(
            "Creating volume from volume snapshot",
            extra={"volume_name": volume_name, "snapshot_id": volume_snap_id},
        )
        try:
            volume: Volume = self.openstack_connection.block_storage.create_volume(
                name=volume_name, metadata=metadata, snapshot_id=volume_snap_id
            )
            logger.info(
                "Volume created from snapshot",
                extra={"volume_id": volume.id, "snapshot_id": volume_snap_id},
            )
            return volume
        except ResourceFailure as e:
            logger.error(
                "Failed to create volume from snapshot",
                extra={"snapshot_id": volume_snap_id, "error": str(e)},
                exc_info=True,
            )
            raise ResourceNotAvailableException(message=e.message)

    def get_servers(self) -> list[Server]:
        logger.debug("Fetching all servers")
        try:
            servers: list[Server] = self.openstack_connection.list_servers()
            logger.debug(
                "Servers fetched successfully",
                extra={"count": len(servers), "server_ids": [s.id for s in servers]},
            )

            flavors = {}
            images = {}
            for server in servers:
                flavor = server.flavor
                if flavor and not flavor.get("name"):
                    if not flavors.get(flavor.id):
                        openstack_flavor = self.openstack_connection.get_flavor(
                            flavor.id
                        )
                        flavors[flavor.id] = openstack_flavor
                        server.flavor = openstack_flavor
                    else:
                        server.flavor = flavors.get(flavor.id)

                image = server.image
                if image and not image.get("name"):
                    if not images.get(image.id):
                        openstack_image = self.openstack_connection.get_image(image.id)
                        images[image.id] = openstack_image
                        server.image = openstack_image
                    else:
                        server.image = images.get(image.id)

            return servers
        except Exception as e:
            logger.error(
                "Error fetching servers", extra={"error": str(e)}, exc_info=True
            )
            raise

    def get_servers_by_ids(self, ids: list[str]) -> list[Server]:
        logger.debug("Fetching servers by IDs", extra={"ids": ids})
        servers: list[Server] = []
        for server_id in ids:
            logger.debug("Fetching server", extra={"server_id": server_id})
            try:
                server = self.openstack_connection.get_server_by_id(server_id)
                if server:
                    servers.append(server)
                    logger.debug("Server found", extra={"server_id": server_id})
                else:
                    logger.warning("Server not found", extra={"server_id": server_id})
            except Exception as e:
                logger.error(
                    "Error fetching server",
                    extra={"server_id": server_id, "error": str(e)},
                    exc_info=True,
                )

        flavors = {}
        images = {}
        for server in servers:
            flavor = server.flavor
            if flavor and not flavor.get("name"):
                if not flavors.get(flavor.id):
                    openstack_flavor = self.openstack_connection.get_flavor(flavor.id)
                    flavors[flavor.id] = openstack_flavor
                    server.flavor = openstack_flavor
                else:
                    server.flavor = flavors.get(flavor.id)

            image = server.image
            if image and not image.get("name"):
                if not image.get(image.id):
                    openstack_image = self.openstack_connection.get_image(image.id)
                    images[image.id] = openstack_image
                    server.image = openstack_image
                else:
                    server.image = images.get(image.id)

        logger.debug(
            "Servers by IDs fetch complete",
            extra={"count": len(servers), "found_ids": [s.id for s in servers]},
        )
        return servers

    def attach_volume_to_server(
        self, openstack_id: str, volume_id: str
    ) -> dict[str, str]:
        logger.info(
            "Attaching volume to server",
            extra={"server_id": openstack_id, "volume_id": volume_id},
        )
        try:
            server = self.get_server(openstack_id=openstack_id)
            volume = self.get_volume(name_or_id=volume_id)
            attachment = self.openstack_connection.attach_volume(
                server=server, volume=volume
            )
            logger.info(
                "Volume attached successfully",
                extra={
                    "server_id": openstack_id,
                    "volume_id": volume_id,
                    "device": attachment["device"],
                },
            )
            return {"device": attachment["device"]}
        except ConflictException as e:
            logger.error(
                "Failed to attach volume - conflict",
                extra={
                    "server_id": openstack_id,
                    "volume_id": volume_id,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise OpenStackConflictException(message=e.message)

    def detach_volume(self, volume_id: str, server_id: str) -> None:
        logger.info(
            "Detaching volume from server",
            extra={"server_id": server_id, "volume_id": volume_id},
        )
        try:
            volume = self.get_volume(name_or_id=volume_id)
            server = self.get_server(openstack_id=server_id)
            self.openstack_connection.detach_volume(volume=volume, server=server)
            logger.info(
                "Volume detached successfully",
                extra={"server_id": server_id, "volume_id": volume_id},
            )
        except ConflictException as e:
            logger.error(
                "Failed to detach volume - conflict",
                extra={"server_id": server_id, "volume_id": volume_id, "error": str(e)},
                exc_info=True,
            )
            raise OpenStackConflictException(message=e.message)

    def resize_volume(self, volume_id: str, size: int) -> None:
        logger.info("Resizing volume", extra={"volume_id": volume_id, "new_size": size})
        try:
            self.openstack_connection.block_storage.extend_volume(volume_id, size)
            logger.info(
                "Volume resized successfully",
                extra={"volume_id": volume_id, "new_size": size},
            )
        except ResourceNotFound as e:
            logger.error(
                "Volume not found for resize",
                extra={"volume_id": volume_id, "error": str(e)},
                exc_info=True,
            )
            raise VolumeNotFoundException(message=e.message, name_or_id=volume_id)
        except OpenStackCloudException as e:
            logger.error(
                "Failed to resize volume",
                extra={"volume_id": volume_id, "error": str(e)},
                exc_info=True,
            )
            raise DefaultException(message=str(e))

    def create_volume(
        self, volume_name: str, volume_storage: int, metadata: dict[str, str]
    ) -> Volume:
        logger.info(
            "Creating new volume",
            extra={
                "volume_name": volume_name,
                "size_gb": volume_storage,
                "metadata": metadata,
            },
        )
        try:
            volume: Volume = self.openstack_connection.block_storage.create_volume(
                name=volume_name, size=volume_storage, metadata=metadata
            )
            logger.info(
                "Volume created successfully",
                extra={
                    "volume_id": volume.id,
                    "volume_name": volume_name,
                    "size_gb": volume_storage,
                },
            )
            return volume
        except ResourceFailure as e:
            logger.error(
                "Failed to create volume",
                extra={
                    "volume_name": volume_name,
                    "size_gb": volume_storage,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise ResourceNotAvailableException(message=e.message)

    def get_network(self) -> Network:
        logger.debug("Fetching network", extra={"network_name": self.NETWORK})
        try:
            network: Network = self.openstack_connection.get_network(
                name_or_id=self.NETWORK
            )
            if network is None:
                logger.error("Network not found", extra={"network_name": self.NETWORK})
                raise Exception(f"Network {self.NETWORK} not found!")
            logger.debug("Network found", extra={"network_id": network.id})
            return network
        except Exception as e:
            logger.error(
                "Error fetching network",
                extra={"network_name": self.NETWORK, "error": str(e)},
                exc_info=True,
            )
            raise

    def import_keypair(self, keyname: str, public_key: str) -> dict[str, str]:
        logger.debug("Fetching keypair", extra={"keyname": keyname})
        keypair: dict[str, str] = self.openstack_connection.get_keypair(
            name_or_id=keyname
        )

        if not keypair:
            logger.info("Creating new keypair", extra={"keyname": keyname})
            new_keypair: dict[str, str] = self.openstack_connection.create_keypair(
                name=keyname, public_key=public_key
            )
            logger.info(
                "Keypair created successfully",
                extra={"keyname": keyname, "key_id": new_keypair["id"]},
            )
            return new_keypair

        elif keypair["public_key"] != public_key:
            logger.info("Keypair has changed - replacing", extra={"keyname": keyname})
            self.delete_keypair(key_name=keyname)
            old_keypair: dict[str, str] = self.openstack_connection.create_keypair(
                name=keyname, public_key=public_key
            )
            logger.info(
                "Keypair replaced successfully",
                extra={"keyname": keyname, "key_id": old_keypair["id"]},
            )
            return old_keypair
        else:
            logger.debug("Keypair exists and is up-to-date", extra={"keyname": keyname})
            return keypair

    def get_keypair_public_key_by_name(self, key_name: str):
        logger.debug("Fetching keypair public key", extra={"key_name": key_name})

        key_pair: Keypair = self.openstack_connection.get_keypair(name_or_id=key_name)
        if key_pair:
            return key_pair.public_key
        return ""

    def delete_keypair(self, key_name: str) -> None:
        logger.info("Deleting keypair", extra={"keyname": key_name})
        key_pair = self.openstack_connection.get_keypair(name_or_id=key_name)
        if key_pair:
            self.openstack_connection.delete_keypair(name=key_name)
            logger.info("Keypair deleted successfully", extra={"keyname": key_name})

    def create_add_keys_script(
        self, additional_owner_keys: list[str], addtional_user_keys: list[str]
    ) -> str:
        logger.debug(
            "Creating add keys script",
            extra={
                "owner_key_count": len(additional_owner_keys),
                "user_key_count": len(addtional_user_keys),
            },
        )
        file_dir = os.path.dirname(os.path.abspath(__file__))
        key_script = os.path.join(file_dir, "scripts/bash/add_keys_to_authorized.sh")
        if not additional_owner_keys:
            additional_owner_keys = []
        if not addtional_user_keys:
            addtional_user_keys = []

        bash_addtional_user_keys_array = "("
        for key in addtional_user_keys:
            bash_addtional_user_keys_array += f'"{key}" '
        bash_addtional_user_keys_array += ")"
        bash_addtional_owner_keys_array = "("
        for key in additional_owner_keys:
            bash_addtional_owner_keys_array += f'"{key}" '
        bash_addtional_owner_keys_array += ")"
        with open(key_script, "r") as file:
            text = file.read()
            text = text.replace(
                "ADDITIONAL_USER_KEYS_TO_ADD", bash_addtional_user_keys_array
            )
            text = text.replace("OWNER_KEYS_TO_ADD", bash_addtional_owner_keys_array)
            text = encodeutils.safe_encode(text.encode("utf-8"))
        key_script = text
        return key_script

    def create_save_metadata_auth_token_script(
        self, token: str, metadata_endpoint: str
    ) -> str:
        logger.debug(
            "Creating save metadata auth token script",
            extra={
                "metadata_endpoint": metadata_endpoint,
            },
        )
        file_dir = os.path.dirname(os.path.abspath(__file__))
        metadata_token_script_path = os.path.join(
            file_dir, "scripts/bash/save_metadata_auth_token.sh"
        )

        with open(metadata_token_script_path, "r") as file:
            text = file.read()

            # Use a unique placeholder in the script for replacement
            placeholder = "REPLACE_WITH_ACTUAL_TOKEN"
            endpoint_placeholder = "REPLACE_WITH_ACTUAL_METADATA_INFO_ENDPOINT"

            # Replace the placeholder with the actual token
            text = text.replace(placeholder, token)
            text = text.replace(endpoint_placeholder, metadata_endpoint)

            text = encodeutils.safe_encode(text.encode("utf-8"))

        return text

    def netcat(self, port: int) -> bool:
        host = self.INTERNAL_GATEWAY_IP if self.INTERNAL_GATEWAY_IP else self.GATEWAY_IP
        logger.debug("Checking SSH connectivity", extra={"host": host, "port": port})
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(5)
            r = sock.connect_ex((host, port))
            if r == 0:
                logger.debug(
                    "SSH connection successful", extra={"host": host, "port": port}
                )
            else:
                logger.debug(
                    "SSH connection failed",
                    extra={"host": host, "port": port, "error_code": r},
                )
        return r == 0

    def get_flavor(self, name_or_id: str, ignore_error: bool = False) -> Flavor:
        logger.debug("Fetching flavor", extra={"name_or_id": name_or_id})
        try:
            flavor: Flavor = self.openstack_connection.get_flavor(
                name_or_id=name_or_id, get_extra=True
            )

            if flavor is None:
                logger.warning("Flavor not found", extra={"name_or_id": name_or_id})

                if not ignore_error:
                    raise FlavorNotFoundException(
                        message=f"Flavor not found: {name_or_id}", name_or_id=name_or_id
                    )
                else:
                    return None

            logger.debug("Flavor found", extra={"flavor_id": flavor.id})
            return flavor
        except Exception as e:
            logger.error(
                "Error fetching flavor",
                extra={"name_or_id": name_or_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def get_flavors(self) -> list[Flavor]:
        logger.debug("Fetching all flavors")
        try:
            flavors: list[Flavor] = self.openstack_connection.list_flavors(
                get_extra=True
            )
            logger.debug(
                "Flavors fetched successfully",
                extra={
                    "count": len(flavors),
                    "flavor_names": [f.name for f in flavors],
                },
            )
            return flavors
        except Exception as e:
            logger.error(
                "Error fetching flavors", extra={"error": str(e)}, exc_info=True
            )
            raise

    def get_servers_by_bibigrid_id(self, bibigrid_id: str) -> list[Server]:
        logger.debug(
            "Fetching servers by Bibigrid ID", extra={"bibigrid_id": bibigrid_id}
        )
        filters = {"bibigrid_id": bibigrid_id, "name": bibigrid_id}
        try:
            servers: list[Server] = self.openstack_connection.list_servers(
                filters=filters
            )
            logger.debug(
                "Servers by Bibigrid ID fetched",
                extra={"bibigrid_id": bibigrid_id, "count": len(servers)},
            )

            flavors = {}
            images = {}
            for server in servers:
                flavor = server.flavor
                if not flavor.get("name"):
                    if not flavors.get(flavor.id):
                        openstack_flavor = self.openstack_connection.get_flavor(
                            flavor.id
                        )
                        flavors[flavor.id] = openstack_flavor
                        server.flavor = openstack_flavor
                    else:
                        server.flavor = flavors.get(flavor.id)

                image = server.image
                if not image.get("name"):
                    if not images.get(image.id):
                        openstack_image = self.openstack_connection.get_image(image.id)
                        images[image.id] = openstack_image
                        server.image = openstack_image
                    else:
                        server.image = images.get(image.id)

            return servers
        except Exception as e:
            logger.error(
                "Error fetching servers by Bibigrid ID",
                extra={"bibigrid_id": bibigrid_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def get_active_image_by_os_version(
        self, os_version: str, os_distro: Union[str, None]
    ) -> Image:
        logger.debug(
            "Fetching active image by OS version",
            extra={"os_version": os_version, "os_distro": os_distro},
        )
        try:
            images = self.openstack_connection.list_images()
            for image in images:
                image_os_version = image.get("os_version", None)
                image_os_distro = image.get("os_distro", None)
                image_properties = image.get("properties", None)
                base_image_ref = (
                    image_properties.get("base_image_ref", None)
                    if image_properties
                    else None
                )

                if (
                    os_version == image_os_version
                    and image.status == "active"
                    and base_image_ref is None
                ):
                    if os_distro and os_distro == image_os_distro:
                        logger.debug(
                            "Active image found",
                            extra={
                                "image_id": image.id,
                                "os_version": os_version,
                                "os_distro": os_distro,
                            },
                        )
                        return image
                    elif os_distro is None:
                        logger.debug(
                            "Active image found (no distro filter)",
                            extra={"image_id": image.id, "os_version": os_version},
                        )
                        return image

            logger.warning(
                "No active image found",
                extra={"os_version": os_version, "os_distro": os_distro},
            )
            raise ImageNotFoundException(
                message=f"No active image found for os_version={os_version}, os_distro={os_distro}",
                name_or_id="",
            )
        except Exception as e:
            logger.error(
                "Error fetching active image",
                extra={
                    "os_version": os_version,
                    "os_distro": os_distro,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise

    def get_active_image_by_os_version_and_slurm_version(
        self, os_version, os_distro, slurm_version
    ) -> Image:
        logger.debug(
            "Fetching active image by OS version and Slurm version",
            extra={
                "os_version": os_version,
                "os_distro": os_distro,
                "slurm_version": slurm_version,
            },
        )
        images = self.openstack_connection.list_images()
        backup_image = None

        for image in images:
            if image and image.status == "active":
                image_os_version = image.get("os_version", None)
                image_os_distro = image.get("os_distro", None)
                properties = image.get("properties", None)

                if os_version == image_os_version and "worker" in image.get("tags", []):
                    if os_distro and os_distro == image_os_distro:
                        backup_image = image
                        if (
                            properties
                            and properties.get("slurm_version") == slurm_version
                        ):
                            logger.debug(
                                "Active image with matching Slurm version found",
                                extra={
                                    "image_id": image.id,
                                    "slurm_version": slurm_version,
                                },
                            )
                            return image

        logger.debug(
            "No Slurm-specific image found, returning backup",
            extra={"backup_image_id": backup_image.id if backup_image else None},
        )
        return backup_image

    def get_image(
        self,
        name_or_id: str,
        replace_inactive: bool = False,
        ignore_not_active: bool = False,
        replace_not_found: bool = False,
        ignore_not_found: bool = False,
        slurm_version: str | None = None,
    ) -> Image:
        logger.debug(
            "Fetching image",
            extra={"name_or_id": name_or_id, "slurm_version": slurm_version},
        )

        try:
            image: Image | None = self.openstack_connection.get_image(
                name_or_id=name_or_id
            )

            # --- Image not found ---
            if image is None:
                logger.debug(
                    "Image not found directly, checking replacement options",
                    extra={"name_or_id": name_or_id},
                )
                if replace_not_found:
                    for version in SUPPORTED_OS_VERSIONS:
                        if version in name_or_id:
                            if slurm_version:
                                image = self.get_active_image_by_os_version_and_slurm_version(
                                    os_version=version,
                                    os_distro="ubuntu",
                                    slurm_version=slurm_version,
                                )
                                logger.debug(
                                    "Found replacement image with Slurm version",
                                    extra={"image_id": image.id if image else None},
                                )
                                return image
                            image = self.get_active_image_by_os_version(
                                os_version=version, os_distro="ubuntu"
                            )
                            logger.debug(
                                "Found replacement image",
                                extra={"image_id": image.id if image else None},
                            )
                            return image

                if ignore_not_found:
                    return None

                logger.error("Image not found", extra={"name_or_id": name_or_id})
                raise ImageNotFoundException(
                    message=f"Image not found: {name_or_id}",
                    name_or_id=name_or_id,
                )

            # --- Image found but inactive ---
            if image.status != "active":
                logger.warning(
                    "Image found but not active",
                    extra={"image_id": image.id, "status": image.status},
                )
                if replace_inactive:
                    os_version = image["os_version"]
                    os_distro = image["os_distro"]

                    if slurm_version:
                        image = self.get_active_image_by_os_version_and_slurm_version(
                            os_version=os_version,
                            os_distro=os_distro,
                            slurm_version=slurm_version,
                        )
                    else:
                        image = self.get_active_image_by_os_version(
                            os_version=os_version, os_distro=os_distro
                        )

                    if image:
                        logger.debug(
                            "Found replacement for inactive image",
                            extra={"image_id": image.id},
                        )
                        return image

                if not ignore_not_active:
                    logger.error(
                        "Image is not active",
                        extra={"image_id": image.id, "status": image.status},
                    )
                    raise ImageNotFoundException(
                        message=f"Image {name_or_id} is not active (status: {image.status})",
                        name_or_id=name_or_id,
                    )

            logger.debug(
                "Image retrieved successfully",
                extra={"image_id": image.id, "status": image.status},
            )
            return image
        except Exception as e:
            logger.error(
                "Error fetching image",
                extra={"name_or_id": name_or_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def create_snapshot(
        self,
        openstack_id: str,
        name: str,
        username: str,
        base_tags: list[str],
        description: str,
    ) -> str:
        logger.info(
            "Creating snapshot from server instance",
            extra={
                "server_id": openstack_id,
                "snapshot_name": name,
                "username": username,
                "description": description,
                "tags": base_tags,
            },
        )

        try:
            snapshot_munch = self.openstack_connection.create_image_snapshot(
                server=openstack_id, name=name, description=description
            )
            for tag in base_tags:
                self.openstack_connection.image.add_tag(
                    image=snapshot_munch["id"], tag=tag
                )
            snapshot_id: str = snapshot_munch["id"]
            logger.info(
                "Snapshot created successfully",
                extra={
                    "snapshot_id": snapshot_id,
                    "server_id": openstack_id,
                    "snapshot_name": name,
                },
            )
            return snapshot_id

        except ConflictException as e:
            logger.error(
                "Failed to create snapshot - conflict",
                extra={
                    "server_id": openstack_id,
                    "snapshot_name": name,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise OpenStackConflictException(message=e.message)
        except OpenStackCloudException as e:
            logger.error(
                "Failed to create snapshot",
                extra={
                    "server_id": openstack_id,
                    "snapshot_name": name,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise DefaultException(message=e.message)

    def delete_image(self, image_id: str) -> None:
        logger.info("Deleting image", extra={"image_id": image_id})
        try:
            image = self.openstack_connection.get_image(image_id)
            if image is None:
                logger.warning(
                    "Image not found for deletion", extra={"image_id": image_id}
                )
                raise ImageNotFoundException(
                    message=f"Image not found: {image_id}", name_or_id=image_id
                )
            self.openstack_connection.compute.delete_image(image_id)
            logger.info("Image deleted successfully", extra={"image_id": image_id})
        except Exception as e:
            logger.error(
                "Failed to delete image",
                extra={"image_id": image_id, "error": str(e)},
                exc_info=True,
            )
            raise DefaultException(message=str(e))

    def get_public_images(self) -> list[Image]:
        logger.debug("Fetching public images")
        try:
            # Use compute.images() method with filters and extra_info
            images = self.openstack_connection.image.images(
                status="active", visibility="public"
            )
            # Use list comprehension to filter images based on tags
            images = [
                image for image in images if "tags" in image and len(image["tags"]) > 0
            ]
            image_names = [image.name for image in images]
            logger.debug(
                "Public images fetched successfully",
                extra={"count": len(images), "image_names": image_names},
            )
            return images
        except Exception as e:
            logger.error(
                "Error fetching public images", extra={"error": str(e)}, exc_info=True
            )
            raise

    def get_private_images(self) -> list[Image]:
        logger.debug("Fetching private images")
        try:
            images = self.openstack_connection.image.images(
                status="active", visibility="private"
            )
            images = [
                image for image in images if "tags" in image and len(image["tags"]) > 0
            ]
            image_names = [image.name for image in images]
            logger.debug(
                "Private images fetched successfully",
                extra={"count": len(images), "image_names": image_names},
            )
            return images
        except Exception as e:
            logger.error(
                "Error fetching private images", extra={"error": str(e)}, exc_info=True
            )
            raise

    def get_images(self) -> list[Image]:
        logger.debug("Fetching all images")
        try:
            images = self.openstack_connection.image.images(status="active")
            images = [
                image for image in images if "tags" in image and len(image["tags"]) > 0
            ]
            image_names = [image.name for image in images]
            logger.debug(
                "Images fetched successfully",
                extra={"count": len(images), "image_names": image_names},
            )
            return images
        except Exception as e:
            logger.error(
                "Error fetching images", extra={"error": str(e)}, exc_info=True
            )
            raise

    def get_calculation_values(self) -> dict[str, str]:
        logger.debug("Fetching calculation values")
        return {
            "SSH_PORT_CALCULATION": self.SSH_PORT_CALCULATION,
            "UDP_PORT_CALCULATION": self.UDP_PORT_CALCULATION,
        }

    def get_gateway_ip(self) -> dict[str, str]:
        logger.debug(
            "Fetching gateway IP",
            extra={
                "gateway_ip": self.GATEWAY_IP,
                "internal_gateway_ip": self.INTERNAL_GATEWAY_IP,
            },
        )
        return {
            "gateway_ip": self.GATEWAY_IP,
            "internal_gateway_ip": (
                self.INTERNAL_GATEWAY_IP
                if self.INTERNAL_GATEWAY_IP
                else self.GATEWAY_IP
            ),
        }

    def create_mount_init_script(
        self,
        new_volumes: list[dict[str, str]] = None,  # type: ignore
        attach_volumes: list[dict[str, str]] = None,  # type: ignore
    ) -> str:
        logger.debug(
            "Creating mount init script",
            extra={"new_volumes": new_volumes, "attach_volumes": attach_volumes},
        )
        if not new_volumes and not attach_volumes:
            logger.debug("No volumes to mount, returning empty script")
            return ""

        file_dir: str = os.path.dirname(os.path.abspath(__file__))
        mount_script: str = os.path.join(file_dir, "scripts/bash/mount.sh")

        if new_volumes:
            volume_ids_new = [vol["openstack_id"] for vol in new_volumes]
            paths_new = [vol["path"] for vol in new_volumes]
        else:
            volume_ids_new = []
            paths_new = []

        if attach_volumes:
            volume_ids_attach = [vol["openstack_id"] for vol in attach_volumes]
            paths_attach = [vol["path"] for vol in attach_volumes]
        else:
            volume_ids_attach = []
            paths_attach = []

        bash_volume_path_new_array_string = "("
        for path in paths_new:
            bash_volume_path_new_array_string += path + " "
        bash_volume_path_new_array_string += ")"

        bash_volume_path_attach_array_string = "("
        for path in paths_attach:
            bash_volume_path_attach_array_string += path + " "
        bash_volume_path_attach_array_string += ")"

        bash_volume_id_new_array_string = "("
        for volume_id in volume_ids_new:
            bash_volume_id_new_array_string += "virtio-" + volume_id[0:20] + " "
        bash_volume_id_new_array_string += ")"

        bash_volume_id_attach_array_string = "("
        for volume_id in volume_ids_attach:
            bash_volume_id_attach_array_string += "virtio-" + volume_id[0:20] + " "
        bash_volume_id_attach_array_string += ")"

        with open(mount_script, "r") as file:
            text = file.read()
            text = text.replace("VOLUME_IDS_NEW", bash_volume_id_new_array_string)
            text = text.replace("VOLUME_PATHS_NEW", bash_volume_path_new_array_string)
            text = text.replace("VOLUME_IDS_ATTACH", bash_volume_id_attach_array_string)
            text = text.replace(
                "VOLUME_PATHS_ATTACH", bash_volume_path_attach_array_string
            )
            text = encodeutils.safe_encode(text.encode("utf-8"))
        logger.debug(
            "Mount init script created successfully",
            extra={
                "new_volume_count": len(new_volumes) if new_volumes else 0,
                "attach_volume_count": len(attach_volumes) if attach_volumes else 0,
            },
        )
        return text

    def create_or_get_default_ssh_security_group(self):
        logger.debug(
            "Checking for default SimpleVM SSH Security Group",
            extra={"security_group": self.DEFAULT_SECURITY_GROUP_NAME},
        )
        sec = self.openstack_connection.get_security_group(
            name_or_id=self.DEFAULT_SECURITY_GROUP_NAME
        )
        if not sec:
            logger.info(
                "Default SimpleVM SSH Security group not found - creating",
                extra={"security_group": self.DEFAULT_SECURITY_GROUP_NAME},
            )

            sec = self.create_security_group(
                name=self.DEFAULT_SECURITY_GROUP_NAME,
                ssh=True,
                description="Default SSH SimpleVM Security Group",
            )
        logger.debug(
            "Default SSH security group ready",
            extra={"security_group_id": sec.id if sec else None},
        )
        return sec

    def add_default_security_groups_to_server(self, openstack_id):
        logger.info(
            "Adding default security group to server", extra={"server_id": openstack_id}
        )
        server = self.get_server(openstack_id=openstack_id)
        sec_group = self._get_default_security_groups()
        self.openstack_connection.add_server_security_groups(
            server=server, security_groups=sec_group
        )
        logger.debug("Default security group added", extra={"server_id": openstack_id})

    def delete_security_group_rule(self, openstack_id):
        logger.info("Deleting security group rule", extra={"rule_id": openstack_id})
        try:
            deleted = self.openstack_connection.delete_security_group_rule(
                rule_id=openstack_id
            )
            if deleted:
                logger.info(
                    "Security group rule deleted successfully",
                    extra={"rule_id": openstack_id},
                )
            else:
                logger.warning(
                    "Security group rule deletion returned False",
                    extra={"rule_id": openstack_id},
                )
                raise DefaultException(
                    message=f"Could not delete security group rule - {openstack_id}"
                )
        except Exception as e:
            logger.error(
                "Error deleting security group rule",
                extra={"rule_id": openstack_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def open_port_range_for_vm_in_project(
        self, range_start, range_stop, openstack_id, ethertype="IPv4", protocol="TCP"
    ):
        logger.info(
            "Opening port range for VM in project",
            extra={
                "server_id": openstack_id,
                "range_start": range_start,
                "range_stop": range_stop,
                "ethertype": ethertype,
                "protocol": protocol,
            },
        )
        server: Server = self.get_server(openstack_id=openstack_id)

        project_name = server.metadata.get("project_name")
        project_id = server.metadata.get("project_id")

        project_security_group = self.get_or_create_project_security_group(
            project_name=project_name, project_id=project_id
        )
        vm_security_group = self.get_or_create_vm_security_group(
            openstack_id=openstack_id
        )
        current_vm_security_group_names = [
            sec["name"] for sec in server["security_groups"]
        ]
        if openstack_id not in current_vm_security_group_names:
            self.openstack_connection.add_server_security_groups(
                server=server, security_groups=[vm_security_group]
            )
        if ethertype not in ["IPv4", "IPv6"]:
            logger.error("Invalid ethertype", extra={"ethertype": ethertype})
            raise DefaultException(
                message=f"Type {ethertype} does not exist for security group rules"
            )

        try:
            security_rule = self.openstack_connection.create_security_group_rule(
                direction="ingress",
                ethertype=ethertype,
                protocol=protocol,
                port_range_max=range_stop,
                port_range_min=range_start,
                secgroup_name_or_id=vm_security_group,
                remote_group_id=project_security_group,
            )
            logger.info(
                "Port range opened successfully",
                extra={"server_id": openstack_id, "rule_id": security_rule["id"]},
            )
            return security_rule["id"]

        except ConflictException as e:
            logger.error(
                "Failed to create security group rule - conflict",
                extra={"server_id": openstack_id, "error": str(e)},
                exc_info=True,
            )
            raise OpenStackConflictException(message=e.message)

    def create_security_group(
        self,
        name: str,
        udp_port: int = None,  # type: ignore
        ssh: bool = True,
        udp: bool = False,
        description: str = "",
        research_environment_metadata: ResearchEnvironmentMetadata = None,
    ) -> SecurityGroup:
        logger.info(
            "Creating new security group",
            extra={"name_or_id": name, "description": description},
        )
        sec: SecurityGroup = self.openstack_connection.get_security_group(
            name_or_id=name
        )
        if sec:
            logger.debug(
                "Security group already exists",
                extra={"name_or_id": name, "security_group_id": sec.id},
            )
            return sec
        new_security_group: SecurityGroup = (
            self.openstack_connection.create_security_group(
                name=name, description=description
            )
        )

        if udp:
            logger.debug(
                "Adding UDP rule to security group",
                extra={"name_or_id": name, "port": udp_port},
            )

            self.openstack_connection.create_security_group_rule(
                direction="ingress",
                protocol="udp",
                port_range_max=udp_port,
                port_range_min=udp_port,
                secgroup_name_or_id=new_security_group["id"],
                remote_group_id=self.GATEWAY_SECURITY_GROUP_ID,
            )
            self.openstack_connection.create_security_group_rule(
                direction="ingress",
                ethertype="IPv6",
                protocol="udp",
                port_range_max=udp_port,
                port_range_min=udp_port,
                secgroup_name_or_id=new_security_group["id"],
                remote_group_id=self.GATEWAY_SECURITY_GROUP_ID,
            )
        if ssh:
            logger.debug(
                "Adding SSH rule to security group", extra={"name_or_id": name}
            )

            self.openstack_connection.create_security_group_rule(
                direction="ingress",
                protocol="tcp",
                port_range_max=22,
                port_range_min=22,
                secgroup_name_or_id=new_security_group["id"],
                remote_group_id=self.GATEWAY_SECURITY_GROUP_ID,
            )
            self.openstack_connection.create_security_group_rule(
                direction="ingress",
                ethertype="IPv6",
                protocol="tcp",
                port_range_max=22,
                port_range_min=22,
                secgroup_name_or_id=new_security_group["id"],
                remote_group_id=self.GATEWAY_SECURITY_GROUP_ID,
            )
        if research_environment_metadata:
            logger.debug(
                "Adding research environment rule to security group",
                extra={
                    "name_or_id": name,
                    "direction": research_environment_metadata.direction,
                },
            )

            self.openstack_connection.network.create_security_group_rule(
                direction=research_environment_metadata.direction,
                protocol=research_environment_metadata.protocol,
                port_range_max=research_environment_metadata.port,
                port_range_min=research_environment_metadata.port,
                security_group_id=new_security_group["id"],
                remote_group_id=self.FORC_SECURITY_GROUP_ID,
            )

        logger.info(
            "Security group created successfully",
            extra={"name_or_id": name, "security_group_id": new_security_group["id"]},
        )
        return new_security_group

    def is_security_group_in_use(self, security_group_id):
        logger.debug(
            "Checking if security group is in use",
            extra={"security_group_id": security_group_id},
        )

        """
        Checks if a security group is still in use.

        :param conn: An instance of `openstack.connection.Connection`.
        :param security_group_id: The ID of the security group to check.
        :returns: True if the security group is still in use, False otherwise.
        """
        # First, get a list of all instances using the security group
        instances = self.openstack_connection.compute.servers(
            details=True,
            search_opts={"all_tenants": True, "security_group": security_group_id},
        )

        # If any instances are using the security group, return True
        if instances:
            logger.debug(
                "Security group is in use by instances",
                extra={
                    "security_group_id": security_group_id,
                    "instance_count": len(list(instances)),
                },
            )
            return True

        # Otherwise, check if the security group is still associated with any ports
        ports = self.openstack_connection.network.ports(
            security_group_id=security_group_id
        )
        if ports:
            logger.debug(
                "Security group is in use by ports",
                extra={
                    "security_group_id": security_group_id,
                    "port_count": len(list(ports)),
                },
            )
            return True

        # Finally, check if the security group is still associated with any load balancers
        load_balancers = self.openstack_connection.network.load_balancers(
            security_group_id=security_group_id
        )
        if load_balancers:
            logger.debug(
                "Security group is in use by load balancers",
                extra={
                    "security_group_id": security_group_id,
                    "lb_count": len(list(load_balancers)),
                },
            )
            return True

        logger.debug(
            "Security group is not in use",
            extra={"security_group_id": security_group_id},
        )
        # If none of the above are true, the security group is no longer in use
        return False

    def get_research_environment_security_group(self, security_group_name: str):
        logger.debug(
            "Fetching research environment security group",
            extra={"security_group_name": security_group_name},
        )
        security_group = self.openstack_connection.get_security_group(
            name_or_id=security_group_name
        )
        if not security_group:
            logger.warning(
                "Research environment security group not found",
                extra={"security_group_name": security_group_name},
            )
            raise DefaultException(
                message=f"Security Group {security_group_name} not found"
            )
        logger.debug(
            "Research environment security group found",
            extra={
                "security_group_name": security_group_name,
                "security_group_id": security_group.id,
            },
        )
        return security_group

    def get_or_create_research_environment_security_group(
        self, resenv_metadata: ResearchEnvironmentMetadata
    ):
        if not resenv_metadata.needs_forc_support:
            return None
        logger.debug(
            "Checking for research environment security group",
            extra={"security_group_name": resenv_metadata.securitygroup_name},
        )
        sec = self.openstack_connection.get_security_group(
            name_or_id=resenv_metadata.securitygroup_name
        )
        if sec:
            logger.debug(
                "Research environment security group already exists",
                extra={
                    "security_group_name": resenv_metadata.securitygroup_name,
                    "security_group_id": sec.id,
                },
            )
            return sec["id"]

        logger.info(
            "Creating research environment security group",
            extra={"security_group_name": resenv_metadata.securitygroup_name},
        )

        new_security_group = self.openstack_connection.create_security_group(
            name=resenv_metadata.securitygroup_name,
            description=resenv_metadata.description,
        )
        self.openstack_connection.network.create_security_group_rule(
            direction=resenv_metadata.direction,
            protocol=resenv_metadata.protocol,
            port_range_max=resenv_metadata.port,
            port_range_min=resenv_metadata.port,
            security_group_id=new_security_group["id"],
            remote_group_id=self.FORC_SECURITY_GROUP_ID,
        )
        logger.info(
            "Research environment security group created",
            extra={
                "security_group_name": resenv_metadata.securitygroup_name,
                "security_group_id": new_security_group["id"],
            },
        )
        return new_security_group["id"]

    def get_security_group_id_by_name(self, security_group_name):
        logger.debug(
            "Fetching security group ID by name",
            extra={"security_group_name": security_group_name},
        )
        sec = self.openstack_connection.get_security_group(
            name_or_id=security_group_name
        )
        if not sec:
            logger.error(
                "Security group not found",
                extra={"security_group_name": security_group_name},
            )
            raise SecurityGroupNotFoundException(
                message=f"SecurityGroup with name {security_group_name} not found!"
            )
        logger.debug(
            "Security group ID retrieved",
            extra={
                "security_group_name": security_group_name,
                "security_group_id": sec.id,
            },
        )
        return sec["id"]

    def get_or_create_vm_security_group(self, openstack_id):
        logger.debug(
            "Checking for VM security group", extra={"server_id": openstack_id}
        )
        sec = self.openstack_connection.get_security_group(name_or_id=openstack_id)
        if sec:
            logger.debug(
                "VM security group already exists",
                extra={"server_id": openstack_id, "security_group_id": sec.id},
            )
            return sec["id"]
        logger.info("Creating VM security group", extra={"server_id": openstack_id})
        new_security_group = self.openstack_connection.create_security_group(
            name=openstack_id, description=f"VM ID: {openstack_id} Security Group"
        )
        logger.info(
            "VM security group created",
            extra={
                "server_id": openstack_id,
                "security_group_id": new_security_group["id"],
            },
        )
        return new_security_group["id"]

    def get_or_create_project_security_group(self, project_name, project_id):
        security_group_name = f"{project_name}_{project_id}"

        with lock_access:
            if security_group_name not in lock_dict:
                lock_dict[security_group_name] = threading.Lock()
            lock = lock_dict[security_group_name]

        with lock:
            logger.debug(
                "Checking for project security group",
                extra={"project_name": project_name, "project_id": project_id},
            )
            sec = self.openstack_connection.get_security_group(
                name_or_id=security_group_name
            )
            if sec:
                logger.debug(
                    "Project security group already exists",
                    extra={
                        "project_name": project_name,
                        "project_id": project_id,
                        "security_group_id": sec.id,
                    },
                )
                return sec["id"]

            logger.info(
                "Creating project security group",
                extra={"project_name": project_name, "project_id": project_id},
            )
            new_security_group = self.openstack_connection.create_security_group(
                name=security_group_name, description=f"{project_name} Security Group"
            )
            self.openstack_connection.network.create_security_group_rule(
                direction="ingress",
                protocol="tcp",
                port_range_max=22,
                port_range_min=22,
                security_group_id=new_security_group["id"],
                remote_group_id=new_security_group["id"],
            )
            logger.info(
                "Project security group created",
                extra={
                    "project_name": project_name,
                    "project_id": project_id,
                    "security_group_id": new_security_group["id"],
                },
            )
            return new_security_group["id"]

    def get_limits(self) -> dict[str, str]:
        logger.debug("Fetching OpenStack limits")
        try:
            # Retrieve compute and volume limits
            compute_limits = self.openstack_connection.get_compute_limits()
            volume_limits = self.openstack_connection.get_volume_limits()["absolute"]

            # Merge compute and volume limits into a single dictionary
            limits = {**compute_limits, **volume_limits}
            result = {
                "cores_limit": str(limits["max_total_cores"]),
                "vms_limit": str(limits["max_total_instances"]),
                "ram_limit": str(math.ceil(limits["max_total_ram_size"] / 1024)),
                "current_used_cores": str(limits["total_cores_used"]),
                "current_used_vms": str(limits["total_instances_used"]),
                "current_used_ram": str(math.ceil(limits["total_ram_used"] / 1024)),
                "volume_counter_limit": str(limits["max_total_volumes"]),
                "volume_storage_limit": str(limits["max_total_volume_gigabytes"]),
                "current_used_volumes": str(limits["total_volumes_used"]),
                "current_used_volume_storage": str(limits["total_gigabytes_used"]),
            }
            logger.debug(
                "Limits fetched successfully",
                extra={
                    "vm_limit": result["vms_limit"],
                    "vm_used": result["current_used_vms"],
                    "cores_limit": result["cores_limit"],
                    "cores_used": result["current_used_cores"],
                },
            )
            return result
        except Exception as e:
            logger.error(
                "Error fetching OpenStack limits",
                extra={"error": str(e)},
                exc_info=True,
            )
            raise

    def exist_server(self, name: str) -> bool:
        logger.debug("Checking if server exists", extra={"server_name": name})
        try:
            result = self.openstack_connection.compute.find_server(name) is not None
            if result:
                logger.debug("Server exists", extra={"server_name": name})
            else:
                logger.debug("Server not found", extra={"server_name": name})
            return result
        except Exception as e:
            logger.error(
                "Error checking server existence",
                extra={"server_name": name, "error": str(e)},
                exc_info=True,
            )
            return False

    def set_server_metadata(self, openstack_id: str, metadata) -> None:
        logger.info(
            "Setting server metadata",
            extra={"server_id": openstack_id, "metadata": metadata},
        )
        try:
            server: Server = self.get_server(openstack_id)
            self.openstack_connection.compute.set_server_metadata(server, metadata)
            logger.info(
                "Server metadata updated successfully",
                extra={"server_id": openstack_id},
            )
        except OpenStackCloudException as e:
            logger.error(
                "Failed to set server metadata",
                extra={"server_id": openstack_id, "error": str(e)},
                exc_info=True,
            )
            raise DefaultException(
                message=f"Error when setting server {openstack_id} metadata: {e}"
            )

    def get_server_by_unique_name(
        self, unique_name: str, no_connection: bool = False
    ) -> Server:
        logger.debug(
            "Fetching server by unique name", extra={"unique_name": unique_name}
        )

        filters = {"name": unique_name}

        try:
            servers = list(self.openstack_connection.list_servers(filters=filters))
            logger.debug(
                "Servers found by name",
                extra={"unique_name": unique_name, "count": len(servers)},
            )
            if len(servers) == 1:
                server = list(servers)[0]
                logger.debug(
                    "Server details",
                    extra={"server_id": server.id, "vm_state": server.vm_state},
                )
                if server.vm_state == VmStates.ACTIVE.value and not no_connection:
                    ssh_port, udp_port = self._calculate_vm_ports(server=server)

                    if not self.netcat(port=ssh_port):
                        server.task_state = VmTaskStates.CHECKING_SSH_CONNECTION.value

                server.image = self.get_image(
                    name_or_id=server.image["id"],
                    ignore_not_active=True,
                    ignore_not_found=True,
                )

                server.flavor = self.get_flavor(
                    name_or_id=server.flavor["id"], ignore_error=True
                )
                return server
            elif len(servers) == 0:
                logger.warning(
                    "Server not found by name", extra={"unique_name": unique_name}
                )
                raise ServerNotFoundException(
                    message=f"Instance {unique_name} not found",
                    name_or_id=unique_name,
                )
            else:
                logger.error(
                    "Multiple servers found with same name",
                    extra={"unique_name": unique_name, "count": len(servers)},
                )
                raise DefaultException(
                    message=f"Error when getting server {unique_name}! - multiple entries"
                )
        except Exception as e:
            logger.error(
                "Error fetching server by name",
                extra={"unique_name": unique_name, "error": str(e)},
                exc_info=True,
            )
            raise

    def get_server_console(self, openstack_id: str):
        logger.debug("Fetching server console log", extra={"server_id": openstack_id})
        try:
            server: Server = self.openstack_connection.get_server_by_id(id=openstack_id)
            if server is None:
                logger.warning(
                    "Server not found for console log",
                    extra={"server_id": openstack_id},
                )
                raise ServerNotFoundException(
                    message=f"Instance {openstack_id} not found",
                    name_or_id=openstack_id,
                )
            logs: str = self.openstack_connection.get_server_console(
                server=server, length=50
            )
            logger.debug(
                "Console log retrieved",
                extra={"server_id": openstack_id, "log_length": len(logs)},
            )
            return logs
        except Exception as e:
            logger.error(
                "Error fetching server console log",
                extra={"server_id": openstack_id, "error": str(e)},
                exc_info=True,
            )
            raise

    def get_server(self, openstack_id: str, no_connection: bool = False) -> Server:
        try:
            logger.debug("Fetching server by ID", extra={"server_id": openstack_id})
            server: Server = self.openstack_connection.get_server_by_id(id=openstack_id)
            if server is None:
                logger.warning(
                    "Server not found by ID", extra={"server_id": openstack_id}
                )
                raise ServerNotFoundException(
                    message=f"Instance {openstack_id} not found",
                    name_or_id=openstack_id,
                )
            if server.vm_state == VmStates.ACTIVE.value and not no_connection:
                ssh_port, udp_port = self._calculate_vm_ports(server=server)

                if not self.netcat(port=ssh_port):
                    server.task_state = VmTaskStates.CHECKING_SSH_CONNECTION.value

            server.image = self.get_image(
                name_or_id=server.image["id"],
                ignore_not_active=True,
                ignore_not_found=True,
            )
            server.flavor = self.get_flavor(
                name_or_id=server.flavor["id"], ignore_error=True
            )

            logger.debug(
                "Server fetched successfully",
                extra={
                    "server_id": server.id,
                    "server_name": server.name,
                    "vm_state": server.vm_state,
                    "ip_address": server.private_v4,
                },
            )
            return server
        except OpenStackCloudException as e:
            logger.error(
                "Error fetching server",
                extra={"server_id": openstack_id, "error": str(e)},
                exc_info=True,
            )
            raise DefaultException(
                message=f"Error when getting server {openstack_id}! - {e}"
            )

    def resume_server(self, openstack_id: str) -> None:
        logger.info("Resuming server", extra={"server_id": openstack_id})
        try:
            server = self.get_server(openstack_id=openstack_id)
            self.openstack_connection.compute.start_server(server)
            logger.info(
                "Server resumed successfully", extra={"server_id": openstack_id}
            )
        except ConflictException as e:
            logger.error(
                "Failed to resume server - conflict",
                extra={"server_id": openstack_id, "error": str(e)},
                exc_info=True,
            )
            raise OpenStackConflictException(message=str(e))

    def reboot_hard_server(self, openstack_id: str) -> None:
        return self.reboot_server(openstack_id=openstack_id, reboot_type="HARD")

    def reboot_soft_server(self, openstack_id: str) -> None:
        return self.reboot_server(openstack_id=openstack_id, reboot_type="SOFT")

    def reboot_server(self, openstack_id: str, reboot_type: str) -> None:
        logger.info(
            "Rebooting server",
            extra={"server_id": openstack_id, "reboot_type": reboot_type},
        )
        server = self.get_server(openstack_id=openstack_id)
        try:
            self.openstack_connection.compute.reboot_server(server, reboot_type)
            logger.info(
                "Server reboot initiated",
                extra={"server_id": openstack_id, "reboot_type": reboot_type},
            )
        except ConflictException as e:
            logger.error(
                "Failed to reboot server - conflict",
                extra={
                    "server_id": openstack_id,
                    "reboot_type": reboot_type,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise OpenStackConflictException(message=str(e))

    def stop_server(self, openstack_id: str) -> None:
        logger.info("Stopping server", extra={"server_id": openstack_id})
        server = self.get_server(openstack_id=openstack_id)
        try:
            self.openstack_connection.compute.stop_server(server)
            logger.info(
                "Server stopped successfully", extra={"server_id": openstack_id}
            )
        except ConflictException as e:
            logger.error(
                "Failed to stop server - conflict",
                extra={"server_id": openstack_id, "error": str(e)},
                exc_info=True,
            )
            raise OpenStackConflictException(message=e.message)

    def _delete_security_groups_if_not_used(self, security_groups: list[SecurityGroup]):
        if security_groups is not None:
            for sg in security_groups:
                sec = self.openstack_connection.get_security_group(
                    name_or_id=sg["name"]
                )
                if sg[
                    "name"
                ] != self.DEFAULT_SECURITY_GROUP_NAME and not self.is_security_group_in_use(
                    security_group_id=sec.id
                ):
                    logger.info(
                        "Deleting unused security group",
                        extra={
                            "security_group_id": sec.id,
                            "security_group_name": sec["name"],
                        },
                    )
                    try:
                        self.openstack_connection.delete_security_group(sec)
                        logger.debug(
                            "Security group deleted",
                            extra={"security_group_id": sec.id},
                        )
                    except ResourceNotFound:
                        logger.warning(
                            "Security group already deleted or not found",
                            extra={"security_group_id": sec.id},
                        )

    def _remove_security_groups_from_server(self, server: Server) -> None:
        security_groups = server.security_groups

        if security_groups is not None:
            for sg in security_groups:
                sec = self.openstack_connection.get_security_group(
                    name_or_id=sg["name"]
                )
                logger.debug(
                    "Removing security group from server",
                    extra={"server_id": server.id, "security_group_id": sec.id},
                )
                self.openstack_connection.compute.remove_security_group_from_server(
                    server=server, security_group=sec
                )

                if (
                    sg["name"] != self.DEFAULT_SECURITY_GROUP_NAME
                    and ("bibigrid" not in sec.name or "master" not in server.name)
                    and not self.is_security_group_in_use(security_group_id=sec.id)
                ):
                    logger.info(
                        "Deleting unused security group after server removal",
                        extra={"security_group_id": sec.id, "server_id": server.id},
                    )
                    try:
                        self.openstack_connection.delete_security_group(sec)
                    except ResourceNotFound:
                        logger.debug(
                            "Security group already deleted or not found",
                            extra={"security_group_id": sec.id},
                        )

    def remove_security_groups_from_server(self, openstack_id):
        logger.info(
            "Removing security groups from server", extra={"server_id": openstack_id}
        )
        try:
            server: Server = self.get_server(openstack_id=openstack_id)
            self._remove_security_groups_from_server(server)
            logger.info(
                "Security groups removed from server", extra={"server_id": openstack_id}
            )
        except ConflictException as e:
            logger.error(
                "Failed to remove security groups from server",
                extra={"server_id": openstack_id, "error": str(e)},
                exc_info=True,
            )
            raise OpenStackConflictException(message=e.message)

    def _validate_server_for_deletion(self, server: Server) -> None:
        task_state = server.task_state
        if task_state in [
            "image_snapshot",
            "image_pending_upload",
            "image_uploading",
        ]:
            raise ConflictException("task_state in image creating")

    def delete_server(self, openstack_id: str) -> None:
        logger.info("Deleting server", extra={"server_id": openstack_id})
        try:
            server: Server = self.get_server(openstack_id=openstack_id)
            if not server:
                logger.warning(
                    "Server not found for deletion", extra={"server_id": openstack_id}
                )
                raise ServerNotFoundException(
                    message=f"Instance {openstack_id} not found",
                    name_or_id=openstack_id,
                )

            self._validate_server_for_deletion(server=server)

            logger.info(
                "Starting server deletion",
                extra={"server_id": openstack_id, "server_name": server.name},
            )
            self.openstack_connection.compute.delete_server(server.id, force=True)

            security_groups = server.security_groups
            self._delete_security_groups_if_not_used(security_groups)

            logger.info(
                "Server deleted successfully",
                extra={"server_id": openstack_id, "server_name": server.name},
            )
        except ConflictException as e:
            logger.error(
                "Failed to delete server - conflict",
                extra={"server_id": openstack_id, "error": str(e)},
                exc_info=True,
            )
            raise OpenStackConflictException(message=e.message)

    def rescue_server(
        self, openstack_id: str, admin_pass: str = None, image_ref: str = None
    ) -> None:
        logger.info(
            "Rescuing server",
            extra={
                "server_id": openstack_id,
                "admin_pass_set": admin_pass is not None,
                "image_ref": image_ref,
            },
        )

        try:
            server: Server = self.get_server(openstack_id=openstack_id)
            if not server:
                logger.warning(
                    "Server not found for rescue", extra={"server_id": openstack_id}
                )
                raise ServerNotFoundException(
                    message=f"Instance {openstack_id} not found",
                    name_or_id=openstack_id,
                )
            self.openstack_connection.compute.rescue_server(
                server, admin_pass, image_ref
            )
            logger.info("Server rescue initiated", extra={"server_id": openstack_id})
        except ConflictException as e:
            logger.error(
                "Failed to rescue server - conflict",
                extra={"server_id": openstack_id, "error": str(e)},
                exc_info=True,
            )
            raise OpenStackConflictException(message=e.message)

    def unrescue_server(self, openstack_id: str) -> None:
        logger.info("Unrescuing server", extra={"server_id": openstack_id})
        try:
            server: Server = self.get_server(openstack_id=openstack_id)
            if not server:
                logger.warning(
                    "Server not found for unrescue", extra={"server_id": openstack_id}
                )
                raise ServerNotFoundException(
                    message=f"Instance {openstack_id} not found",
                    name_or_id=openstack_id,
                )

            self.openstack_connection.compute.unrescue_server(server)
            logger.info("Server unrescue completed", extra={"server_id": openstack_id})
        except ConflictException as e:
            logger.error(
                "Failed to unrescue server - conflict",
                extra={"server_id": openstack_id, "error": str(e)},
                exc_info=True,
            )
            raise OpenStackConflictException(message=e.message)

    def _calculate_vm_ports(self, server: Server):
        octets = {
            f"oct{enum + 1}": int(elem)
            for enum, elem in enumerate(server.private_v4.split("."))
        }
        ssh_port = int(sympy.sympify(self.SSH_PORT_CALCULATION).subs(dict(octets)))
        udp_port = int(sympy.sympify(self.UDP_PORT_CALCULATION).subs(dict(octets)))

        return ssh_port, udp_port

    def get_vm_ports(self, openstack_id: str) -> dict[str, str]:
        logger.debug(
            "Getting IP and ports for server", extra={"server_id": openstack_id}
        )
        server = self.get_server(openstack_id=openstack_id)
        ssh_port, udp_port = self._calculate_vm_ports(server=server)

        logger.debug(
            "Server ports retrieved",
            extra={
                "server_id": openstack_id,
                "ssh_port": ssh_port,
                "udp_port": udp_port,
            },
        )
        return {"port": str(ssh_port), "udp": str(udp_port)}

    def create_userdata(
        self,
        volume_ids_path_new: list[dict[str, str]],
        volume_ids_path_attach: list[dict[str, str]],
        additional_owner_keys: list[str],
        additional_user_keys: list[str],
        metadata_token: str = None,
        metadata_endpoint: str = None,
        additional_script: str = "",
    ) -> str:
        logger.debug(
            "Creating user data script",
            extra={
                "has_volumes_new": len(volume_ids_path_new or []) > 0,
                "has_volumes_attach": len(volume_ids_path_attach or []) > 0,
                "has_owner_keys": len(additional_owner_keys or []) > 0,
                "has_user_keys": len(additional_user_keys or []) > 0,
                "has_metadata_token": metadata_token is not None,
            },
        )
        unlock_ubuntu_user_script = "#!/bin/bash\npasswd -u ubuntu\n"
        unlock_ubuntu_user_script_encoded = encodeutils.safe_encode(
            unlock_ubuntu_user_script.encode("utf-8")
        )
        init_script = unlock_ubuntu_user_script_encoded

        if additional_owner_keys or additional_user_keys:
            add_key_script = self.create_add_keys_script(
                additional_owner_keys=additional_owner_keys,
                addtional_user_keys=additional_user_keys,
            )
            init_script = (
                add_key_script
                + encodeutils.safe_encode("\n".encode("utf-8"))
                + init_script
            )

        if volume_ids_path_new or volume_ids_path_attach:
            mount_script = self.create_mount_init_script(
                new_volumes=volume_ids_path_new,
                attach_volumes=volume_ids_path_attach,
            )
            init_script = (
                init_script
                + encodeutils.safe_encode("\n".encode("utf-8"))
                + mount_script
            )

        if metadata_token and metadata_endpoint:
            save_metadata_token_script = self.create_save_metadata_auth_token_script(
                token=metadata_token, metadata_endpoint=metadata_endpoint
            )
            init_script = (
                init_script
                + encodeutils.safe_encode("\n".encode("utf-8"))
                + save_metadata_token_script
            )

        if additional_script:
            init_script = (
                init_script
                + encodeutils.safe_encode("\n".encode("utf-8"))
                + encodeutils.safe_encode(additional_script.encode("utf-8"))
            )

        logger.debug(
            "User data script created successfully",
            extra={
                "has_volumes_new": len(volume_ids_path_new or []) > 0,
                "has_volumes_attach": len(volume_ids_path_attach or []) > 0,
                "has_owner_keys": len(additional_owner_keys or []) > 0,
                "has_user_keys": len(additional_user_keys or []) > 0,
                "has_metadata_token": metadata_token is not None,
                "has_additional_script": bool(additional_script),
            },
        )
        return init_script

    def start_server(
        self,
        flavor_name: str,
        image_name: str,
        servername: str,
        metadata: dict[str, str],
        public_key: str,
        research_environment_metadata: Union[ResearchEnvironmentMetadata, None] = None,
        volume_ids_path_new: Union[list[dict[str, str]], None] = None,
        volume_ids_path_attach: Union[list[dict[str, str]], None] = None,
        additional_owner_keys: Union[list[str], None] = None,
        additional_user_keys: Union[list[str], None] = None,
        additional_security_group_ids: Union[list[str], None] = None,
        slurm_version: str = None,
        metadata_token: str = None,
        metadata_endpoint: str = None,
        additional_script: str = "",
    ) -> str:
        logger.info(
            "Starting new server",
            extra={
                "servername": servername,
                "flavor_name": flavor_name,
                "image_name": image_name,
                "project": metadata.get("project_name"),
                "metadata_keys": list(metadata.keys()),
            },
        )

        key_name: str = (
            str(uuid4())[0:3]
            + "_"
            + servername[:10]
            + "_"
            + metadata.get("project_name", "")
        )
        try:
            image: Image = self.get_image(
                name_or_id=image_name,
                replace_inactive=True,
                ignore_not_found=True,
                replace_not_found=True,
                slurm_version=slurm_version,
            )
            flavor: Flavor = self.get_flavor(name_or_id=flavor_name)
            network: Network = self.get_network()
            logger.debug("Using key name", extra={"key_name": key_name})
            project_name = metadata.get("project_name")
            project_id = metadata.get("project_id")
            security_groups = self._get_security_groups_starting_machine(
                additional_security_group_ids=additional_security_group_ids,
                project_name=project_name,
                project_id=project_id,
                research_environment_metadata=research_environment_metadata,
            )

            public_key = urllib.parse.unquote(public_key)
            self.import_keypair(key_name, public_key)
            volumes = self._get_volumes_machines_start(
                volume_ids_path_new=volume_ids_path_new,
                volume_ids_path_attach=volume_ids_path_attach,
            )

            init_script = self.create_userdata(
                volume_ids_path_new=volume_ids_path_new,
                volume_ids_path_attach=volume_ids_path_attach,
                additional_owner_keys=additional_owner_keys,
                additional_user_keys=additional_user_keys,
                metadata_token=metadata_token,
                metadata_endpoint=metadata_endpoint,
                additional_script=additional_script,
            )
            logger.info(
                "Creating OpenStack server instance",
                extra={
                    "servername": servername,
                    "key_name": key_name,
                    "security_groups": security_groups,
                },
            )
            server = self.openstack_connection.create_server(
                name=servername,
                image=image.id,
                flavor=flavor.id,
                network=[network.id],
                key_name=key_name,
                meta=metadata,
                volumes=volumes,
                userdata=init_script,
                security_groups=security_groups,
                boot_from_volume=False,
                boot_volume=None,
            )

            openstack_id: str = server["id"]
            logger.info(
                "Server started successfully",
                extra={"server_id": openstack_id, "servername": servername},
            )
            self.delete_keypair(key_name=key_name)

            return openstack_id

        except OpenStackCloudException as e:
            if key_name:
                self.delete_keypair(key_name=key_name)

            logger.error(
                "Failed to start server",
                extra={
                    "servername": servername,
                    "flavor_name": flavor_name,
                    "image_name": image_name,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise DefaultException(message=str(e))

    def _get_volumes_machines_start(
        self,
        volume_ids_path_new: list[dict[str, str]] = None,
        volume_ids_path_attach: list[dict[str, str]] = None,
    ) -> list[Volume]:
        volume_ids = []
        if volume_ids_path_new:
            volume_ids.extend([vol["openstack_id"] for vol in volume_ids_path_new])
        if volume_ids_path_attach:
            volume_ids.extend([vol["openstack_id"] for vol in volume_ids_path_attach])
        logger.debug("Volumes for machine start", extra={"volume_ids": volume_ids})

        return volume_ids

    def _get_security_groups_starting_machine(
        self,
        additional_security_group_ids: Union[list[str], None] = None,
        project_name: Union[str, None] = None,
        project_id: Union[str, None] = None,
        research_environment_metadata: Union[ResearchEnvironmentMetadata, None] = None,
    ) -> list[str]:
        security_groups = self._get_default_security_groups()
        if research_environment_metadata:
            security_groups.append(
                self.get_or_create_research_environment_security_group(
                    resenv_metadata=research_environment_metadata
                )
            )
        if project_name and project_id:
            security_groups.append(
                self.get_or_create_project_security_group(
                    project_name=project_name, project_id=project_id
                )
            )
        if additional_security_group_ids:
            for security_id in additional_security_group_ids:
                sec = self.openstack_connection.get_security_group(
                    name_or_id=security_id
                )
                if sec:
                    security_groups.append(sec["id"])
        logger.debug(
            "Security groups for machine start",
            extra={"security_groups": security_groups},
        )
        return security_groups

    def start_server_with_playbook(
        self,
        flavor_name: str,
        image_name: str,
        servername: str,
        metadata: dict[str, str],
        research_environment_metadata: ResearchEnvironmentMetadata,
        volume_ids_path_new: list[dict[str, str]] = None,  # type: ignore
        volume_ids_path_attach: list[dict[str, str]] = None,  # type: ignore
        additional_owner_keys: Union[list[str], None] = None,
        additional_user_keys: Union[list[str], None] = None,
        additional_security_group_ids=None,  # type: ignore
        metadata_token: str = None,
        metadata_endpoint: str = None,
        additional_script: str = "",
    ) -> tuple[str, str]:
        logger.info(
            "Starting server with playbook",
            extra={
                "servername": servername,
                "flavor_name": flavor_name,
                "image_name": image_name,
                "project": metadata.get("project_name"),
                "playbook": True,
            },
        )

        project_name = metadata.get("project_name")
        project_id = metadata.get("project_id")
        security_groups = self._get_security_groups_starting_machine(
            additional_security_group_ids=additional_security_group_ids,
            project_name=project_name,
            project_id=project_id,
            research_environment_metadata=research_environment_metadata,
        )
        key_name = None
        try:
            image: Image = self.get_image(name_or_id=image_name)
            flavor: Flavor = self.get_flavor(name_or_id=flavor_name)
            network: Network = self.get_network()

            key_creation: Keypair = self.openstack_connection.create_keypair(
                name=servername
            )
            key_name = key_creation.name

            private_key = key_creation.private_key

            volumes = self._get_volumes_machines_start(
                volume_ids_path_new=volume_ids_path_new,
                volume_ids_path_attach=volume_ids_path_attach,
            )

            init_script = self.create_userdata(
                volume_ids_path_new=volume_ids_path_new,
                volume_ids_path_attach=volume_ids_path_attach,
                additional_owner_keys=additional_owner_keys,
                additional_user_keys=additional_user_keys,
                metadata_token=metadata_token,
                metadata_endpoint=metadata_endpoint,
                additional_script=additional_script,
            )
            server = self.openstack_connection.create_server(
                name=servername,
                image=image.id,
                flavor=flavor.id,
                network=[network.id],
                key_name=servername,
                meta=metadata,
                volumes=volumes,
                userdata=init_script,
                security_groups=security_groups,
                boot_from_volume=False,
            )

            openstack_id = server["id"]
            self.delete_keypair(key_name=key_creation.name)

            logger.info(
                "Server with playbook started successfully",
                extra={"server_id": openstack_id, "servername": servername},
            )
            return openstack_id, private_key

        except OpenStackCloudException as e:
            if key_name:
                self.delete_keypair(key_name=key_name)

            logger.error(
                "Failed to start server with playbook",
                extra={
                    "servername": servername,
                    "flavor_name": flavor_name,
                    "image_name": image_name,
                    "error": str(e),
                },
                exc_info=True,
            )
            raise DefaultException(message=str(e))

    def create_deactivate_update_script(self) -> str:
        file_dir = os.path.dirname(os.path.abspath(__file__))
        deactivate_update_script_file = os.path.join(file_dir, "scripts/bash/mount.sh")
        with open(deactivate_update_script_file, "r") as file:
            deactivate_update_script = file.read()
            deactivate_update_script = encodeutils.safe_encode(
                deactivate_update_script.encode("utf-8")
            )
        return deactivate_update_script

    def add_research_environment_security_group(
        self, server_id: str, security_group_name: str
    ):
        logger.info(
            "Adding research environment security group",
            extra={"server_id": server_id, "security_group": security_group_name},
        )
        server: Server = self.get_server(openstack_id=server_id)
        security_group: SecurityGroup = self.get_research_environment_security_group(
            security_group_name=security_group_name
        )
        if self._is_security_group_already_added_to_server(
            server=server, security_group_name=security_group.name
        ):
            logger.debug(
                "Security group already added to server",
                extra={"server_id": server_id, "security_group": security_group_name},
            )
            return
        self.openstack_connection.compute.add_security_group_to_server(
            server=server, security_group=security_group
        )
        logger.info(
            "Research environment security group added",
            extra={"server_id": server_id, "security_group": security_group_name},
        )

    def add_project_security_group_to_server(
        self, server_id: str, project_name: str, project_id: str
    ):
        logger.info(
            "Adding project security group to server",
            extra={
                "server_id": server_id,
                "project_name": project_name,
                "project_id": project_id,
            },
        )
        server: Server = self.get_server(openstack_id=server_id)
        security_group_id = self.get_or_create_project_security_group(
            project_name=project_name, project_id=project_id
        )
        security_group = self.openstack_connection.get_security_group(
            name_or_id=security_group_id
        )
        if self._is_security_group_already_added_to_server(
            server=server, security_group_name=security_group.name
        ):
            logger.debug(
                "Project security group already added to server",
                extra={"server_id": server_id, "project_name": project_name},
            )
            return
        self.openstack_connection.compute.add_security_group_to_server(
            server=server, security_group=security_group
        )
        logger.info(
            "Project security group added",
            extra={"server_id": server_id, "project_name": project_name},
        )

    def add_metadata_to_server(self, server_id, metadata):
        logger.info(
            "Setting metadata for server",
            extra={"server_id": server_id, "metadata_keys": list(metadata.keys())},
        )
        server = self.get_server(openstack_id=server_id)

        self.openstack_connection.compute.set_server_metadata(server, **metadata)
        logger.debug("Server metadata set", extra={"server_id": server_id})

    def _is_security_group_already_added_to_server(
        self, server: Server, security_group_name: str
    ):
        server_security_groups = self.openstack_connection.list_server_security_groups(
            server
        )

        for sg in server_security_groups:
            if sg["name"] == security_group_name:
                logger.debug(
                    "Security group already added to server",
                    extra={
                        "security_group": security_group_name,
                        "server_id": server.id,
                    },
                )
                return True
        logger.debug(
            "Security group not found on server",
            extra={"security_group": security_group_name, "server_id": server.id},
        )
        return False

    def add_udp_security_group(self, server_id):
        logger.debug("Setting up UDP security group", extra={"server_id": server_id})
        server = self.get_server(openstack_id=server_id)
        sec_name = server.name + "_udp"
        existing_sec = self.openstack_connection.get_security_group(name_or_id=sec_name)
        if existing_sec:
            logger.debug(
                "UDP Security group already exists", extra={"security_group": sec_name}
            )
            if self._is_security_group_already_added_to_server(
                server=server, security_group_name=sec_name
            ):
                logger.debug(
                    "UDP Security group already added to server",
                    extra={"server_id": server_id, "security_group": sec_name},
                )
                return

            logger.debug(
                "Adding existing UDP security group to server",
                extra={"server_id": server_id, "security_group": sec_name},
            )
            self.openstack_connection.compute.add_security_group_to_server(
                server=server_id, security_group=existing_sec
            )
            return

        vm_ports = self.get_vm_ports(openstack_id=server_id)
        udp_port = vm_ports["udp"]

        logger.debug(
            "Creating new UDP security group",
            extra={"server_id": server_id, "udp_port": udp_port},
        )
        security_group = self.create_security_group(
            name=sec_name,
            udp_port=int(udp_port),
            udp=True,
            ssh=False,
            description="UDP",
        )
        logger.debug(
            "Adding UDP security group to server",
            extra={"server_id": server_id, "security_group_id": security_group.id},
        )
        self.openstack_connection.compute.add_security_group_to_server(
            server=server_id, security_group=security_group
        )
        return

    def add_cluster_machine(
        self,
        cluster_id: str,
        cluster_user: str,
        cluster_group_id: list[str],
        image_name: str,
        flavor_name: str,
        name: str,
        key_name: str,
        batch_idx: int,
        worker_idx: int,
    ) -> str:
        logger.info(
            "Adding machine to cluster",
            extra={
                "cluster_id": cluster_id,
                "cluster_user": cluster_user,
                "machine_name": name,
                "batch_idx": batch_idx,
                "worker_idx": worker_idx,
            },
        )
        image: Image = self.get_image(name_or_id=image_name, replace_inactive=True)
        flavor: Flavor = self.get_flavor(name_or_id=flavor_name)
        network = self.get_network()
        metadata = {
            "bibigrid-id": cluster_id,
            "user": cluster_user or "",
            "worker-batch": str(batch_idx),
            "name": name or "",
            "worker-index": str(worker_idx),
        }

        server = self.create_server(
            name=name,
            image_id=image.id,
            flavor_id=flavor.id,
            network_id=network.id,
            userdata=self.DEACTIVATE_UPGRADES_SCRIPT,
            key_name=key_name,
            metadata=metadata,
            security_groups=cluster_group_id,
        )
        logger.info(
            "Cluster machine created",
            extra={
                "cluster_id": cluster_id,
                "machine_id": server["id"],
                "machine_name": name,
            },
        )
        server_id: str = server["id"]
        return server_id
