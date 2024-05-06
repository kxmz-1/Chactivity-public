"""
Represents UI state, Activity discovered.

## Details of Status
Hash is calculated based on UI elements, and is used to determine if it is the same as another status.
Weight is used to determine if the tuple (element, action) should show to LLM.
"""
from enum import IntEnum, auto
import random
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    TypeAlias,
    Union,
    Self,
)
from app.base.base.config import config
from app.base.base.const import (
    ALL_ATTRIBUTES,
    LOGIN_INTERFACE_KEYWORDS,
    MUST_DIFFERENT_ATTRIBUTES,
    TEXT_ATTRIBUTES,
)
from app.base.base.custom_typing import ElementAndDepth, MixedElement, XmlElement, Xpath
from app.base.base.event_handler import send_notification
from app.base.core.persist_knowledge import PersistKnowledge
from app.base.base.util import get_full_activity_name, get_short_activity_name, true
from app.base.device.commands import (
    command_manager,
    get_available_commands_for_xml_element,
)
from app.base.core.xml_util import (
    filter_xpath_remove_index,
    get_xml_hash,
    indent_xml,
    is_element_same,
    keep_only_one_res_id_in_child_texts,
    make_element_description,
    merge_children_text_desc,
    pass_container_text_down,
    pass_down_actionable,
    pass_down_child_texts,
    remove_attr_on_every_element,
    remove_duplicate_near_texts,
    traverse_xml,
)
from app.base.core.activity_knowledge import ActivityPath
from app.base.base.enrich import debug_print, print, debug_print_no


class StatusLevel(IntEnum):
    TEXT = 0
    ATTRIBUTE_IGNORE_TEXT = 1
    ATTRIBUTE_IGNORE_TEXT_AND_DESC = 2
    LAYOUT_IGNORE_ATTRIBUTE = 3
    ACTIVITY_IGNORE_LAYOUT = 4
    PACKAGE = 5


DEFAULT_STATUS_LEVEL = StatusLevel.ATTRIBUTE_IGNORE_TEXT
STATUS_EXPLODED_MAX = 10


WeightType: TypeAlias = float


class Weight:  # 没用Enum，因为运算会有点怪（虽然可以`class Weight(float, Enum)`）
    DISABLED_FOREVER: WeightType = -990.0  # 原地tp
    MIN: WeightType = 0.0
    MAX: WeightType = 100.0
    DEFAULT: WeightType = MAX  # 还没有任何操作，认为有价值
    EACH_ACTION: WeightType = -40.0  # 执行一次操作后Weight衰减
    EACH_NON_ACTION: WeightType = 15.0  # 每次操作未选择Weight增加
    ENTER_CIRCLE: WeightType = -20  # 入环的额外Weight改变，如底部导航栏中主页到某个页面的跳转
    EXIT_CIRCLE: WeightType = -40  # 出环的额外Weight改变，如触发弹窗后的“返回”按钮
    EACH_ACTION_ON_GLOBAL: WeightType = -50.0  # 执行一次操作后Weight衰减（在Activity间的相同元素上应用）
    EACH_NON_ACTION_ON_GLOBAL: WeightType = 6.0  # 每次操作未选择Weight增加（同上）


SPECIAL_WEIGHT_SKIP_CHECK: List[WeightType] = [
    Weight.DISABLED_FOREVER,
]


