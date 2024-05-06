"""
Analyze & process xml tree
"""
import functools
import json
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union, final
from app.base.base.const import (
    OVERRIDE_CHILD_TEXT_CLASSES,
    TEXT_ATTRIBUTES,
    TEXT_VIEW,
    get_element_type_nl,
    PASS_DOWN_ATTRIBUTES,
)
from app.base.base.custom_typing import (
    ElementAndDepth,
    MixedElement,
    XmlElement,
    Xpath,
    Bounds,
)
from app.base.base.util import (
    make_short_resource_id,
    concat_strings,
    flatten,
    is_str_contentful,
    make_list_unique_and_printable,
    make_str_printable,
    sha256,
    true,
)
from lxml import etree
from app.base.base.enrich import print, debug_print, debug_print_no


TEXTS_DELIM_CHAR = ", "
StubElementForNoDescriptionRequired = etree.Element("stub")


def _traverse_xml(
    xml_tree: XmlElement,
    child_element: list,
    flat_element_list: list,
    key_depth: int = 0,
) -> None:
    """
    Traverse the xml_tree, yield each key node and its depth
    """
    orig_child_element = child_element
    if "depth" in xml_tree.attrib:
        child_element = []
        key_depth += 1
    for child in xml_tree:
        _traverse_xml(child, child_element, flat_element_list, key_depth)
    if "depth" in xml_tree.attrib:
        orig_child_element.append((xml_tree, child_element))
        flat_element_list.append((xml_tree, key_depth))


def traverse_xml(xml_tree: XmlElement) -> List[ElementAndDepth]:
    """
    Traverse the xml_tree, return each key node and its depth
    """
    child_elements, flat_element_list = [], []
    _traverse_xml(xml_tree, child_elements, flat_element_list)
    return flat_element_list


def _indent_xml(
    xml_tree: XmlElement,
    root_element_tree: etree._ElementTree,
    detection_function: Callable,
    depth: int = 0,
) -> int:
    """
    Add depth attribute to valuable elements in xml_tree, DFS
    :param xml_tree: The current processing xml tree
    :param root_element_tree: The root xml tree
    :param detection_function: Detect if the element is valuable
    :return: total count of valuable elements in current xml tree
    """
    child_key_count = 0
    for child in xml_tree:
        child_key_count += _indent_xml(
            child, root_element_tree, detection_function, depth + 1
        )
    child_texts = make_element_description_list(
        xml_tree, ignore_common_attrs=True, no_wrap_child_texts=True, no_near_texts=True
    )
    # add near texts
    near_texts = []
    for node in xml_tree.itersiblings():
        if node == xml_tree:
            continue
        node_desc = make_element_description_list(
            node, ignore_common_attrs=True, no_wrap_child_texts=True, no_near_texts=True
        )
        if node_desc:
            near_texts.extend(node_desc)
    near_texts = make_list_unique_and_printable(near_texts)
    xml_tree.attrib["near_texts"] = json.dumps(near_texts)
    is_this_important = detection_function(xml_tree)
    xml_tree.attrib["child_key_count"] = str(child_key_count)
    if is_this_important:
        xml_tree.attrib["depth"] = str(depth)
        xml_tree.attrib["xpath"] = root_element_tree.getpath(xml_tree)
        child_key_count += 1
    child_texts.extend(
        flatten(
            [
                json.loads(child.attrib["child_texts"])
                for child in xml_tree
                if "depth" not in child.attrib
            ]
        )
    )
    child_texts = [i for i in child_texts if i not in near_texts]
    xml_tree.attrib["child_texts"] = json.dumps(child_texts)
    return child_key_count


def indent_xml(
    xml_tree: XmlElement, detection_function: Callable[[XmlElement], bool]
) -> XmlElement:
    """
    Add depth attribute to valuable elements in xml_tree
    :param xml_tree: The xml tree
    :param detection_function: Detect if the element is valuable
    :return: The original xml tree, with depth attribute added
    """
    root_element_tree: etree._ElementTree = xml_tree.getroottree()
    _indent_xml(xml_tree, root_element_tree, detection_function)
    return xml_tree


