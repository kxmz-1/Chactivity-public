"""
Useful type aliases & classes highly related to testing.
"""
from typing import Dict, List, Optional, TypeAlias, Union
from app.base.core.activity_status_memory import Activity, Status
from app.base.base.custom_typing import XmlElement, Xpath


class LLMChoice:
    def __init__(
        self,
        prompt_index: Union[str, int],
        element: Optional[XmlElement],
        element_desc: str,
        commands: List[str],
        depth: int,
        operated_before: bool,
    ):
        self.prompt_index = str(prompt_index)
        self.element = element  # None for GLOBAL
        self.element_desc = element_desc
        self.commands = commands
        self.depth = depth
        self.operated_before = operated_before

    @property
    def prompt(self) -> str:
        """
        e.g. 3 └└ (click input submit): "class: EditText", "child texts: '['resource_id: authenticationEmailEditText']"
        """
        return f"{self.prompt_index} {self.prompt_without_index}" + (
            " (operated before)" if self.operated_before else ""
        )

    @property
    def prompt_without_index(self) -> str:
        """
        e.g. └└ (click input submit): "class: EditText", "child texts: '['resource_id: authenticationEmailEditText']"
        """
        return f"{'└'*(self.depth-1)} {self.prompt_without_index_and_depth}"

    @property
    def prompt_without_index_and_depth(self) -> str:
        """
        e.g. (click input submit): "class: EditText", "child texts: '['resource_id: authenticationEmailEditText']"
        """
        return f"({' '.join(self.commands)}): {self.element_desc}"

    @property
    def is_global(self) -> bool:
        return self.element is None

    @property
    def xpath(self) -> Optional[Xpath]:
        """
        Element xpath, None for GLOBAL
        """
        return None if self.element is None else self.element.attrib["xpath"]


ChoiceMappingType: TypeAlias = Dict[str, LLMChoice]


class EnvAndAction:
    @property
    def xpath(self) -> Optional[Xpath]:
        """
        Element xpath, None for GLOBAL
        """
        return None if self.element is None else self.element.attrib["xpath"]

    @property
    def description_for_llm(self) -> str:
        """
        The exact history entry line provided to LLM.
        """
        return f"{self.fixed_operation_description}"

    def __init__(
        self,
        activity: Activity,
        status: Status,
        element: Optional[XmlElement],  # None for GLOBAL
        command: str,
        extra: dict,
        fixed_operation_description: str,
    ):
        self.activity = activity
        self.status = status
        self.element = element
        self.command = command
        self.extra = extra
        self.fixed_operation_description = fixed_operation_description
        self.operation_description = fixed_operation_description
