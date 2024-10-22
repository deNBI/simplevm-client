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

lock_dict = {}
lock_access = threading.Lock()


class OpenStackConnector:
    def __init__(self, config_file: str):
        # Config FIle Data
        logger.info("Initializing OpenStack Connector")
        self.GATEWAY_IP: str = ""
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

        self.load_env_config()
        logger.info(f"Loading config file -- {config_file}")
        self.load_config_yml(config_file)

        try:
            # Create an authentication session

            if self.USE_APPLICATION_CREDENTIALS:

                logger.info("Using Application Credentials for OpenStack Connection")
                # Create an authentication session
                auth = application_credential.ApplicationCredential(
                    auth_url=self.AUTH_URL,
                    application_credential_id=self.APPLICATION_CREDENTIAL_ID,
                    application_credential_secret=self.APPLICATION_CREDENTIAL_SECRET,
                )

                sess = session.Session(auth=auth)

                # Configure session settings as needed
                sess.session.connections_pool = True
                sess.session.connection_pool_size = 32

                # Create the Connection object with the session
                self.openstack_connection = connection.Connection(session=sess)

            else:
                logger.info("Using User Credentials for OpenStack Connection")
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
                sess.session.connection_pool_size = 32  # Number of connections to pool
                self.openstack_connection = connection.Connection(
                    session=sess,
                    compute_api_version=self.NOVA_MICROVERSION,
                )
            self.openstack_connection.authorize()
            self.get_network()

            logger.info("Connected to Openstack")
            self.create_or_get_default_ssh_security_group()
        except Exception:
            logger.error("Client failed authentication at Openstack!")
            raise ConnectionError("Client failed authentication at Openstack")

        self.DEACTIVATE_UPGRADES_SCRIPT = self.create_deactivate_update_script()

    def load_config_yml(self, config_file: str) -> None:
        logger.info(f"Load config file openstack config - {config_file}")
        with open(config_file, "r") as ymlfile:
            cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)

            self.GATEWAY_IP = cfg["openstack"]["gateway_ip"]
            self.NETWORK = cfg["openstack"]["network"]
            self.PRODUCTION = cfg["production"]
            self.CLOUD_SITE = cfg["openstack"]["cloud_site"]
            self.SSH_PORT_CALCULATION = cfg["openstack"]["ssh_port_calculation"]
            self.UDP_PORT_CALCULATION = cfg["openstack"]["udp_port_calculation"]
            self.FORC_SECURITY_GROUP_ID = cfg["openstack"].get(
                "forc_security_group_id", None
            )
            if not self.FORC_SECURITY_GROUP_ID:
                logger.info("No Forc Security Group defined")
            self.DEFAULT_SECURITY_GROUP_NAME = "defaultSimpleVM"
            self.DEFAULT_SECURITY_GROUPS = [self.DEFAULT_SECURITY_GROUP_NAME]
            self.GATEWAY_SECURITY_GROUP_ID = cfg["openstack"][
                "gateway_security_group_id"
            ]
            if "compute_api_version" in cfg["openstack"]:
                self.NOVA_MICROVERSION = cfg["openstack"]["compute_api_version"]

    def _get_default_security_groups(self):
        return self.DEFAULT_SECURITY_GROUPS.copy()

    def load_env_config(self) -> None:
        logger.info("Load environment config: OpenStack")

        self.AUTH_URL = os.environ.get("OS_AUTH_URL")
        if not self.AUTH_URL:
            logger.error("OS_AUTH_URL not provided in env!")
            sys.exit(1)

        self.USE_APPLICATION_CREDENTIALS = (
            os.environ.get("USE_APPLICATION_CREDENTIALS", "False").lower() == "true"
        )

        if self.USE_APPLICATION_CREDENTIALS:
            logger.info("APPLICATION CREDENTIALS will be used!")
            try:
                self.APPLICATION_CREDENTIAL_ID = os.environ[
                    "OS_APPLICATION_CREDENTIAL_ID"
                ]
                self.APPLICATION_CREDENTIAL_SECRET = os.environ[
                    "OS_APPLICATION_CREDENTIAL_SECRET"
                ]
            except KeyError as e:
                logger.error(
                    f"Usage of Application Credentials enabled - but {e.args[0]} not provided in env!"
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
                missing_keys_str = ", ".join(missing_keys)
                logger.error(
                    f"Usage of Username/Password enabled - but keys {missing_keys_str} not provided in env!"
                )
                sys.exit(1)
            else:
                self.USERNAME = os.environ["OS_USERNAME"]
                self.PASSWORD = os.environ["OS_PASSWORD"]
                self.PROJECT_NAME = os.environ["OS_PROJECT_NAME"]
                self.PROJECT_ID = os.environ["OS_PROJECT_ID"]
                self.USER_DOMAIN_NAME = os.environ["OS_USER_DOMAIN_NAME"]
                self.PROJECT_DOMAIN_ID = os.environ["OS_PROJECT_DOMAIN_ID"]

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
            f"Create Server:\n\tname: {name}\n\timage_id:{image_id}\n\tflavor_id:{flavor_id}\n\tmetadata:{metadata}"
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
        return server

    def get_volume(self, name_or_id: str) -> Volume:
        logger.info(f"Get Volume {name_or_id}")
        volume: Volume = self.openstack_connection.get_volume(name_or_id=name_or_id)
        if volume is None:
            logger.exception(f"No Volume with id {name_or_id}")
            raise VolumeNotFoundException(
                message=f"No Volume with id {name_or_id}", name_or_id=name_or_id
            )
        return volume

    def delete_volume(self, volume_id: str) -> None:
        try:
            logger.info(f"Delete Volume {volume_id}")
            self.openstack_connection.delete_volume(name_or_id=volume_id)
        except ResourceNotFound as e:
            logger.exception(f"No Volume with id {volume_id}")
            raise VolumeNotFoundException(message=e.message, name_or_id=volume_id)

        except ConflictException as e:
            logger.exception(f"Delete volume: {volume_id}) failed!")
            raise OpenStackCloudException(message=e.message)
        except OpenStackCloudException as e:
            raise DefaultException(message=e.message)

    def create_volume_snapshot(
        self, volume_id: str, name: str, description: str
    ) -> str:
        try:
            logger.info(f"Create Snapshot for Volume {volume_id}")
            volume_snapshot = self.openstack_connection.create_volume_snapshot(
                volume_id=volume_id, name=name, description=description
            )
            return volume_snapshot["id"]
        except ResourceNotFound as e:
            logger.error(f"No Volume with id {volume_id}")
            raise VolumeNotFoundException(message=e.message, name_or_id=volume_id)
        except OpenStackCloudException as e:
            raise DefaultException(message=e.message)

    def get_volume_snapshot(self, name_or_id: str) -> Snapshot:
        logger.info(f"Get volume Snapshot {name_or_id}")
        snapshot: Snapshot = self.openstack_connection.get_volume_snapshot(
            name_or_id=name_or_id
        )
        if snapshot is None:
            logger.exception(f"No volume Snapshot with id {name_or_id}")
            raise VolumeNotFoundException(
                message=f"No volume Snapshot with id {name_or_id}",
                name_or_id=name_or_id,
            )
        return snapshot

    def delete_volume_snapshot(self, snapshot_id: str) -> None:
        try:
            logger.info(f"Delete volume Snapshot {snapshot_id}")
            self.openstack_connection.delete_volume_snapshot(name_or_id=snapshot_id)
        except ResourceNotFound as e:
            logger.exception(f"Snapshot not found: {snapshot_id}")

            raise SnapshotNotFoundException(message=e.message, name_or_id=snapshot_id)

        except ConflictException as e:
            logger.exception(f"Delete volume snapshot: {snapshot_id}) failed!")
            raise OpenStackCloudException(message=e.message)
        except OpenStackCloudException as e:
            raise DefaultException(message=e.message)

    def create_volume_by_source_volume(
        self, volume_name: str, metadata: dict[str, str], source_volume_id: str
    ) -> Volume:
        logger.info(f"Creating volume from source volume with id {source_volume_id}")
        try:
            volume: Volume = self.openstack_connection.block_storage.create_volume(
                name=volume_name, metadata=metadata, source_volume_id=source_volume_id
            )
            return volume
        except ResourceFailure as e:
            logger.exception(
                f"Trying to create volume from source volume with id {source_volume_id} failed",
                exc_info=True,
            )
            raise ResourceNotAvailableException(message=e.message)

    def create_volume_by_volume_snap(
        self, volume_name: str, metadata: dict[str, str], volume_snap_id: str
    ) -> Volume:
        logger.info(f"Creating volume from volume snapshot with id {volume_snap_id}")
        try:
            volume: Volume = self.openstack_connection.block_storage.create_volume(
                name=volume_name, metadata=metadata, snapshot_id=volume_snap_id
            )
            return volume
        except ResourceFailure as e:
            logger.exception(
                f"Trying to create volume from volume snapshot with id {volume_snap_id} failed",
                exc_info=True,
            )
            raise ResourceNotAvailableException(message=e.message)

    def get_servers(self) -> list[Server]:
        logger.info("Get servers")
        servers: list[Server] = self.openstack_connection.list_servers()
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
        return servers

    def get_servers_by_ids(self, ids: list[str]) -> list[Server]:
        logger.info(f"Get Servers by IDS : {ids}")
        servers: list[Server] = []
        for server_id in ids:
            logger.info(f"Get server {server_id}")
            try:
                server = self.openstack_connection.get_server_by_id(server_id)
                if server:
                    servers.append(server)
                else:
                    logger.error(f"Requested VM {server_id} not found!")

            except Exception as e:
                logger.exception(f"Requested VM {server_id} not found!\n {e}")
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
        return servers

    def attach_volume_to_server(
        self, openstack_id: str, volume_id: str
    ) -> dict[str, str]:
        server = self.get_server(openstack_id=openstack_id)
        volume = self.get_volume(name_or_id=volume_id)

        logger.info(f"Attaching volume {volume_id} to virtualmachine {openstack_id}")
        try:
            attachment = self.openstack_connection.attach_volume(
                server=server, volume=volume
            )
            return {"device": attachment["device"]}
        except ConflictException as e:
            logger.exception(
                f"Trying to attach volume {volume_id} to vm {openstack_id} error failed!",
                exc_info=True,
            )
            raise OpenStackConflictException(message=e.message)

    def detach_volume(self, volume_id: str, server_id: str) -> None:
        try:
            logger.info(f"Delete Volume Attachment  {volume_id} - {server_id}")
            volume = self.get_volume(name_or_id=volume_id)
            server = self.get_server(openstack_id=server_id)
            self.openstack_connection.detach_volume(volume=volume, server=server)
        except ConflictException as e:
            logger.exception(
                f"Delete volume attachment (server: {server_id} volume: {volume_id}) failed!"
            )
            raise OpenStackConflictException(message=e.message)

    def resize_volume(self, volume_id: str, size: int) -> None:
        try:
            logger.info(f"Extend volume {volume_id} to size {size}")
            self.openstack_connection.block_storage.extend_volume(volume_id, size)
        except ResourceNotFound as e:
            raise VolumeNotFoundException(message=e.message, name_or_id=volume_id)
        except OpenStackCloudException as e:
            logger.exception(f"Could not extend volume {volume_id}")
            raise DefaultException(message=str(e))

    def create_volume(
        self, volume_name: str, volume_storage: int, metadata: dict[str, str]
    ) -> Volume:
        logger.info(f"Creating volume with {volume_storage} GB storage")
        try:
            volume: Volume = self.openstack_connection.block_storage.create_volume(
                name=volume_name, size=volume_storage, metadata=metadata
            )
            return volume
        except ResourceFailure as e:
            logger.exception(
                f"Trying to create volume with {volume_storage} GB  failed",
                exc_info=True,
            )
            raise ResourceNotAvailableException(message=e.message)

    def get_network(self) -> Network:
        logger.info(f"Getting Network: {self.NETWORK}")
        network: Network = self.openstack_connection.get_network(
            name_or_id=self.NETWORK
        )
        if network is None:
            logger.exception(f"Network {self.NETWORK} not found!")
            raise Exception(f"Network {self.NETWORK} not found!")
        return network

    def import_keypair(self, keyname: str, public_key: str) -> dict[str, str]:
        logger.info(f"Get Keypair {keyname}")
        keypair: dict[str, str] = self.openstack_connection.get_keypair(
            name_or_id=keyname
        )
        if not keypair:
            logger.info(f"Create Keypair {keyname}")

            new_keypair: dict[str, str] = self.openstack_connection.create_keypair(
                name=keyname, public_key=public_key
            )
            return new_keypair

        elif keypair["public_key"] != public_key:
            logger.info(f"Key {keyname} has changed. Replace old Key")
            self.delete_keypair(key_name=keyname)
            old_keypair: dict[str, str] = self.openstack_connection.create_keypair(
                name=keyname, public_key=public_key
            )
            return old_keypair
        else:
            return keypair

    def get_keypair_public_key_by_name(self, key_name: str):
        logger.info(f"Get keypair: {key_name}")

        key_pair: Keypair = self.openstack_connection.compute.find_keypair(key_name)
        if key_pair:
            return key_pair.public_key
        return ""

    def delete_keypair(self, key_name: str) -> None:
        logger.info(f"Delete keypair: {key_name}")

        key_pair = self.openstack_connection.compute.find_keypair(key_name)
        if key_pair:
            self.openstack_connection.delete_keypair(name=key_name)

    def create_add_keys_script(self, keys: list[str]) -> str:
        logger.info("create add key script")
        file_dir = os.path.dirname(os.path.abspath(__file__))
        key_script = os.path.join(file_dir, "scripts/bash/add_keys_to_authorized.sh")
        bash_keys_array = "("
        for key in keys:
            bash_keys_array += f'"{key}" '
        bash_keys_array += ")"

        with open(key_script, "r") as file:
            text = file.read()
            text = text.replace("KEYS_TO_ADD", bash_keys_array)
            text = encodeutils.safe_encode(text.encode("utf-8"))
        key_script = text
        return key_script

    def create_save_metadata_auth_token_script(
        self, token: str, metadata_endpoint: str
    ) -> str:
        logger.info("create save metadata auth token script")
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

    def netcat(self, host: str, port: int) -> bool:
        logger.info(f"Checking SSH Connection {host}:{port}")
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.settimeout(5)
            r = sock.connect_ex((host, port))
            logger.info(f"Checking SSH Connection {host}:{port} Result = {r}")
        return r == 0

    def get_flavor(self, name_or_id: str, ignore_error: bool = False) -> Flavor:
        logger.info(f"Get flavor {name_or_id}")

        flavor: Flavor = self.openstack_connection.get_flavor(
            name_or_id=name_or_id, get_extra=True
        )

        if flavor is None:
            logger.error(f"Flavor {name_or_id} not found!")

            if not ignore_error:
                raise FlavorNotFoundException(
                    message=f"Flavor {name_or_id} not found!", name_or_id=name_or_id
                )
            else:
                return Flavor()

        return flavor

    def get_flavors(self) -> list[Flavor]:
        logger.info("Get Flavors")
        flavors: list[Flavor] = self.openstack_connection.list_flavors(get_extra=True)
        logger.info([flav["name"] for flav in flavors])
        return flavors

    def get_servers_by_bibigrid_id(self, bibigrid_id: str) -> list[Server]:
        logger.info(f"Get Servery by Bibigrid id: {bibigrid_id}")
        filters = {"bibigrid_id": bibigrid_id, "name": bibigrid_id}
        servers: list[Server] = self.openstack_connection.list_servers(filters=filters)
        flavors = {}
        images = {}
        for server in servers:
            flavor = server.flavor
            if not flavor.get("name"):
                if not flavors.get(flavor.id):
                    openstack_flavor = self.openstack_connection.get_flavor(flavor.id)
                    flavors[flavor.id] = openstack_flavor
                    server.flavor = openstack_flavor
                else:
                    server.flavor = flavors.get(flavor.id)
            image = server.image
            if not image.get("name"):
                if not image.get(image.id):
                    openstack_image = self.openstack_connection.get_image(image.id)
                    images[image.id] = openstack_image
                    server.image = openstack_image
                else:
                    server.image = images.get(image.id)
        return servers

    def get_active_image_by_os_version(
        self, os_version: str, os_distro: Union[str, None]
    ) -> Image:
        logger.info(f"Get active Image by os-version: {os_version}")
        images = self.openstack_connection.list_images()
        for image in images:

            image_os_version = image.get("os_version", None)
            image_os_distro = image.get("os_distro", None)
            image_properties = image.get("properties", None)
            if image_properties:

                base_image_ref = image_properties.get("base_image_ref", None)
            else:
                base_image_ref = None
            if (
                os_version == image_os_version
                and image.status == "active"
                and base_image_ref is None
            ):

                if os_distro and os_distro == image_os_distro:
                    return image
                elif os_distro is None:
                    return image
        raise ImageNotFoundException(
            message=f"Old Image was deactivated! No image with os_version:{os_version} and os_distro:{os_distro} found!",
            name_or_id="",
        )

    def get_active_image_by_os_version_and_slurm_version(
        self, os_version, os_distro, slurm_version
    ) -> Image:
        logger.info(
            f"Get active Image by os-version: {os_version} and slurm_version {slurm_version}"
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
                        if properties.get("slurm_version" == slurm_version):
                            return image

        return backup_image

    def get_image(
        self,
        name_or_id: str,
        replace_inactive: bool = False,
        ignore_not_active: bool = False,
        replace_not_found: bool = False,
        ignore_not_found: bool = False,
        slurm_version: str = None,
    ) -> Image:
        logger.info(f"Get Image {name_or_id}")

        image: Image = self.openstack_connection.get_image(name_or_id=name_or_id)
        if image is None and not ignore_not_found:
            raise ImageNotFoundException(
                message=f"Image {name_or_id} not found!", name_or_id=name_or_id
            )
        elif image is None and replace_not_found:
            for version in ["20.04", "22.04", "2004", "2204"]:
                if version in name_or_id:
                    if slurm_version:
                        image = self.get_active_image_by_os_version_and_slurm_version(
                            os_version=version,
                            os_distro="ubuntu",
                            slurm_version=slurm_version,
                        )
                    else:
                        image = self.get_active_image_by_os_version(
                            os_version=version, os_distro="ubuntu"
                        )

        elif image and image.status != "active" and replace_inactive:
            image_os_version = image["os_version"]
            image_os_distro = image["os_distro"]
            if slurm_version:
                image = self.get_active_image_by_os_version_and_slurm_version(
                    os_version=image_os_version,
                    os_distro=image_os_distro,
                    slurm_version=slurm_version,
                )
            else:
                image = self.get_active_image_by_os_version(
                    os_version=image_os_version, os_distro=image_os_distro
                )
        elif image and image.status != "active" and not ignore_not_active:
            raise ImageNotFoundException(
                message=f"Image {name_or_id} found but not active!",
                name_or_id=name_or_id,
            )
        return image

    def create_snapshot(
        self,
        openstack_id: str,
        name: str,
        username: str,
        base_tags: list[str],
        description: str,
    ) -> str:
        logger.info(
            f"Create Snapshot from Instance {openstack_id} with name {name} for {username}"
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
            return snapshot_id

        except ConflictException as e:
            logger.exception(f"Create snapshot {openstack_id} failed!")

            raise OpenStackConflictException(message=e.message)
        except OpenStackCloudException as e:
            raise DefaultException(message=e.message)

    def delete_image(self, image_id: str) -> None:
        logger.info(f"Delete Image {image_id}")
        try:
            image = self.openstack_connection.get_image(image_id)
            if image is None:
                logger.exception(f"Image {image_id} not found!")
                raise ImageNotFoundException(
                    message=f"Image {image_id} not found!", name_or_id=image_id
                )
            self.openstack_connection.compute.delete_image(image_id)
        except Exception as e:
            logger.exception(f"Delete Image {image_id} failed!")
            raise DefaultException(message=str(e))

    def get_public_images(self) -> list[Image]:
        logger.info("Get public images")
        # Use compute.images() method with filters and extra_info
        images = self.openstack_connection.image.images(
            status="active", visibility="public"
        )
        # Use list comprehension to filter images based on tags
        images = [
            image for image in images if "tags" in image and len(image["tags"]) > 0
        ]
        image_names = [image.name for image in images]
        logger.info(f"Found public images - {image_names}")

        return images

    def get_private_images(self) -> list[Image]:
        logger.info("Get private images")
        # Use compute.images() method with filters and extra_info
        images = self.openstack_connection.image.images(
            status="active", visibility="private"
        )
        # Use list comprehension to filter images based on tags
        images = [
            image for image in images if "tags" in image and len(image["tags"]) > 0
        ]
        image_names = [image.name for image in images]
        logger.info(f"Found private images - {image_names}")

        return images

    def get_images(self) -> list[Image]:
        logger.info("Get Images")
        images = self.openstack_connection.image.images(status="active")
        images = [
            image for image in images if "tags" in image and len(image["tags"]) > 0
        ]
        image_names = [image.name for image in images]

        logger.info(f"Found  images - {image_names}")
        return images

    def get_calculation_values(self) -> dict[str, str]:
        logger.info("Get Client Calculation Values")
        logger.info(
            {
                "SSH_PORT_CALCULATION": self.SSH_PORT_CALCULATION,
                "UDP_PORT_CALCULATION": self.UDP_PORT_CALCULATION,
            }
        )
        return {
            "SSH_PORT_CALCULATION": self.SSH_PORT_CALCULATION,
            "UDP_PORT_CALCULATION": self.UDP_PORT_CALCULATION,
        }

    def get_gateway_ip(self) -> dict[str, str]:
        logger.info("Get Gateway IP")

        return {"gateway_ip": self.GATEWAY_IP}

    def create_mount_init_script(
        self,
        new_volumes: list[dict[str, str]] = None,  # type: ignore
        attach_volumes: list[dict[str, str]] = None,  # type: ignore
    ) -> str:
        logger.info(f"Create init script for volume ids:{new_volumes}")
        if not new_volumes and not attach_volumes:
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
            logger.info(attach_volumes)
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
        return text

    def create_or_get_default_ssh_security_group(self):
        logger.info("Get default SimpleVM SSH Security Group")
        sec = self.openstack_connection.get_security_group(
            name_or_id=self.DEFAULT_SECURITY_GROUP_NAME
        )
        if not sec:
            logger.info("Default SimpleVM SSH Security group not found... Creating")

            sec = self.create_security_group(
                name=self.DEFAULT_SECURITY_GROUP_NAME,
                ssh=True,
                description="Default SSH SimpleVM Security Group",
            )
        return sec

    def add_default_security_groups_to_server(self, openstack_id):
        logger.info(f"Add default Security Group Rule to vm -- {openstack_id}")
        server = self.get_server(openstack_id=openstack_id)
        sec_group = self._get_default_security_groups()
        self.openstack_connection.add_server_security_groups(
            server=server, security_groups=sec_group
        )

    def delete_security_group_rule(self, openstack_id):
        logger.info(f"Delete Security Group Rule -- {openstack_id}")
        deleted = self.openstack_connection.delete_security_group_rule(
            rule_id=openstack_id
        )
        logger.info(f"Delete Result -- {deleted}")
        if not deleted:
            raise DefaultException(
                message=f"Could not delete security group rule - {openstack_id}"
            )

    def open_port_range_for_vm_in_project(
        self, range_start, range_stop, openstack_id, ethertype="IPv4", protocol="TCP"
    ):
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
            return security_rule["id"]

        except ConflictException as e:
            logger.exception(
                f"Could not create security group rule for instance {openstack_id}"
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
        logger.info(f"Create new security group {name}")
        sec: SecurityGroup = self.openstack_connection.get_security_group(
            name_or_id=name
        )
        if sec:
            logger.info(f"Security group with name {name} already exists.")
            return sec
        new_security_group: SecurityGroup = (
            self.openstack_connection.create_security_group(
                name=name, description=description
            )
        )

        if udp:
            logger.info(
                "Add udp rule ports {}  to security group {}".format(udp_port, name)
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
            logger.info(f"Add ssh rule to security group {name}")

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
            logger.info(f"Add research env rule to security group {name}")

            self.openstack_connection.network.create_security_group_rule(
                direction=research_environment_metadata.direction,
                protocol=research_environment_metadata.protocol,
                port_range_max=research_environment_metadata.port,
                port_range_min=research_environment_metadata.port,
                security_group_id=new_security_group["id"],
                remote_group_id=self.FORC_SECURITY_GROUP_ID,
            )

        return new_security_group

    def is_security_group_in_use(self, security_group_id):
        logger.info(f"Checking if security group [{security_group_id}] is in use")

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
            return True

        # Otherwise, check if the security group is still associated with any ports
        ports = self.openstack_connection.network.ports(
            security_group_id=security_group_id
        )
        if ports:
            return True

        # Finally, check if the security group is still associated with any load balancers
        load_balancers = self.openstack_connection.network.load_balancers(
            security_group_id=security_group_id
        )
        if load_balancers:
            return True

        # If none of the above are true, the security group is no longer in use
        return False

    def get_research_environment_security_group(self, security_group_name: str):
        security_group = self.openstack_connection.get_security_group(
            name_or_id=security_group_name
        )
        if not security_group:
            raise DefaultException(
                message=f"Security Group {security_group_name} not found"
            )
        return security_group

    def get_or_create_research_environment_security_group(
        self, resenv_metadata: ResearchEnvironmentMetadata
    ):
        if not resenv_metadata.needs_forc_support:
            return None
        logger.info(
            f"Check if Security Group for resenv - {resenv_metadata.securitygroup_name} exists... "
        )
        sec = self.openstack_connection.get_security_group(
            name_or_id=resenv_metadata.securitygroup_name
        )
        if sec:
            logger.info(
                f"Security group {resenv_metadata.securitygroup_name} already exists."
            )
            return sec["id"]

        logger.info(
            f"No security Group for {resenv_metadata.securitygroup_name} exists. Creating.. "
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
        return new_security_group["id"]

    def get_security_group_id_by_name(self, security_group_name):
        logger.info(f"Get Security Group ID by name: {security_group_name}")
        sec = self.openstack_connection.get_security_group(
            name_or_id=security_group_name
        )
        logger.info(f"Got Keypair: {sec}")
        if not sec:
            raise SecurityGroupNotFoundException(
                message=f"SecurityGroup with name {security_group_name} not found!"
            )
        return sec["id"]

    def get_or_create_vm_security_group(self, openstack_id):
        logger.info(f"Check if Security Group for vm - [{openstack_id}] exists... ")
        sec = self.openstack_connection.get_security_group(name_or_id=openstack_id)
        if sec:
            logger.info(f"Security group [{openstack_id}]  already exists.")
            return sec["id"]
        logger.info(f"No security Group for [{openstack_id}]  exists. Creating.. ")
        new_security_group = self.openstack_connection.create_security_group(
            name=openstack_id, description=f"VM ID: {openstack_id} Security Group"
        )
        return new_security_group["id"]

    def get_or_create_project_security_group(self, project_name, project_id):
        security_group_name = f"{project_name}_{project_id}"

        with lock_access:
            if security_group_name not in lock_dict:
                lock_dict[security_group_name] = threading.Lock()
            lock = lock_dict[security_group_name]

        with lock:
            logger.info(
                f"Check if Security Group for project - [{project_name}-{project_id}] exists... "
            )
            sec = self.openstack_connection.get_security_group(
                name_or_id=security_group_name
            )
            if sec:
                logger.info(
                    f"Security group [{project_name}-{project_id}]  already exists."
                )
                return sec["id"]

            logger.info(
                f"No security Group for [{project_name}-{project_id}]  exists. Creating.. "
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
            return new_security_group["id"]

    def get_limits(self) -> dict[str, str]:
        logger.info("Get Limits")
        # Retrieve compute and volume limits
        compute_limits = self.openstack_connection.get_compute_limits()
        volume_limits = self.openstack_connection.get_volume_limits()["absolute"]

        # Merge compute and volume limits into a single dictionary
        limits = {**compute_limits, **volume_limits}
        return {
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

    def exist_server(self, name: str) -> bool:
        if self.openstack_connection.compute.find_server(name) is not None:
            return True
        else:
            return False

    def set_server_metadata(self, openstack_id: str, metadata) -> None:
        try:
            logger.info(f"Set Server Metadata: {openstack_id} --> {metadata}")
            server: Server = self.get_server(openstack_id)
            self.openstack_connection.compute.set_server_metadata(server, metadata)
        except OpenStackCloudException as e:
            raise DefaultException(
                message=f"Error when setting server {openstack_id} metadata --> {metadata}! - {e}"
            )

    def get_server_by_unique_name(self, unique_name: str) -> Server:
        logger.info(f"Get Server by unique_name: {unique_name}")

        filters = {"name": unique_name}

        servers = list(self.openstack_connection.list_servers(filters=filters))
        logger.info(f"Found {len(servers)} with name {unique_name}")
        if len(servers) == 1:
            server = list(servers)[0]
            logger.info(server)
            if server.vm_state == VmStates.ACTIVE.value:
                ssh_port, udp_port = self._calculate_vm_ports(server=server)

                if not self.netcat(host=self.GATEWAY_IP, port=ssh_port):
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
            logger.exception(f"Instance {unique_name} not found")
            raise ServerNotFoundException(
                message=f"Instance {unique_name} not found",
                name_or_id=unique_name,
            )
        else:
            raise DefaultException(
                message=f"Error when getting server {unique_name}! - multiple entries"
            )

    def get_server(self, openstack_id: str) -> Server:
        try:
            logger.info(f"Get Server by id: {openstack_id}")
            server: Server = self.openstack_connection.get_server_by_id(id=openstack_id)
            if server is None:
                logger.exception(f"Instance {openstack_id} not found")
                raise ServerNotFoundException(
                    message=f"Instance {openstack_id} not found",
                    name_or_id=openstack_id,
                )
            if server.vm_state == VmStates.ACTIVE.value:
                ssh_port, udp_port = self._calculate_vm_ports(server=server)

                if not self.netcat(host=self.GATEWAY_IP, port=ssh_port):
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
        except OpenStackCloudException as e:
            raise DefaultException(
                message=f"Error when getting server {openstack_id}! - {e}"
            )

    def resume_server(self, openstack_id: str) -> None:
        logger.info(f"Resume Server {openstack_id}")
        try:
            server = self.get_server(openstack_id=openstack_id)
            self.openstack_connection.compute.start_server(server)

        except ConflictException as e:
            logger.exception(f"Resume Server {openstack_id} failed!")
            raise OpenStackConflictException(message=str(e))

    def reboot_hard_server(self, openstack_id: str) -> None:
        return self.reboot_server(openstack_id=openstack_id, reboot_type="HARD")

    def reboot_soft_server(self, openstack_id: str) -> None:
        return self.reboot_server(openstack_id=openstack_id, reboot_type="SOFT")

    def reboot_server(self, openstack_id: str, reboot_type: str) -> None:
        logger.info(f"Reboot Server {openstack_id} - {reboot_type}")
        server = self.get_server(openstack_id=openstack_id)
        try:
            self.openstack_connection.compute.reboot_server(server, reboot_type)
        except ConflictException as e:
            logger.exception(f"Reboot Server {openstack_id} failed!")

            raise OpenStackConflictException(message=str(e))

    def stop_server(self, openstack_id: str) -> None:
        logger.info(f"Stop Server {openstack_id}")
        server = self.get_server(openstack_id=openstack_id)
        try:
            self.openstack_connection.compute.stop_server(server)

        except ConflictException as e:
            logger.exception(f"Stop Server {openstack_id} failed!")
            raise OpenStackConflictException(message=e.message)

    def _remove_security_groups_from_server(self, server: Server) -> None:
        security_groups = server.security_groups

        if security_groups is not None:
            for sg in security_groups:
                sec = self.openstack_connection.get_security_group(
                    name_or_id=sg["name"]
                )
                logger.info(f"Remove security group {sec.id} from server {server.id}")
                self.openstack_connection.compute.remove_security_group_from_server(
                    server=server, security_group=sec
                )

                if (
                    sg["name"] != self.DEFAULT_SECURITY_GROUP_NAME
                    and ("bibigrid" not in sec.name or "master" not in server.name)
                    and not self.is_security_group_in_use(security_group_id=sec.id)
                ):
                    logger.info(f"Delete security group {sec}")
                    try:
                        self.openstack_connection.delete_security_group(sec)
                    except ResourceNotFound:
                        logger.info(
                            f"Could not remoeve security group {sec.id} from server"
                        )

    def _validate_server_for_deletion(self, server: Server) -> None:
        task_state = server.task_state
        if task_state in [
            "image_snapshot",
            "image_pending_upload",
            "image_uploading",
        ]:
            raise ConflictException("task_state in image creating")

    def delete_server(self, openstack_id: str) -> None:
        logger.info(f"Delete Server {openstack_id}")
        try:
            server: Server = self.get_server(openstack_id=openstack_id)
            if not server:
                logger.error(f"Instance {openstack_id} not found")
                raise ServerNotFoundException(
                    message=f"Instance {openstack_id} not found",
                    name_or_id=openstack_id,
                )

            self._validate_server_for_deletion(server=server)
            self._remove_security_groups_from_server(server=server)
            self.openstack_connection.compute.delete_server(server.id, force=True)

        except ConflictException as e:
            logger.error(f"Delete Server {openstack_id} failed!")

            raise OpenStackConflictException(message=e.message)
        
    def rescue_server(self, openstack_id: str, admin_pass: str = None, image_ref: str = None) -> None:
        logger.info(f"Rescue Server {openstack_id}")
        try:
            server: Server = self.get_server(openstack_id=openstack_id)
            if not server:
                logger.error(f"Instance {openstack_id} not found")
                raise ServerNotFoundException(
                    message=f"Instance {openstack_id} not found",
                    name_or_id=openstack_id,
                )
            self.openstack_connection.compute.rescue_server(server.id, admin_pass, image_ref)

        except ConflictException as e:
            logger.error(f"Rescue Server {openstack_id} failed!")

            raise OpenStackConflictException(message=e.message)    

    def _calculate_vm_ports(self, server: Server):
        fixed_ip = server.private_v4
        base_port = int(fixed_ip.split(".")[-1])  # noqa F841
        subnet_port = int(fixed_ip.split(".")[-2])  # noqa F841

        x = sympy.symbols("x")
        y = sympy.symbols("y")
        ssh_port = int(
            sympy.sympify(self.SSH_PORT_CALCULATION).evalf(
                subs={x: base_port, y: subnet_port}
            )
        )
        udp_port = int(
            sympy.sympify(self.UDP_PORT_CALCULATION).evalf(
                subs={x: base_port, y: subnet_port}
            )
        )
        return ssh_port, udp_port

    def get_vm_ports(self, openstack_id: str) -> dict[str, str]:
        logger.info(f"Get IP and PORT for server {openstack_id}")
        server = self.get_server(openstack_id=openstack_id)
        ssh_port, udp_port = self._calculate_vm_ports(server=server)

        return {"port": str(ssh_port), "udp": str(udp_port)}

    def create_userdata(
        self,
        volume_ids_path_new: list[dict[str, str]],
        volume_ids_path_attach: list[dict[str, str]],
        additional_keys: list[str],
        metadata_token: str = None,
        metadata_endpoint: str = None,
    ) -> str:
        unlock_ubuntu_user_script = "#!/bin/bash\npasswd -u ubuntu\n"
        unlock_ubuntu_user_script_encoded = encodeutils.safe_encode(
            unlock_ubuntu_user_script.encode("utf-8")
        )
        init_script = unlock_ubuntu_user_script_encoded
        logger.info(
            f"Metadata token {metadata_token} | Metadata Endpoint {metadata_endpoint}"
        )
        if additional_keys:
            add_key_script = self.create_add_keys_script(keys=additional_keys)
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
        additional_keys: Union[list[str], None] = None,
        additional_security_group_ids: Union[list[str], None] = None,
        slurm_version: str = None,
        metadata_token: str = None,
        metadata_endpoint: str = None,
    ) -> str:
        logger.info(f"Start Server {servername}")

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
            logger.info(f"Key name {key_name}")
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
                additional_keys=additional_keys,
                metadata_token=metadata_token,
                metadata_endpoint=metadata_endpoint,
            )
            logger.info(f"Starting Server {servername}...")
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
            logger.info(f"Started Server {servername} with id - {openstack_id}")
            self.delete_keypair(key_name=key_name)

            return openstack_id

        except OpenStackCloudException as e:
            if key_name:
                self.delete_keypair(key_name=key_name)

            logger.exception(f"Start Server {servername} error")
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
        logger.info(f"volume ids {volume_ids}")

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
        additional_keys: list[str] = None,  # type: ignore
        additional_security_group_ids=None,  # type: ignore
        metadata_token: str = None,
        metadata_endpoint: str = None,
    ) -> tuple[str, str]:
        logger.info(f"Start Server {servername}")

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
                additional_keys=additional_keys,
                metadata_token=metadata_token,
                metadata_endpoint=metadata_endpoint,
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

            return openstack_id, private_key

        except OpenStackCloudException as e:
            if key_name:
                self.delete_keypair(key_name=key_name)

            logger.exception(f"Start Server {servername} error")
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
        logger.info(f"Setting up {security_group_name} security group for {server_id}")
        server: Server = self.get_server(openstack_id=server_id)
        security_group: SecurityGroup = self.get_research_environment_security_group(
            security_group_name=security_group_name
        )
        if self._is_security_group_already_added_to_server(
            server=server, security_group_name=security_group.name
        ):
            return
        self.openstack_connection.compute.add_security_group_to_server(
            server=server, security_group=security_group
        )

    def add_metadata_to_server(self, server_id, metadata):
        server = self.get_server(openstack_id=server_id)

        self.openstack_connection.compute.set_server_metadata(server, **metadata)

    def _is_security_group_already_added_to_server(
        self, server: Server, security_group_name: str
    ):
        server_security_groups = self.openstack_connection.list_server_security_groups(
            server
        )

        for sg in server_security_groups:
            if sg["name"] == security_group_name:
                logger.info(
                    f" Security group with name {security_group_name} already added to server."
                )
                return True
        return False

    def add_udp_security_group(self, server_id):
        logger.info(f"Setting up UDP security group for {server_id}")
        server = self.get_server(openstack_id=server_id)
        sec_name = server.name + "_udp"
        existing_sec = self.openstack_connection.get_security_group(name_or_id=sec_name)
        if existing_sec:
            logger.info(f"UDP Security group with name {sec_name} already exists.")
            if self._is_security_group_already_added_to_server(
                server=server, security_group_name=sec_name
            ):
                logger.info(
                    f"UDP Security group with name {sec_name} already added to server."
                )

                return

            self.openstack_connection.compute.add_security_group_to_server(
                server=server_id, security_group=existing_sec
            )

            return
        vm_ports = self.get_vm_ports(openstack_id=server_id)
        udp_port = vm_ports["udp"]

        security_group = self.create_security_group(
            name=sec_name,
            udp_port=int(udp_port),
            udp=True,
            ssh=False,
            description="UDP",
        )
        logger.info(f"Add security group {security_group.id} to server {server_id}")
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
        logger.info(f"Add machine to {cluster_id}")
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
        logger.info(f"Created cluster machine:{server['id']}")
        server_id: str = server["id"]
        return server_id
