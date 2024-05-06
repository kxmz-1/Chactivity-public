from typing import List
from app.base.base.custom_typing import MixedElement, XmlElement
from . import command_manager
from . import click
from . import back

# from . import long_press
from . import input
from . import submit
from . import scroll
from . import sleep as sleep_command_init

# from . import submit
from . import base
from . import monkey

BaseCommand = base.BaseCommand


def get_available_commands_for_xml_element(element: XmlElement) -> List[str]:
    ret = [
        k.get_prompt_element_description(
            MixedElement(xml_element=element, web_element=None)
        )
        for k in command_manager.CommandManager.all_command_list
        if k.perform_on_element
    ]
    return [k for k in ret if k is not False and isinstance(k, str)]
