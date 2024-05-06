"""
Operate Appium and help with UI testing.
"""
from typing import Dict, List, Tuple, Union
from appium.webdriver.common.appiumby import AppiumBy
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.wait import WebDriverWait

from app.base.base.custom_typing import (
    SelectorElements,
    Xpath,
    Driver,
)
from tenacity import retry, stop_after_attempt, wait_fixed
from selenium.common.exceptions import TimeoutException


class Selector:
    """
    A helper class to find elements.
    """

    def __init__(self, driver: Driver):
        self.driver: Driver = driver

    @retry(stop=stop_after_attempt(5), wait=wait_fixed(0.5), reraise=True)
    def _xpath_inner(self, xpath: Xpath) -> SelectorElements:
        """
        Find elements by xpath, with delay to wait for the elements to be loaded.
        """
        wait = WebDriverWait(self.driver, 3)
        wait.until(
            expected_conditions.presence_of_all_elements_located(
                (AppiumBy.XPATH, xpath)
            )
        )

        return self.driver.find_elements(AppiumBy.XPATH, xpath)

    def xpath(self, xpath: Xpath) -> SelectorElements:
        """
        Find elements by xpath, wrapped to ensure raise `TimeoutException
        """
        ret = self._xpath_inner(xpath)
        if not ret:
            raise TimeoutException(f"Cannot find element by xpath: {xpath}")
        return ret