def do_func_on_every_element(xml_tree: XmlElement, func: Callable[[XmlElement], Any]):
    """
    Traverse every element (DFS), and do func on it
    """
    func(xml_tree)
    for i in xml_tree:
        do_func_on_every_element(i, func)


def make_new_tree(xml_tree: XmlElement) -> XmlElement:
    new_tree = etree.fromstring(etree.tostring(xml_tree))
    return new_tree


default_value_for_types = {
    bool: False,
    int: 0,
    float: 0.0,
    str: "",
    list: [],
    dict: {},
    tuple: (),
    set: set(),
}


def remove_attr_on_every_element(
    xml_tree: XmlElement, attrs: Union[Set[str], List[str]]
) -> XmlElement:
    """
    Return a new tree without specific attributes
    """
    xml_tree_new = make_new_tree(xml_tree)

    def remove_attr(element: XmlElement):
        for attr in attrs:
            if attr in element.attrib:
                element.attrib[attr] = default_value_for_types[
                    type(element.attrib[attr])
                ]

    do_func_on_every_element(xml_tree_new, remove_attr)
    return xml_tree_new


def get_xml_hash(xml_tree: XmlElement) -> str:
    return sha256(etree.tostring(xml_tree, encoding="unicode"))


def pass_down_actionable(xml_tree: XmlElement) -> XmlElement:
    """
    Make father's actionable attribute to be false if any of its children is actionable
    Original code from Dezhi Ran.
    Found in Spotify `Now Playing Bar` and sidebar
    """

    def pass_down(element: XmlElement):
        list_group = ["android.widget.RelativeLayout", "android.view.ViewGroup"]
        if element.get("class") not in list_group:
            return
        childs: List[XmlElement] = [child for child in element]
        if len(childs) >= 2:
            # unset all PASS_DOWN_ATTRIBUTES on parent
            parent_has_attrs = [i for i in PASS_DOWN_ATTRIBUTES if true(element.get(i))]
            if not parent_has_attrs:
                return
            for attr in parent_has_attrs:
                element.set(attr, "false")

            # here if images and texts are in the same group, we will pass only to the texts
            any_child_has_text = any(
                [true(child.get("text", "").strip()) for child in childs]
            )
            for child in childs:
                this_child_has_text = true(child.get("text", "").strip())
                if any_child_has_text and not this_child_has_text:
                    continue
                # update child's attributes

                # if child.get("resource-id", ""):
                #     child.attrib["resource-id"] = concat_strings(
                #         [
                #             make_short_resource_id(child.get("resource-id", "")),
                #             make_short_resource_id(element.get("resource-id", "")),
                #         ],
                #         " under ",
                #     )
                child.attrib["content-desc"] = concat_strings(
                    [
                        child.get("content-desc", ""),
                        element.get("content-desc", ""),
                    ],
                    " under ",
                )
                child.attrib["text"] = concat_strings(
                    [child.get("text", ""), element.get("text", "")], " under "
                )
                for attr in parent_has_attrs:
                    child.set(attr, "true")

    do_func_on_every_element(xml_tree, pass_down)
    return xml_tree


