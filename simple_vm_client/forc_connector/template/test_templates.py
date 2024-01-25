import copy
import os
import unittest
from distutils.version import LooseVersion
from unittest.mock import MagicMock, Mock, call, mock_open, patch

import pytest
import requests
import yaml

from simple_vm_client.forc_connector.template.template import (
    CONDA,
    FILENAME,
    ResearchEnvironmentMetadata,
    Template,
)
from simple_vm_client.ttypes import ResearchEnvironmentTemplate

METADATA_EXAMPLE = ResearchEnvironmentMetadata(
    template_name="example_template",
    port="8080",
    wiki_link="https://example.com/wiki",
    description="Example template for testing",
    title="Example Template",
    community_driven=True,
    logo_url="https://example.com/logo.png",
    info_url="https://example.com/info",
    securitygroup_name="example_group",
    securitygroup_description="Example security group",
    securitygroup_ssh=True,
    direction="inbound",
    protocol="tcp",
    information_for_display="Some information",
    needs_forc_support=True,
    min_ram=2,
    min_cores=1,
    is_maintained=True,
    forc_versions=["1.0.0", "2.0.0"],
    incompatible_versions=["3.0.0"],
)
MOCK_TEMPLATES = [
    ResearchEnvironmentTemplate(
        template_name="template_1",
        title="Template 1",
        description="TemplateDesc1",
        logo_url="https://logo1.de",
        info_url="https://info1.de",
        port=80,
        incompatible_versions=["1.0.0"],
        is_maintained=True,
        information_for_display="Info1",
        min_cores=10,
        min_ram=2,
    ),
    ResearchEnvironmentTemplate(
        template_name="template_2",
        title="Template 2",
        description="TemplateDesc2",
        logo_url="https://logo2.de",
        info_url="https://info2.de",
        port=8080,
        incompatible_versions=["2.0.0"],
        is_maintained=False,
        information_for_display="Info2",
        min_cores=5,
        min_ram=4,
    ),
    ResearchEnvironmentTemplate(
        template_name="template_3",
        title="Template 3",
        description="TemplateDesc3",
        logo_url="https://logo3.de",
        info_url="https://info3.de",
        port=8000,
        incompatible_versions=["3.0.0"],
        is_maintained=True,
        information_for_display="Info3",
        min_cores=8,
        min_ram=6,
    ),
    ResearchEnvironmentTemplate(
        template_name="template_4",
        title="Template 4",
        description="TemplateDesc4",
        logo_url="https://logo4.de",
        info_url="https://info4.de",
        port=8088,
        incompatible_versions=["4.0.0"],
        is_maintained=False,
        information_for_display="Info4",
        min_cores=12,
        min_ram=8,
    ),
]


