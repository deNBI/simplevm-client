import json
import os
import time
import urllib

import redis
import requests
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from openstack.compute.v2.server import Server

from simple_vm_client.ttypes import (
    Backend,
    BackendNotFoundException,
    CondaPackage,
    DefaultException,
    PlaybookNotFoundException,
    PlaybookResult,
    TemplateNotFoundException,
)
from simple_vm_client.util.logger import setup_custom_logger
from simple_vm_client.util.state_enums import VmTaskStates

from .playbook.playbook import Playbook
from .template.template import ResearchEnvironmentMetadata, Template

logger = setup_custom_logger(__name__)
BIOCONDA = "bioconda"


class ForcConnector:
    active_playbooks: dict[str, Playbook] = {}

    def __init__(self, config_file: str):
        logger.info("Initializing Forc Connector")

        self.FORC_BACKEND_URL: str = ""  # type: ignore
        self.FORC_ACCESS_URL: str = ""  # type: ignore
        self.GITHUB_PLAYBOOKS_REPO: str = ""  # type: ignore
        self.REDIS_HOST: str = ""  # type: ignore
        self.REDIS_PORT: int = None  # type: ignore
        self.FORC_API_KEY: str = ""
        self.redis_pool: redis.ConnectionPool = None  # type: ignore
        self.redis_connection: redis.Redis.connection_pool = None
        self.load_config(config_file=config_file)
        self.connect_to_redis()
        self.template = Template(
            github_playbook_repo=self.GITHUB_PLAYBOOKS_REPO,
            forc_backend_url=self.FORC_BACKEND_URL,
            forc_api_key=self.FORC_API_KEY,
        )
        self.start_template_update_scheduler()

    def load_config(self, config_file: str) -> None:
        logger.info("Load config file: FORC")
        with open(config_file, "r") as ymlfile:
            cfg = yaml.load(ymlfile, Loader=yaml.SafeLoader)
            # Check if "bibigrid" key is present in the loaded YAML
            self.REDIS_HOST = cfg["redis"]["host"]
            self.REDIS_PORT = cfg["redis"]["port"]
            if "forc" not in cfg:
                # Optionally, you can log a message or take other actions here
                logger.info("Forc configuration not found. Skipping.")
                return
            if not cfg["forc"].get("activated", True):
                logger.info("Forc Config available but deactivated. Skipping..")
                return
            self.FORC_BACKEND_URL = cfg["forc"]["forc_backend_url"]
            self.FORC_ACCESS_URL = cfg["forc"]["forc_access_url"]
            self.GITHUB_PLAYBOOKS_REPO = cfg["forc"]["github_playbooks_repo"]
            self.UPDATE_TEMPLATES_SCHEDULE = cfg["forc"].get(
                "update_templates_schedule", 12
            )

        self.load_env()

    def update_templates(self):
        max_retries = 5
        retry_interval = 900  # 15 minutes in seconds

        for _ in range(max_retries):
            if self.is_any_playbook_active():
                logger.info(
                    "Currently an active playbook is running, delaying update template"
                )
                time.sleep(retry_interval)
            else:
                break

        if not self.is_any_playbook_active():
            logger.info("No active playbook --start update \n\n\n\n")
            self.template.update_playbooks()
        else:
            logger.error(
                "Failed to update templates after {} retries".format(max_retries)
            )

    def start_template_update_scheduler(self):
        logger.info(
            f"Setting Update Playbook Schedule to: every {self.UPDATE_TEMPLATES_SCHEDULE} hours"
        )
        schedule_in_seconds = self.UPDATE_TEMPLATES_SCHEDULE * 60 * 60

        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(
            self.update_templates,
            "interval",
            seconds=int(schedule_in_seconds),
            coalesce=True,
        )
        self.scheduler.start()

    def connect_to_redis(self) -> None:
        logger.info("Connect to redis")
        self.redis_pool = redis.ConnectionPool(
            host=self.REDIS_HOST, port=self.REDIS_PORT
        )

        self.redis_connection = redis.Redis(
            connection_pool=self.redis_pool,
        )
        if self.redis_connection.ping():
            logger.info("Redis connection created!")
        else:
            logger.error("Could not connect to redis!")

    def get_users_from_backend(self, backend_id: str) -> list[str]:
        logger.info(f"Get users from backend {backend_id}")
        get_url = f"{self.FORC_BACKEND_URL}users/{backend_id}"
        try:
            response = requests.get(
                get_url,
                timeout=(30, 30),
                headers={"X-API-KEY": self.FORC_API_KEY},
            )
            if response.status_code == 401:
                return ["Error: 401"]
            else:
                return [response.json()]
        except requests.Timeout as e:
            logger.info(msg=f"Get users for backend timed out. {e}")
            return []

    def delete_user_from_backend(self, backend_id: str, user_id: str) -> dict[str, str]:
        logger.info(f"Delete user {user_id} from backend {backend_id}")
        delete_url = f"{self.FORC_BACKEND_URL}users/{backend_id}"
        user_info = {
            "user": user_id,
        }
        try:
            response = requests.delete(
                delete_url,
                json=user_info,
                timeout=(30, 30),
                headers={"X-API-KEY": self.FORC_API_KEY},
            )
            data: dict[str, str] = response.json()
            return data
        except requests.Timeout as e:
            logger.info(msg=f"Delete user from backend timed out. {e}")
            return {"Error": "Timeout."}
        except Exception as e:
            logger.exception(e)
            raise BackendNotFoundException(message=str(e), name_or_id=backend_id)

    def delete_backend(self, backend_id: str) -> None:
        logger.info(f"Delete Backend {backend_id}")
        delete_url = f"{self.FORC_BACKEND_URL}backends/{backend_id}"
        try:
            response = requests.delete(
                delete_url,
                timeout=(30, 30),
                headers={"X-API-KEY": self.FORC_API_KEY},
            )
            if response.status_code:
                if response.status_code == 404 or response.status_code == 500:
                    try:
                        response_data = response.json()
                        raise BackendNotFoundException(
                            message=str(json.dumps(response_data)),
                            name_or_id=str(backend_id),
                        )
                    except ValueError:
                        logger.exception(str(response.content))
                        raise BackendNotFoundException(
                            message=str(response.content), name_or_id=str(backend_id)
                        )

        except requests.Timeout:
            logger.exception(msg="delete_backend timed out")
            raise DefaultException(message="delete_backend timed out")

    def add_user_to_backend(self, backend_id: str, user_id: str) -> dict[str, str]:
        logger.info(f"Add User {user_id} to backend {backend_id}")
        post_url = f"{self.FORC_BACKEND_URL}users/{backend_id}"
        user_info = {
            "user": user_id,
        }

        try:
            response = requests.post(
                post_url,
                json=user_info,
                timeout=(30, 30),
                headers={
                    "X-API-KEY": self.FORC_API_KEY,
                },
            )
            try:
                data: dict[str, str] = response.json()
            except Exception as e:
                logger.exception(e)
                raise BackendNotFoundException(message=str(e), name_or_id=backend_id)
            return data
        except requests.Timeout as e:
            logger.info(msg=f"add user to backend timed out. {e}")
            return {"Error": "Timeout."}
        except Exception as e:
            logger.exception(e)
            raise BackendNotFoundException(message=str(e), name_or_id=backend_id)

    def create_backend(
        self, owner: str, user_key_url: str, template: str, upstream_url: str
    ) -> Backend:
        logger.info(
            f"Create Backend - [Owner:{owner}, user_key_url:{user_key_url}, template:{template}, upstream_url:{upstream_url}"
        )

        template_version = self.template.get_template_version_for(template=template)
        if not template_version:
            logger.warning(
                f"No suitable template version found for {template}. Aborting backend creation!"
            )
            raise TemplateNotFoundException(
                message=f"No suitable template version found for {template}. Aborting backend creation!",
                template=template,
            )

        post_url = f"{self.FORC_BACKEND_URL}backends"
        backend_info = {
            "owner": owner,
            "user_key_url": user_key_url,
            "template": template,
            "template_version": template_version,
            "upstream_url": upstream_url,
        }

        try:
            response = requests.post(
                post_url,
                json=backend_info,
                timeout=(30, 30),
                headers={"X-API-KEY": self.FORC_API_KEY},
            )

            data = response.json()
            logger.info(f"Backend created {data}")

            new_backend = Backend(
                id=int(data["id"]),
                owner=data["owner"],
                location_url=data["location_url"],
                template=data["template"],
                template_version=data["template_version"],
            )
            return new_backend

        except requests.Timeout as e:
            logger.info(f"create_backend timed out. {e}")
            raise DefaultException(message=e)

        except Exception as e:
            logger.exception(e)
            raise DefaultException(message=e)

    def get_backends(self) -> list[Backend]:
        logger.info("Get Backends")
        get_url = f"{self.FORC_BACKEND_URL}backends"
        try:
            response = requests.get(
                get_url,
                timeout=(30, 30),
                headers={"X-API-KEY": self.FORC_API_KEY},
            )
            if response.status_code == 401:
                raise DefaultException(message=str(response.json()))
            else:
                backends = []
                for data in response.json():
                    backends.append(
                        Backend(
                            id=data["id"],
                            owner=data["owner"],
                            location_url=data["location_url"],
                            template=data["template"],
                            template_version=data["template_version"],
                        )
                    )
                return backends
        except requests.Timeout as e:
            logger.exception(msg=f"create_backend timed out. {e}")
            raise DefaultException(message=str(e))

    def get_backends_by_template(self, template: str) -> list[Backend]:
        logger.info(f"Get Backends by template: {template}")
        get_url = f"{self.FORC_BACKEND_URL}backends/byTemplate/{template}"
        try:
            response = requests.get(
                get_url,
                timeout=(30, 30),
                headers={"X-API-KEY": self.FORC_API_KEY},
            )
            if response.status_code == 401:
                raise DefaultException(message=str(response.json()))

            else:
                backends = []
                for data in response.json():
                    backends.append(
                        Backend(
                            id=data["id"],
                            owner=data["owner"],
                            location_url=data["location_url"],
                            template=data["template"],
                            template_version=data["template_version"],
                        )
                    )
                return backends
        except requests.Timeout as e:
            logger.exception(msg=f"create_backend timed out. {e}")
            raise DefaultException(message=str(e))

    def get_backend_by_id(self, id: str) -> Backend:
        logger.info(f"Get backends by id: {id}")
        get_url = f"{self.FORC_BACKEND_URL}backends/{id}"
        try:
            response = requests.get(
                get_url,
                timeout=(30, 30),
                headers={"X-API-KEY": self.FORC_API_KEY},
            )
            try:
                data = response.json()
            except Exception as e:
                logger.exception(e)
                raise DefaultException(message=str(e))

            return Backend(
                id=data["id"],
                owner=data["owner"],
                location_url=data["location_url"],
                template=data["template"],
                template_version=data["template_version"],
            )
        except requests.Timeout as e:
            logger.exception(msg=f"create_backend timed out. {e}")
            raise DefaultException(message=str(e))

    def get_backends_by_owner(self, owner: str) -> list[Backend]:
        logger.info(f"Get backends by owner: {owner}")
        get_url = f"{self.FORC_BACKEND_URL}backends/byOwner/{owner}"
        try:
            response = requests.get(
                get_url,
                timeout=(30, 30),
                headers={"X-API-KEY": self.FORC_API_KEY},
            )
            if response.status_code == 401:
                raise DefaultException(message=str(response.json()))

            else:
                backends = []
                for data in response.json():
                    backends.append(
                        Backend(
                            id=data["id"],
                            owner=data["owner"],
                            location_url=data["location_url"],
                            template=data["template"],
                            template_version=data["template_version"],
                        )
                    )
                return backends
        except requests.Timeout as e:
            logger.exception(msg=f"create_backend timed out. {e}")
            raise DefaultException(message=str(e))

    def has_forc(self) -> bool:
        logger.info("Check has forc")
        return self.FORC_BACKEND_URL is not None

    def get_forc_backend_url(self) -> str:
        logger.info("Get Forc Url")
        return self.FORC_BACKEND_URL

    def get_forc_access_url(self) -> str:
        logger.info("Get Forc Access Url")
        return self.FORC_ACCESS_URL

    def load_env(self) -> None:
        logger.info("Load env: FORC")
        self.FORC_API_KEY = os.environ.get("FORC_API_KEY", None)

    def is_any_playbook_active(self) -> bool:
        for openstack_id in ForcConnector.active_playbooks:
            if (
                self.redis_connection.exists(openstack_id) == 1
                and openstack_id in ForcConnector.active_playbooks
            ):
                return True
        return False

    def is_playbook_active(self, openstack_id: str) -> bool:
        return (
            self.redis_connection.exists(openstack_id) == 1
            and openstack_id in ForcConnector.active_playbooks
        )

    def get_playbook_logs(self, openstack_id: str) -> PlaybookResult:
        logger.warning(f"Get Playbook logs {openstack_id}")

        if self.is_playbook_active(openstack_id):
            playbook = ForcConnector.active_playbooks[openstack_id]
            status, stdout, stderr = playbook.get_logs()
            logger.warning(f" Playbook logs {openstack_id} status: {status}")

            playbook.cleanup(openstack_id)
            ForcConnector.active_playbooks.pop(openstack_id)

            return PlaybookResult(status=status, stdout=stdout, stderr=stderr)
        else:
            raise PlaybookNotFoundException(
                message=f"No active Playbook found for {openstack_id}!",
                name_or_id=openstack_id,
            )

    def set_vm_wait_for_playbook(
        self, openstack_id: str, private_key: str, name: str
    ) -> None:
        logger.info(
            f"Set vm {openstack_id}: {VmTaskStates.PREPARE_PLAYBOOK_BUILD.value} "
        )
        self.redis_connection.hset(
            name=openstack_id,
            mapping=dict(
                key=private_key,
                name=name,
                status=VmTaskStates.PREPARE_PLAYBOOK_BUILD.value,
            ),
        )

    def get_playbook_status(self, server: Server) -> Server:
        openstack_id = server.id

        if self.redis_connection.exists(openstack_id) == 1:
            logger.info(f"Get VM {openstack_id} Playbook status")

            if openstack_id in ForcConnector.active_playbooks:
                logger.info(ForcConnector.active_playbooks)
                playbook = ForcConnector.active_playbooks[openstack_id]
                playbook.check_status(openstack_id)
            status = self.redis_connection.hget(openstack_id, "status").decode("utf-8")
            logger.info(f"VM {openstack_id} Playbook status -> {status}")

            # Server needs to have no task state(so port is not closed)
            if (
                status == VmTaskStates.PREPARE_PLAYBOOK_BUILD.value
                and not server.task_state
            ):
                server.task_state = VmTaskStates.PREPARE_PLAYBOOK_BUILD.value
            elif status == VmTaskStates.BUILD_PLAYBOOK.value:
                server.task_state = VmTaskStates.BUILD_PLAYBOOK.value
            elif status == VmTaskStates.PLAYBOOK_FAILED.value:
                server.task_state = VmTaskStates.PLAYBOOK_FAILED.value
            elif status == VmTaskStates.PLAYBOOK_SUCCESSFUL.value:
                server.task_state = VmTaskStates.PLAYBOOK_SUCCESSFUL.value
        return server

    def get_metadata_by_research_environment(
        self, research_environment: str
    ) -> ResearchEnvironmentMetadata:
        logger.info(f"Get Metadata Research environment: {research_environment}")
        if research_environment in self.template.loaded_research_env_metadata:
            resenv_metadata = self.template.loaded_research_env_metadata[
                research_environment
            ]
            return resenv_metadata
        elif (
            research_environment != "user_key_url" and research_environment != BIOCONDA
        ):
            logger.error(
                f"Failure to load metadata of reasearch enviroment: {research_environment}"
            )
            return None
        return None

    def create_and_deploy_playbook(
        self,
        public_key: str,
        research_environment_template: str,
        create_only_backend: bool,
        conda_packages: list[CondaPackage],
        apt_packages: list[str],
        openstack_id: str,
        port: int,
        ip: str,
        cloud_site: str,
        base_url: str = "",
    ) -> int:
        logger.info(f"Starting Playbook for (openstack_id): {openstack_id}")
        key: str = self.redis_connection.hget(openstack_id, "key").decode("utf-8")
        playbook = Playbook(
            ip=ip,
            port=port,
            research_environment_template=research_environment_template,
            research_environment_template_version=self.template.get_template_version_for(
                template=research_environment_template
            ),
            create_only_backend=create_only_backend,
            osi_private_key=key,
            public_key=urllib.parse.unquote(public_key),
            pool=self.redis_pool,
            conda_packages=conda_packages,
            apt_packages=apt_packages,
            cloud_site=cloud_site,
            base_url=base_url,
        )
        logger.info(playbook)
        max_wait_time = 5 * 60  # 5 minutes in seconds
        interval = 60  # Check every minute

        start_time = time.time()
        while self.template.is_update_locked():
            elapsed_time = time.time() - start_time
            if elapsed_time > max_wait_time:
                logger.error(
                    "Template update is taking too long, cancelling playbook creation."
                )
                self.redis_connection.hset(
                    openstack_id, "status", VmTaskStates.PLAYBOOK_FAILED.value
                )
                return -1
            logger.info(
                f"Template is currently updating...Wait for {max_wait_time / 60 - int(elapsed_time / 60)} minutes..."
            )
            time.sleep(interval)

        self.redis_connection.hset(
            openstack_id, "status", VmTaskStates.BUILD_PLAYBOOK.value
        )
        playbook.run_it()

        ForcConnector.active_playbooks[openstack_id] = playbook
        logger.info(f"Playbook for (openstack_id): {openstack_id} started!")
        return 0
