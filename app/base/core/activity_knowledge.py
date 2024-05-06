"""
Record ActivityPath, which is a path from one activity to another activity.
The path is represented by a Record, which is a list of command.
Meta data like package name, activity name, and requirement of app first launch \
are also stored in ActivityPath.
"""
from typing import Callable, Self, Union
from app.base.base.custom_typing import Driver, WebElement
from app.base.base.util import get_full_activity_name
from app.base.device.commands import BaseCommand
from app.base.core.record import Record


class ActivityPath:
    package: str
    activity: str
    record: Record
    require_app_first_init: bool
    require_app_homepage: bool

    def __init__(
        self,
        package: str,
        activity: str,
        record: Union[dict, Record],
        require_app_first_init: bool = True,
        require_app_homepage: bool = True,
    ) -> None:
        self.package = package
        self.activity = get_full_activity_name(
            package_name=package, activity_name=activity
        )
        if isinstance(record, dict):
            self.record = Record.from_dict(record)
        else:
            self.record = record
        self.require_app_first_init = require_app_first_init
        self.require_app_homepage = require_app_homepage

    def __len__(self):
        return len(self.record)

    def get_full_activity_name(self, activity_name: str) -> str:
        return self.record.get_full_activity_name(activity_name)

    def reproduce(
        self,
        is_app_first_launch: bool,
        is_app_homepage: bool,
        selector: Callable[[str], WebElement],
        hash_getter: Callable[[], str],
        command_getter: Callable[[str], BaseCommand],
        driver: Driver,
    ):
        if is_app_first_launch != self.require_app_first_init:
            raise RuntimeError("App first launch requirement not satisfied")
        if is_app_homepage != self.require_app_homepage:
            raise RuntimeError("App homepage requirement not satisfied")
        self.record.reproduce(selector, command_getter, hash_getter)
        current_activity = self.get_full_activity_name(driver.current_activity)
        expected_activity = self.get_full_activity_name(self.activity)
        if current_activity != expected_activity:
            raise RuntimeError(
                f"Current activity {current_activity} not match target activity {expected_activity}."
            )

    def to_dict(self) -> dict:
        return {
            "package": self.package,
            "activity": self.activity,
            "record": self.record.to_dict(),
            "require_app_first_init": self.require_app_first_init,
            "require_app_homepage": self.require_app_homepage,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls(
            data["package"],
            data["activity"],
            data["record"],
            data["require_app_first_init"],
            data["require_app_homepage"],
        )
