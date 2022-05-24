from enum import Enum


class VmTaskStates(Enum):
    # OS task states
    SCHEDULING = 'scheduling'
    BLOCK_DEVICE_MAPPING = 'block_device_mapping'
    NETWORKING = 'networking'
    SPAWNING = 'spawning'
    IMAGE_SNAPSHOT = 'image_snapshot'
    IMAGE_SNAPSHOT_PENDING = 'image_snapshot_pending'
    IMAGE_PENDING_UPLOAD = 'image_pending_upload'
    IMAGE_UPLOADING = 'image_uploading'
    IMAGE_BACKUP = 'image_backup'
    UPDATING_PASSWORD = 'updating_password'
    RESIZE_PREP = 'resize_prep'
    RESIZE_MIGRATING = 'resize_migrating'
    RESIZE_MIGRATED = 'resize_migrated'
    RESIZE_FINISH = 'resize_finish'
    RESIZE_REVERTING = 'resize_reverting'
    RESIZE_CONFIRMING = 'resize_confirming'
    REBOOTING = 'rebooting'
    REBOOT_PENDING = 'reboot_pending'
    REBOOT_STARTED = 'reboot_started'
    REBOOTING_HARD = 'rebooting_hard'
    REBOOT_PENDING_HARD = 'reboot_pending_hard'
    REBOOT_STARTED_HARD = 'reboot_started_hard'
    PAUSING = 'pausing'
    UNPAUSING = 'unpausing'
    SUSPENDING = 'suspending'
    RESUMING = 'resuming'
    POWERING_OFF = 'powering-off'
    POWERING_ON = 'powering-on'
    RESCUING = 'rescuing'
    UNRESCUING = 'unrescuing'
    REBUILDING = 'rebuilding'
    REBUILD_BLOCK_DEVICE_MAPPING = "rebuild_block_device_mapping"
    REBUILD_SPAWNING = 'rebuild_spawning'
    MIGRATING = "migrating"
    DELETING = 'deleting'
    SOFT_DELETING = 'soft-deleting'
    RESTORING = 'restoring'
    SHELVING = 'shelving'
    SHELVING_IMAGE_PENDING_UPLOAD = 'shelving_image_pending_upload'
    SHELVING_IMAGE_UPLOADING = 'shelving_image_uploading'
    SHELVING_OFFLOADING = 'shelving_offloading'
    UNSHELVING = 'unshelving'

    # Custom task states
    PREPARE_PLAYBOOK_BUILD = "prepare_playbook_build"
    PLAYBOOK_SUCCESSFUL = "playbook_successful"
    PLAYBOOK_FAILED = "playbook_failed"
    CHECKING_SSH_CONNECTION = "checking_ssh_connection"
    BUILD_PLAYBOOK = "building_playbook"
    CHECKING_STATUS = "checking_status"


class VmStates(Enum):
    # OS vm states
    ACTIVE = 'active'
    BUILDING = 'building'
    PAUSED = 'paused'
    SUSPENDED = 'suspended'
    STOPPED = 'stopped'
    RESCUED = 'rescued'
    RESIZED = 'resized'
    SOFT_DELETED = 'soft-delete'
    DELETED = 'deleted'
    ERROR = 'error'
    SHELVED = 'shelved'
    SHELVED_OFFLOADED = 'shelved_offloaded'

    # Custom vm states
    NOT_FOUND = "not_found"
    CREATION_FAILED = "creation_failed"
    CLIENT_OFFLINE = "client_offline"
    PLANNED = "planned"
    PORT_CLOSED = "port_closed"
