from abc import abstractmethod, ABC
from typing import Final, List, Literal, Optional, Union, ClassVar, final
from app.base.base.custom_typing import Driver, MixedElement, WebElement, XmlElement


class BaseCommand(ABC):
    driver: Final[Driver]

    prompt_event_description: ClassVar[str] = ""
    command_name: ClassVar[str] = ""

    perform_on_element: ClassVar[bool] = True
    # Whether this event can be performed on a specific element.
    perform_on_global: ClassVar[bool] = False
    # Whether this event can be performed on global page.
    function_call_properties: ClassVar[dict] = {
        # "value1": {"type": "number", "description": "first number"},
        # "unit": {"type": "string", "enum": ["celsius", "fahrenheit"]},
    }

    @final
    def __init__(self, driver: Driver):
        self.driver = driver

    @abstractmethod
    def perform_action(self, element: MixedElement, extra_data: dict) -> str:
        """
        Use LLM's reply to perform an action on the element
        :param element: The element to perform action on
        :param extra_data: Extra data for the action
        """
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def get_prompt_element_description(
        cls, element: MixedElement
    ) -> Union[str, Literal[False]]:
        """
        How should the element be described in the prompt
        e.g. `clickable` in `INDEX-1: clickable`
        :param element: The element to describe
        :return: The description if the element is actionable, False otherwise
        """
        raise NotImplementedError

    @final
    @classmethod
    def get_function_call(cls) -> dict:
        ret = {
            "name": cls.command_name,
            "description": cls.prompt_event_description,
            "parameters": {"properties": cls.function_call_properties},
        }
        ret["parameters"]["type"] = "object"
        # assume every parameter is required
        ret["parameters"]["required"] = [
            i for i in ret["parameters"]["properties"].keys()
        ]
        ret_tool = {"type": "function", "function": ret}
        return ret_tool
