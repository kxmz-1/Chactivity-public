import base64
import os
from pprint import pprint
import sys
from typing import Optional

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)


from app.base.device.adb_util import get_all_serial
from app.base.core.xml_util import (
    get_bound_center,
    make_element_description,
    parse_bounds,
)
from app.base.core.activity_status_memory import Activity, ActivityManager
from app.base.base.util import get_full_activity_name

# from app.base.base.enrich import print
from app.base.device.commands import BaseCommand, get_available_commands_for_xml_element
from app.base.device.commands.command_manager import CommandManager, CommandType
from app.base.core.persist_knowledge import PersistKnowledge
from app.base.base.custom_typing import MixedElement, XmlElement, WebElement
from app.base.device.appium_util import Selector

try:
    serial = sys.argv[1]
except IndexError:
    serials = get_all_serial()
    if len(serials) == 1:
        serial = serials[0]
    else:
        print(
            "Usage: python get_key_elements_of_current_view.py <serial of android device>"
        )
        sys.exit(1)

from lxml import etree
from io import BytesIO
from PIL import Image, ImageFont, ImageDraw
from appium import webdriver
from selenium.common.exceptions import TimeoutException

desired_caps = {
    "platformName": "Android",
    "deviceName": serial,
    "automationName": "UiAutomator2",
    "uiautomator2ServerInstallTimeout": 3000000,
    "adbExecTimeout": 4000000,
    "newCommandTimeout": 100000,
}
print("[*] Connecting to Appium...")
driver = webdriver.webdriver.WebDriver(
    "http://localhost:4723", desired_capabilities=desired_caps
)
print("[*] Connected to Appium.")

# main
current_package = driver.current_package
current_activity = get_full_activity_name(
    package_name=current_package, activity_name=driver.current_activity
)
print("[*] Current activity:", current_activity)

xml_content: str = driver.page_source
xml_tree = etree.fromstring(xml_content.encode("utf-8"))
persist_knowledge = PersistKnowledge(current_package)
activity_manager = ActivityManager(persist_knowledge, current_package)
activity = Activity(
    package_name=current_package,
    activity_name=current_activity,
    activity_manager=activity_manager,
)

status = activity.add_status(
    xml_tree=xml_tree,
    xml=xml_content,
    step_count=0,
)
print("[*] Initialized status.")


def clear_screen():
    os_type = os.name
    if os_type == "nt":
        os.system("cls")
    else:
        os.system("clear")


def dump_xml(path: str = "window_dump.xml"):
    with open(path, "wb") as f:
        f.write(etree.tostring(xml_tree))


command_handlers: list[BaseCommand] = [
    command(driver) for command in CommandManager.all_command_list
]
selector = Selector(driver)


def get_command_handler(command_name: str) -> BaseCommand:
    """
    Get command handler by command name
    """
    result = [i for i in command_handlers if i.command_name == command_name]
    if not result:
        raise ValueError("No such command name: " + command_name)
    assert len(result) == 1
    return result[0]


def get_web_element_by_xml_element(
    xml_element: Optional[XmlElement],
) -> Optional[WebElement]:
    if xml_element is None:
        return None
    xpath = xml_element.get("xpath", None)
    if xpath is None:
        return None
    ret = selector.xpath(xpath)[0]
    return ret


def get_mixed_element_by_xml_element(xml_element: Optional[XmlElement]) -> MixedElement:
    return MixedElement(
        xml_element=xml_element,
        web_element=get_web_element_by_xml_element(xml_element=xml_element),
    )


def print_elements():
    for element, depth in status.get_elements():
        # clear_screen()
        print()
        #    print(etree.tostring(element.getparent(), encoding="utf-8").decode("utf-8"))  # type: ignore
        #    print(etree.tostring(element, encoding="utf-8").decode("utf-8"))
        desc = make_element_description(element)
        print(desc)
        print(get_available_commands_for_xml_element(element=element))
        print()
        # if "Settings and privacy" in desc:
        #     try:
        #         get_command_handler("click").perform_action(
        #             get_mixed_element_by_xml_element(xml_element=element), {}
        #         )
        #     except TimeoutException:
        #         print("TimeoutException")


