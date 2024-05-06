"""
Register all test types.
Each test type should be a subclass of `base.Chactivity`.
"""
from typing import Dict, List, Type, TypeAlias
from . import base

TestTypeType: TypeAlias = Type[base.Chactivity]


# Copy & Paste LMAO
class TestManager:
    all_command_list: List[TestTypeType] = []
    name_command_table: Dict[str, TestTypeType] = {}

    @classmethod
    def register(cls, task_handler: TestTypeType) -> TestTypeType:
        cls.all_command_list.append(task_handler)
        if task_handler.task_type in cls.name_command_table:
            raise ValueError(f"Duplicate name {task_handler.task_type}")
        cls.name_command_table[task_handler.task_type] = task_handler
        return task_handler

    @classmethod
    def get(cls, task_type: str) -> TestTypeType:
        if task_type not in cls.name_command_table:
            raise ValueError(
                f"Unknown task type `{task_type}`. Valid task types are {cls.name_command_table.keys()}"
            )
        return cls.name_command_table[task_type]
