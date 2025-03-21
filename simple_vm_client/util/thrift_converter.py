from __future__ import annotations

from openstack.block_storage.v2.snapshot import Snapshot as OpenStack_Snapshot
from openstack.block_storage.v2.volume import Volume as OpenStack_Volume
from openstack.compute.v2.flavor import Flavor as OpenStack_Flavor
from openstack.compute.v2.image import Image as OpenStack_Image
from openstack.compute.v2.server import Server as OpenStack_Server

from simple_vm_client.ttypes import VM, Flavor, Image, Snapshot, Volume
from simple_vm_client.util.logger import setup_custom_logger
from simple_vm_client.util.state_enums import VmStates

logger = setup_custom_logger(__name__)


def os_to_thrift_image(openstack_image: OpenStack_Image) -> Image:
    properties = openstack_image.get("properties")
    if not properties:
        properties = {}
    image_type = properties.get("image_type", "image")
    slurm_version = properties.get("slurm_version", "")
    image = Image(
        name=openstack_image.name,
        min_disk=openstack_image.min_disk,
        min_ram=openstack_image.min_ram,
        status=openstack_image.status,
        created_at=openstack_image.created_at,
        updated_at=openstack_image.updated_at,
        os_version=openstack_image.get("os_version", ""),
        os_distro=openstack_image.get("os_distro", ""),
        slurm_version=openstack_image.get("slurm_version", slurm_version),
        title=properties.get("title", ""),
        openstack_id=openstack_image.id,
        description=properties.get("description", ""),
        tags=openstack_image.get("tags", []),
        is_snapshot=image_type == "snapshot",
    )
    return image


def os_to_thrift_images(openstack_images: list[OpenStack_Image]) -> list[Image]:
    return [os_to_thrift_image(openstack_image=img) for img in openstack_images]


def os_to_thrift_flavor(openstack_flavor: OpenStack_Flavor) -> Flavor:
    flavor = Flavor(
        vcpus=openstack_flavor.vcpus,
        ram=openstack_flavor.ram,
        disk=openstack_flavor.disk,
        name=openstack_flavor.name or openstack_flavor.get("original_name", "N/A"),
        ephemeral_disk=openstack_flavor.ephemeral,
        description=openstack_flavor.description or "",
    )
    return flavor


def os_to_thrift_flavors(openstack_flavors: list[OpenStack_Flavor]) -> list[Flavor]:
    return [
        os_to_thrift_flavor(openstack_flavor=flavor) for flavor in openstack_flavors
    ]


def os_to_thrift_volume(openstack_volume: OpenStack_Volume) -> Volume:
    if not openstack_volume:
        return Volume(status=VmStates.NOT_FOUND)
    attachments = openstack_volume.attachments
    device = None
    server_id = None
    if attachments:
        try:
            device = openstack_volume.attachments[0]["device"]
            server_id = openstack_volume.attachments[0]["server_id"]
        except Exception as e:
            logger.error(f"Exception on os_to_thrift_volume:\n{e}")
    volume = Volume(
        status=openstack_volume.status,
        id=openstack_volume.id,
        name=openstack_volume.name,
        description=openstack_volume.description,
        created_at=openstack_volume.created_at,
        device=device,
        size=openstack_volume.size,
        server_id=server_id,
    )
    return volume


def os_to_thrift_volume_snapshot(openstack_snapshot: OpenStack_Snapshot) -> Snapshot:
    if not openstack_snapshot:
        return Snapshot(status=VmStates.NOT_FOUND)
    snapshot = Snapshot(
        status=openstack_snapshot.status,
        id=openstack_snapshot.id,
        name=openstack_snapshot.name,
        description=openstack_snapshot.description,
        created_at=openstack_snapshot.created_at,
        size=openstack_snapshot.size,
        volume_id=openstack_snapshot.volume_id,
    )
    return snapshot


def os_to_thrift_server(openstack_server: OpenStack_Server) -> VM:
    if not openstack_server:
        logger.info("Openstack server not found")

        return VM(vm_state=VmStates.NOT_FOUND)
    fixed_ip = ""
    floating_ip = ""
    if openstack_server.flavor:

        flavor = os_to_thrift_flavor(openstack_flavor=openstack_server.flavor)
    else:
        flavor = None
    if openstack_server.image:
        image = os_to_thrift_image(openstack_image=openstack_server.image)
    else:
        image = None
    for values in openstack_server.addresses.values():
        for address in values:
            if address["OS-EXT-IPS:type"] == "floating":
                floating_ip = address["addr"]
            elif address["OS-EXT-IPS:type"] == "fixed":
                fixed_ip = address["addr"]
    server = VM(
        flavor=flavor,
        image=image,
        metadata=openstack_server.metadata,
        project_id=openstack_server.project_id,
        keyname=openstack_server.key_name,
        openstack_id=openstack_server.id,
        name=openstack_server.name,
        created_at=openstack_server.created_at,
        task_state=openstack_server.task_state or "",
        vm_state=openstack_server.vm_state,
        fixed_ip=fixed_ip,
        floating_ip=floating_ip,
    )

    return server


def os_to_thrift_servers(openstack_servers: list[OpenStack_Server]) -> list[VM]:
    return [
        os_to_thrift_server(openstack_server=openstack_server)
        for openstack_server in openstack_servers
    ]


def thrift_to_dict(obj):
    if hasattr(obj, "thrift_spec") and obj.thrift_spec is not None:
        result = {}
        for field in obj.thrift_spec:
            if field is not None:
                field_id, field_type, field_name, *rest = field
                value = getattr(obj, field_name, None)
                result[field_name] = thrift_to_dict(value)
        return result
    elif isinstance(obj, list):
        return [thrift_to_dict(item) for item in obj]
    elif isinstance(obj, dict):
        return {
            thrift_to_dict(key): thrift_to_dict(value) for key, value in obj.items()
        }
    else:
        return obj
