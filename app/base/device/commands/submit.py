from app.base.base.const import TEXT_VIEW
from . import base, command_manager
from app.base.core.xml_util import make_element_description


@command_manager.CommandManager.register
class SubmitCommand(base.BaseCommand):
    command_name = "submit"
    prompt_event_description = (
        'Only when target is a element and target includes "submit" attribute, \
you can submit the text box\'s content (e.g. apply, search, send) '
        "using: COMMAND=submit, EXTRA={}"
    )
    perform_on_element = True

    # function_call_properties = {
    #     "action": {
    #         "type": "string",
    #         "description": "action to perform",
    #         "enum": ["go", "search", "send"],
    #     }
    # }

    @classmethod
    def get_prompt_element_description(cls, element):
        assert element.xml_element is not None
        return "submit" if element.xml_element.get("class") in TEXT_VIEW else False

    def perform_action(self, element, extra_data):
        desc = f"Submit the content of {make_element_description(element, direct_text_only=True)}"
        for action in ("go", "search", "send"):
            self.driver.execute_script(
                "mobile: performEditorAction", {"action": action}
            )
        return desc
