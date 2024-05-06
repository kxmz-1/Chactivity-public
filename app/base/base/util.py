"""
low-level useful functions
"""
from pathlib import Path
import random
import time
from typing import Callable, Any, Iterable, List, Optional, Tuple, Type, Union
from hashlib import sha256 as hashlib_sha256

import regex
from app.base.base.const import ACTIONABLE_ATTRIBUTES
from app.base.base.custom_typing import XmlElement
from app.base.base.enrich import print, debug_print, debug_print_no
from os.path import commonprefix


def is_str_contentful(s: Optional[str]) -> bool:
    """
    Check if a string is not empty after strip
    :param s: The string to check
    :return: True if not empty, False if empty
    """
    if s is None or s.strip() == "":
        return False
    return True


def make_str_printable(s: Optional[str]) -> str:
    """
    remove all non-printable char from the string
    """
    if not s:
        return ""
    return "".join([ch for ch in s if ch.isprintable()])


def make_list_unique_and_printable(l: List[str]) -> List[str]:
    """
    Make a list unique and printable
    """
    return [i for i in make_list_unique([make_str_printable(s) for s in l]) if i]


def flatten(flatten_list: list) -> Iterable[Any]:
    """
    flatten a list
    src: https://www.zhihu.com/question/63739026/answer/212712388
    """
    for each in flatten_list:
        if not isinstance(each, list):
            yield each
        else:
            yield from flatten(each)


def strip_list(l: list) -> list:
    """
    Remove prefix & suffix list elements that bool is False
    """
    if not l:
        return l
    start_index = 0
    end_index = len(l)
    while start_index < end_index and not l[start_index]:
        start_index += 1
    while end_index >= start_index and not l[end_index - 1]:
        end_index -= 1
    return l[start_index:end_index]


def concat_strings(strings: List[Optional[str]], middle: str = "") -> str:
    """
    Concatenate strings with middle string, and strip empty strings or None
    """
    assert len(strings) == 2  # only support 2 strings currently
    contents = [s for s in strings if s]
    if len(contents) == 1:
        return contents[0]
    return middle.join(['"' + i + '"' for i in strings if i])


def construct_xpath_by_selectors(selectors: List[str]) -> str:
    """
    Construct xpath by selectors
    :param selectors: list of selectors, e.g. ["@class='android.widget.TextView'", "@resource-id='com.android.settings:id/title'"]
    :return: xpath string
    """
    return "//*" + "".join(f"[{selector}]" for selector in selectors)


def check_selectors_unique(selectors: List[str], root_tree: XmlElement) -> bool:
    """
    Checks if given selectors matches exactly only one element
    :param selectors: list of selectors, e.g. ["@class='android.widget.TextView'", "@resource-id='com.android.settings:id/title'"]
    :param root_tree: root tree of the xml
    :return: True if the selectors matches exactly one element, False otherwise
    """
    return len(root_tree.xpath(construct_xpath_by_selectors(selectors))) == 1


def get_element_exact_xpath(
    element: XmlElement, root_tree: XmlElement
) -> Optional[str]:
    """
    Get the exact xpath of an element, None if not found
    """
    # first construct the xpath class and resource-id
    selectors: List[str] = [
        "@class='%s'" % element.get("class"),
        "@resource-id='%s'" % element.get("resource-id"),
    ]
    for actionable_attribute in ACTIONABLE_ATTRIBUTES:
        selectors.append(
            "@%s='%s'" % (actionable_attribute, element.get(actionable_attribute))
        )
    if check_selectors_unique(selectors, root_tree):
        return construct_xpath_by_selectors(selectors)

    # then check if content-desc is unique
    selectors.append("@content-desc='%s'" % element.get("content-desc"))
    if check_selectors_unique(selectors, root_tree):
        return construct_xpath_by_selectors(selectors)
    """concat_strings(
        [
            "/",
            concat_strings(
                [
                    f"{elem.tag}[{elem.attrib['resource-id']}]"
                    if "resource-id" in elem.attrib
                    else elem.tag
                    for elem in element.iterancestors()
                ],
                "/",
            ),
            element.tag,
            f"[{element.attrib['resource-id']}]"
            if "resource-id" in element.attrib
            else "",
        ]
    )"""


