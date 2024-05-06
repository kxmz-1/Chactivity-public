"""
Record the actions during a testing.
"""
import time
from typing import Dict, Final, List, Optional, Callable, Self, Tuple, Type, Union
from app.base.base.custom_typing import Driver, MixedElement, WebElement, Xpath
from app.base.base.util import get_full_activity_name
from app.base.core.xml_util import StubElementForNoDescriptionRequired
from app.base.device.commands import BaseCommand
from app.base.base.enrich import debug_print


class RecordItem:
    version: int = 2

    def __init__(
        self,
        command_name: str,
        source_activity: str,
        target_acticity: str,
        element_xpath: Optional[str],
        extra_data: dict,
        time_space_before_action: float,
        action_time_used: float,
        source_status_hash: str,
        target_status_hash: str,
        action_description: Optional[str] = None,
    ):
        self.command_name = command_name
        self.source_activity = source_activity
        self.target_acticity = target_acticity
        self.element_xpath = element_xpath
        self.extra_data = extra_data
        self.time_space_before_action = time_space_before_action
        self.action_time_used = action_time_used
        self.source_status_hash = source_status_hash
        self.target_status_hash = target_status_hash
        self.action_description = action_description

    dump_attrs: List[str] = [
        "command_name",
        "source_activity",
        "target_acticity",
        "element_xpath",
        "extra_data",
        "time_space_before_action",
        "action_time_used",
        "source_status_hash",
        "target_status_hash",
        "action_description",
    ]

    def to_dict(self) -> dict:
        ret = {}
        for attr in self.dump_attrs:
            ret[attr] = getattr(self, attr)
        ret["version"] = self.version
        return ret

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        assert data["version"] == cls.version
        kwargs = {}
        for attr in cls.dump_attrs:
            kwargs[attr] = data[attr]
        return cls(**kwargs)


