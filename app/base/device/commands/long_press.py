from appium.webdriver.common.touch_action import TouchAction

from app.base.base.util import true
from . import base, command_manager
from app.base.core.xml_util import make_element_description


@command_manager.CommandManager.register
class LongPressCommand(base.BaseCommand):
    command_name = "long_press"
    prompt_event_description = "Only when you are required to long press a element by provided UI description, '\
        'you can use this function to perform a long press action. Most time, you don't need to use this function"
    perform_on_element = True

    @classmethod
    def get_prompt_element_description(cls, element):
        assert element.xml_element is not None
        return (
            "long_press" if true(element.xml_element.get("long-clickable")) else False
        )

    def perform_action(self, element, extra_data):
        assert element.web_element is not None
        desc = f"Long press {make_element_description(element, direct_text_only=True)}"
        TouchAction(self.driver).long_press(element.web_element).perform()
        return desc