def true(x: Union[str, None]) -> bool:
    """
    return True if x is "true", False otherwise
    """
    return x == "true"


def sha256(content: Union[str, bytes], usedforsecurity: bool = True) -> str:
    """
    return sha256 hexdigest of content
    """
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib_sha256(content, usedforsecurity=usedforsecurity).hexdigest()


def make_sth_a_list_if_it_is_not_a_list(sth) -> list:
    if isinstance(sth, list):
        return sth
    return [
        sth,
    ]


def ensure_dir(path: Union[str, Path]) -> Path:
    """
    Ensure the directory exists
    :param path: The directory path
    :return: The directory Path path
    """
    if isinstance(path, str):
        path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_file(path: Union[str, Path]) -> Path:
    """
    Ensure the file exists
    :param path: The file path
    :return: The file Path object
    """
    if isinstance(path, str):
        path = Path(path)
    ensure_dir(path.parent)
    path.touch(exist_ok=True)
    return path


def get_full_activity_name(package_name: str, activity_name: str) -> str:
    if activity_name.startswith("."):
        activity_name = package_name + activity_name
    return activity_name


def get_short_activity_name(package_name: str, activity_name: str) -> str:
    if activity_name.startswith(package_name):
        activity_name = activity_name[len(package_name) :]
    return activity_name


def is_desc_similar(desc1: str, desc2: str, prefix: str, suffix: str) -> bool:
    """
    Check if two description are similar(same, or both are digits and length difference is less than 2)
    """
    if desc1 == desc2:
        return True
    if desc1 == "" or desc2 == "":
        return False
    if (
        not desc1.startswith(prefix)
        or not desc2.startswith(prefix)
        or not desc1.endswith(suffix)
        or not desc2.endswith(suffix)
    ):
        return False
    if desc1.isdigit() and desc2.isdigit() and abs(len(desc1) - len(desc2)) < 2:
        return True
    return False


def is_all_desc_similar(descs: List[str]) -> bool:
    """
    Check if all descriptions are similar, False for empty list or list with only one element
    """
    if len(descs) <= 1:
        return False
    common_prefix, common_suffix = max_common_prefix(descs), max_common_suffix(descs)
    for i in range(len(descs) - 1):
        if not is_desc_similar(descs[i], descs[i + 1], common_prefix, common_suffix):
            return False
    return True


def make_short_resource_id(res_id: Optional[str]) -> str:
    """
    Remove the package name from resource id
    """
    if not res_id:
        return ""
    return res_id.split("/", 1)[-1]


def make_list_unique(l: List[Any]) -> List[Any]:
    """
    Make a list unique
    """
    return list(dict.fromkeys(l))


def random_sample_with_order(l: List[Any], n: int) -> List[Any]:
    """
    Randomly sample n elements from a list, but keep the order
    """
    if n >= len(l):
        return l
    indexs = random.sample(range(len(l)), n)
    indexs.sort()
    return [l[i] for i in indexs]


def max_common_prefix(strings: List[str]) -> str:
    """
    Get the max common prefix of a list of strings
    """
    if not strings:
        return ""
    return commonprefix(strings)


def max_common_suffix(strings: List[str]) -> str:
    """
    Get the max common suffix of a list of strings
    """
    if not strings:
        return ""
    return commonprefix([s[::-1] for s in strings])[::-1]


def parse_regex(
    pattern: regex.Pattern[str], string: str, no_raise: bool = False
) -> Tuple[str, ...]:
    result = pattern.search(string)
    if result is None:
        if no_raise:
            return tuple()
        raise ValueError("Regex pattern not found.")
    return result.groups()


def clean_sentence_to_phrase(prefix: str, sentence: str) -> str:
    """
    Make LLM reply (description for sth.) a phrase
    """
    prefix_wrapper = "".join(['"', "\\", "'"])
    sentence = (
        sentence.lstrip(prefix_wrapper)
        .removeprefix(prefix)
        .lstrip(prefix_wrapper)
        .strip(" .")
    )
    return sentence


def get_readable_time(
    format: str = "%Y-%m-%d %H:%M:%S", current_time: Optional[Union[float, int]] = None
) -> str:
    """
    Get current time or provided time in human readable format
    """
    if current_time is None:
        current_time = time.time()
    return time.strftime(format, time.localtime(current_time))
