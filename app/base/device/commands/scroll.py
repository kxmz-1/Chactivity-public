from app.base.device.adb_util import get_device_size
from app.base.base.util import true
from . import base, command_manager
from app.base.core.xml_util import (
    get_bound_center,
    get_side_centers,
    parse_bounds,
)
from app.base.core.xml_util import make_element_description


@command_manager.CommandManager.register
class ScrollCommand(base.BaseCommand):
    command_name = "scroll"
    prompt_event_description = "Only when you want to load more content in a scrollable view, you can use this function to scroll it. "
    perform_on_element = True
    perform_on_global = False

    function_call_properties = {
        "direction": {
            "type": "string",
            "description": "direction to scroll to",
            "enum": ["UP", "DOWN", "LEFT", "RIGHT"],
        },
    }

    @classmethod
    def get_prompt_element_description(cls, element):
        assert element.xml_element is not None
        return "scroll" if true(element.xml_element.get("scrollable")) else False

    def perform_action(self, element, extra_data):
        if "direction" not in extra_data:
            raise command_manager.NoEnoughArgumentsError("direction")
        direction: str = extra_data["direction"].lower()
        if " or " in direction:
            direction = "DOWN".lower()
        if element.is_global:
            # LLM thinks it can be global event, so let's do it.
            desc = f"Scroll the whole view {direction}"
            bounds = ((0, 0), get_device_size(extra_data["chat_device_serial"]))
        else:
            assert element.web_element is not None
            desc = f'Scroll "{make_element_description(element, direct_text_only=True)}" {direction}'
            bounds = parse_bounds(element.web_element.get_attribute("bounds"))  # type: ignore
        center = get_bound_center(bounds)
        target = get_side_centers(bounds)[direction]
        self.driver.swipe(center[0], center[1], target[0], target[1], 1000)
        return desc
