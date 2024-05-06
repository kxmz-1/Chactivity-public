"""
Events used in pyee and their definitions.
"""
from enum import Enum, StrEnum, auto
from typing import List, Union
import pyee

ee = pyee.EventEmitter()


class Events(StrEnum):
    """
    All events used in pyee
    """

    onNotification = auto()
    # send a notification, shown in console and log file.
    # onNotification(level: str, content: str)
    onChatMessage = auto()
    # send a chat message from/to LLM, shown in console and log file.
    # onChatMessage(role: str, content: str)
    onDeviceReAvailable = auto()
    # emit when a device is idle (all tests finished)
    # onDeviceReAvailable(device: Device)
    onDeviceOccupied = auto()
    # emit when a device is occupied (a test begins running)
    # onDeviceOccupied(device: Device)
    onPackageTestFinished = auto()
    # emit when a package test is finished
    # onPackageTestFinished()
    KeyboardInterrupt = auto()
    # emit when a KeyboardInterrupt is raised, used to stop tests
    # KeyboardInterrupt()
    failFast = auto()
    # emit when an unknown error is raised in a test, used to stop all tests for debugging
    # failFast()


def send_notification(level: Union[str, List[str]], content: str) -> bool:
    """
    Send a basic notification to the user.
    :param level: The level of the notification, can be "info", "warning", "error", "success". Use `|` to delim multiple flags.
    :param content: The content of the notification.
    """
    if isinstance(level, list):
        level = "|".join(level)
    return ee.emit(Events.onNotification, level, content)