class Status:
    description: Optional[str] = None  # let llm analyze & fill this

    def __init__(
        self,
        activity: "Activity",
        xml: str,
        xml_tree: XmlElement,
        step_count: int,
        status_level: StatusLevel,
        from_status: Optional["Status"] = None,
    ):
        self.activity: Activity = activity
        self.xml: str = xml
        self.xml_tree = xml_tree
        self.status_level: StatusLevel = status_level
        self.hash: str = ""
        self.step_count: int = step_count
        self.init_status_hash(status_level)
        self.init_element_tree()
        self._all_elements: List[ElementAndDepth] = list(
            self.get_elements(disable_weight=True)
        )
        self._xpath_to_element: Dict[Xpath, XmlElement] = {
            element.attrib["xpath"]: element for element, _ in self._all_elements
        }
        self.element_weights: Dict[Xpath, WeightType] = {}
        self._init_element_weights()
        # we use weight to determine if the element should show, but who knows what exactly we have to do LOL
        self.element_depths: Dict[Xpath, int] = dict()
        # used for ban circle, if depth bigger arrived somewhere with depth lower, we ban it.
        self.elements_to_this: List[XmlElement] = []
        # used to record which elements can lead to this status
        self.from_status: Optional[Status] = from_status
        self.has_inputed: bool = False

    @staticmethod
    def calc_hash(
        xml_tree: XmlElement, status_level: StatusLevel, activity: Optional["Activity"]
    ) -> str:
        match status_level:
            case StatusLevel.TEXT:
                hash = get_xml_hash(xml_tree)
            case StatusLevel.ATTRIBUTE_IGNORE_TEXT:
                hash = get_xml_hash(
                    remove_attr_on_every_element(
                        xml_tree, {"text"} | MUST_DIFFERENT_ATTRIBUTES
                    )
                )
            case StatusLevel.ATTRIBUTE_IGNORE_TEXT_AND_DESC:
                hash = get_xml_hash(
                    remove_attr_on_every_element(
                        xml_tree,
                        TEXT_ATTRIBUTES | MUST_DIFFERENT_ATTRIBUTES,
                    )
                )
            case StatusLevel.LAYOUT_IGNORE_ATTRIBUTE:
                hash = get_xml_hash(
                    remove_attr_on_every_element(xml_tree, ALL_ATTRIBUTES)
                )
            case StatusLevel.ACTIVITY_IGNORE_LAYOUT:
                assert activity is not None, RuntimeError(
                    "activity is None when generating status hash and `status_level` is ACTIVITY_IGNORE_LAYOUT"
                )
                hash = activity.activity_name
            case StatusLevel.PACKAGE:
                assert activity is not None, RuntimeError(
                    "activity is None when generating status hash and `status_level` is PACKAGE"
                )
                hash = activity.package_name
            case _:
                raise ValueError(f"Unknown status level: {status_level}")
        hash = str(status_level) + hash
        return hash

    def init_status_hash(self, status_level: StatusLevel) -> None:
        self.status_level: StatusLevel = status_level
        self.hash = self.calc_hash(self.xml_tree, status_level, self.activity)

    @property
    def pretty_name(self) -> str:
        return self.activity.activity_name + " , hash: " + self.hash[:8]

    def init_element_tree(self):
        """
        Pre-process UI hireachy xml tree.
        Rewrite attributes for further analysis.

        总的来说：
        1. 向下传递actionable
        2. 过滤哪些元素可以操作（写入depth属性）
        3. 把所有元素的text和content-desc合并到父元素
        4. 为每个元素写入父元素上合并的child_texts属性
        """
        pass_down_actionable(self.xml_tree)
        pass_container_text_down(self.xml_tree)
        current_found_elements: List[XmlElement] = []

        def detection_function_actionable(
            element,
            event_handlers: List[
                command_manager.CommandType
            ] = command_manager.CommandManager.all_command_list,
        ):
            ret = any(get_available_commands_for_xml_element(element))
            if ret:
                current_found_elements.append(element)
            return ret

        indent_xml(self.xml_tree, detection_function=detection_function_actionable)
        merge_children_text_desc(self.xml_tree)  # disabled for now
        pass_down_child_texts(self.xml_tree, current_found_elements)
        keep_only_one_res_id_in_child_texts(current_found_elements)
        remove_duplicate_near_texts(self.xml_tree, current_found_elements)

    def get_elements(self, disable_weight: bool = False) -> List[ElementAndDepth]:
        """
        Get all elements in current status.
        """
        if not config.app.core.filter_by_status_weight:
            return traverse_xml(self.xml_tree)
        elements = traverse_xml(self.xml_tree)
        for element_and_depth in elements[:]:
            if not true(element_and_depth[0].get("displayed")):
                elements.remove(element_and_depth)
        ret = []
        current_status_ban_count = 0
        for element, depth in elements:
            rand = 0.0
            rand1_meet = disable_weight or (
                (rand := random.random()) < self.get_weight(element) / Weight.MAX
            )
            if rand1_meet:
                ret.append((element, depth))
            else:
                if not rand1_meet:
                    current_status_ban_count += 1
        return ret

    def get_weight(self, element: Union[Xpath, XmlElement]) -> WeightType:
        if isinstance(element, XmlElement):
            xpath = element.attrib["xpath"]
        else:
            xpath = element
        return self.element_weights[xpath]

    def _init_element_weights(self) -> None:
        count = 0
        for element, _ in self._all_elements:
            xpath = element.attrib["xpath"]
            self.update_element_weight(xpath, Weight.DEFAULT)
        debug_print_no(
            f"init_element_weights: {count} elements banned in status {self.hash} in activity {self.activity.activity_name}"
        )
        self.update_element_weight("back", Weight.DEFAULT)

    def update_element_weight(self, xpath: Xpath, weight: WeightType) -> None:
        current_weight = self.element_weights.get(xpath)
        if weight in SPECIAL_WEIGHT_SKIP_CHECK:
            new_weight = weight
        elif current_weight in SPECIAL_WEIGHT_SKIP_CHECK:
            new_weight = current_weight
        else:
            new_weight = min(Weight.MAX, max(Weight.MIN, weight))
        if current_weight != new_weight and weight != Weight.DEFAULT:
            debug_print_no(
                f"update_element_weight: {xpath}, from {current_weight} to {new_weight} in status {self.hash} in activity {self.activity.activity_name}"
            )
        self.element_weights[xpath] = new_weight

    def add_element_weight(self, xpath: Xpath, weight: WeightType) -> None:
        self.update_element_weight(xpath, self.element_weights[xpath] + weight)

    def on_element_action(
        self,
        elem: XmlElement,
        step_number: int,
        new_status: Self,
        command: str,
        useful: bool,
        extra: dict = {},
    ) -> None:
        """
        Call on old status (self) when an action finished.
        """
        self.activity.activity_manager.add_operated_element(elem)
        if elem not in self.elements_to_this:
            self.elements_to_this.append(elem)
        if command == "input":
            self.activity.activity_manager.add_filled_text(
                make_element_description(elem, ignore_text_for_inputable=True),
                extra["text"],
            )
            self.has_inputed = True
        xpath: Xpath = elem.attrib["xpath"]
        self.element_depths[xpath] = step_number
        if useful and (new_status.step_count < self.step_count):
            # we go back to a previous status, so we should ban the source element to this
            # Remove nodes which lead into a circle
            max_element, max_depth = None, -1
            for element, depth in new_status.element_depths.items():
                if depth > max_depth:
                    # element is the max depth element, which is the last action before entering the circle
                    max_element, max_depth = element, depth
            if max_element is not None:
                new_status.add_element_weight(max_element, Weight.ENTER_CIRCLE)
            self.add_element_weight(xpath, Weight.EXIT_CIRCLE)
        prompt = elem.attrib["prompt"]
        for element, _ in self._all_elements:
            current_xpath: Xpath = element.attrib["xpath"]
            if self.element_weights[current_xpath] in SPECIAL_WEIGHT_SKIP_CHECK:
                continue
            if element.attrib["prompt"] == prompt:
                if useful:
                    self.add_element_weight(
                        current_xpath,
                        Weight.EACH_ACTION,
                    )
                    self.activity.activity_manager.on_action_action(element, command)
                else:
                    self.activity.activity_manager.global_ban_action(element, command)
            else:
                self.add_element_weight(
                    current_xpath,
                    Weight.EACH_NON_ACTION,
                )
                self.activity.activity_manager.on_action_non_action(element, command)

    def single_ban_element(self, xpath_or_command: str) -> None:
        """
        Ban a single element or `back` command.
        """
        self.update_element_weight(xpath_or_command, Weight.DISABLED_FOREVER)

    @property
    def banned_elements(self) -> List[Xpath]:
        """
        Get all elements that are banned to this status.
        """
        res: List[Xpath] = []
        for xpath in self.element_weights:
            if self.element_weights[xpath] == Weight.DISABLED_FOREVER:
                res.append(xpath)
        return res

    def to_dict(self) -> dict:
        return {
            "hash": self.hash,
            "banned_elements_count": len(self.banned_elements),
            "description": self.description,
        }

    @property
    def is_login_page(self) -> bool:
        """
        Detect if this status is a login page based on texts and commands.
        """
        thereshold_all = 3
        thereshold_button = 1
        thereshold_input = 1
        for element, _ in self.get_elements(disable_weight=True):
            commands = get_available_commands_for_xml_element(element)
            for keyword in LOGIN_INTERFACE_KEYWORDS:
                if keyword.lower().replace(" ", "") in make_element_description(
                    element
                ).lower().replace(" ", ""):
                    thereshold_all -= 1
                    if "input" in commands:
                        thereshold_input -= 1
                    if "click" in commands:
                        thereshold_button -= 1
                    if max(thereshold_all, thereshold_button, thereshold_input) <= 0:
                        return True
        return False

    @property
    def is_all_text_filled(self) -> bool:
        """
        Detect if all text fields are filled.
        """
        for element, _ in self.get_elements(disable_weight=True):
            if "input" in get_available_commands_for_xml_element(element):
                if (
                    self.activity.activity_manager.filled_text_for(
                        make_element_description(
                            element, ignore_text_for_inputable=True
                        )
                    )
                    is None
                ):
                    return False
        return True


