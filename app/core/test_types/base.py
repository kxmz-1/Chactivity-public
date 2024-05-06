"""
Base class for all testers.
Defines basic process of testing.
"""
from abc import abstractmethod
from enum import StrEnum
from io import TextIOWrapper
import json
import os
from pathlib import Path
from pprint import pformat
import time
from traceback import print_exc
from typing import (
    ClassVar,
    Iterable,
    List,
    Literal,
    Optional,
    Self,
    Tuple,
    Dict,
    TypeAlias,
    TypedDict,
    Union,
)
import regex
from app.base.core.activity_status_memory import (
    Activity,
    Status,
    ActivityManager,
    Weight,
    WeightType,
)
from app.base.base.const import WHITELIST_APP_DURING_TESTING
from app.base.device.device_util import Device
from app.base.core.persist_knowledge import PersistKnowledge
from app.base.input_output.test_input_data import Task
from app.base.input_output.test_result import (
    PackageTestResult,
    TestingResults,
    ActivityTestResult,
)
from appium import webdriver
from rich.pretty import pretty_repr
from app.base.device.appium_util import (
    Selector,
)
from app.base.core.xml_util import (
    extract_xml_texts,
    has_same_parent,
    make_element_description,
    make_element_metadatas,
)
from app.base.llm.llm import (
    SingleContextType,
    chat_class as Chat,
    Chat as ChatClass,
    get_llm_connection_error_types,
)
from app.base.base.custom_typing import (
    ElementAndDepth,
    MixedElement,
    XmlElement,
    Xpath,
)
from app.base.base.event_handler import Events, ee, send_notification
from app.base.base.config import config
from app.base.file_analyzer.apk_util import APK
from app.base.device.adb_util import try_install as adb_try_install
from app.base.base.util import (
    clean_sentence_to_phrase,
    ensure_dir,
    ensure_file,
    get_element_exact_xpath,
    get_full_activity_name,
    get_short_activity_name,
    get_readable_time,
    is_all_desc_similar,
    random_sample_with_order,
    true,
    is_desc_similar,
    parse_regex,
)
from app.base.base.enrich import debug_print, print, debug_print_no
from app.base.device.commands import (
    command_manager,
    get_available_commands_for_xml_element,
)
from app.base.device.commands import BaseCommand
import jinja2
from app.base.base.enrich import console, print, debug_orig_print
from selenium.common.exceptions import InvalidSessionIdException
from rich import traceback

from app.base.core.record import Record
from app.base.device.commands.global_command import GlobalCommand
from app.core.custom_typing import ChoiceMappingType, LLMChoice, EnvAndAction
from app.base.base.logger import get_profiler, write_profiler_result

prompt_tmpl = jinja2.Environment(loader=jinja2.FileSystemLoader("app/prompts"))
REGEX_FLAG = regex.MULTILINE | regex.REVERSE | regex.IGNORECASE
# `regex` has reverse flag but `re` doesn't
# regex.REVERSE is used to return only the LAST one
choice_id_first: int = 0
# global_element_index: str = "-1"

prefix_for_every_description = "It is "
has_cleared_persist_knowledge: Dict[
    str, bool
] = {}  # For each package name, clear only once


class Templates(StrEnum):
    fixed_system = "fixed_system.jinja"
    before_test_ask_to_guess_goal = "before_test_ask_to_guess_goal.jinja"
    before_test_find_a_good_start = "before_test_find_a_good_start.jinja"
    before_test_think_a_idea = "before_test_think_a_idea.jinja"
    every_step_history = "every_step_history.jinja"
    every_status_ask_to_describe_status = "every_status_ask_to_describe_status.jinja"
    every_step_insert_idea = "every_step_insert_idea.jinja"
    every_step_get_action = "every_step_get_action.jinja"
    after_test_generate_activity_description = (
        "after_test_generate_activity_description.jinja"
    )

    def __repr__(self) -> str:
        """
        For Jinja2 to render
        """
        return repr(self.value)


