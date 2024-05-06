"""
Implement the test type `act2act`.
This test type is used to navigate to a specific activity based on \
its `name` and (optional, ~5 words) `description`.
"""
import time
from typing import Literal, NotRequired, TypedDict, Union

from app.base.input_output.test_result import TestingResults
from .base import (
    Chactivity,
    REGEX_FLAG,
    ChoiceMappingType,
    EnvAndAction,
    prompt_tmpl,
    LLMChoice,
    Templates,
    prefix_for_every_description,
)
from .test_manager import TestManager
import json
from typing import List, Literal, Optional, Self, Tuple, Dict, TypeAlias, Union
import regex
from app.base.core.activity_status_memory import (
    DEFAULT_STATUS_LEVEL,
    Activity,
    Status,
    Weight,
)
from selenium.common.exceptions import (
    TimeoutException,
    InvalidElementStateException,
    StaleElementReferenceException,
)
from app.base.llm.llm import (
    ParsedFuncitonCall,
    chat_class as Chat,
    Chat as ChatClass,
    get_llm_connection_error_types,
    string_to_function_calls,
)
from app.base.base.custom_typing import MixedElement, XmlElement, Xpath, WebElement
from app.base.base.event_handler import Events, ee, send_notification
from app.base.base.config import config
from app.base.base.util import (
    parse_regex,
)
from app.base.base.enrich import debug_print, print, debug_print_no
from app.base.core.activity_knowledge import ActivityPath
from app.base.device.commands import command_manager
from lxml import etree
from app.base.core.record import Record

parse_element_pattern = regex.compile(r"INDEX-(\d+|BADGOAL)", REGEX_FLAG)


class TargetType(TypedDict):
    activity_name: str
    description: NotRequired[Optional[str]]