class Record:
    data: List[RecordItem]
    package_name: str
    package_version: Optional[str]
    version: int = 1
    start_time: float
    last_action_finish_time: float
    source_activity: str
    source_status: str  # sha256(xml)
    end_time: float = -1
    current_action_start_time: float
    finished: bool = False
    meta_attrs: List[str] = [
        "version",
        "package_name",
        "package_version",
        "source_activity",
        "source_status",
        "start_time",
        "end_time",
        "finished",
    ]

    def __init__(self, package_name: str, package_version: Optional[str] = None):
        self.package_name = package_name
        self.package_version = package_version
        self.first_step_to_target = {}
        self.start()

    def start_action(self) -> Self:
        self.current_action_start_time = time.time()
        return self

    def get_full_activity_name(self, activity: str) -> str:
        return get_full_activity_name(
            package_name=self.package_name, activity_name=activity
        )

    def add(
        self,
        command_name: str,
        source_activity: str,
        target_activity: str,
        element_xpath: Optional[Xpath],
        extra_data: dict,
        source_status_hash: str,
        target_status_hash: str,
        action_description: Optional[str],
    ) -> Self:
        if self.finished:
            raise RuntimeError("Trying to add data to a finished record.")
        current_time = time.time()
        source_activity = self.get_full_activity_name(source_activity)
        target_activity = self.get_full_activity_name(target_activity)
        self.data.append(
            RecordItem(
                command_name,
                source_activity,
                target_activity,
                element_xpath,
                extra_data,
                self.current_action_start_time - self.last_action_finish_time,
                time.time() - self.current_action_start_time,
                source_status_hash,
                target_status_hash,
                action_description=action_description,
            )
        )
        self.last_action_finish_time = current_time
        return self

    def start(self) -> Self:
        self.finished: bool = False
        self.data = []
        self.start_time = time.time()
        self.last_action_finish_time = self.start_time
        return self

    def end(self) -> Self:
        if self.finished:
            raise RuntimeError("Trying to finish a finished record.")
        self.end_time = time.time()
        self.finished = True
        return self

    @property
    def total_time(self) -> float:
        assert self.finished
        return self.end_time - self.start_time

    def set_source(self, activity: str, status: str) -> Self:
        self.source_activity = activity
        self.source_status = status
        return self

    def to_dict(self) -> dict:
        ret = {
            "data": [item.to_dict() for item in self.data],
        }
        for attr in self.meta_attrs:
            ret[attr] = getattr(self, attr)
        return ret

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        assert data["version"] == cls.version
        self = cls(package_name=data["package_name"])
        for item_data in data["data"]:
            assert item_data["version"] == RecordItem.version
            self.data.append(RecordItem.from_dict(item_data))
        for attr in self.meta_attrs:
            setattr(self, attr, data[attr])
        if not self.finished:
            self.end()
        return self

    def reproduce(
        self,
        selector: Callable[[str], WebElement],
        command_getter: Callable[[str], BaseCommand],
        hash_getter: Callable[[], str],
        ignore_sleep: bool = False,
        sleep_time_multiple_factor: float = 3,
    ) -> Self:
        """
        Reproduce the record.
        :param selector: The selector to select web element based on xpath.
        :param command_getter: Get command handler by name
        :param ignore_sleep: Whether to ignore sleep time.
        :param sleep_time_multiple_factor: The multiple factor of sleep time. The bigger, the faster.
        """
        SLEEP_MULTIPLE_WORK_AT_LEAST_FOR_SECONDS: Final[float] = 10
        old_current_activity = None
        old_current_hash = None
        last_action = None
        for item in self.data:
            if not ignore_sleep:
                sleep_time = item.time_space_before_action / sleep_time_multiple_factor
                if (
                    item.time_space_before_action
                    > SLEEP_MULTIPLE_WORK_AT_LEAST_FOR_SECONDS
                ):
                    sleep_time /= sleep_time_multiple_factor
                time.sleep(sleep_time)
            element = (
                selector(item.element_xpath) if item.element_xpath is not None else None
            )
            command = command_getter(item.command_name)
            # debug log
            new_current_activity = command.driver.current_activity
            new_current_hash = hash_getter()
            if old_current_activity is not None and old_current_hash is not None:
                debug_print("Action:", last_action)
                debug_print(
                    "Expected activity:",
                    item.source_activity,
                    "->",
                    item.target_acticity,
                )
                debug_print(
                    "Actual activity:", old_current_activity, "->", new_current_activity
                )
                debug_print(
                    "Expected status hash:",
                    item.source_status_hash,
                    "->",
                    item.target_status_hash,
                )
                debug_print(
                    "Actual status hash:", old_current_hash, "->", new_current_hash
                )
            old_current_activity = new_current_activity
            old_current_hash = new_current_hash
            last_action = item.command_name
            # end debug log
            command.perform_action(
                MixedElement(
                    xml_element=StubElementForNoDescriptionRequired, web_element=element
                ),
                item.extra_data,
            )
        return self

    def __len__(self):
        return len(self.data)

    def __getitem__(self, subscript: Union[int, slice]) -> Self:
        record = self.copy()
        new_data = self.data[subscript]
        if isinstance(new_data, RecordItem):
            new_data = [
                new_data,
            ]
        record.data = new_data
        return record

    def find_first_to_target(self, activity: str) -> int:
        """
        Find the first item that achieved the target activity.
        :param activity: The target activity.
        :return: The index of the first item that achieved the target activity.
        :raise ValueError: If the target activity is not found.
        """
        activity = self.get_full_activity_name(activity)
        for index, item in enumerate(self.data):
            if self.get_full_activity_name(item.target_acticity) == activity:
                return index
        raise ValueError(f"Target activity {activity} not found.")

    def test_find_all_firsts_to_target(self) -> Dict[str, int]:
        ret = {}
        for index, item in enumerate(self.data):
            if item.target_acticity not in ret:
                ret[item.target_acticity] = index
        return ret

    def copy(self) -> Self:
        new_instance = Record(
            package_name=self.package_name, package_version=self.package_version
        )
        new_instance.__dict__ = self.__dict__.copy()
        new_instance.data = self.data[:]
        return new_instance

    def __bool__(self) -> bool:
        raise RuntimeError(
            f"{repr(self.__class__)} should not be used as boolean value."
        )