class Activity:
    def __init__(
        self,
        package_name: str,
        activity_name: str,
        activity_manager: "ActivityManager",
        status_level: StatusLevel = DEFAULT_STATUS_LEVEL,
    ):
        self.package_name: str = package_name
        self.activity_name: str = get_full_activity_name(
            package_name=package_name, activity_name=activity_name
        )
        self.statuses: List[Status] = []
        self.status_level: StatusLevel = status_level
        self.activity_knowledges: List[ActivityPath] = []
        self.activity_manager: ActivityManager = activity_manager
        self.description: Optional[
            str
        ] = self.activity_manager.persist_knowledge.activity_description.get(
            self.activity_name, None
        )
        self.is_description_fixed: bool = False

    @property
    def elemenets_to_this(self) -> List[XmlElement]:
        """
        Get all elements that can lead to this activity.
        """
        res: List[XmlElement] = []
        for status in self.statuses:
            res.extend(status.elements_to_this)
        return res

    def add_activity_knowledges(self, *activity_knowledge: ActivityPath) -> None:
        self.activity_knowledges.extend(activity_knowledge)

    def add_status(self, xml: str, xml_tree: XmlElement, step_count: int) -> Status:
        """
        Add a status if it is new, otherwise do nothing.
        """
        this_status = self._get_status(xml, xml_tree, step_count=step_count)
        if this_status not in self.statuses:
            this_status.from_status = self._last_status
            self.statuses.append(this_status)
        return this_status

    @property
    def _last_status(self) -> Optional[Status]:
        return self.statuses[-1] if self.statuses else None

    @property
    def _last_activity(self) -> Optional["Activity"]:
        return (
            self.activity_manager.last_activities[-1]
            if self.activity_manager.last_activities
            else None
        )

    def _get_status(self, xml: str, xml_tree: XmlElement, step_count: int) -> Status:
        """
        Return the status with cache.
        """
        this_status = Status(
            activity=self,
            xml=xml,
            xml_tree=xml_tree,
            status_level=self.status_level,
            step_count=step_count,
        )
        for status in self.statuses:
            if status.hash == this_status.hash:
                del this_status
                return status
        return this_status

    @property
    def is_status_exploded(self) -> bool:
        """
        If more than STATUS_EXPLODED_MAX statuses, then it is exploded. Some actions might be taken if this happens.
        """
        return len(self.statuses) > STATUS_EXPLODED_MAX

    @property
    def short_name(self) -> str:
        return get_short_activity_name(self.package_name, self.activity_name)

    def to_dict(self) -> dict:
        return {
            "activity_name": self.activity_name,
            "statuses": [status.to_dict() for status in self.statuses],
            "status_level": self.status_level.value,
            "description": self.description,
        }