def pass_container_text_down(xml_tree: XmlElement) -> XmlElement:
    """
    Make `TextInputLayout` text attribute passed down to no text available children.

    Example:
    ```xml
    <TextInputLayout package="net.p4p.absen" class="TextInputLayout" text="Password" clickable="false" enabled="true" focusable="false" long-clickable="false" password="false" selected="false" bounds="[44,1578][1036,1740]">
        <android.widget.FrameLayout package="net.p4p.absen" class="android.widget.FrameLayout" text="" clickable="false" enabled="true" focusable="false" long-clickable="false" password="false" selected="false" bounds="[44,1608][1036,1740]">
        <android.widget.EditText package="net.p4p.absen" class="android.widget.EditText" text="" resource-id="net.p4p.absen:id/authenticationPasswordEditText" clickable="true" enabled="true" focusable="true" long-clickable="true" password="true" selected="false" bounds="[44,1608][1036,1740]"/>
        <android.widget.ImageButton package="net.p4p.absen" class="android.widget.ImageButton" text="" content-desc="Toggle password visibility" resource-id="net.p4p.absen:id/text_input_password_toggle" checkable="true" clickable="true" enabled="true" focusable="true" long-clickable="false" password="false" selected="false" bounds="[904,1608][1036,1740]"/>
        </android.widget.FrameLayout>
    </TextInputLayout>
    ```
    We can note that the `TextInputLayout` has text attribute, but its child `EditText` has no text attribute.

    To avoid overriding the text attribute of `TextInputLayout`, we pass attributes to `content-desc`.
    """

    def pass_down(element: XmlElement):
        if not element.get("class") in OVERRIDE_CHILD_TEXT_CLASSES:
            return
        element_attr = {k: v for k in TEXT_ATTRIBUTES if (v := element.get(k))}
        if not element_attr:
            return
        all_texts = "Description: " + ", ".join(element_attr.values())
        set_to_child = False
        TARGET_ATTR = "content-desc"
        for child in element.iterdescendants():
            if child.get(TARGET_ATTR, "") == "":
                child.set(TARGET_ATTR, all_texts)
                set_to_child = True
        if set_to_child:
            for attr in element_attr.keys():
                element.set(attr, "")
            element.set("abort_pass_up", "true")

    do_func_on_every_element(xml_tree, pass_down)
    return xml_tree


def merge_children_text_desc(xml_tree: XmlElement) -> XmlElement:
    """
    Merge text and content-desc of children into the parent
    """

    return xml_tree

    def merge(element: XmlElement):
        if ("depth" not in element.attrib) or (
            element.attrib["child_key_count"] != "0"
        ):
            # filter out non-key elements and not last-leaf elements
            return
        texts: List[str] = []
        for i in element.iterdescendants():
            if "depth" in i.attrib:
                continue
            texts.append(i.attrib["text"])
            texts.append(i.attrib["content-desc"])
        element.attrib["children_text"] = merge_text_parts(texts)

    do_func_on_every_element(xml_tree, merge)
    return xml_tree


def pass_down_child_texts(
    xml_tree: XmlElement, key_elements: List[XmlElement]
) -> XmlElement:
    """
    Make key elements' child_texts attribute to be the union of its direct parent's child_texts and its own child_texts
    """
    for key_element in key_elements:
        parent = key_element.getparent()
        if parent is None:  # root node detection
            continue
        if parent.get("depth", "") != "":  # do not pass from key element to key element
            continue
        parent_child_texts = json.loads(parent.get("child_texts", "[]"))
        if parent_child_texts == []:
            continue
        for child in parent:  # merge parent's child_texts into child's child_texts
            child_child_texts: List[str] = json.loads(child.get("child_texts", "[]"))
            if child_child_texts == parent_child_texts:
                continue
            final_child_texts = make_list_unique_and_printable(
                [
                    i
                    for i in (parent_child_texts + child_child_texts)
                    if i not in json.loads(child.get("near_texts", "[]"))
                ]
            )
            child.attrib["child_texts"] = json.dumps(final_child_texts)

    return xml_tree


def merge_text_parts(strings: List[str]) -> str:
    return TEXTS_DELIM_CHAR.join(
        [f'"{i}"' for i in strings if i != "" and i is not None]
    )


def is_element_inputable(element: XmlElement) -> bool:
    return element.get("class") in TEXT_VIEW


