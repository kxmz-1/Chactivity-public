from app.base.base.util import true
from . import base, command_manager
from app.base.core.xml_util import make_element_description


@command_manager.CommandManager.register
class ClickCommand(base.BaseCommand):
    command_name = "click"
    prompt_event_description = (
        'Only when target is a element and target includes "click" attribute, you can click it '
        "using this function to perform a click action. This is the action you need to perform most time."
    )
    perform_on_element = True
    function_call_properties = {
        # "element": {"type": "int", "description": "element index to click"},
        # Currently, we choose element before click, so we don't need to specify element index.
    }

    @classmethod
    def get_prompt_element_description(cls, element):
        assert element.xml_element is not None
        return "click" if true(element.xml_element.get("clickable")) else False

    def perform_action(self, element, extra_data):
        desc = f'Click "{make_element_description(element, direct_text_only=True)}"'
        assert element.web_element is not None
        element.web_element.click()
        return desc