class TestTemplate(unittest.TestCase):
    GITHUB_REPO_STAGING = (
        "https://github.com/deNBI/resenvs/archive/refs/heads/staging.zip"
    )
    FORC_URL = "https://FAKE_URL.de"

    def get_metadata_example(self):
        return copy.deepcopy(METADATA_EXAMPLE)

    def init_template(
        self, github_playbook_repo=None, forc_url="", forc_api_key="1234"
    ):
        with patch.object(Template, "__init__", lambda x, y, z: None):
            template = Template(None, None)
            template.FORC_URL = forc_url
            template.GITHUB_PLAYBOOKS_REPO = github_playbook_repo
            template.FORC_API_KEY = forc_api_key
            template.TEMPLATES_URL = f"{template.FORC_URL}templates"
            template.BACKENDS_URL = f"{template.FORC_URL}backends"
            template.BACKENDS_BY_OWNER_URL = f"{template.BACKENDS_URL}/byOwner"
            template.BACKENDS_BY_TEMPLATE_URL = f"{template.BACKENDS_URL}/byTemplate"
            template._forc_allowed: dict[str, list[str]] = {}
            template._all_templates = [CONDA]
            template._loaded_resenv_metadata: dict[
                str, ResearchEnvironmentMetadata
            ] = {}
            template._allowed_forc_templates: list[ResearchEnvironmentTemplate] = []

        return template

    @patch("requests.get")
    @patch("zipfile.ZipFile")
    @patch("builtins.open", create=True)
    @patch("simple_vm_client.forc_connector.template.template.logger.info")
    def test_download_and_extract_playbooks(
        self, mock_logger_info, mock_open, mock_zipfile, mock_requests
    ):
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        # Set up mock responses
        mock_response = Mock()
        mock_response.content = b"Mock content"
        mock_requests.return_value = mock_response

        # Call the method to test
        template._download_and_extract_playbooks()

        # Assert that the requests.get method was called with the correct URL
        mock_requests.assert_called_once_with(template.GITHUB_PLAYBOOKS_REPO)

        # Assert logging messages
        mock_logger_info.assert_any_call(
            f"STARTED update of playbooks from - {template.GITHUB_PLAYBOOKS_REPO}"
        )
        mock_logger_info.assert_any_call("Downloading Completed")

        # Assert that the open method was called with the correct file name and mode
        mock_open.assert_called_once_with(FILENAME, "wb")

        # Assert that the write method was called on the file object
        mock_open.return_value.__enter__.return_value.write.assert_called_once_with(
            mock_response.content
        )

        # Assert that the zipfile.ZipFile constructor was called with the correct file name and mode
        mock_zipfile.assert_called_once_with(FILENAME, "r")

    @patch("glob.glob")
    @patch("shutil.copytree")
    @patch("shutil.rmtree")
    @patch(
        "os.path.isdir", return_value=True
    )  # Mock os.path.isdir to always return True
    def test_copy_resenvs_templates(
        self, mock_isdir, mock_rmtree, mock_copytree, mock_glob
    ):
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        # Set up mock responses
        mock_glob.return_value = ["/path/to/directory/resenvs"]

        def mock_glob_side_effect(pattern):
            if pattern == Template.get_playbook_dir() + "*":
                return ["/path/to/directory/resenvs"]
            else:
                return []

        mock_glob.side_effect = mock_glob_side_effect

        # Call the method to test
        template._copy_resenvs_templates()

        # Assert that glob.glob was called with the correct parameters
        mock_glob.assert_called_once_with(Template.get_playbook_dir() + "*")

        # Assert that shutil.copytree was called with the correct parameters
        mock_copytree.assert_called_once_with(
            "/path/to/directory/resenvs",
            Template.get_playbook_dir(),
            dirs_exist_ok=True,
        )

        # Assert that shutil.rmtree was called with the correct parameters
        mock_rmtree.assert_called_once_with(
            "/path/to/directory/resenvs", ignore_errors=True
        )

    @patch("os.listdir")
    @patch("os.path.isdir")
    def test_update_loaded_templates(self, mock_isdir, mock_listdir):
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        # Set up mock responses
        mock_listdir.return_value = [
            "template1",
            "template2",
            "non_template",
            "optional",
            "packer",
            ".github",
            "cluster",
        ]
        mock_isdir.side_effect = (
            lambda path: "non_template" not in path
        )  # Mock isdir to return True for templates

        # Call the method to test
        template._update_loaded_templates()

        # Assert that os.listdir was called with the correct parameters
        mock_listdir.assert_called_once_with(Template.get_playbook_dir())

        # Assert that os.path.isdir was called for each template
        mock_isdir.assert_any_call(
            os.path.join(Template.get_playbook_dir(), "template1")
        )
        mock_isdir.assert_any_call(
            os.path.join(Template.get_playbook_dir(), "template2")
        )
        mock_isdir.assert_any_call(
            os.path.join(Template.get_playbook_dir(), "non_template")
        )
        with pytest.raises(AssertionError):
            mock_isdir.assert_called_with(
                os.path.join(Template.get_playbook_dir(), "packer")
            )
        with pytest.raises(AssertionError):
            mock_isdir.assert_called_with(
                os.path.join(Template.get_playbook_dir(), ".github")
            )
        with pytest.raises(AssertionError):
            mock_isdir.assert_called_with(
                os.path.join(Template.get_playbook_dir(), "cluster")
            )
        with pytest.raises(AssertionError):
            mock_isdir.assert_called_with(
                os.path.join(Template.get_playbook_dir(), "optional")
            )

        # Assert that the _all_templates attribute is updated correctly
        expected_templates = ["template1", "template2"]
        self.assertEqual(template._all_templates, expected_templates)

    @patch("simple_vm_client.forc_connector.template.template.logger.warning")
    def test_update_playbooks_no_github_repo(self, mock_logger_warning):
        template = self.init_template()
        template.update_playbooks()
        mock_logger_warning.assert_called_once_with(
            "Github playbooks repo URL is None. Aborting download of playbooks."
        )

    @patch("simple_vm_client.forc_connector.template.template.os.popen")
    @patch("simple_vm_client.forc_connector.template.template.logger.info")
    def test_install_ansible_galaxy_requirements(self, mock_logger_info, mock_os_popen):
        # Set up mocks
        mock_os_popen_instance = MagicMock()
        mock_os_popen.return_value = mock_os_popen_instance
        mock_os_popen_instance.read.return_value = "Mocked output"

        # Create an instance of the Template class
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        # Call the method to be tested
        template._install_ansible_galaxy_requirements()

        # Assertions
        mock_logger_info.assert_any_call("Installing Ansible galaxy requirements..")
        mock_os_popen.assert_called_with(
            f"ansible-galaxy install -r {Template.get_playbook_dir()}/packer/requirements.yml"
        )
        mock_os_popen_instance.read.assert_called_once()
        mock_logger_info.assert_any_call("Mocked output")

    def test_get_template_version_for_existing_template(self):
        # Mock _forc_allowed with some versions for the template
        template_name = "example_template"
        expected_version = "1.2.3"
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        template._forc_allowed = {template_name: [expected_version]}

        # Call the method to be tested
        result_version = template.get_template_version_for(template_name)

        # Assertion
        self.assertEqual(result_version, expected_version)

    def test_get_template_version_for_nonexistent_template(self):
        # Mock _forc_allowed without the template
        template_name = "nonexistent_template"
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        template._forc_allowed = {}

        # Call the method to be tested
        result_version = template.get_template_version_for(template_name)

        # Assertion
        self.assertEqual(result_version, "")

    @patch("simple_vm_client.forc_connector.template.template.logger.info")
    def test_get_allowed_templates(self, mock_logger_info):
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        template._allowed_forc_templates = MOCK_TEMPLATES

        result_templates = template.get_allowed_templates()

        # Assertions
        self.assertEqual(result_templates, MOCK_TEMPLATES)

        # Check log output if needed
        mock_logger_info.assert_any_call("Allowed templates:")
        for template in MOCK_TEMPLATES:
            mock_logger_info.assert_any_call(template)

    @patch("simple_vm_client.forc_connector.template.template.requests.get")
    @patch("simple_vm_client.forc_connector.template.template.logger.info")
    def test_get_forc_template_version(self, mock_logger_info, mock_requests_get):
        # Set up the mock response
        expected_response = Mock()
        mock_requests_get.return_value = expected_response
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        # Call the method to be tested
        result_response = template._get_forc_template_version(
            template_name="mock_name", forc_version="mock_version"
        )

        # Assertions
        self.assertEqual(result_response, expected_response)

        # Additional assertions based on your specific requirements
        get_url = f"{template.TEMPLATES_URL}/mock_name/mock_version"
        mock_logger_info.assert_called_once_with(
            f"Get Forc Template Version - {get_url}"
        )

        mock_requests_get.assert_called_once_with(
            get_url,
            timeout=(30, 30),
            headers={"X-API-KEY": template.FORC_API_KEY},
            verify=True,
        )

    def test_update_forc_allowed_versions(self):
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        # Call the method to be tested
        template._update_forc_allowed_versions(
            name="mock_name", allowed_versions=["1.0.0", "2.0.0", "1.5.0"]
        )

        # Assertions
        expected_forc_allowed = {"mock_name": ["2.0.0", "1.5.0", "1.0.0"]}
        self.assertEqual(template._forc_allowed, expected_forc_allowed)

    @patch(
        "simple_vm_client.forc_connector.template.template.Template._get_forc_template_version"
    )
    def test_update_forc_allowed(self, mock_get_forc_template_version):
        # Set up the mock for _get_forc_template_version
        mock_get_forc_template_version.return_value.status_code = 200
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        # Call the method to be tested
        metadata_example = self.get_metadata_example()
        template._update_forc_allowed(metadata_example)
        versions = template._forc_allowed[metadata_example.template_name]
        versions.sort(key=LooseVersion, reverse=True)

        # Assertions
        self.assertCountEqual(versions, metadata_example.forc_versions)
        for forc_version in metadata_example.forc_versions:
            f"{template.TEMPLATES_URL}/{metadata_example.template_name}/{forc_version}"
            mock_get_forc_template_version.assert_any_call(
                forc_version=forc_version, template_name=metadata_example.template_name
            )

    @patch(
        "simple_vm_client.forc_connector.template.template.Template._get_forc_template_version"
    )
    def test_update_forc_allowed_no_support_needed(
        self, mock_get_forc_template_version
    ):
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        metadata_example = self.get_metadata_example()
        metadata_example.needs_forc_support = False
        template._update_forc_allowed(metadata_example)
        mock_get_forc_template_version.assert_not_called()

    @patch("simple_vm_client.forc_connector.template.template.requests.get")
    @patch("simple_vm_client.forc_connector.template.template.logger.error")
    @patch("simple_vm_client.forc_connector.template.template.logger.info")
    def test_update_forc_allowed_with_exception(
        self, mock_logger_info, mock_logger_error, mock_requests_get
    ):
        mock_requests_get.side_effect = requests.exceptions.Timeout("Timeout occurred")

        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        metadata_example = self.get_metadata_example()

        template._update_forc_allowed(metadata_example)
        for forc_version in metadata_example.forc_versions:
            get_url = f"{template.TEMPLATES_URL}/{metadata_example.template_name}/{forc_version}"
            mock_logger_info.assert_any_call(f"Get Forc Template Version - {get_url}")
            mock_requests_get.assert_any_call(
                get_url,
                timeout=(30, 30),
                headers={"X-API-KEY": template.FORC_API_KEY},
                verify=True,
            )

        # Check that logger.error is called for each forc_version
        expected_calls = [
            call("Checking template/version timed out. Timeout occurred")
        ] * len(METADATA_EXAMPLE.forc_versions)
        mock_logger_error.assert_has_calls(expected_calls, any_order=True)

    @patch("builtins.open", new_callable=mock_open, read_data="key: value\n")
    @patch("simple_vm_client.forc_connector.template.template.yaml.load")
    def test_load_yaml(self, mock_yaml_load, mock_open):
        # Arrange
        file_path = "fake/path/to/template_metadata.yml"
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        # Set the return value for yaml.load
        mock_yaml_load.return_value = {"key": "value"}

        # Act
        result = template._load_yaml(file_path)

        # Assert
        mock_open.assert_called_once_with(file_path)
        mock_yaml_load.assert_called_once_with(
            mock_open.return_value, Loader=yaml.FullLoader
        )
        self.assertEqual(result, {"key": "value"})

    @patch("simple_vm_client.forc_connector.template.template.logger.exception")
    def test_handle_metadata_exception(self, mock_logger_exception):
        # Arrange
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        template_metadata_name = "fake_metadata_name"
        template_name = "fake_template"
        fake_exception = ValueError("Fake error message")

        # Act
        template._handle_metadata_exception(
            template_metadata_name, template_name, fake_exception
        )

        # Assert
        mock_logger_exception.assert_called_once_with(
            f"Failed to load Metadata yml: {template_metadata_name}\n{str(fake_exception)}"
        )

    @patch("simple_vm_client.forc_connector.template.template.Template._load_yaml")
    @patch(
        "simple_vm_client.forc_connector.template.template.Template._add_forc_allowed_template"
    )
    @patch(
        "simple_vm_client.forc_connector.template.template.Template._handle_metadata_exception"
    )
    def test_load_resenv_metadata(
        self, mock_handle_exception, mock_add_forc_allowed, mock_load_yaml
    ):
        # Arrange
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        mock_template_metadata: ResearchEnvironmentMetadata = (
            self.get_metadata_example()
        )  # Replace with your example metadata
        mock_load_yaml.return_value = mock_template_metadata.__dict__
        template._all_templates = [mock_template_metadata.template_name]

        # Act
        result = template._load_resenv_metadata()

        # Assert
        mock_load_yaml.assert_called_once()  # Check if _load_yaml was called
        self.assertIsInstance(
            mock_add_forc_allowed.call_args[0][0], ResearchEnvironmentMetadata
        )

        self.assertEqual(
            len(result), 1
        )  # Check if one item is returned in the result list
        self.assertIsInstance(
            result[0], ResearchEnvironmentMetadata
        )  # Check if the item is an instance of ResearchEnvironmentMetadata
        mock_handle_exception.assert_not_called()  # Ensure _handle_metadata_exception is not called

    @patch("simple_vm_client.forc_connector.template.template.Template._load_yaml")
    @patch("simple_vm_client.forc_connector.template.template.logger.exception")
    def test_load_resenv_metadata_exception(
        self, mock_logger_exception, mock_load_yaml
    ):
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        mock_template_metadata: ResearchEnvironmentMetadata = (
            self.get_metadata_example()
        )
        exception_message = "Some error"
        mock_load_yaml.side_effect = Exception("Some error")
        mock_load_yaml.return_value = mock_template_metadata.__dict__
        template._all_templates = [mock_template_metadata.template_name]

        # Act
        template._load_resenv_metadata()

        mock_logger_exception.assert_called_once_with(
            f"Failed to load Metadata yml: {mock_template_metadata.template_name}_metadata.yml\n{exception_message}"
        )

    def test_add_forc_allowed_template(self):
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        mock_template_metadata: ResearchEnvironmentMetadata = (
            self.get_metadata_example()
        )

        # Act
        template._add_forc_allowed_template(mock_template_metadata)

        # Assert
        self.assertEqual(
            len(template._allowed_forc_templates), 1
        )  # Check if the template was added
        added_template = template._allowed_forc_templates[0]
        self.assertIsInstance(
            added_template, ResearchEnvironmentTemplate
        )  # Check if the added item is an instance of ResearchEnvironmentTemplate
        self.assertEqual(
            added_template.template_name, mock_template_metadata.template_name
        )

    @patch("simple_vm_client.forc_connector.template.template.requests.get")
    def test_get_forc_templates(self, mock_requests_get):
        # Arrange
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        expected_response = [
            {"template_name": "template1"},
            {"template_name": "template2"},
        ]
        mock_requests_get.return_value.json.return_value = expected_response

        # Act
        result = template._get_forc_templates()

        # Assert
        mock_requests_get.assert_called_once_with(
            template.TEMPLATES_URL,
            timeout=(30, 30),
            headers={"X-API-KEY": template.FORC_API_KEY},
            verify=True,
        )
        self.assertEqual(
            result, expected_response
        )  # Check if the result matches the expected response

    @patch("simple_vm_client.forc_connector.template.template.requests.get")
    @patch("simple_vm_client.forc_connector.template.template.logger.exception")
    def test_get_forc_templates_exception(
        self, mock_logger_exception, mock_requests_get
    ):
        # Arrange
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        error_msg = "Error fetching FORC templates"
        mock_requests_get.side_effect = requests.RequestException(error_msg)

        # Act
        result = template._get_forc_templates()

        # Assert
        mock_requests_get.assert_called_once_with(
            template.TEMPLATES_URL,
            timeout=(30, 30),
            headers={"X-API-KEY": template.FORC_API_KEY},
            verify=True,
        )
        self.assertEqual(result, [])
        mock_logger_exception.assert_called_once_with(
            f"Error while fetching FORC templates: {error_msg}"
        )

    @patch(
        "simple_vm_client.forc_connector.template.template.Template._get_forc_templates"
    )
    def test_cross_check_forc_image(self, mock_get_forc_templates):
        # Arrange
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        tags = ["template1", "template2"]
        allowed_templates = {"template1": ["version1"], "template2": ["version2"]}
        mock_get_forc_templates.return_value = [
            {"name": "template1", "version": "version1"},
            {"name": "template2", "version": "version2"},
        ]
        template._forc_allowed = allowed_templates
        template._all_templates = tags

        # Act
        result = template.cross_check_forc_image(tags)

        # Assert
        mock_get_forc_templates.assert_called_once()
        self.assertTrue(result)  # Check if the result is True for a valid case

    @patch(
        "simple_vm_client.forc_connector.template.template.Template._get_forc_templates"
    )
    @patch("simple_vm_client.forc_connector.template.template.logger.exception")
    def test_cross_check_forc_image_exception(
        self, mock_logger_exception, mock_get_forc_templates
    ):
        # Arrange
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        tags = ["template1", "template2"]
        mock_get_forc_templates.side_effect = Exception("Simulated exception")

        # Act
        result = template.cross_check_forc_image(tags)

        # Assert
        mock_get_forc_templates.assert_called_once()
        self.assertFalse(result)
        mock_logger_exception.assert_called_once_with(
            "Could not get templates from FORC."
        )

    @patch(
        "simple_vm_client.forc_connector.template.template.Template._update_forc_allowed"
    )
    def test_process_template_metadata(self, mock_update_forc_allowed):
        # Arrange
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        metadata = self.get_metadata_example()

        # Act
        template._process_template_metadata(metadata)

        # Assert
        mock_update_forc_allowed.assert_called_once_with(metadata)
        self.assertEqual(
            template._loaded_resenv_metadata[metadata.template_name], metadata
        )

    @patch(
        "simple_vm_client.forc_connector.template.template.Template._update_forc_allowed"
    )
    def test_process_template_metadata_existing_template(
        self, mock_update_forc_allowed
    ):
        # Arrange
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        existing_metadata = self.get_metadata_example()
        new_metadata = self.get_metadata_example()
        new_metadata.port = 9000
        template._loaded_resenv_metadata[
            existing_metadata.template_name
        ] = existing_metadata
        # Act
        template._process_template_metadata(new_metadata)

        # Assert
        mock_update_forc_allowed.assert_called_once_with(new_metadata)
        self.assertEqual(
            template._loaded_resenv_metadata[existing_metadata.template_name],
            new_metadata,
        )

    @patch(
        "simple_vm_client.forc_connector.template.template.Template._load_resenv_metadata"
    )
    @patch(
        "simple_vm_client.forc_connector.template.template.Template._process_template_metadata"
    )
    @patch("simple_vm_client.forc_connector.template.template.logger.exception")
    def test_load_and_update_resenv_metadata(
        self,
        mock_logger_exception,
        mock_process_template_metadata,
        mock_load_resenv_metadata,
    ):
        # Arrange
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        # Mocking the _load_resenv_metadata method to return a list of ResearchEnvironmentMetadata instances
        mock_metadata1 = self.get_metadata_example()
        mock_metadata2 = self.get_metadata_example()
        mock_load_resenv_metadata.return_value = [mock_metadata1, mock_metadata2]

        # Mocking the _process_template_metadata method to raise an exception for one of the metadata instances
        mock_exception = Exception("Failed to parse Metadata yml")
        mock_process_template_metadata.side_effect = [None, mock_exception]

        # Act
        template._load_and_update_resenv_metadata()

        # Assert
        mock_load_resenv_metadata.assert_called_once()  # Check if _load_resenv_metadata was called
        mock_process_template_metadata.assert_has_calls(
            [unittest.mock.call(mock_metadata1), unittest.mock.call(mock_metadata2)]
        )  # Check if _process_template_metadata was called for each metadata instance
        mock_logger_exception.assert_called_once_with(
            f"Failed to parse Metadata yml: {mock_metadata2}\n{mock_exception}"
        )  # Check if logger.exception was called for the exception case

    @patch(
        "simple_vm_client.forc_connector.template.template.Template._download_and_extract_playbooks"
    )
    @patch(
        "simple_vm_client.forc_connector.template.template.Template._copy_resenvs_templates"
    )
    @patch(
        "simple_vm_client.forc_connector.template.template.Template._update_loaded_templates"
    )
    @patch(
        "simple_vm_client.forc_connector.template.template.Template._install_ansible_galaxy_requirements"
    )
    @patch(
        "simple_vm_client.forc_connector.template.template.Template._load_and_update_resenv_metadata"
    )
    @patch("simple_vm_client.forc_connector.template.template.logger.error")
    @patch("simple_vm_client.forc_connector.template.template.logger.info")
    def test_update_playbooks(
        self,
        mock_logger_info,
        mock_logger_error,
        mock_load_and_update_resenv_metadata,
        mock_install_ansible_galaxy_requirements,
        mock_update_loaded_templates,
        mock_copy_resenvs_templates,
        mock_download_and_extract_playbooks,
    ):
        # Arrange
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )

        # Act
        template.update_playbooks()

        # Assert
        mock_logger_error.assert_not_called()  # Check if logger.error was not called when GITHUB_PLAYBOOKS_REPO is not None
        mock_download_and_extract_playbooks.assert_called_once()  # Check if _download_and_extract_playbooks was called
        mock_copy_resenvs_templates.assert_called_once()  # Check if _copy_resenvs_templates was called
        mock_update_loaded_templates.assert_called_once()  # Check if _update_loaded_templates was called
        mock_install_ansible_galaxy_requirements.assert_called_once()  # Check if _install_ansible_galaxy_requirements was called
        mock_load_and_update_resenv_metadata.assert_called_once()  # Check if _load_and_update_resenv_metadata was called
        mock_logger_info.assert_any_call(
            f"Loaded Template Names: {template._all_templates}"
        )  # Check if logger.info was called

    @patch(
        "simple_vm_client.forc_connector.template.template.Template.update_playbooks"
    )
    def test_init(self, mock_update_playbooks):
        # Arrange
        github_playbook_repo = "https://github.com/playbooks"
        forc_url = "https://forc.example.com/"
        forc_api_key = "your-api-key"

        # Act
        instance = Template(github_playbook_repo, forc_url, forc_api_key)

        # Assert
        self.assertEqual(instance.GITHUB_PLAYBOOKS_REPO, github_playbook_repo)
        self.assertEqual(instance.FORC_URL, forc_url)
        self.assertEqual(instance.FORC_API_KEY, forc_api_key)
        self.assertEqual(instance.TEMPLATES_URL, f"{forc_url}templates")
        self.assertEqual(instance.BACKENDS_URL, f"{forc_url}backends")
        self.assertEqual(instance.BACKENDS_BY_OWNER_URL, f"{forc_url}backends/byOwner")
        self.assertEqual(
            instance.BACKENDS_BY_TEMPLATE_URL, f"{forc_url}backends/byTemplate"
        )
        self.assertEqual(instance._forc_allowed, {})
        self.assertEqual(instance._all_templates, [CONDA])
        self.assertEqual(instance._loaded_resenv_metadata, {})
        self.assertEqual(instance._allowed_forc_templates, [])
        mock_update_playbooks.assert_called_once()

    def test_loaded_research_env_metadata_property(self):
        # Arrange
        template = self.init_template(
            github_playbook_repo=TestTemplate.GITHUB_REPO_STAGING,
            forc_url=TestTemplate.FORC_URL,
        )
        mock_metadata1 = self.get_metadata_example()
        mock_metadata2 = self.get_metadata_example()

        # Act
        template._loaded_resenv_metadata = {
            "template1": mock_metadata1,
            "template2": mock_metadata2,
        }
        result = template.loaded_research_env_metadata

        # Assert
        self.assertEqual(
            result, {"template1": mock_metadata1, "template2": mock_metadata2}
        )


if __name__ == "__main__":
    unittest.main()