def get_screenshot_with_index(path: str = "draw_img.png") -> str:
    circle_size = 30
    x_offset = 20
    y_offset = 5
    resize_factor = 2
    first_index = 1
    # const end
    base64_image = driver.get_screenshot_as_png()
    print("[*] Got screenshot.")
    image = Image.open(BytesIO(base64_image)).convert(
        mode="RGB"
    )  # we need to add opacity ellipse
    circles: list[tuple[int, int]] = []
    for element, _ in status.get_elements():
        bound = element.get("bounds")
        assert bound is not None
        bounds = parse_bounds(bound)
        bound_center = get_bound_center(bounds)
        circles.append(bound_center)
    # sort cicrles
    # We found LLM tend to read from left to right, top to bottom, so it's better to sort the circles in this way.
    circle_sort_x_factor = 10  # increase this means x is less important
    circle_sort_y_factor = 150
    circles.sort(
        key=lambda x: (
            round(x[1] // circle_sort_y_factor),
            round(x[0] // circle_sort_x_factor),
        )
    )
    pprint(circles)
    font_style = ImageFont.truetype(r"calibri.ttf", size=60)
    draw = ImageDraw.Draw(image, "RGBA")
    for bound_center in circles:
        draw.ellipse(
            (
                bound_center[0] - circle_size + x_offset,
                bound_center[1] - circle_size + y_offset,
                bound_center[0] + circle_size + x_offset,
                bound_center[1] + circle_size + y_offset,
            ),
            (0, 0, 0, 180),
        )
        draw.text(
            (bound_center[0] - 15 + x_offset, bound_center[1] - 25 + y_offset),
            str(first_index),
            fill=(255, 255, 255, 255),
            font=font_style,
        )
        first_index += 1
    image = image.resize((image.width // resize_factor, image.height // resize_factor))
    image.save(path)
    print("[*] Finished drawing.")
    # breakpoint()
    return path


def ask_llm_about_screenshot():
    from app.base.llm.llm import chat_class

    llm = chat_class()
    llm.model("gpt-4-vision-preview")
    llm.system(
        "You are interacting with an Android application. Please give instructions based on provided UI screen and user instruction."
    )
    image_file = open(get_screenshot_with_index(), "rb")
    base64_image = base64.b64encode(image_file.read()).decode("utf-8")
    llm.message(
        "user",
        msg=[
            {
                "type": "text",
                "text": "1. There are several circles with number inside indicating UI elements. Please tell me what every element is. You should give the description along with the number displayed in the circle.\n",
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64_image}",
                    "detail": "high",
                },
            },
        ],
    )
    print("[*] Sent screenshot to LLM.")
    llm.update_ask_kwarg(max_tokens=2048)
    ret = (
        llm.ask(save_to_context=True, use_cache=False)
        .replace("\r\n", "\n")
        .replace("\n\n", "\n")
    )
    # print(llm.last_chat)
    # print("[llm] token count:", llm.token_count)
    print("[llm] Response:")
    print("=" * 20)
    print(ret)
    print("=" * 20)
    print()
    llm.message(
        "user",
        msg="Based only on your previous description, if I want to open the sidebar, which circle should I click? There must be an answer.",
    )
    llm.prompts[1]["content"].pop(-1)  # type: ignore
    ret1 = (
        llm.ask(save_to_context=True, use_cache=False)
        .replace("\r\n", "\n")
        .replace("\n\n", "\n")
    )
    print("[llm] Response:")
    print("=" * 20)
    print(ret1)
    print("=" * 20)


# get_screenshot_with_index()
# ask_llm_about_screenshot()
print_elements()
dump_xml()
