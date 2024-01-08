import glob
import os
import shutil
import zipfile
from distutils.version import LooseVersion
from pathlib import Path

import requests
import yaml

from simple_vm_client.ttypes import ResearchEnvironmentTemplate
from simple_vm_client.util.logger import setup_custom_logger

# from resenv.backend.Backend import Backend

TEMPLATE_NAME = "template_name"
CONDA = "conda"
ALL_TEMPLATES = [CONDA]
logger = setup_custom_logger(__name__)
FORC_VERSIONS = "forc_versions"
FORC_API_KEY = os.environ.get("FORC_API_KEY", None)
PORT = "port"
SECURITYGROUP_NAME = "securitygroup_name"
SECURITYGROUP_DESCRIPTION = "securitygroup_description"
SECURITYGROUP_SSH = "securitygroup_ssh"
DIRECTION = "direction"
PROTOCOL = "protocol"
INFORMATION_FOR_DISPLAY = "information_for_display"
NO_TEMPLATE_NAMES = ["packer", "optional", ".github", "cluster", "conda"]
NEEDS_FORC_SUPPORT = "needs_forc_support"
MIN_RAM = "min_ram"
MIN_CORES = "min_cores"
FILENAME = "resenv_repo"


class ResearchEnvironmentMetadata:
    def __init__(
        self,
        template_name: str,
        port: str,
        securitygroup_name: str,
        securitygroup_description: str,
        securitygroup_ssh: bool,
        direction: str,
        protocol: str,
        description: str,
        logo_url: str,
        info_url: str,
        information_for_display: str,
        title: str,
        community_driven: bool = False,
        wiki_link: str = "",
        needs_forc_support: bool = True,
        min_ram: int = 0,
        min_cores: int = 0,
        is_maintained: bool = True,
        forc_versions: list[str] = [],
        incompatible_versions: list[str] = [],
    ):
        self.template_name = template_name
        self.port = port
        self.wiki_link = wiki_link
        self.description = description
        self.title = title
        self.community_driven = community_driven
        self.logo_url = logo_url
        self.info_url = info_url
        self.securitygroup_name = securitygroup_name
        self.securitygroup_description = securitygroup_description
        self.securitygroup_ssh = securitygroup_ssh
        self.direction = direction
        self.protocol = protocol
        self.information_for_display = information_for_display
        self.needs_forc_support = needs_forc_support
        self.min_ram = min_ram
        self.min_cores = min_cores
        self.is_maintained = is_maintained
        self.forc_versions = forc_versions
        self.incompatible_versions = incompatible_versions