class ActivityManager:
    all_known_activity: Dict[Tuple[str, str], Activity]
    # key: (package_name, activity_name)
    last_activities: List[Activity]

    def __init__(self, persist_knowledge: PersistKnowledge, package_name: str) -> None:
        self.reset_all_known_activity()
        self.persist_knowledge = persist_knowledge
        self.package_name = package_name
        for invalid_action in self.persist_knowledge.invalid_actions:
            self._set_action_weight(invalid_action, Weight.DISABLED_FOREVER)
        self.human_description: Dict[str, str] = {}

    def add_operated_element(self, element: XmlElement) -> None:
        self.operated_elements_description.add(
            make_element_description(element, ignore_text_for_inputable=True)
        )

    def reset_all_known_activity(self) -> None:
        self.all_known_activity = {}
        self.last_activities = []
        self.action_weights = {}
        self.filled_texts: Dict[str, str] = {}
        self.operated_elements_description: Set[str] = set()

    def get_activity(self, package_name: str, activity_name: str, **kwargs) -> Activity:
        unique_tuple = (package_name, activity_name)
        if unique_tuple in self.all_known_activity:
            return self.all_known_activity[unique_tuple]
        else:
            new_activity = Activity(
                package_name=package_name,
                activity_name=activity_name,
                activity_manager=self,
                **kwargs,
            )
            activity_name = new_activity.activity_name
            if self.human_description.get(new_activity.activity_name, ""):
                new_activity.description = self.human_description[activity_name]
                new_activity.is_description_fixed = True
            self.all_known_activity[unique_tuple] = new_activity
            self.last_activities.append(new_activity)
            return new_activity

    def get_last_activity(self, package_name: str) -> Optional[Activity]:
        if package_name not in self.last_activities:
            return None
        return self.last_activities[-1]

    def to_dict(self) -> dict:
        return {
            "package_name": self.package_name,
            "activities": [activity.to_dict() for activity in self.last_activities],
        }

    # global action weight
    @staticmethod
    def get_action_key(element: XmlElement, command: str) -> str:
        return (
            filter_xpath_remove_index(element.attrib["xpath"])
            + make_element_description(element)
            + command
        )

    def _set_action_weight(self, xpath_and_desc: str, weight: WeightType):
        current_weight = self.action_weights.setdefault(xpath_and_desc, Weight.DEFAULT)
        if weight in SPECIAL_WEIGHT_SKIP_CHECK:
            new_weight = weight
        elif current_weight in SPECIAL_WEIGHT_SKIP_CHECK:
            new_weight = current_weight
        else:
            new_weight = min(Weight.MAX, max(Weight.MIN, weight))
        if current_weight != new_weight and weight != Weight.DEFAULT:
            debug_print_no(
                f"global_update_action_weight: {xpath_and_desc}, from {current_weight} to {new_weight}"
            )
        self.action_weights[xpath_and_desc] = new_weight

    def update_action_weight(
        self, element: XmlElement, command: str, weight: WeightType
    ) -> None:
        xpath_and_desc = self.get_action_key(element, command)
        self._set_action_weight(xpath_and_desc, weight)

    def add_action_weight(
        self, element: XmlElement, command: str, weight: WeightType
    ) -> None:
        xpath_and_desc = self.get_action_key(element, command)
        new_weight = (
            self.action_weights.setdefault(xpath_and_desc, Weight.DEFAULT) + weight
        )
        self.update_action_weight(element, command, new_weight)

    def on_action_action(self, element: XmlElement, command: str) -> None:
        self.add_action_weight(element, command, Weight.EACH_ACTION_ON_GLOBAL)

    def on_action_non_action(self, element: XmlElement, command: str) -> None:
        if self.get_action_key(element, command) not in self.action_weights:
            return
        self.add_action_weight(element, command, Weight.EACH_NON_ACTION_ON_GLOBAL)

    def should_show_action(self, element: XmlElement, command: str) -> bool:
        if not config.app.core.filter_by_global_weight:
            return True
        xpath_and_desc = self.get_action_key(element, command)
        if xpath_and_desc not in self.action_weights:
            return True
        weight = self.action_weights[xpath_and_desc]
        if weight == Weight.DISABLED_FOREVER:
            return False
        return random.random() < weight / Weight.MAX

    def global_ban_action(self, element: XmlElement, command: Optional[str]) -> None:
        """
        Ban (element, command) pair forever.
        if command is None, ban all commands available this element.
        """
        if command is None:
            for command_type in command_manager.CommandManager.all_command_list:
                self.global_ban_action(element, command_type.command_name)
            return
        self.persist_knowledge.add_invalid_action(
            unique_id=self.get_action_key(element, command)
        )
        self.update_action_weight(element, command, Weight.DISABLED_FOREVER)

    def filled_text_for(self, element_description: str) -> Optional[str]:
        return self.filled_texts.get(element_description, None)

    def add_filled_text(self, element_description: str, text: str) -> None:
        self.filled_texts[element_description] = text

    def set_human_description(self, known_description: Dict[str, str]):
        self.human_description = known_description
