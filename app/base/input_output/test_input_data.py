"""
Read & process test input data from json file
"""
import json
import os
from typing import Any, Dict, NotRequired, Optional, TypedDict, Union
from pathlib import Path


class Task:
    task_type: str
    target: Any

    def __init__(self, task_type: str, target, extra_kwargs: Dict[str, Any]):
        self.task_type = task_type
        self.target = target
        self.extra_kwargs = extra_kwargs

    def __repr__(self):
        return f"{self.task_type}({self.target})"

    def to_dict(self):
        return {
            "task_type": self.task_type,
            "target": self.target,
            "extra_kwargs": self.extra_kwargs,
        }


class TestInputDataJson(TypedDict):
    apk: NotRequired[str]
    package_name: NotRequired[str]
    tasks: Dict[str, Any]
    known_activities_data: NotRequired[Dict[str, Any]]
    capabilities_mixin: NotRequired[Dict[str, Any]]
    device_type: NotRequired[str]


class TestInputData:
    def __init__(self, file_path: Union[str, Path]):
        self.file_path: str = str(file_path)
        self._original_json: TestInputDataJson = json.load(
            open(file_path, "r", encoding="utf8")
        )

        apk_path: Optional[str] = self._original_json.get("apk", None)
        self.apk_file: Optional[str] = None
        if apk_path:
            if apk_path.startswith("*APK_DIR*/") and os.environ.get("APK_DIR"):
                apk_path = os.path.join(
                    os.environ["APK_DIR"], apk_path.replace("*APK_DIR*/", "")
                )
            self.apk_file = apk_path

        package_name: Optional[str] = self._original_json.get("package_name", None)

        # we don't check apk / (package_name & home_activity) here as it is checked in Chactivity.init

        self._extra_kwargs: dict = {
            "apk": self.apk_file,
            "package_name": package_name,
            "known_activities_data": self._original_json.get("known_activities", {}),
            "capabilities_mixin": self._original_json.get("capabilities_mixin", {}),
        }
        task_type = self._original_json["tasks"]["type"]
        self.tasks = [
            Task(
                task_type=task_type,
                target=target,
                extra_kwargs=self._extra_kwargs,
            )
            for target in self._original_json["tasks"]["targets"]
        ]

        self.device_types: Optional[str] = self._original_json.get("device_type", None)