class Chactivity:
    task_type: ClassVar[str] = "base"
    server_url: str
    capabilities: dict
    driver: webdriver.webdriver.WebDriver
    selector: Selector
    command_handlers: List[command_manager.base.BaseCommand]
    interrupt_during_testing: bool
    activity_test_result: ActivityTestResult
    aut_package_name: str
    known_activities_data: dict  # record to achieve this ; description given by LLM or human ;
    last_actions: List[EnvAndAction]
    last_actions_filter_circle_for_llm_only: List[EnvAndAction]
    record: Optional[Record]
    mapping: ChoiceMappingType = {}
    detail_log_file: Path
    detail_log_file_handle: TextIOWrapper
    status: Status
    activity: Activity
    persist_knowledge: PersistKnowledge
    idea: str
    insert_contents_for_func_call: Dict[str, str]  # tag, content
    key_ctx_for_last_step: Optional[ChatClass] = None
    time_of_step_start: float
    time_of_step_end: float = 0

    # BEGIN initailization

    def __init__(self):
        self.init_reset_test_status()

    def get_command_handler(self, command_name: str) -> BaseCommand:
        """
        Get command handler by command name
        """
        result = [i for i in self.command_handlers if i.command_name == command_name]
        if not result:
            raise ValueError("No such command name: " + command_name)
        assert len(result) == 1
        return result[0]

    def _post_connect(self):
        """
        Init some stuff (element selector, command handlers) \
        after connecting to appium server (with self.driver)
        """
        self.selector = Selector(self.driver)
        self.command_handlers = [
            cls(self.driver) for cls in command_manager.CommandManager.all_command_list
        ]

    def _pre_init_apk_process(
        self,
        package_name: Optional[str] = None,
        home_activity: Optional[str] = None,
        apk: Optional[APK] = None,
        apk_file: Optional[str] = None,
    ) -> Tuple[str, str, Optional[APK], Optional[str]]:
        """
        Parse & Verify given arguments related to APK.
        Generate needed arguments from given arguments.
        """
        if apk_file is not None:
            if apk is None:
                try:
                    apk = APK(apk_file)
                except FileNotFoundError:
                    message = f"apk_file: {apk_file} not exist! Please check your config file."
                    send_notification("error|apk_file_not_found", message)
                    raise FileNotFoundError(message)
            else:
                if os.path.abspath(apk_file) != os.path.abspath(apk.apk_path):
                    raise ValueError(
                        "Path of apk ({os.path.abspath(apk_file)}) doesn't match apk_file's path ({os.path.abspath(apk.apk_path)})"
                    )
        if (
            apk
            and apk.package_name
            and package_name
            and apk.package_name != package_name
        ):
            raise ValueError(
                "Package name given ({package_name}) doesn't match apk or apk_file's ({apk.package_name})"
            )
        if apk is None:
            if not (package_name and home_activity):
                raise ValueError(
                    "Not enough arguments provided. You should provide either (apk) or (package_name and home_activity)."
                )
        else:
            package_name = package_name or apk.package_name
            home_activity = home_activity or apk.home_activity
        assert home_activity
        return package_name, home_activity, apk, apk_file

    def init(
        self,
        device: Device,
        server_url: str = config.appium.server,
        package_name: Optional[str] = None,
        home_activity: Optional[str] = None,
        apk: Optional[APK] = None,
        apk_file: Optional[Union[str, Path]] = None,
        capabilities_mixin: Optional[dict] = None,
        known_activities_data: Optional[dict] = None,
    ) -> Self:
        """
        Set necessary attributes and init the tester.
        Create a remote appium connection and init `self.driver`

        :param server_url: The appium server url
        :param device: The target device
        :param package_name: Target app's APK instance
        :param home_activity: The begin activity of testing. Need to be exported.
        :param apk: Target app's APK instance
        :param apk_file: Target app's apk file
        :param capabilities_mixin: A dict to override the default capabilities
        """
        if isinstance(apk_file, Path):
            apk_file = str(apk_file)
        if known_activities_data is None:
            known_activities_data = {}
        if capabilities_mixin is None:
            capabilities_mixin = {}

        self.device: Device = device

        package_name, home_activity, apk, apk_file = self._pre_init_apk_process(
            package_name, home_activity, apk, apk_file
        )
        self.aut_package_name = package_name
        self.known_activities_data = known_activities_data
        clear_persist = (
            config.app.core.wipe_persist_knowledge
            and has_cleared_persist_knowledge.get(self.aut_package_name, False) is False
        )
        self.persist_knowledge: PersistKnowledge = PersistKnowledge(
            package_name=self.aut_package_name, clear=clear_persist
        )
        if clear_persist:
            has_cleared_persist_knowledge[self.aut_package_name] = True
        self.activity_manager: ActivityManager = ActivityManager(
            persist_knowledge=self.persist_knowledge,
            package_name=self.aut_package_name,
        )

        if apk_file:
            adb_try_install(
                serial=device.serial, package_name=package_name, apk_file=apk_file
            )

        capabilities = dict()
        capabilities.update(config.appium.capabilities)
        capabilities.update(device.appium_capabilities)
        capabilities.update(
            {
                "appPackage": package_name,
                "appActivity": home_activity,
                "udid": device.serial,
            }
        )
        capabilities.update(capabilities_mixin)
        self.init_driver(server_url, capabilities)
        return self

    def init_driver(self, server_url: str, capabilities: dict):
        """
        Create a remote appium connection and init `self.driver`
        """
        self.server_url = server_url
        self.capabilities = capabilities
        self.driver = webdriver.webdriver.WebDriver(
            server_url, desired_capabilities=capabilities
        )
        self._post_connect()

    # END initailization

    # BEGIN utils
    @property
    def current_activity_name(self) -> str:
        """
        Get current activity name from cached Activity object.
        """
        return self.activity.activity_name

    def get_full_activity_name(
        self, activity_name: str, package_name: Optional[str] = None
    ) -> str:
        """
        Get full activity name from the given activity name.
        If the given activity name is already full, return it directly.

        :param activity_name: activity name (e.g. .Settings)
        :param package_name: (optional) package name (e.g. com.android.settings)
        :return: full activity name (e.g. com.android.settings.Settings)
        """
        assert self.aut_package_name or package_name
        package_name = package_name or self.aut_package_name
        return get_full_activity_name(
            package_name=package_name, activity_name=activity_name
        )

    def get_short_activity_name(
        self, activity_name: str, package_name: Optional[str] = None
    ) -> str:
        """
        Get short activity name from the given activity name.
        If the given activity name is already short, return it directly.

        :param activity_name: activity name (e.g. com.android.settings.Settings)
        :param package_name: (optional) package name (e.g. com.android.settings)
        :return: short activity name (e.g. .Settings)
        """
        assert self.aut_package_name or package_name
        package_name = package_name or self.aut_package_name
        return get_short_activity_name(
            package_name=package_name, activity_name=activity_name
        )

    def get_current_activity_name_from_appium(
        self, current_package_from_appium: Optional[str] = None
    ) -> str:
        """
        Get full current activity name from Appium.

        :param package_name: (optional) package name (e.g. com.android.settings)
        :return: full activity name (e.g. com.android.settings.Settings)
        """
        if current_package_from_appium is None:
            current_package_from_appium = self.driver.current_package
        return self.get_full_activity_name(
            activity_name=self.driver.current_activity,
            package_name=current_package_from_appium,
        )

    @property
    def step_count(self) -> int:
        """
        Get current step count from `self.activity_test_result`.
        """
        return self.activity_test_result.step_count

    def back_to_app(self, package_name: Optional[str] = None) -> None:
        """
        Bring an app to foreground, without restarting it.

        :param package_name: Package name, leave it None for AUT.
        """
        if package_name is None:
            package_name = self.aut_package_name
        self.driver.activate_app(package_name)

    def back_to_app_if_current_package_invalid(
        self,
        delay: float = 5,
        back_limit: int = 5,
        current_package_name: Optional[str] = None,
    ) -> bool:
        """
        First, detect if current package is our AUT or in whitelist (camera, file selection...)
        If not, try `back button` & `self.back_to_app` to bring AUT to foreground, \
        without restarting it.
        If failed, raise RuntimeError.

        :param delay: delay before checking our process and send a back command
        :param back_limit: max times sending back command
        :raises RuntimeError: if failed to bring AUT to foreground
        :return: whether success or not
        """

        def is_success(package_name: Optional[str] = None) -> bool:
            """
            Check if the current package is our AUT or in whitelist
            """
            if package_name is None:
                package_name = self.driver.current_package
            return package_name in (
                {self.aut_package_name} | WHITELIST_APP_DURING_TESTING
            )

        if is_success(current_package_name):
            return False

        count = 0
        self.back_to_app()
        while not (success := is_success()) and count < back_limit:
            time.sleep(delay)
            self.driver.back()
            count += 1
        if not success:
            self.back_to_app()
            time.sleep(delay)
        count = 0
        while not (success := is_success()) and count < back_limit:
            time.sleep(delay)
            self.driver.back()
            count += 1
        if not is_success():
            raise RuntimeError(
                f"Failed to bring AUT to foreground\nCurrent Package: {self.driver.current_package}, Current Activity: {self.driver.current_activity}"
            )
        return True

    @staticmethod
    def render_template(template: Templates, **kwargs) -> str:
        """
        Alias for Jinja2 template rendering
        """
        return prompt_tmpl.get_template(template).render(**kwargs)

    # END utils

    # BEGIN record-related stuff (see activity_knowledge.py)

    @property
    def require_app_first_init(self) -> bool:
        """
        Detect if the app should be initialized manually before testing.
        Stored in ActivityPath for further reproduction.
        """
        return self.capabilities.get("noReset", False)

    @property
    def require_app_homepage(self) -> bool:
        """
        Detect if the app should be at homepage before testing.
        Stored in ActivityPath for further reproduction.
        """
        return True

    # END record-related stuff

    # BEGIN reset after each task

    def _restart_app(self, new_session: bool = False):
        """
        Restart AUT
        """
        if new_session:
            try:
                self.driver.quit()
            except InvalidSessionIdException:
                pass
            self.init_driver(self.server_url, self.capabilities)
        else:
            try:
                self.driver.close_app()
                self.driver.launch_app()
            except InvalidSessionIdException:
                self.init_driver(self.server_url, self.capabilities)

    def reset_after_each_task(self):
        """
        Reset the tester with extra cleanup and init stuff.
        Should be called after each test task (except the last one).
        """
        self.init_reset_test_status()
        self.activity_manager.reset_all_known_activity()
        self.activity_manager.set_human_description(self.known_activities_data)
        self._restart_app()

    def init_reset_test_status(self):
        """
        Reset the tester with extra cleanup and init stuff.
        Should be called before each test task.
        """
        self.interrupt_during_testing = False
        # self.known_activities_data = {}
        self.last_llm_context = []
        self.last_actions = []
        self.last_actions_filter_circle_for_llm_only = []
        self.record = None
        self.start_time: float = time.time()
        self._init_detail_log()
        self.insert_contents_for_func_call = {}

    def _init_detail_log(self):
        """
        Init the detail log file Markdown file.
        """
        if not config.app.log.detail_step_log_file:
            return
        self._try_close_detail_log()
        self.detail_log_file = ensure_file(
            get_readable_time(config.app.log.detail_step_log_file)
        )
        self.detail_log_file_handle = open(self.detail_log_file, "w", encoding="utf-8")

    def _try_close_detail_log(self):
        """
        Close the detail log file Markdown file.
        """
        if (
            getattr(self, "detail_log_file_handle", None)
            and not self.detail_log_file_handle.closed
        ):
            self.detail_log_file_handle.close()
            log_file: str = str(self.detail_log_file)
            ret = os.system(
                f"pandoc \"{log_file}\" -o \"{log_file.removesuffix('.md')}.html\""
            )
            if ret == 0:
                os.remove(log_file)

    # END reset after each task

    # BEGIN testing log stuff

    @property
    @abstractmethod
    def goal_pretty_name(self) -> str:
        """
        Get a pretty name of `self.goal` to display in logs.
        """
        raise NotImplementedError

    def _log_step(
        self,
        context: Optional[ChatClass],
        env_and_action: EnvAndAction,
    ):
        """
        Write the step detail to Markdown file after each step.
        """
        assert self.record is not None
        # Metadata at the begin of the file
        if self.detail_log_file_handle.tell() == 0:
            self.detail_log_file_handle.write(
                "# Metadata\n\n"
                + f"- Device serial: {self.device.serial}\n\n"
                + f"- Package name: {self.aut_package_name}\n\n"
                + f"- Start time: {get_readable_time(current_time=self.start_time, format='%Y-%m-%d %H:%M:%S')}\n\n"
                + f"- Target: {self.goal_pretty_name}\n\n"
            )
        # Step title
        self.detail_log_file_handle.write(f"## Step {self.step_count}\n\n")
        # LLM context
        self.detail_log_file_handle.write(f"### LLM context of {self.step_count}\n\n")
        self.detail_log_file_handle.write("```python\n")
        if context is None:
            self.detail_log_file_handle.write(f"None (back to previous page)\n")
        else:
            self.detail_log_file_handle.write(
                f"{pformat(context.prompts).replace('```', '`-`-`')}\n"
            )
        self.detail_log_file_handle.write("```\n\n")
        # Time cost
        self.detail_log_file_handle.write(f"### Time cost of {self.step_count}\n\n")
        self.detail_log_file_handle.write(
            f"{self.time_of_step_end-self.time_of_step_start:.2f}\n\n"
        )
        # Description
        self.detail_log_file_handle.write(f"### Description of {self.step_count}\n\n")
        self.detail_log_file_handle.write(
            f"Our: {env_and_action.fixed_operation_description}\n\n"
        )
        # Screenshot
        self.detail_log_file_handle.write(
            f"### Screenshot after action of {self.step_count}\n\n"
        )
        self.detail_log_file_handle.write(
            f'<img src="data:image/png;base64,{self.driver.get_screenshot_as_base64()}" width="30%" align="center" />\n\n'
        )
        # Flush to file
        self.detail_log_file_handle.flush()

    def _log_result(self, result: TestingResults) -> TestingResults:
        """
        Write the result to Markdown file after each test task.
        Should be the last log in the Markdown file.
        """
        assert self.record is not None
        self.detail_log_file_handle.write(f"## Result\n\n")
        self.detail_log_file_handle.write(f"{result.name}\n")
        self.detail_log_file_handle.flush()
        return result

    def _testing_interrupt_with_error(
        self,
        error: str,
        is_llm_reason: bool,
        status_code: TestingResults,
        with_full_llm_context: Optional[bool] = None,
        with_traceback: bool = False,
        notification_type: Optional[str] = "error",
    ) -> TestingResults:
        """
        Used when whole testing or single step is interrupted by error, \
        and show optional error message and traceback.
        Usage: `return self._testing_interrupt_with_error(...)`

        :param error: error message
        :param is_llm_reason: whether the error is from mistaken understanding of LLM (not including BADGOAL). Doesn't include auth error, network error, etc.
        :param status_code: status code to return
        :param with_full_llm_context: whether to show full LLM context or only the last one, None to don't show
        :param with_traceback: whether to show traceback
        :param notification_type: notification type, None to don't show
        """
        notification_content = error
        if is_llm_reason:
            assert status_code & TestingResults.LLM_REPLY_WRONG_RETRY
            if with_full_llm_context is None:
                with_full_llm_context = (
                    True  # full context is needed for LLM error by default
                )
        if with_full_llm_context is not None:
            # insert LLM context
            if not self.last_llm_context:
                notification_content += "\nLLM Context is None"
            else:
                if with_full_llm_context is True:
                    notification_content += (
                        "\nLLM Context:\n```python\n"
                        + pretty_repr(self.last_llm_context)
                        + "\n```"
                    )
                else:
                    notification_content += (
                        "\nLast LLM Message:\n```python\n"
                        + pretty_repr(self.last_llm_context)
                        + "\n```"
                    )
        if notification_type:
            ee.emit(Events.onNotification, notification_type, notification_content)
        if with_traceback:
            ee.emit(Events.onNotification, "info", "Exception:")
            ee.emit(
                Events.onNotification,
                "info",
                content="",
                extra_rich_printable_stuff=[
                    traceback.Traceback(show_locals=True),
                ],
                no_content=True,
            )
        return status_code

    # END testing log stuff

    # BEGIN core - prompt generator

    def generate_status_description(self) -> Optional[ChatClass]:
        """
        Fetch all texts from current status and ask LLM to describe it (or to say, summarize).
        """
        if not config.app.core.enable_description_generation:
            return None
        if self.step_count == 0 or (
            self.step_count > 0 and self.status != self.last_actions[-1].status
        ):
            current_activity = self.current_activity_name
            state = "\n".join([i.prompt for i in self.mapping.values()])
            last_activity = ""
            last_status_description = ""
            if self.last_actions:
                if self.last_actions[-1].activity != self.activity:
                    last_activity = self.last_actions[-1].activity.activity_name
                last_status_description = self.last_actions[-1].status.description
            content = self.render_template(
                Templates.every_status_ask_to_describe_status,
                current_activity=current_activity,
                state=extract_xml_texts(self.status.xml_tree),
                last_activity=last_activity,
                last_status_description=last_status_description,
                this_status_description=self.status.description,
                prefix=prefix_for_every_description,
            )
            ctx = (
                Chat()
                .system(
                    self.render_template(
                        Templates.fixed_system,
                    )
                )
                .user(
                    content
                )  # remember to change _testing_construct_context if you change this!
            )
            self.status.description = clean_sentence_to_phrase(
                prefix=prefix_for_every_description,
                sentence=ctx.ask(save_to_context=True),
            )
            ctx.add_to_cache()
            debug_print_no(self.status.description)
            return ctx
        return None

    @abstractmethod
    def generate_goal_description(self) -> None:
        """
        If the goal description is not given, ask LLM to guess the goal.
        Set `self.goal_description` to the guessed goal.
        e.g. for `.SettingsActivity`, the answer should be `for editing settings`
        """
        raise NotImplementedError

    def _make_global_prompts(self) -> ChoiceMappingType:
        """
        Generate the lines for global commands in our provided element list.
        Always empty for now (global command `back` is specially treated).
        """
        global_commands: List[GlobalCommand] = [i for i in self.command_handlers if i.perform_on_global]  # type: ignore
        self.global_mappings = {}
        self.all_global_mappings = {}
        for global_command in global_commands:
            choice = LLMChoice(
                prompt_index=global_command.command_name,
                element=None,
                element_desc=global_command.prompt_description_in_elements,
                commands=[global_command.command_name],
                depth=0,
                operated_before=False,
            )
            self.all_global_mappings[global_command.command_name] = choice
            if (
                self.status.element_weights.get(global_command.command_name)
                != Weight.DISABLED_FOREVER
            ):
                self.global_mappings[global_command.command_name] = choice
        return {}

    def get_element_commands(self, current_element: XmlElement) -> List[str]:
        """
        Get the commands' names available on given element (not including global commands)
        """
        commands_list_include_false: List[Union[str, Literal[False]]] = [
            (
                i.get_prompt_element_description(
                    MixedElement(xml_element=current_element, web_element=None)
                )
            )
            for i in self.command_handlers
            if i.perform_on_element
        ]
        commands_list: List[str] = [i for i in commands_list_include_false if i]
        return commands_list

    def _make_global_and_elements_prompt(self) -> None:
        """
        Generate the prompt of current available elements & global commands
        """
        self.mapping = {}
        mapping = self.mapping

        # ======
        # Check commands available on global
        # ======

        global_mapping = (
            self._make_global_prompts()
        )  # always empty, see _make_global_prompts for details
        index: int = (
            int(list(global_mapping.keys())[-1]) + 1
            if global_mapping
            else choice_id_first
        )
        mapping.update(global_mapping)

        # ======
        # Parse layout xml and find the actionable elements
        # ======

        self.status.init_element_tree()
        count_all = len(list(self.status.get_elements(disable_weight=True)))
        key_elements = list(self.status.get_elements())
        count_first_choice = len(key_elements)
        if not key_elements:
            key_elements = list(self.status.get_elements(disable_weight=True))
        debug_print_no(
            f"WeightBan (Status) - {count_all} -> {count_first_choice} (Finally: {len(key_elements)})"
        )

        # ======
        # If continuous elements have same resource-id, only keep the first `max_allow_continuous_same_resource_id` elements
        # ======

        if config.app.core.filter_continuous_same_elements:
            count_1 = len(key_elements)
            key_elements = self._make_global_and_elements_prompt_filter_same(
                key_elements
            )
            count_2 = len(key_elements)
            debug_print_no(f"FilterSame - {count_1} -> {count_2}")
        count_2 = len(key_elements)

        # ======
        # If there are any text without text inputed, require text input before any other action
        # ======

        has_no_inputed_text = any(
            1
            for i, _ in key_elements
            if (
                ("input" in get_available_commands_for_xml_element(i))
                and (
                    (
                        text := self.activity_manager.filled_text_for(
                            make_element_description(i, ignore_text_for_inputable=True)
                        )
                    )
                    is None
                )
            )
        )

        debug_print_no(f"{has_no_inputed_text=}")

        # ======
        # Generate prompts for each actionable element
        # ======
        for current_element, key_depth in key_elements:
            current_element: XmlElement
            key_depth: int
            element_desc = make_element_description(current_element)
            commands_list = self.get_element_commands(current_element)
            # filter out leaf nodes without text description
            if (
                not element_desc
                and int(current_element.get("child_key_count", "")) == 0
            ):
                continue
            # filter based on global weight
            for command in commands_list[:]:
                if not self.activity_manager.should_show_action(
                    current_element, command
                ):
                    commands_list.remove(command)
                    send_notification(
                        "info|global_weight_ban",
                        f"due to global weight, hide {command} on {element_desc}",
                    )
            if has_no_inputed_text:
                if (
                    "input" in commands_list
                    and self.activity_manager.filled_text_for(
                        make_element_description(
                            current_element, ignore_text_for_inputable=True
                        )
                    )
                    is None
                ):
                    commands_list = ["input"]
                else:
                    commands_list = []
                    self.insert_contents_for_func_call[
                        "no_inputed_box"
                    ] = "Please note that some input boxes has not been inputed, you must fill they in to perform any other action."
            # filter out nodes without any command
            if not commands_list:
                continue
            while (
                (last_index := str(index - 1)) in mapping
                and not mapping[last_index].is_global
                and mapping[last_index].element_desc == ""
                and mapping[last_index].depth >= key_depth
            ):
                mapping.pop(last_index)
                index -= 1  # if last one has no desc and this one is not its child, just ignore last one.
            choice = LLMChoice(
                prompt_index=str(index),
                element=current_element,
                element_desc=element_desc,
                commands=commands_list,
                depth=key_depth,
                operated_before=(
                    make_element_description(
                        current_element, ignore_text_for_inputable=True
                    )
                    in self.activity.activity_manager.operated_elements_description
                ),
            )
            mapping[str(index)] = choice
            index += 1
            current_element.attrib["prompt"] = choice.prompt_without_index
        # Remove last elements if they don't have description
        while (
            (last_index := str(index - 1)) in mapping
            and not mapping[last_index].is_global
            and mapping[last_index].element_desc == ""
        ):
            mapping.pop(last_index)
            index -= 1  # if last one has no desc, just ignore last one.

        # Set prompt attribute for elements excluded from mapping
        for element, key_depth in self.status.get_elements(disable_weight=True):
            if "prompt" not in element.attrib:
                element_desc = make_element_description(element)
                element.attrib["prompt"] = LLMChoice(
                    prompt_index=-1,
                    element=element,
                    element_desc=element_desc,
                    commands=self.get_element_commands(element),
                    depth=key_depth,
                    operated_before=(
                        make_element_description(
                            element, ignore_text_for_inputable=True
                        )
                        in self.activity.activity_manager.operated_elements_description
                    ),
                ).prompt_without_index
        debug_print_no(
            f"WeightBan + MappingBan - {count_2} (and global {len(global_mapping)}) -> {len(mapping)-len(global_mapping)} (and global {len(global_mapping)})"
        )
        # assert mapping
        self.mapping = mapping

    def _make_global_and_elements_prompt_filter_same(
        self,
        key_elements: Iterable[ElementAndDepth],
        max_allow_same_count: int = 5,
    ) -> List[ElementAndDepth]:
        """
        Invoked at the end of _make_global_and_elements_prompt, filter out elements with same resource-id.
        Keep only little same elements from key_elements for better performance.
        """
        # debug_print(key_elements)
        res_id_str = "resource-id"
        last_res_id: Optional[str] = None
        last_key_depth: Optional[int] = None
        last_element: Optional[XmlElement] = None
        key_elements_filter_duplicate: List[ElementAndDepth] = []
        same_elements: List[ElementAndDepth] = []

        def push_all_staged_elements():
            """
            Call when finishing finding a group of same elements, randomly select some of them to keep.
            """
            nonlocal same_elements
            max_allow_same_count_override: int = max_allow_same_count
            descs = [make_element_description(i[0]) for i in same_elements]
            if is_all_desc_similar(descs):
                max_allow_same_count_override = min(3, max_allow_same_count)
                # if all elements have same description (which is identical to LLM), only keep 3 of them

            key_elements_filter_duplicate.extend(
                random_sample_with_order(same_elements, max_allow_same_count_override)
            )
            same_elements = []

        for current_element, key_depth in key_elements:
            current_element: XmlElement
            key_depth: int
            res_id: Optional[str] = current_element.get(res_id_str)
            debug_print_no((res_id, key_depth, current_element.getparent()))
            if last_element is not None:
                if (
                    res_id == last_res_id
                    and key_depth == last_key_depth
                    and has_same_parent(current_element, last_element)
                    and current_element.get("class") == last_element.get("class")
                    and int(current_element.get("child_key_count", "0")) == 0
                ):
                    debug_print_no("yes they are the same!")
                else:
                    push_all_staged_elements()
            same_elements.append((current_element, key_depth))
            last_res_id = res_id
            last_key_depth = key_depth
            last_element = current_element
        push_all_staged_elements()
        return key_elements_filter_duplicate

    # END core - prompt generator

    # BEGIN main entry point, detect success & failure

    def do_test_for_all_targets(
        self, targets_inside: List[Task], package_test_result: PackageTestResult
    ) -> PackageTestResult:
        """
        Receive a list of targets, and test them one by one.
        Return a `PackageTestResult` with all `ActivityResult` included.
        """
        targets_length = len(targets_inside)
        for i, target in enumerate(targets_inside):
            ee.emit(
                Events.onNotification,
                "info|single_job_test_process",
                f"[{i+1}/{targets_length}] Begin testing on {target}",
            )

            try:
                profiler = get_profiler()
                with profiler:
                    activity_test_result = self.do_test_for_single_target(target)
                write_profiler_result(profiler=profiler, prefix="single-")
            except Exception as e:
                ee.emit(
                    Events.onNotification,
                    "error",
                    f"[{i+1}/{targets_length}] !!!Uncaught error raised!!!Error occurred: {e}",
                )
                print_exc()
                raise AssertionError from e
            if (
                getattr(self, "detail_log_file_handle", None)
                and not self.detail_log_file_handle.closed
            ):
                self._log_result(activity_test_result.status)
                self._try_close_detail_log()
            self.summarize_and_review_after_each_task(activity_test_result)
            self.write_full_json_log_for_last_task()
            package_test_result.append(activity_test_result)
            ee.emit(
                Events.onNotification,
                ("success" if activity_test_result.successful else "error")
                + "|single_job_test_result",
                f"[{i+1}/{targets_length}] End testing on {target} | Result: {activity_test_result.result_symbol} | Time elapsed: {activity_test_result.total_time:.0f}",
            )
            if i != targets_length - 1:  # skip initailization for the last task
                self.reset_after_each_task()
        package_test_result.end()
        return package_test_result

    @abstractmethod
    def on_success(self) -> None:
        """
        Called when the test is successful.
        """
        raise NotImplementedError

    def do_test_for_single_target(self, task: Task) -> ActivityTestResult:
        """
        Receive a single target, and test it.
        Cannot be multi-threaded for the same AUT.
        """
        assert getattr(self, "driver", None), RuntimeError(
            "You must call init() or related functions before do_test_for_single_target()"
        )
        self.task = task
        self.check_single_task(task)
        self._pre_single_task(task)
        activity_test_result = ActivityTestResult(
            activity_name=task.target["activity_name"],
            device_serial=self.device.serial,
            package_name=self.aut_package_name,
            package_version=None,
        )
        self.activity_test_result = activity_test_result
        try:
            # time1 = time.time()
            self.generate_goal_description()
            # self.generate_idea()
            self.idea = ""
            send_notification(
                "info|before_core_step|current_goal",
                f"Current goal:{self.goal_pretty_name}",
            )
            # time2 = time.time()
            # send_notification(
            #     "info|before_core_step|goal_description|timeit",
            #     f"Time cost for generating goal description: {time2-time1:.2f} seconds",
            # )
            # time1 = time.time()
            if config.app.core.find_a_good_start:
                self.llm_find_a_good_start_activity()
                # time2 = time.time()
                # send_notification(
                #     "info|before_core_step|good_start|timeit",
                #     f"Time cost for finding a good start: {time2-time1:.2f} seconds",
                # )
            while not self.is_successful():
                if (failed_result := self.is_failed()) is not False:
                    return activity_test_result.end(failed_result)
                self.time_of_step_start = time.time()
                step_result = self._core_step()
                self.time_of_step_end = time.time()
                if (not self.interrupt_during_testing) and self.last_actions:
                    self._log_step(self.key_ctx_for_last_step, self.last_actions[-1])
                if (
                    handle_result := self._handle_single_step_return_if_failed(
                        step_result
                    )
                ) is not None:
                    return activity_test_result.end(handle_result)
            else:
                self.on_success()
                ee.emit(Events.onNotification, "success", "[+] Testing successful!")
                # ee.emit(
                #     Events.onNotification,
                #     "info|success_record",
                #     "Record:\n```python\n"
                #     + str(activity_test_result.record.to_dict())
                #     + "\n```",
                # )
                return activity_test_result.end(TestingResults.RETURN_SUCCESSFUL)
        except InvalidSessionIdException:
            ret = self._testing_interrupt_with_error(
                error="[-] Testing interrupted! (Session died)",
                is_llm_reason=False,
                status_code=TestingResults.RETURN_SESSION_DIED,
                with_full_llm_context=True,
                with_traceback=True,
                notification_type="error",
            )
            return activity_test_result.end(ret)
        except get_llm_connection_error_types():
            ret = self._testing_interrupt_with_error(
                error="[-] Testing interrupted! (LLM connection error)",
                is_llm_reason=False,  # it's True, as it is not a wrong reply
                status_code=TestingResults.RETURN_NETWORK_ERROR,
                with_full_llm_context=True,
                with_traceback=True,
                notification_type="error",
            )
            return activity_test_result.end(ret)
        except Exception:  # noqa
            ret = self._testing_interrupt_with_error(
                error="[-] Poor Code Quality!!!Uncaught error raised when testing!!!",
                is_llm_reason=False,
                status_code=TestingResults.RETURN_ERROR,
                with_full_llm_context=True,
                with_traceback=True,
                notification_type="error",
            )
            # if we are in fail-fast mode, stop program for debugging
            ee.emit(Events.failFast)
            return activity_test_result.end(ret)

    # END main entry point

    # REWRITE EVERYTHING IN SUBCLASSES!
    @abstractmethod
    def is_successful(self) -> bool:
        """
        Detect if the test should be abort because task achieved.
        """
        raise NotImplementedError

    def is_failed(self) -> Union[Literal[False], TestingResults]:
        """
        Detect if the test should be abort because task failed (hit any limits for testing).
        Called before each step.

        :return: False if not failed, otherwise return the TestingResult
        """
        delta_time = time.time() - self.start_time
        if (
            self.step_count >= config.app.core.max_step
            or delta_time > config.app.core.max_time
        ):
            if self.step_count >= config.app.core.max_step:
                hint = f"max_step({config.app.core.max_step})"
                ret = TestingResults.RETURN_MAX_STEP_REACHED
            else:  # timeout
                hint = f"max_time({config.app.core.max_time})"
                ret = TestingResults.RETURN_MAX_TIME_REACHED
            ee.emit(
                Events.onNotification,
                "error",
                f"[-] Testing failed! ({hint})\n{config.app.core.max_step} attempts in {delta_time} sceonds have been made, but the goal is not achieved.",
            )
            return ret
        return False

    @abstractmethod
    def _handle_single_step_return_if_failed(
        self, work_result: TestingResults
    ) -> Union[TestingResults, None]:
        """
        Process the return value of `_core_step`, and return the status code if failed.

        :return: False if not failed, otherwise return the status code
        """
        raise NotImplementedError

    #    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
    @abstractmethod
    def _core_step(self) -> TestingResults:
        """
        The core logic for a step (element selection, action, description, etc.)

        :return: status code of current activity testing status, \
        indicating whether the step is normally finished or not (e.g. LLM reply wrong, network error, etc.)
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def check_single_task(cls, task: Task) -> None:
        """
        Check if the task is valid, raise ValueError if not.
        """
        raise NotImplementedError

    def _pre_single_task(self, task: Task) -> None:
        """
        Do some preparation before do_test_for_single_target was executed, such as editing task.
        """
        pass

    @abstractmethod
    def global_init_by_task(self, task: Task, device: Device) -> Self:
        """
        Set necessary attributes based on the task and chosen device.
        All sequent task should have similar attributes (e.g. Appium capabilities, package name).
        """
        raise NotImplementedError

    def generate_activity_description(self, activity: Activity) -> Optional[str]:
        """
        Generate a description for the given activity based on all status explored.
        If there is only one status, return it directly.
        If there are multiple status, ask LLM to summarize them.
        If there is none status, return None.
        """
        if not config.app.core.enable_description_generation:
            return None
        status_descriptions = [
            status.description for status in activity.statuses if status.description
        ]
        if not status_descriptions:
            return None
        if len(status_descriptions) == 1:
            return status_descriptions[0]
        else:
            ctx = (
                Chat()
                .system(
                    self.render_template(
                        Templates.fixed_system,
                    )
                )
                .user(
                    prompt_tmpl.get_template(
                        Templates.after_test_generate_activity_description
                    ).render(
                        status_descriptions=status_descriptions,
                        activity_name=self.get_short_activity_name(
                            activity.activity_name
                        ),
                        package_name=self.aut_package_name,
                        prefix=prefix_for_every_description,
                    )
                )
            )
            answer = clean_sentence_to_phrase(
                prefix=prefix_for_every_description, sentence=ctx.ask()
            )
            ctx.add_to_cache()
            return answer

    @abstractmethod
    def summarize_and_review_after_each_task(self, result: ActivityTestResult) -> None:
        """
        Set persistent knowledge based on the decisions and results of current finished task.
        """
        raise NotImplementedError

    @abstractmethod
    def llm_find_a_good_start_activity(self) -> None:
        """
        Ask LLM to start from a activity associated with the goal, and try to achieve the selected activity if possible.
        If any error occurred or the selected activity is not achieved, ignore it and continue or relaunch AUT (randomly selected).
        If success, reinitalize record, status, etc.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_idea(self) -> None:
        """
        Generate a detailed way to achieve the goal.
        Disabled due to lack of accuracy.
        """
        raise NotImplementedError

    @abstractmethod
    def generate_full_json_log_for_last_task(self) -> dict:
        """
        Dump target, steps, metadatas, results and other information to a dict.
        """
        raise NotImplementedError

    def write_full_json_log_for_last_task(self) -> None:
        """
        Write the full json log for current finished task to a file.
        """
        if not config.app.log.result_json_file:
            return
        with open(
            ensure_file(get_readable_time(config.app.log.result_json_file)),
            "w",
            encoding="utf-8",
        ) as f:
            json.dump(
                self.generate_full_json_log_for_last_task(),
                f,
                indent=4,
                ensure_ascii=False,
            )

    @property
    def last_llm_context(self) -> List[SingleContextType]:
        return self._last_llm_context

    @last_llm_context.setter
    def last_llm_context(self, value):
        self._last_llm_context = value
        with open(
            ensure_file("results/running/llm_context.json"), "w", encoding="utf8"
        ) as f:
            json.dump(value, f, indent=4, ensure_ascii=False)
