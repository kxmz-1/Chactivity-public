"""
Persist useful knowledge learned from finished testing for future use.
For example:
- `ActivityPath` for find start activity
- `ActivityDescription` for mapping activity to natural language
- `InvalidAction` for preventing useless interactions with UI elements
"""
from enum import StrEnum
import os
import json
from typing import Any, Dict, List, Optional, Self, Tuple, TypedDict

from app.base.base.config import config
from app.base.base.custom_typing import Xpath
from app.base.base.util import ensure_dir
from app.base.core.activity_knowledge import ActivityPath
from app.base.base.event_handler import ee, Events, send_notification


class PersistKnowledge:
    """
    Store ActivityPath, Activity desctiption, invalid actions for future use.
    Save in multiple JSON files.
    """

    version: int = 1
    activity_path: List[ActivityPath]
    activity_description: Dict[str, Optional[str]]
    invalid_actions: List[str]
    failed_ideas: Dict[str, List[str]]

    class Files(StrEnum):
        ActivityPath = "activity_path.json"
        ActivityDescription = "activity_description.json"
        InvalidAction = "invalid_actions.json"
        FailedIdeas = "failed_ideas.json"

    def __init__(
        self,
        package_name: str,
        path: str = config.app.core.persist_knowledge_path,
        clear: bool = False,
    ):
        self.path: str = os.path.join(os.path.expanduser(path), package_name)
        self.clear()
        if clear:
            self.save()
        try:
            self.load()
        except FileNotFoundError:
            pass
        except json.JSONDecodeError:
            send_notification(
                "warning|persist_json_load",
                f"JSONDecodeError when loading {self.path}, please check the file.",
            )

    # only one instance for each package
    _instances: Dict[str, Self] = {}

    def __new__(cls, package_name: str, *args, **kwargs):
        if package_name not in cls._instances:
            cls._instances[package_name] = super().__new__(cls)
        return cls._instances[package_name]

    @staticmethod
    def json_dump(obj: Any, file_path: str):
        """
        Dump the object to JSON file.
        """
        with open(file_path, "w", encoding="utf8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=4)

    @staticmethod
    def json_load(file_path: str) -> Any:
        """
        Load the object from JSON file.
        """
        with open(file_path, "r", encoding="utf8") as f:
            return json.load(f)

    def silent_save(self, object, path):
        try:
            self.json_dump(object, path)
        except:
            pass

    def silent_load(self, path, default):
        try:
            return self.json_load(path)
        except:
            return default

    def save(self):
        """
        Save the data in JSON files.
        """
        ensure_dir(self.path)
        self.json_dump(
            [i.to_dict() for i in self.activity_path],
            os.path.join(self.path, self.Files.ActivityPath),
        )
        self.json_dump(
            self.activity_description,
            os.path.join(self.path, self.Files.ActivityDescription),
        )
        self.json_dump(
            self.invalid_actions, os.path.join(self.path, self.Files.InvalidAction)
        )
        self.json_dump(
            self.failed_ideas, os.path.join(self.path, self.Files.FailedIdeas)
        )

    def load(self):
        """
        Load the data from JSON files.
        """
        self.activity_path = [
            ActivityPath.from_dict(i)
            for i in self.silent_load(
                os.path.join(self.path, self.Files.ActivityPath), []
            )
        ]
        self.activity_description = self.silent_load(
            os.path.join(self.path, self.Files.ActivityDescription), {}
        )
        self.invalid_actions = self.silent_load(
            os.path.join(self.path, self.Files.InvalidAction), []
        )
        self.failed_ideas = self.silent_load(
            os.path.join(self.path, self.Files.FailedIdeas), {}
        )

    def add_activity_path(self, activity_path: ActivityPath):
        """
        Add an ActivityPath to the knowledge.
        """
        self.activity_path.append(activity_path)

    def get_activity_paths(self) -> Dict[str, List[ActivityPath]]:
        """
        Get the simplest ActivityPaths to a specific activity.
        """
        ret: Dict[str, List[ActivityPath]] = {}
        for i in self.activity_path:
            ret.setdefault(i.activity, []).append(i)
        for each in ret.values():  # sort, the shortest path is the best
            each.sort(key=lambda x: len(x))
        return ret

    def add_activity_description(self, activity_name: str, description: Optional[str]):
        """
        Add an Activity description to the knowledge.
        """
        self.activity_description[activity_name] = description

    def get_activity_description(self, activity_name: str) -> Optional[str]:
        """
        Get the description of an activity.
        """
        return self.activity_description.get(activity_name, None)

    def should_ban_action(self, unique_id: str) -> bool:
        """
        Check if the element should be banned.
        """
        if unique_id in self.invalid_actions:
            return True
        return False

    def add_invalid_action(self, unique_id: str):
        """
        Add an invalid action to the knowledge.
        """
        if unique_id not in self.invalid_actions:
            self.invalid_actions.append(unique_id)

    def add_failed_idea(self, target: str, idea: str):
        """
        Add a failed idea to the knowledge.
        """
        if idea not in self.failed_ideas.get(target, []):
            self.failed_ideas.setdefault(target, []).append(idea)

    def get_failed_ideas(self) -> Dict[str, List[str]]:
        """
        Get the failed ideas for targets.
        """
        return self.failed_ideas

    def clear(self):
        """
        Clear the knowledge.
        """
        self.activity_path = []
        self.activity_description = {}
        self.invalid_actions = []
        self.failed_ideas = {}