@TestManager.register
class Act2Act(Chactivity):
    task_type = "act2act"
    goal_activity_name: str
    goal_description: Optional[str] = None
    llm_start_activity: Optional[str] = None
    function_call_queue: List[ParsedFuncitonCall]

    def is_successful(self):
        known_paths = self.persist_knowledge.get_activity_paths()
        if self.goal_activity_name in known_paths:
            send_notification(
                "warning|goal_activity_known", f"Current goal {self.goal_activity_name} is already achieved before, pass."
            )
            return True
        return self.get_current_activity_name_from_appium() == self.goal_activity_name

    def is_failed(self) -> TestingResults | Literal[False]:
        return super().is_failed()

    @property
    def goal_pretty_name(self):
        return self.goal_activity_name

    def _handle_single_step_return_if_failed(
        self, work_result: TestingResults
    ) -> Union[TestingResults, None]:
        if work_result & TestingResults.BADGOAL:
            return TestingResults.RETURN_BADGOAL
        assert work_result & TestingResults.UNFINISHED, ValueError(
            "work_result should be UNFINISHED if not BADGOAL"
        )
        if work_result & TestingResults.LLM_REPLY_WRONG_RETRY:
            self.activity_test_result.llm_reply_wrong_retry_count += 1
            if (
                self.activity_test_result.llm_reply_wrong_retry_count
                >= config.app.core.abort_activity_test_on_llm_error_count
            ):
                ee.emit(
                    Events.onNotification,
                    "error",
                    "[-] ",
                )
                return TestingResults.RETURN_MAX_LLM_ERROR_REACHED
        return None

    def _init_activity_and_status(self):
        """
        Get current activity and status from Appium, and init `self.activity` and `self.status`.
        """
        package_name = self.driver.current_package
        self.activity: Activity = self.activity_manager.get_activity(
            package_name=package_name,
            activity_name=self.get_current_activity_name_from_appium(
                current_package_from_appium=package_name
            ),
        )
        xml: str = self.driver.page_source
        xml_tree = etree.fromstring(xml.encode("utf-8"))
        self.status: Status = self.activity.add_status(
            xml, xml_tree, step_count=self.activity_test_result.step_count
        )

    def _init_record(self):
        """
        Init `self.record` based on current activity and status if not exists.
        """
        if self.record is None:
            self.record: Record = self.activity_test_result.record.set_source(
                activity=self.current_activity_name,
                status=self.status.hash,
            )

    def on_success(self):
        self._update_status_before_each_step(is_successful=True)

    def _update_status_before_each_step(self, is_successful: bool = False) -> None:
        """
        Called before each step.
        Init status and activity, and update record based on previous action.
        Analyzation of valid elements, update of weights are done here.

        If is_successful is True, then we only need to memorize the current status.
        """
        self.current_package_name: str = self.driver.current_package
        if not is_successful:
            has_package_changed = self.back_to_app_if_current_package_invalid(
                current_package_name=self.current_package_name
            )
            if (
                has_package_changed is True
            ):  # this action upexpected changed package, and shold be blocked.
                self.current_package_name = self.driver.current_package
                last_stat = self.last_actions[-1] if self.last_actions else None
                if last_stat:
                    if last_stat.element is not None:
                        last_stat.status.activity.activity_manager.global_ban_action(
                            last_stat.element,
                            last_stat.command,
                        )
                    else:
                        assert last_stat.command == "back"
                        last_stat.status.single_ban_element(last_stat.command)
                time.sleep(2)
                if self.last_actions:
                    self.last_actions.pop()  # remove the last action which caused package change
        self._init_activity_and_status()
        self._init_record()
        if not self.interrupt_during_testing:
            # an action has been performed successfully
            last_stat = self.last_actions[-1] if self.last_actions else None
            assert self.record is not None
            if last_stat:  # at least 1 action executed
                # set `useful`
                useful: bool = False
                if last_stat.status != self.status:
                    # if status changed, then we consider it useful
                    useful = True
                elif last_stat.element is not None:
                    if any(
                        [i for i in self.mapping.values() if "input" in i.commands]
                    ) and last_stat.command in ("click", "submit", "input"):
                        # if last action is performed when there is an input element, and the action is click or submit or input, then we consider it useful
                        useful = True
                        # we now force everything inputed before other steps
                # update weights
                if last_stat.element is not None:
                    last_stat.status.on_element_action(
                        last_stat.element,
                        step_number=self.activity_test_result.step_count,
                        new_status=self.status,
                        command=last_stat.command,
                        useful=useful,
                        extra=last_stat.extra,
                    )
                # add action to record only when status changed
                if useful:
                    self.record.add(
                        last_stat.command,
                        self.get_full_activity_name(last_stat.activity.activity_name),
                        self.get_full_activity_name(self.activity.activity_name),
                        last_stat.xpath,
                        last_stat.extra,
                        last_stat.status.hash,
                        self.status.hash,
                        self.last_actions[-1].description_for_llm,
                    )
                # remember the last action
                activity_path: ActivityPath = ActivityPath(
                    self.aut_package_name,
                    self.current_activity_name,
                    self.record.copy().end(),
                    self.require_app_first_init,
                    self.require_app_homepage,
                )
                self.activity.add_activity_knowledges(activity_path)
                self.persist_knowledge.add_activity_path(activity_path)
        self._make_global_and_elements_prompt()

    def generate_goal_description(self):
        if self.goal_description is not None:
            return
        content = self.render_template(
            Templates.before_test_ask_to_guess_goal,
            goal_activity_name=self.goal_activity_name,
            prefix=prefix_for_every_description,
        )
        ctx = Chat()
        ret = (
            ctx.system(
                self.render_template(
                    Templates.fixed_system,
                )
            ).user(content)
        ).ask()
        ret.removeprefix(prefix_for_every_description).strip(".").strip()
        ctx.add_to_cache()
        self.goal_description = " ".join(ret.split("\n"))
        send_notification(
            "info|goal_description",
            f"Goal description for {self.goal_activity_name} is \"{self.goal_description}\" by LLM",
        )

    def _testing_construct_context(
        self,
        status_content_ctx: Optional[ChatClass] = None,
    ) -> Union[Tuple[LLMChoice, str, dict, Optional[ChatClass]], TestingResults]:
        """
        Based on current status (mappings for elements and global commands, description), \
        invoke LLM to get the action to perform.
        Return the action to perform, or TestingResults if failed.

        :return: (choice (metadata for selected element), command, extra_data, chat_instance) or TestingResults
        """
        elements_prompt = "\n".join([i.prompt for i in self.mapping.values()])
        debug_print_no(f"{elements_prompt=}")
        status_content_ctx = None
        if status_content_ctx is None:
            ctx = Chat().system(
                self.render_template(
                    Templates.fixed_system,
                )
            )
        else:
            assert isinstance(status_content_ctx, ChatClass)
            ctx = status_content_ctx
            ctx.prompts[-2][
                "content"
            ] = "My next message is the summary of current on-screen texts."
            ctx.prompts[-1]["role"] = "user"  # pretend UI state is provided by user

        if self.last_actions:
            # insert last *context_history_length* history entries as a separate prompt
            ctx.user(
                self.render_template(
                    Templates.every_step_history,
                    history=[i.description_for_llm for i in self.last_actions],
                    limit=config.app.core.context_history_length,
                )
            )
        ctx.user(
            self.render_template(
                Templates.every_step_get_action,
                state=elements_prompt,
                current_activity=self.get_short_activity_name(
                    self.current_activity_name
                ),
                this_activity_description=self.status.description,
                goal_activity=self.get_short_activity_name(self.goal_activity_name),
                goal_activity_description=self.goal_description,
                show_badgoal=len(self.last_actions)
                >= config.app.core.show_badgoal_prompt_at_least_after,
                show_back="back" in self.global_mappings,
                show_login_hint=any(
                    "input" in llm_choice.commands
                    for llm_choice in self.mapping.values()
                ),
            )
        )
        if self.current_package_name != self.aut_package_name:
            ctx.user(
                f"Please be aware that current package name is {self.current_package_name}, but not our testing app. You may have been required to perform some operation (such as taking photos, selecting files) to return to our app."
            )
        # ctx.user(self.render_template(Templates.insert_idea, idea=self.idea))
        ctx.user(
            f"Now please give your analyze. "
            f"Remember that any element index not in range {list([k for k,v in self.mapping.items() if v.commands])} does not exist and you shold NEVER select them. "
            f"You must NOT perform an unsupported command on a element."
        )
        if self.insert_contents_for_func_call:
            ctx.user("\n".join(self.insert_contents_for_func_call.values()))
        if self.status.is_login_page:
            if any(
                1
                for i in self.mapping.values()
                if "input" in i.commands and not i.operated_before
            ):
                ctx.user(
                    "Please note that this page is a login page. You must input email/username and password in related input-required elements, and click login to proceed testing.\n"
                    "To see whether you have finished input of both value, see your action history entries.\n"
                    "Do not register new account."
                )
            else:
                ctx.user(
                    "Please note that this page is a login page. You must click login to proceed testing.\n"
                    "Do not register new account."
                )
        has_command_choices = [i for i in self.mapping.values() if i.commands]
        if (
            all(i.commands == ["input"] for i in has_command_choices)
            and len(has_command_choices) >= 2
        ):
            debug_print_no(
                "due to only input in current mapping, inserted multi function call hint."
            )
            ctx.user(
                "You might use several function call in one reply to input all texts."
            )
        ctx.update_ask_kwarg(
            tools=self._construct_merged_function_call(),
        )
        if config.app.core.analyze_before_function_call:
            ctx.user(
                "Please first analyze the current screen, and deduce what to do to achieve our target, and finally return the corresponding element and command."
            )
            ctx.update_ask_kwarg(tool_choice="none")
            # pass tools, but not allow to use it
        else:
            ctx.update_ask_kwarg(tool_choice="auto")
        ret_parsed: List[ParsedFuncitonCall] = []
        if self.function_call_queue:
            # process unparsed function calls in queue
            ret_parsed = [self.function_call_queue[0]]
            found_mapping = [
                i
                for i in self.mapping.values()
                if i.xpath == ret_parsed[0]["arguments"]["xpath"]
            ]
            if not found_mapping:
                # invalid xpath, clear all
                debug_print_no("Error parsing mapping!")
                debug_print_no(self.function_call_queue)
                ret_parsed = []
                self.function_call_queue = []
            else:
                debug_print_no("SUCCESS parsing mapping!")
                self.function_call_queue.pop(0)
                assert ret_parsed[0]["name"] == "input"
                ret_parsed[0]["arguments"].pop("xpath")
                ret_parsed[0]["arguments"]["element_index"] = found_mapping[
                    0
                ].prompt_index
                ctx = None
        if not ret_parsed:
            # no queue unparsed, start a new chat
            assert ctx is not None
            ret = ctx.ask(save_to_context=True)
            if not ctx.last_is_function_call:
                ctx.user("Great! Now, invoke the corresponding function call.")
                ctx.update_ask_kwarg(tool_choice="auto")
                ret = ctx.ask(save_to_context=True)
            self.last_llm_context = ctx.prompts
            try:
                ret_parsed = string_to_function_calls(ret)
            except json.JSONDecodeError:
                # pass several weird cases in LLM response
                match_function_like = regex.search(r"(\w+)\((\d+)\)", ret)
                try:
                    if match_function_like:
                        ret_parsed = [
                            {
                                "name": match_function_like.group(1),
                                "arguments": {
                                    "element_index": int(match_function_like.group(2))
                                },
                            }
                        ]
                    else:
                        raise ValueError
                except:
                    return self._testing_interrupt_with_error(
                        f"LLM failed to invoke function call:\n{ret}",
                        True,
                        TestingResults.RETURN_LLM_REPLY_WRONG_RETRY,
                        with_full_llm_context=True,
                    )
            if len(ret_parsed) > 1:
                # store multiple `input` function calls into queue
                for item in ret_parsed:
                    if (
                        item["name"] != "input"
                        or (index := str(item["arguments"]["element_index"]))
                        not in self.mapping
                        or item["name"] not in self.mapping[index].commands
                    ):
                        break
                else:
                    for item in ret_parsed[1:]:
                        index = str(item["arguments"]["element_index"])
                        xpath = self.mapping[index].xpath
                        item["arguments"].pop("element_index")
                        item["arguments"]["xpath"] = xpath
                        self.function_call_queue.append(item)
            ret_parsed = [
                ret_parsed[0],
            ]

        # Match LLM reply to element, command and extra to perform

        ret_command = ret_parsed[0]["name"]
        if ret_command in self.global_mappings:
            choice = self.global_mappings[ret_command]
        else:
            element_index = str(ret_parsed[0]["arguments"]["element_index"])
            if element_index not in self.mapping:
                self.activity_test_result.llm_reply_wrong_retry_count += 1
                self.insert_contents_for_func_call[
                    "element_not_exist"
                ] = f"Please note that element {element_index} does not exist. Do not select it."
                return self._testing_interrupt_with_error(
                    f"LLM selected element_index \"{element_index}\" not in {self.mapping.keys()}",
                    True,
                    TestingResults.RETURN_LLM_REPLY_WRONG_RETRY,
                    with_full_llm_context=True,
                )
            choice = self.mapping[element_index]
            if ret_command not in choice.commands:
                self.activity_test_result.llm_reply_wrong_retry_count += 1
                self.insert_contents_for_func_call[
                    "command_not_supported"
                ] = f"Please note that function {ret_command} is not supported on element {element_index}."
                return self._testing_interrupt_with_error(
                    f"LLM selected command \"{ret_command}\" not in {choice.commands}",
                    True,
                    TestingResults.RETURN_LLM_REPLY_WRONG_RETRY,
                    with_full_llm_context=True,
                )
        self.insert_contents_for_func_call.clear()
        ret_extra: dict = ret_parsed[0]["arguments"]
        ret_extra.pop("element_index", None)
        if ctx is not None:
            ctx.reset_ask_kwarg()

        return choice, ret_command, ret_extra, ctx

    def _construct_merged_function_call(self) -> list:
        """
        Construct the processed function call to send to LLM.
        Used to generate available commands and required params for LLM to choose from.
        """
        all_commands: Dict[str, List[str]] = {}  # command_name -> [prompt_index, ...]
        for choice in self.mapping.values():
            for command in choice.commands:
                all_commands.setdefault(command, []).append(choice.prompt_index)
        all_functions = []
        for command_name, prompt_indexes in all_commands.items():
            func_tool = self.get_command_handler(command_name).get_function_call()
            func = func_tool["function"]
            func["parameters"]["properties"] = func["parameters"]["properties"].copy()
            func["parameters"]["properties"]["element_index"] = {
                "type": "number",
                "enum": prompt_indexes,
                "description": "The index of the element to perform action on",
            }
            func["parameters"]["required"] = func["parameters"]["required"].copy()
            func["parameters"]["required"].append("element_index")
            all_functions.append(func_tool)
        if "back" in self.global_mappings:
            all_functions.append(self.get_command_handler("back").get_function_call())
        return all_functions

    #    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2), reraise=True)
    def _core_step(self) -> TestingResults:
        time.sleep(config.app.core.wait_time_between_steps)
        self._update_status_before_each_step()
        self.interrupt_during_testing = True  # Prevent multiple initalization of current status

        # ======
        # Generate activity description
        # ======

        status_content_ctx = self.generate_status_description()

        # ======
        # Stage 1: Choose the best element
        # ======
        ctx = None
        operation_description = ""
        if len(self.mapping) == 0:
            choice = list(self.all_global_mappings.values())[0]
            command = "back"
            extra_data = {}
            operation_description = "Navigate back beacuse no action can be taken."
        else:
            llm_results = self._testing_construct_context(
                status_content_ctx=status_content_ctx,
            )
            if isinstance(llm_results, TestingResults):
                return llm_results
            choice, command, extra_data, ctx = llm_results

        # ======
        # Parse LLM reply
        # ======

        extra_data["chat_device_serial"] = self.device.serial

        # ======
        # Translate LLM reply to element and command
        # ======

        command_runner_class = command_manager.CommandManager.name_command_table.get(
            command
        )
        assert command_runner_class is not None, AssertionError(
            f"No such command {command} although it is supported"
        )
        command_runner = command_runner_class(driver=self.driver)

        xpath: Optional[str] = choice.xpath
        """
        debug_print_no("xpath:", xpath)
        unique_path: Optional[str]
        if choice.is_global:
            unique_path = None
        else:
            unique_path = get_element_exact_xpath(choice.element, self.status.xml_tree)
        debug_orig_print("unique_path:", unique_path)
        """

        # ======
        # Finish parsing LLM reply, begin perform action
        # ======

        self.activity_test_result.record.start_action()

        try:
            target: MixedElement = MixedElement(
                xml_element=choice.element,
                web_element=None if not xpath else self.selector.xpath(xpath)[0],
            )
            fixed_operation_description = command_runner.perform_action(
                element=target,
                extra_data=extra_data,
            )
        except (TimeoutException, StaleElementReferenceException):
            # The xpath may be invalid, try again
            return self._testing_interrupt_with_error(
                f"Timeout when performing action. (activity={self.current_activity_name}, xpath={xpath}, command={command})",
                False,
                TestingResults.UNFINISHED,
                with_full_llm_context=False,
                with_traceback=False,
                notification_type="info",
            )
        except command_manager.NoEnoughArgumentsError as exc:
            return self._testing_interrupt_with_error(
                f"Required arguments for command ({exc.argument_name}) not provided by LLM.",
                True,
                TestingResults.RETURN_LLM_REPLY_WRONG_RETRY,
                with_full_llm_context=False,
                with_traceback=False,
                notification_type="info",
            )
        except InvalidElementStateException:
            return self._testing_interrupt_with_error(
                f"Element disappeared when performing action. (activity={self.current_activity_name}, xpath={xpath}, command={command})",
                False,
                TestingResults.UNFINISHED,
                with_full_llm_context=False,
                with_traceback=False,
                notification_type="info",
            )
        if ctx is not None:
            ctx.add_to_cache()

        # ======
        # Post perform action
        # ======

        new_activity = self.get_current_activity_name_from_appium()
        env_and_action = EnvAndAction(
            self.activity,
            self.status,
            choice.element,
            command,
            extra_data,
            fixed_operation_description,
        )
        self.last_actions.append(env_and_action)
        # random ** to avoid duplicate entries in history
        # useless now
        index = 0
        for index, action in enumerate(self.last_actions_filter_circle_for_llm_only):
            if (
                action.status == env_and_action.status
                and len(self.last_actions_filter_circle_for_llm_only) - index > 5
            ):  # circle length > 5, WHY?
                break
        self.last_actions_filter_circle_for_llm_only = self.last_actions[:index]
        self.last_actions_filter_circle_for_llm_only.append(env_and_action)
        # end useless now
        self.key_ctx_for_last_step = ctx

        ee.emit(
            Events.onNotification,
            "info|step_detail",
            f"Status: {self.status.pretty_name}\n"
            + f"Step: {self.activity_test_result.step_count} | "
            f"Activity: {self.get_short_activity_name(self.current_activity_name)} -> "
            f"{self.get_short_activity_name(new_activity)} | Choice: {fixed_operation_description} (LLM description: {operation_description})",
        )

        # End perform action
        self.interrupt_during_testing = False
        return TestingResults.RETURN_STEP_NORMALLY_FINISHED

    @classmethod
    def check_single_task(cls, task):
        target: TargetType = task.target
        activity_name = target["activity_name"]
        assert not activity_name.startswith("."), ValueError(
            f"Provided target activity {activity_name} is not full name."
        )

    def _pre_single_task(self, task):
        super()._pre_single_task(task)
        target: TargetType = task.target
        self.goal_activity_name: str = target["activity_name"]
        if description := target.get("description"):
            self.goal_description = description
        elif desc := self.known_activities_data.get(self.goal_activity_name, {}).get(
            "description"
        ):
            self.goal_description = desc
        else:
            self.goal_description = None
        self.function_call_queue = []

    def global_init_by_task(self, task, device) -> Self:
        self.init(
            device=device,
            apk_file=task.extra_kwargs.get("apk"),
            package_name=task.extra_kwargs.get("package_name"),
            known_activities_data=task.extra_kwargs.get("known_activities_data"),
            capabilities_mixin=task.extra_kwargs.get("capabilities_mixin", ""),
        )
        return self

    def llm_find_a_good_start_activity(self):
        known_paths = self.persist_knowledge.get_activity_paths()
        for k in known_paths:
            if len(known_paths[k]) == 0:
                known_paths.pop(k)
        if not known_paths:
            return
        known_paths.pop(self.get_current_activity_name_from_appium(), None)
        if not known_paths:
            return
        activities: Dict[str, Optional[str]] = {}
        for activity_name, actvity_paths in known_paths.items():
            activities.update(
                {
                    activity_name: self.persist_knowledge.get_activity_description(
                        activity_name=activity_name
                    )
                }
            )
        for attempt in range(3):
            ctx = (
                Chat()
                .system(self.render_template(Templates.fixed_system))
                .user(
                    self.render_template(
                        Templates.before_test_find_a_good_start,
                        package_name=self.aut_package_name,
                        goal_activity_name=self.goal_activity_name,
                        goal_description=self.goal_description,
                        activities=activities,
                    )
                )
                # .user(self.render_template(Templates.insert_idea, idea=self.idea))
            )
            answer = ctx.ask(save_to_context=True)
            self.last_llm_context = ctx.prompts
            find_a_good_start_activity_pattern = regex.compile(
                r"[Aa]ctivity <?`?`?<?([a-zA-Z-Z.]+)`?`?>?>? is my choice", REGEX_FLAG
            )
            selected_activity_names = parse_regex(
                find_a_good_start_activity_pattern, answer, no_raise=True
            )
            debug_print_no(ctx.prompts[-2]["content"])
            if not selected_activity_names:
                debug_print_no(f"Failed parsing good_start by LLM by regex {str(find_a_good_start_activity_pattern)}.")
                debug_print_no(answer, ctx.prompts[-1]["content"])
                continue
            selected_activity_name = selected_activity_names[0]
            if selected_activity_name not in activities:
                debug_print_no(
                    f"selected good_start {selected_activity_name} is not found in {activities.keys()}"
                )
                continue
            break
        else:
            send_notification("info|good_start|good_start_failed", f"Good start activity is not selected by LLM, ignore.")
            return
        selected_activity_paths = known_paths[selected_activity_name]

        def selector_for_reproduce(xpath: Xpath) -> WebElement:
            return self.selector.xpath(xpath)[0]

        def hash_getter_for_reproduce() -> str:
            xml = self.driver.page_source
            xml_tree = etree.fromstring(xml.encode("utf-8"))
            status_hash = Status.calc_hash(xml_tree, DEFAULT_STATUS_LEVEL, None)
            return status_hash

        for selected_activity_path in selected_activity_paths[:3]:  # try at most 3 paths for each activity
            try:
                selected_activity_path.reproduce(
                    is_app_first_launch=self.require_app_first_init,
                    is_app_homepage=self.require_app_homepage,
                    selector=selector_for_reproduce,
                    hash_getter=hash_getter_for_reproduce,
                    command_getter=self.get_command_handler,
                    driver=self.driver,
                )
            except (RuntimeError, TimeoutException) as e:
                self.persist_knowledge.activity_path.remove(selected_activity_path)  # type: ignore
                self.persist_knowledge.save()
                self._restart_app()
            break
        else:  # failed to reproduce any path
            send_notification(
                "warning|good_start_failed",
                f"Good start {selected_activity_name} selected by LLM is not reproduced, ignore.",
            )
            return
        ctx.add_to_cache()
        send_notification("info|good_start", f"Good start activity is selected by LLM: {selected_activity_name}")
        self.llm_start_activity = selected_activity_name
        self._init_activity_and_status()
        self._init_record()

    def generate_idea(self):
        ctx = (
            Chat()
            .system(
                self.render_template(
                    Templates.fixed_system,
                )
            )
            .user(
                prompt_tmpl.get_template(Templates.before_test_think_a_idea).render(
                    goal_activity=self.goal_activity_name,
                    goal_description=self.goal_description,
                    package_name=self.aut_package_name,
                    paths=set(
                        self.persist_knowledge.failed_ideas.get(
                            self.goal_activity_name, []
                        )
                    ),
                )
            )
        )
        answer = ctx.ask(save_to_context=True)
        self.last_llm_context = ctx.prompts
        self.idea = answer
        ctx.add_to_cache()

    def summarize_and_review_after_each_task(self, result):
        for activity in self.activity_manager.all_known_activity.values():
            if activity.is_description_fixed:
                # ee.emit(
                #     Events.onNotification,
                #     "debug|actiivty_description_generation",
                #     f"{activity.activity_name} is keeping human-provided desc: {activity.description}",
                # )
                continue
            try:
                activity.description = self.generate_activity_description(activity)
            except get_llm_connection_error_types():
                send_notification(
                    "error|summarize_and_review_after_each_task",
                    f"Due to LLM connection issue, failed generating description for {activity.activity_name}",
                )
                activity.description = None
            ee.emit(
                Events.onNotification,
                "debug|actiivty_description_generation",
                f"LLM-generated Description for {activity.activity_name}: {activity.description}",
            )
            self.persist_knowledge.add_activity_description(
                activity_name=activity.activity_name, description=activity.description
            )
        # if result.failed and hasattr(self, "idea") and self.idea:
        #     self.persist_knowledge.add_failed_idea(self.goal_activity_name, self.idea)
        self.persist_knowledge.save()
        ee.emit(
            Events.onNotification,
            "info|summeraize_and_review_after_each_task",
            f"Finish saving memory to {self.persist_knowledge.path}",
        )

    def generate_full_json_log_for_last_task(self) -> dict:
        ret = {
            "target": self.goal_activity_name,
            "success": self.activity_test_result.get_result_bool(),
            "fail_reasons": self.activity_test_result.fail_reasons,
            "step_count": self.activity_test_result.step_count,
            "time": self.activity_test_result.total_time,
            "llm_error": self.activity_test_result.llm_reply_wrong_retry_count,
            # "idea": self.idea,
            "task": self.task.to_dict(),
            "record": self.record.to_dict() if (self.record is not None) else None,
            "activity_and_status_knowledge": self.activity_manager.to_dict(),
        }
        return ret