@functools.lru_cache(maxsize=10)
def make_element_description_list(
    element: Union[MixedElement, XmlElement],
    ignore_common_attrs: bool = False,
    no_wrap_child_texts: bool = False,
    ignore_text_for_inputable: bool = False,
    no_near_texts: bool = False,
) -> List[str]:
    NO_TEXT = "(no text)"
    content_list = []
    if isinstance(element, MixedElement):
        assert isinstance(element.xml_element, XmlElement)
        element = element.xml_element
    assert isinstance(element, XmlElement), ValueError(
        f"Unknown element type: {type(element)}"
    )
    for attr in TEXT_ATTRIBUTES:
        if is_str_contentful(element.get(attr)):
            is_inputable = is_element_inputable(element)
            if ignore_text_for_inputable and attr == "text" and is_inputable:
                continue
            content_list.append(element.get(attr))
    #        else:
    #            content_list.append(NO_TEXT)
    if resource_id := element.get("resource-id"):
        content_list.append(f"resource_id: {make_short_resource_id(resource_id)}")
    #    if not ignore_common_attrs:
    #        if class_name := element.get("class"):
    #            content_list.append(f"class: {class_name.split('.')[-1]}")
    for k, v in {"child_texts": "child texts", "near_texts": "near texts"}.items():
        if no_near_texts and k == "near_texts":
            continue
        if (val := element.get(k, None)) is not None and val != "" and val != "[]":
            attr_val_list = json.loads(val)
            attr_val_list = make_list_unique_and_printable(
                [i[:100] for i in attr_val_list]
            )
            attr_val_list = [i for i in attr_val_list if i not in content_list]
            if not attr_val_list:
                continue
            if no_wrap_child_texts and k == "child_texts":
                content_list.extend(attr_val_list)
            else:
                content_list.append(
                    f"{v}: {[i for i in attr_val_list if i not in content_list]}"
                )

    # 1. Clear all non-printable characters
    content_list = make_list_unique_and_printable(content_list)
    if ignore_common_attrs:
        if NO_TEXT in content_list:
            content_list.remove(NO_TEXT)
    return content_list


@functools.lru_cache(maxsize=10)
def make_element_description(
    element: Union[MixedElement, XmlElement, ElementAndDepth],
    ignore_common_attrs: bool = False,
    direct_text_only: bool = False,
    ignore_text_for_inputable: bool = False,
) -> str:
    """
    Generate the pure printable text for the element

    :param element: The element
    :param ignore_common_attrs: Do not include `class` attribute in the description. Not used now.
    :param direct_text_only: Return only the first available text part for the element. Used in action description.
    """
    if isinstance(element, MixedElement):
        assert isinstance(element.xml_element, XmlElement)
        element = element.xml_element
    if isinstance(element, tuple):
        element = element[0]  # ElementAndDepth
    assert isinstance(element, XmlElement), ValueError(
        f"Unknown element type: {type(element)}"
    )
    if element is StubElementForNoDescriptionRequired:
        return ""
    content_list = make_element_description_list(
        element,
        ignore_common_attrs=ignore_common_attrs,
        ignore_text_for_inputable=ignore_text_for_inputable,
    )
    content_list = [i for i in content_list if i != "" and i is not None]
    if direct_text_only:
        return content_list[0] if content_list else "an element without text"
    desc = merge_text_parts(content_list)
    return desc


def make_element_metadatas(element: Optional[XmlElement]) -> Dict[str, str]:
    # resource-id, text, class, child_texts, content-desc
    metadatas = {}
    if element is None:
        return metadatas
    attrs_to_names: Dict[str, str] = {
        "resource-id": "Resource id",
        "text": "Text",
        "class": "Widget class",
        "child_texts": "Children node texts",
        "near_texts": "Parent or sibling node texts",
        "content-desc": "Content description",
    }
    for attr in attrs_to_names:
        if (
            attr in element.attrib
            and element.get(attr)
            and element.attrib[attr] != "[]"
        ):
            metadatas[attrs_to_names[attr]] = element.attrib[attr]
            if attr == "resource-id":
                metadatas[attrs_to_names[attr]] = make_short_resource_id(
                    element.attrib[attr]
                )
    if (nl_element_type := get_element_type_nl(element.attrib["class"])) is not None:
        metadatas["Element type"] = nl_element_type
    return metadatas


@functools.lru_cache(maxsize=10)
def extract_xml_texts(
    xml_tree: XmlElement, max_text_length_each: int = 50
) -> List[str]:
    """
    Extract all texts from the xml tree
    """
    texts = []
    for element in xml_tree.iterdescendants():
        texts.append(element.get("text"))
        texts.append(element.get("content-desc"))
        texts.append(
            "resource-id: " + make_short_resource_id(element.get("resource-id", ""))
        )
    texts = [
        make_str_printable(t[:max_text_length_each])
        for t in texts
        if t != "" and t is not None and len(t) > 1
    ]
    texts = [t for t in texts if t]
    return list(set(texts))


