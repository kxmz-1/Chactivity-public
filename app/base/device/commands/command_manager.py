from typing import Dict, List, Type, TypeAlias
from . import base

CommandType: TypeAlias = Type[base.BaseCommand]


# all register is done when you import command_manager, which will trigger the import of __init__.py
class CommandManager:
    all_command_list: List[CommandType] = []
    name_command_table: Dict[str, CommandType] = {}

    @classmethod
    def register(cls, event_handler: CommandType) -> CommandType:
        cls.all_command_list.append(event_handler)
        if event_handler.command_name in cls.name_command_table:
            raise ValueError(f"Duplicate event name {event_handler.command_name}")
        cls.name_command_table[event_handler.command_name] = event_handler
        return event_handler

    @classmethod
    def get_event_handler(cls, command_name: str) -> CommandType:
        return cls.name_command_table[command_name]


class NoEnoughArgumentsError(AttributeError):
    def __init__(self, argument_name: str):
        self.argument_name = argument_name

    def __str__(self):
        return (
            f"Argument {self.argument_name} is required in EXTRA but LLM not provided."
        )
