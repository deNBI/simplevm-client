import glob
import os
import shutil
import zipfile
from distutils.version import LooseVersion
from pathlib import Path

import requests
import yaml
from ttypes import ResearchEnvironmentTemplate
from util.logger import setup_custom_logger

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
NO_TEMPLATE_NAMES = ["packer"]
NEEDS_FORC_SUPPORT = "needs_forc_support"


class ResearchEnvironmentMetadata:
    def __init__(
            self,
            name: str,
            port: str,
            security_group_name: str,
            security_group_description: str,
            security_group_ssh: bool,
            direction: str,
            protocol: str,
            information_for_display: str,
    ):
        self.name = name
        self.port = port
        self.security_group_name = security_group_name
        self.security_group_description = security_group_description
        self.security_group_ssh = security_group_ssh
        self.direction = direction
        self.protocol = protocol
        self.information_for_display = information_for_display


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

    def update_playbooks(self) -> None:
        if self.GITHUB_PLAYBOOKS_REPO is None:
            logger.info(
                "Github playbooks repo url is None. Aborting download of playbooks."
            )
            return
        logger.info(f"STARTED update of playbooks from - {self.GITHUB_PLAYBOOKS_REPO}")
        r = requests.get(self.GITHUB_PLAYBOOKS_REPO)
        filename = "resenv_repo"
        with open(filename, 'wb') as output_file:
            output_file.write(r.content)
        logger.info('Downloading Completed')
        with zipfile.ZipFile(filename, 'r') as zip_ref:
            zip_ref.extractall(Template.get_playbook_dir())

        resenvs_unziped_dir = next(filter(lambda f: os.path.isdir(f) and "resenvs" in f, glob.glob(Template.get_playbook_dir() + '*')))
        shutil.copytree(resenvs_unziped_dir, Template.get_playbook_dir(), dirs_exist_ok=True)
        shutil.rmtree(resenvs_unziped_dir, ignore_errors=True)
        self._all_templates = [name for name in os.listdir(Template.get_playbook_dir()) if
                               name not in NO_TEMPLATE_NAMES and os.path.isdir(os.path.join(Template.get_playbook_dir(), name))]
        logger.info(f"Loaded Template Names: {self._all_templates}")

        templates_metadata: list[dict[str, str]] = self.load_resenv_metadata()
        for template_metadata in templates_metadata:
            try:
                if template_metadata.get(NEEDS_FORC_SUPPORT, False):

                    metadata = ResearchEnvironmentMetadata(
                        template_metadata[TEMPLATE_NAME],
                        template_metadata[PORT],
                        template_metadata[SECURITYGROUP_NAME],
                        template_metadata[SECURITYGROUP_DESCRIPTION],
                        bool(template_metadata[SECURITYGROUP_SSH]),
                        template_metadata[DIRECTION],
                        template_metadata[PROTOCOL],
                        template_metadata[INFORMATION_FOR_DISPLAY],
                    )
                    self.update_forc_allowed(template_metadata)
                    if metadata.name not in list(self._loaded_resenv_metadata.keys()):
                        self._loaded_resenv_metadata[metadata.name] = metadata
                    else:
                        if self._loaded_resenv_metadata[metadata.name] != metadata:
                            self._loaded_resenv_metadata[metadata.name] = metadata

            except Exception as e:
                logger.exception(
                    "Failed to parse Metadata yml: "
                    + str(template_metadata)
                    + "\n"
                    + str(e)
                )
        logger.info(f"Allowed Forc {self._forc_allowed}")

    def cross_check_forc_image(self, tags: list[str]) -> bool:
        get_url = self.TEMPLATES_URL
        try:
            response = requests.get(
                get_url,
                timeout=(30, 30),
                headers={"X-API-KEY": FORC_API_KEY},
                verify=True,
            )
            if response.status_code != 200:
                return True
            else:
                templates = response.json()
        except Exception:
            logger.exception("Could not get templates from FORC.")
            templates = []
        cross_tags = list(set(self._all_templates).intersection(tags))
        for template_dict in templates:
            if (
                    template_dict["name"] in self._forc_allowed
                    and template_dict["name"] in cross_tags
            ):
                if (
                        template_dict["version"]
                        in self._forc_allowed[template_dict["name"]]
                ):
                    return True
        return False

    @staticmethod
    def get_playbook_dir() -> str:
        Path(f"{os.path.dirname(os.path.realpath(__file__))}/plays/").mkdir(
            parents=True, exist_ok=True
        )
        dir_path = f"{os.path.dirname(os.path.realpath(__file__))}/plays/"
        return dir_path

    def add_forc_allowed_template(self, metadata: dict) -> None:
        if metadata.get("needs_forc_support", False):
            logger.info(f"Add {metadata} - to allowed templates")
            template = ResearchEnvironmentTemplate(
                template_name=metadata["template_name"],
                title=metadata["title"],
                description=metadata["description"],
                logo_url=metadata["logo_url"],
                info_url=metadata["info_url"],
                port=int(metadata["port"]),
                incompatible_versions=metadata[
                    "incompatible_versions"
                ],
                is_maintained=metadata["is_maintained"],
                information_for_display=metadata[
                    "information_for_display"
                ],
            )
            self._allowed_forc_templates.append(template)

    def load_resenv_metadata(self) -> list[dict[str, str]]:
        templates_metada = []
        for template in self._all_templates:
            try:
                with open(f"{Template.get_playbook_dir()}{template}/{template}_metadata.yml") as template_metadata:
                    try:
                        loaded_metadata = yaml.load(
                            template_metadata, Loader=yaml.FullLoader
                        )

                        templates_metada.append(loaded_metadata)
                        self.add_forc_allowed_template(metadata=loaded_metadata)


                    except Exception as e:
                        logger.exception(
                            "Failed to parse Metadata yml: " + template_metadata + "\n" + str(e)
                        )
            except Exception as e:
                logger.exception(f"No Metadata File found for {template} - {e}")
        return templates_metada

    def get_template_version_for(self, template: str) -> str:
        template_versions: list[str] = self._forc_allowed.get(template)  # type: ignore
        if template_versions:
            return template_versions[0]
        return ""

    def get_allowed_templates(self) -> list[ResearchEnvironmentTemplate]:
        logger.info(f"Allowed templates -> {self._allowed_forc_templates}")
        return self._allowed_forc_templates

    def update_forc_allowed(self, template_metadata: dict[str, str]) -> None:
        if template_metadata["needs_forc_support"]:
            name = template_metadata[TEMPLATE_NAME]
            allowed_versions = []
            for forc_version in template_metadata[FORC_VERSIONS]:
                get_url = f"{self.TEMPLATES_URL}/{name}/{forc_version}"
                logger.info(f"Check Forc Allowed for - {get_url}")
                try:
                    response = requests.get(
                        get_url,
                        timeout=(30, 30),
                        headers={"X-API-KEY": self.FORC_API_KEY},
                        verify=True,
                    )
                    logger.info(response.content)
                    if response.status_code == 200:
                        allowed_versions.append(forc_version)
                except requests.Timeout as e:
                    logger.info(f"checking template/version timed out. {e}")
            allowed_versions.sort(key=LooseVersion)
            allowed_versions.reverse()
            self._forc_allowed[name] = allowed_versions