def has_same_parent(
    element1: Optional[XmlElement], element2: Optional[XmlElement], max_depth: int = 3
) -> bool:
    """
    Check if two elements have the same parent / grandparent / `max_depth`th parent.
    """
    for _ in range(max_depth):
        if element1 is None and element2 is None:  # root node detection
            return True
        if element1 is None or element2 is None:
            return False
        element1 = element1.getparent()
        element2 = element2.getparent()
        if element1 == element2:
            return True
    return False


def filter_xpath_remove_index(xpath: Xpath) -> Xpath:
    """
    Remove all index from xpath.
    e.g. "aaa/bbb/c[2]/d[3]" -> "aaa/bbb/c/d"
    """
    parts = xpath.split("/")
    parts = [i[: i.find("[")] for i in parts]
    return "/".join(parts)


def is_element_same(
    elem1_mixed: Union[XmlElement, MixedElement],
    elem2_mixed: Union[XmlElement, MixedElement],
) -> bool:
    """
    Check if two elements are the same.
    """
    # detect if at least one is global element
    elem1 = (
        elem1_mixed if isinstance(elem1_mixed, XmlElement) else elem1_mixed.xml_element
    )
    elem2 = (
        elem2_mixed if isinstance(elem2_mixed, XmlElement) else elem2_mixed.xml_element
    )
    if elem1 is None or elem2 is None:
        return False
    # detect if they have same prompt
    if make_element_description(elem1) != make_element_description(elem2):
        return False
    # detect if they have same xpath (not considering xpath index)
    xpath1 = filter_xpath_remove_index(elem1.attrib["xpath"])
    xpath2 = filter_xpath_remove_index(elem2.attrib["xpath"])
    # xpath1 = elem1.attrib["xpath"]
    # xpath2 = elem2.attrib["xpath"]
    if xpath1 != xpath2:
        return False
    return True


def keep_only_one_res_id_in_child_texts(key_elements: List[XmlElement]) -> None:
    for element in key_elements:
        child_texts: List[str] = json.loads(element.get("child_texts", "[]"))
        if len(child_texts) <= 1:
            continue
        has_resource_id = False
        for child_text in child_texts[:]:
            if child_text.startswith("resource_id: "):
                if has_resource_id:
                    child_texts.remove(child_text)
                else:
                    has_resource_id = True
        element.set("child_texts", json.dumps(child_texts))


def parse_bounds(bound: str) -> Bounds:
    """
    Parse the bounds string to a tuple of 2 points
    :param bound: The bound string
    :return: The bound tuple
    """
    bound = bound.replace("][", ",").replace("[", "").replace("]", "")
    x1, y1, x2, y2 = [int(s) for s in bound.split(",")]
    return (x1, y1), (x2, y2)


def get_bound_center(bounds: Bounds) -> Tuple[int, int]:
    """
    Get the center point of the bounds
    :param bounds: The bounds
    :return: The center point
    """
    (x1, y1), (x2, y2) = bounds
    return (x1 + x2) // 2, (y1 + y2) // 2


def get_side_centers(bounds: Bounds) -> Dict[str, Tuple[int, int]]:
    """
    Get the center point of each side
    :param bounds: The bounds

    """
    (x1, y1), (x2, y2) = bounds
    ret = dict()
    ret["up"] = ((x1 + x2) // 2, y1)
    ret["down"] = ((x1 + x2) // 2, y2)
    ret["left"] = (x1, (y1 + y2) // 2)
    ret["right"] = (x2, (y1 + y2) // 2)
    return ret


def remove_duplicate_near_texts(xml_tree: XmlElement, elements: List[XmlElement]):
    all_direct_near_texts = []
    for element in elements:
        all_direct_near_texts.extend(json.loads(element.get("near_texts", "[]")))
    for element in elements:
        current_near_texts = json.loads(element.get("near_texts", "[]"))
        current_near_texts = [
            i for i in current_near_texts if i not in all_direct_near_texts
        ]
        element.set("near_texts", json.dumps(current_near_texts))
