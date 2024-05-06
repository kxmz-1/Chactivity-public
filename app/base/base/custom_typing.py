"""
Custom typing for the project
"""
from typing import List, Optional, Type, Union, TypeAlias, Tuple
from appium.webdriver.webelement import WebElement
from lxml import etree

from appium.webdriver.webdriver import WebDriver as Driver

SelectorElements: TypeAlias = Union[List[WebElement], List]
Bounds: TypeAlias = Tuple[Tuple[int, int], Tuple[int, int]]
XmlElement: TypeAlias = etree._Element
Xpath: TypeAlias = str
ElementAndDepth: TypeAlias = Tuple[XmlElement, int]


class MixedElement:
    def __init__(
        self, xml_element: Optional[XmlElement], web_element: Optional[WebElement]
    ):
        """
        For a regular element, both xml_element and web_element are not None.
        For a global element, xml_element is None and web_element is None.
        During record reproduce, xml_element may be None for regular elements.
        """
        self.xml_element = xml_element
        self.web_element = web_element

    @property
    def is_global(self) -> bool:
        return self.xml_element is None and self.web_element is None
