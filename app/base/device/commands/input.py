from app.base.base.const import TEXT_VIEW
from app.base.llm.secret_manager import fill_secrets, get_prompts_for_secrets
from . import base, command_manager
from app.base.core.xml_util import is_element_inputable, make_element_description


@command_manager.CommandManager.register
class InputCommand(base.BaseCommand):
    command_name = "input"
    prompt_event_description = (
        'Only when target is a element and target includes "input" attribute, you can input any text in it '
        + "to login, search, or input any text. Use it only when you are sure this is a must for achieving your goal."
        + "\n    "
        + "\n    ".join(get_prompts_for_secrets())
        + "\n    Please note that the $ characters are part of the text and thus should be inputed."
    )
    perform_on_element = True

    function_call_properties = {
        "text": {"type": "string", "description": "text to input"},
    }

    @classmethod
    def get_prompt_element_description(cls, element):
        # detect if the class is input-able based on its class
        assert element.xml_element is not None
        return "input" if is_element_inputable(element.xml_element) else False

    def perform_action(self, element, extra_data):
        assert "text" in extra_data, command_manager.NoEnoughArgumentsError("text")
        assert element.web_element is not None
        text = extra_data["text"]
        text = fill_secrets(text)
        desc = f'Input "{text}" to "{make_element_description(element, direct_text_only=True)}"'
        element.web_element.clear()
        element.web_element.send_keys(text)
        return desc