class Template(object):
    def __init__(self, github_playbook_repo: str, forc_url: str, forc_api_key: str):
        self.GITHUB_PLAYBOOKS_REPO = github_playbook_repo
        self.FORC_URL = forc_url
        self.FORC_API_KEY = forc_api_key
        self.TEMPLATES_URL = f"{self.FORC_URL}templates"
        self.BACKENDS_URL = f"{self.FORC_URL}backends"
        self.BACKENDS_BY_OWNER_URL = f"{self.BACKENDS_URL}/byOwner"
        self.BACKENDS_BY_TEMPLATE_URL = f"{self.BACKENDS_URL}/byTemplate"
        self._forc_allowed: dict[str, list[str]] = {}
        self._all_templates = [CONDA]
        self._loaded_resenv_metadata: dict[str, ResearchEnvironmentMetadata] = {}
        self._allowed_forc_templates: list[ResearchEnvironmentTemplate] = []
        self.update_playbooks()

    @property
    def loaded_research_env_metadata(self) -> dict[str, ResearchEnvironmentMetadata]:
        return self._loaded_resenv_metadata

    def _download_and_extract_playbooks(self) -> None:
        logger.info(f"STARTED update of playbooks from - {self.GITHUB_PLAYBOOKS_REPO}")
        r = requests.get(self.GITHUB_PLAYBOOKS_REPO)
        with open(FILENAME, "wb") as output_file:
            output_file.write(r.content)
        logger.info("Downloading Completed")

        with zipfile.ZipFile(FILENAME, "r") as zip_ref:
            zip_ref.extractall(Template.get_playbook_dir())

    def _copy_resenvs_templates(self) -> None:
        resenvs_unziped_dir = next(
            filter(
                lambda f: os.path.isdir(f) and "resenvs" in f,
                glob.glob(Template.get_playbook_dir() + "*"),
            )
        )
        shutil.copytree(
            resenvs_unziped_dir, Template.get_playbook_dir(), dirs_exist_ok=True
        )
        shutil.rmtree(resenvs_unziped_dir, ignore_errors=True)

    def _update_loaded_templates(self) -> None:
        self._all_templates = [
            name
            for name in os.listdir(Template.get_playbook_dir())
            if name not in NO_TEMPLATE_NAMES
            and os.path.isdir(os.path.join(Template.get_playbook_dir(), name))
        ]

    def _load_and_update_resenv_metadata(self) -> None:
        templates_metadata = self._load_resenv_metadata()

        for template_metadata in templates_metadata:
            try:
                self._process_template_metadata(template_metadata)
            except Exception as e:
                logger.exception(
                    f"Failed to parse Metadata yml: {template_metadata}\n{e}"
                )

    def _process_template_metadata(
        self, template_metadata: ResearchEnvironmentMetadata
    ) -> None:
        if template_metadata.needs_forc_support:
            self._update_forc_allowed(template_metadata)

            if template_metadata.template_name not in self._loaded_resenv_metadata:
                self._loaded_resenv_metadata[
                    template_metadata.template_name
                ] = template_metadata
            elif (
                self._loaded_resenv_metadata[template_metadata.template_name]
                != template_metadata
            ):
                self._loaded_resenv_metadata[
                    template_metadata.template_name
                ] = template_metadata

    def update_playbooks(self) -> None:
        if self.GITHUB_PLAYBOOKS_REPO is None:
            logger.error(
                "Github playbooks repo URL is None. Aborting download of playbooks."
            )
            return

        self._download_and_extract_playbooks()

        self._copy_resenvs_templates()

        self._update_loaded_templates()

        logger.info(f"Loaded Template Names: {self._all_templates}")

        self._install_ansible_galaxy_requirements()

        self._load_and_update_resenv_metadata()

        logger.info(f"Allowed Forc {self._forc_allowed}")

    def _get_forc_templates(self) -> list[dict]:
        try:
            response = requests.get(
                self.TEMPLATES_URL,
                timeout=(30, 30),
                headers={"X-API-KEY": self.FORC_API_KEY},
                verify=True,
            )
            response.raise_for_status()  # Raise HTTPError for bad responses
            return response.json()
        except requests.RequestException as e:
            logger.exception(f"Error while fetching FORC templates: {e}")
            return []

    def cross_check_forc_image(self, tags: list[str]) -> bool:
        try:
            templates = self._get_forc_templates()
        except Exception:
            logger.exception("Could not get templates from FORC.")
            templates = []

        cross_tags = set(self._all_templates).intersection(tags)

        for template_dict in templates:
            template_name = template_dict["name"]

            if template_name in self._forc_allowed and template_name in cross_tags:
                template_version = template_dict["version"]
                if template_version in self._forc_allowed[template_name]:
                    return True

        return False

    @staticmethod
    def get_playbook_dir() -> str:
        Path(f"{os.path.dirname(os.path.realpath(__file__))}/plays/").mkdir(
            parents=True, exist_ok=True
        )
        dir_path = f"{os.path.dirname(os.path.realpath(__file__))}/plays/"
        return dir_path

    def _add_forc_allowed_template(self, metadata: ResearchEnvironmentMetadata) -> None:
        if metadata.needs_forc_support:
            logger.info(f"Add {metadata.template_name} - to allowed templates")
            template = ResearchEnvironmentTemplate(
                template_name=metadata.template_name,
                title=metadata.title,
                description=metadata.description,
                logo_url=metadata.logo_url,
                info_url=metadata.info_url,
                port=int(metadata.port),
                incompatible_versions=metadata.incompatible_versions,
                is_maintained=metadata.is_maintained,
                information_for_display=metadata.information_for_display,
                min_ram=metadata.min_ram,
                min_cores=metadata.min_cores,
            )
            self._allowed_forc_templates.append(template)

    def _load_resenv_metadata(self) -> list[ResearchEnvironmentMetadata]:
        templates_metadata = []

        for template in self._all_templates:
            if template not in NO_TEMPLATE_NAMES:
                template_metadata_name = f"{template}_metadata.yml"
                try:
                    metadata_path = os.path.join(
                        Template.get_playbook_dir(), template, template_metadata_name
                    )

                    loaded_metadata = self._load_yaml(metadata_path)

                    research_environment_metadata: ResearchEnvironmentMetadata = (
                        ResearchEnvironmentMetadata(**loaded_metadata)
                    )

                    self._add_forc_allowed_template(research_environment_metadata)
                    templates_metadata.append(research_environment_metadata)
                except Exception as e:
                    self._handle_metadata_exception(template_metadata_name, template, e)

        return templates_metadata

    def _load_yaml(self, file_path: str) -> dict:
        with open(file_path) as template_metadata:
            return yaml.load(template_metadata, Loader=yaml.FullLoader) or {}

    def _handle_metadata_exception(
        self, template_metadata_name: str, template: str, exception: Exception
    ) -> None:
        logger.exception(
            f"Failed to load Metadata yml: {template_metadata_name}\n{str(exception)}"
        )

    def get_template_version_for(self, template: str) -> str:
        template_versions: list[str] = self._forc_allowed.get(template)  # type: ignore
        if template_versions:
            return template_versions[0]
        return ""

    def _install_ansible_galaxy_requirements(self):
        logger.info("Installing Ansible galaxy requirements..")
        stream = os.popen(
            f"ansible-galaxy install -r {Template.get_playbook_dir()}/packer/requirements.yml"
        )
        output = stream.read()
        logger.info(output)

    def get_allowed_templates(self) -> list[ResearchEnvironmentTemplate]:
        logger.info("Allowed templates:")
        for template in self._allowed_forc_templates:
            logger.info(template)

        return self._allowed_forc_templates

    def _get_forc_template_version(
        self, template_name: str, forc_version: str
    ) -> requests.Response:
        get_url = f"{self.TEMPLATES_URL}/{template_name}/{forc_version}"
        logger.info(f"Get Forc Template Version - {get_url}")
        return requests.get(
            get_url,
            timeout=(30, 30),
            headers={"X-API-KEY": self.FORC_API_KEY},
            verify=True,
        )

    def _update_forc_allowed_versions(
        self, name: str, allowed_versions: list[str]
    ) -> None:
        allowed_versions.sort(key=LooseVersion, reverse=True)
        self._forc_allowed[name] = allowed_versions

    def _update_forc_allowed(
        self, template_metadata: ResearchEnvironmentMetadata
    ) -> None:
        if not template_metadata.needs_forc_support:
            return

        name = template_metadata.template_name
        allowed_versions = []

        for forc_version in template_metadata.forc_versions:
            try:
                response = self._get_forc_template_version(
                    template_name=name, forc_version=forc_version
                )
                if response.status_code == 200:
                    allowed_versions.append(forc_version)
            except requests.Timeout as e:
                logger.error(f"Checking template/version timed out. {e}")

        self._update_forc_allowed_versions(name, allowed_versions)
