import logging
import os
import re
from pathlib import Path

import questionary
from rich.console import Console
from rich.syntax import Syntax

import nf_core.modules.modules_utils
import nf_core.utils
from nf_core.components.components_command import ComponentCommand
from nf_core.components.components_utils import (
    get_components_to_install,
    prompt_component_version_sha,
)
from nf_core.modules.modules_json import ModulesJson
from nf_core.modules.modules_repo import NF_CORE_MODULES_NAME

log = logging.getLogger(__name__)


class ComponentInstall(ComponentCommand):
    def __init__(
        self,
        pipeline_dir,
        component_type,
        force=False,
        prompt=False,
        sha=None,
        remote_url=None,
        branch=None,
        no_pull=False,
        installed_by=False,
    ):
        super().__init__(component_type, pipeline_dir, remote_url, branch, no_pull)
        self.force = force
        self.prompt = prompt
        self.sha = sha
        if installed_by:
            self.installed_by = installed_by
        else:
            self.installed_by = self.component_type

    def install(self, component, silent=False):
        if self.repo_type == "modules":
            log.error(f"You cannot install a {component} in a clone of nf-core/modules")
            return False
        # Check whether pipelines is valid
        if not self.has_valid_directory():
            return False

        if self.component_type == "modules":
            # Check modules directory structure
            self.check_modules_structure()

        # Verify that 'modules.json' is consistent with the installed modules and subworkflows
        modules_json = ModulesJson(self.dir)
        if not silent:
            modules_json.check_up_to_date()

        # Verify SHA
        if not self.modules_repo.verify_sha(self.prompt, self.sha):
            return False

        # Check and verify component name
        component = self.collect_and_verify_name(component, self.modules_repo)
        if not component:
            return False

        # Get current version
        current_version = modules_json.get_component_version(
            self.component_type, component, self.modules_repo.remote_url, self.modules_repo.repo_path
        )

        # Set the install folder based on the repository name
        install_folder = os.path.join(self.dir, self.component_type, self.modules_repo.repo_path)

        # Compute the component directory
        component_dir = os.path.join(install_folder, component)

        # Check that the component is not already installed
        component_not_installed = self.check_component_installed(
            component, current_version, component_dir, self.modules_repo, self.force, self.prompt, silent
        )
        if not component_not_installed:
            log.debug(
                f"{self.component_type[:-1].title()} is already installed and force is not set.\nAdding the new installation source {self.installed_by} for {self.component_type[:-1]} {component} to 'modules.json' without installing the {self.component_type}."
            )
            modules_json.load()
            modules_json.update(self.component_type, self.modules_repo, component, current_version, self.installed_by)
            return False

        version = self.get_version(component, self.sha, self.prompt, current_version, self.modules_repo)
        if not version:
            return False

        # Remove component if force is set and component is installed
        install_track = None
        if self.force:
            log.debug(f"Removing installed version of '{self.modules_repo.repo_path}/{component}'")
            self.clear_component_dir(component, component_dir)
            install_track = self.clean_modules_json(component, self.modules_repo, modules_json)
        if not silent:
            log.info(f"{'Rei' if self.force else 'I'}nstalling '{component}'")
        log.debug(
            f"Installing {self.component_type} '{component}' at modules hash {version} from {self.modules_repo.remote_url}"
        )

        # Download component files
        if not self.install_component_files(component, version, self.modules_repo, install_folder):
            return False

        # Update module.json with newly installed subworkflow
        modules_json.load()
        modules_json.update(
            self.component_type, self.modules_repo, component, version, self.installed_by, install_track
        )

        if self.component_type == "subworkflows":
            # Install included modules and subworkflows
            self.install_included_components(component_dir)

        if not silent:
            # Print include statement
            component_name = "_".join(component.upper().split("/"))
            log.info(f"Use the following statement to include this {self.component_type[:-1]}:")
            Console().print(
                Syntax(
                    f"include {{ {component_name} }} from '../{Path(install_folder, component).relative_to(self.dir)}/main'",
                    "groovy",
                    theme="ansi_dark",
                    padding=1,
                )
            )
            if self.component_type == "subworkflows":
                subworkflow_config = Path(install_folder, component, "nextflow.config").relative_to(self.dir)
                if os.path.isfile(subworkflow_config):
                    log.info("Add the following config statement to use this subworkflow:")
                    Console().print(
                        Syntax(f"includeConfig '{subworkflow_config}'", "groovy", theme="ansi_dark", padding=1)
                    )
        return True

    def install_included_components(self, subworkflow_dir):
        """
        Install included modules and subworkflows
        """
        modules_to_install, subworkflows_to_install = get_components_to_install(subworkflow_dir)
        for s_install in subworkflows_to_install:
            original_installed = self.installed_by
            self.installed_by = Path(subworkflow_dir).parts[-1]
            self.install(s_install, silent=True)
            self.installed_by = original_installed
        for m_install in modules_to_install:
            original_component_type = self.component_type
            self.component_type = "modules"
            original_installed = self.installed_by
            self.installed_by = Path(subworkflow_dir).parts[-1]
            self.install(m_install, silent=True)
            self.component_type = original_component_type
            self.installed_by = original_installed

    def collect_and_verify_name(self, component, modules_repo):
        """
        Collect component name.
        Check that the supplied name is an available module/subworkflow.
        """
        if component is None:
            component = questionary.autocomplete(
                f"{'Tool' if self.component_type == 'modules' else 'Subworkflow'} name:",
                choices=sorted(modules_repo.get_avail_components(self.component_type)),
                style=nf_core.utils.nfcore_question_style,
            ).unsafe_ask()

        # Check that the supplied name is an available module/subworkflow
        if component and component not in modules_repo.get_avail_components(self.component_type):
            log.error(
                f"{self.component_type[:-1].title()} '{component}' not found in list of available {self.component_type}."
            )
            log.info(f"Use the command 'nf-core {self.component_type} list' to view available software")
            return False

        if not modules_repo.component_exists(component, self.component_type):
            warn_msg = f"{self.component_type[:-1].title()} '{component}' not found in remote '{modules_repo.remote_url}' ({modules_repo.branch})"
            log.warning(warn_msg)
            return False

        return component

    def check_component_installed(self, component, current_version, component_dir, modules_repo, force, prompt, silent):
        """
        Check that the module/subworkflow is not already installed.

        Return:
            True: if the component is not installed
            False: if the component is installed
        """
        if (current_version is not None and os.path.exists(component_dir)) and not force:
            # make sure included components are also installed
            if self.component_type == "subworkflows":
                self.install_included_components(component_dir)
            if not silent:
                log.info(f"{self.component_type[:-1].title()} '{component}' is already installed.")

            if prompt:
                message = (
                    "?" if self.component_type == "modules" else " of this subworkflow and all it's imported modules?"
                )
                force = questionary.confirm(
                    f"{self.component_type[:-1].title()} {component} is already installed. \nDo you want to force the reinstallation{message}",
                    style=nf_core.utils.nfcore_question_style,
                    default=False,
                ).unsafe_ask()

            if not force:
                if not silent:
                    repo_flag = (
                        "" if modules_repo.repo_path == NF_CORE_MODULES_NAME else f"-g {modules_repo.remote_url} "
                    )
                    branch_flag = "" if modules_repo.branch == "master" else f"-b {modules_repo.branch} "

                    log.info(
                        f"To update '{component}' run 'nf-core {self.component_type} {repo_flag}{branch_flag}update {component}'. To force reinstallation use '--force'."
                    )
                return False

        return True

    def get_version(self, component, sha, prompt, current_version, modules_repo):
        """
        Get the version to install
        """
        if sha:
            version = sha
        elif prompt:
            try:
                version = prompt_component_version_sha(
                    component,
                    self.component_type,
                    installed_sha=current_version,
                    modules_repo=modules_repo,
                )
            except SystemError as e:
                log.error(e)
                return False
        else:
            # Fetch the latest commit for the module
            version = modules_repo.get_latest_component_version(component, self.component_type)
        return version

    def clean_modules_json(self, component, modules_repo, modules_json):
        """
        Remove installed version of module/subworkflow from modules.json
        """
        for repo_url, repo_content in modules_json.modules_json["repos"].items():
            for dir, dir_components in repo_content[self.component_type].items():
                for name, component_values in dir_components.items():
                    if name == component and dir == modules_repo.repo_path:
                        repo_to_remove = repo_url
                        log.debug(
                            f"Removing {self.component_type[:-1]} '{modules_repo.repo_path}/{component}' from repo '{repo_to_remove}' from modules.json."
                        )
                        modules_json.remove_entry(
                            self.component_type, component, repo_to_remove, modules_repo.repo_path
                        )
                        return component_values["installed_by"]
