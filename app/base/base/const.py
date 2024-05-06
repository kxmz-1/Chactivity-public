"""
Constants related with Android UI & testing.
"""
from enum import StrEnum
from threading import Lock
from typing import Dict, Final, List, Optional, Set, Tuple


TEXT_VIEW: Final[Set[str]] = {
    "android.widget.EditText",
    "android.widget.AutoCompleteTextView",
    "android.widget.MultiAutoCompleteTextView",
    "android.inputmethodservice.ExtractEditText",
}

NAME_ATTRIBUTE_NAME: Final[str] = "@android:name"
WRITE_GITHUB_SUMMARY_LOCK: Final[Lock] = Lock()
PASS_DOWN_ATTRIBUTES: Final[Set[str]] = {
    "clickable",
    "long-clickable",
    "scrollable",
}
ACTIONABLE_ATTRIBUTES: Final[Set[str]] = {
    "checkable",
    "clickable",
    "focusable",
    "long-clickable",
    "password",
    "scrollable",
}

MUST_DIFFERENT_ATTRIBUTES: Final[Set[str]] = {
    "index",
    "bounds",
}

ALL_ATTRIBUTES: Final[Set[str]] = {
    "index",
    "package",
    "class",
    "text",
    "resource-id",
    "checkable",
    "checked",
    "clickable",
    "enabled",
    "focusable",
    "focused",
    "long-clickable",
    "password",
    "scrollable",
    "selected",
    "bounds",
    "displayed",
}


class LLM_ELEMENT_TYPES(StrEnum):
    textbox = "textbox"
    button = "button"
    checkbox = "checkbox"
    container = "container"


CLASS_TO_TYPE: Dict[str, LLM_ELEMENT_TYPES] = {}
CLASS_TO_TYPE.update({class_: LLM_ELEMENT_TYPES.textbox for class_ in TEXT_VIEW})
CLASS_TO_TYPE.update(
    {
        "android.widget.Button": LLM_ELEMENT_TYPES.button,
        "android.widget.ImageButton": LLM_ELEMENT_TYPES.button,
        "android.widget.CheckBox": LLM_ELEMENT_TYPES.checkbox,
        "android.widget.Switch": LLM_ELEMENT_TYPES.checkbox,
        "android.widget.SwitchCompat": LLM_ELEMENT_TYPES.checkbox,
        "android.widget.ToggleButton": LLM_ELEMENT_TYPES.checkbox,
        "android.widget.RadioButton": LLM_ELEMENT_TYPES.checkbox,
        "android.view.ViewGroup": LLM_ELEMENT_TYPES.container,
        "androidx.recyclerview.widget.RecyclerView": LLM_ELEMENT_TYPES.container,
        "android.widget.FrameLayout": LLM_ELEMENT_TYPES.container,
        "android.widget.LinearLayout": LLM_ELEMENT_TYPES.container,
        "android.widget.RelativeLayout": LLM_ELEMENT_TYPES.container,
        "android.widget.TableLayout": LLM_ELEMENT_TYPES.container,
        "android.widget.GridLayout": LLM_ELEMENT_TYPES.container,
        "android.widget.ListView": LLM_ELEMENT_TYPES.container,
        "android.widget.ScrollView": LLM_ELEMENT_TYPES.container,
    }
)

ELEMENT_TYPE_TO_NL: Final[Dict[LLM_ELEMENT_TYPES, str]] = {
    LLM_ELEMENT_TYPES.textbox: "input field",
    LLM_ELEMENT_TYPES.button: "button",
    LLM_ELEMENT_TYPES.checkbox: "checkbox",
    LLM_ELEMENT_TYPES.container: "container (e.g. list, grid, scroll)",
}


def get_element_type_nl(class_: str) -> Optional[str]:
    """
    Get a natural language description of the element type
    """
    type_ = CLASS_TO_TYPE.get(class_)
    if type_ is None:
        return None
    return ELEMENT_TYPE_TO_NL.get(type_)


# A list of apps that might be achieved in a normal testing scenario.
# For example, some apps might require a photo taken by the camera.
# If we achieved somewhere NOT in the list, we will bring the app to the foreground.
# This list may vary across ROMs.
WHITELIST_APP_DURING_TESTING: Final[Set[str]] = {
    # browser (empty)
    # "com.android.chrome",
    # "com.android.browser",
    # camera
    "com.android.camera",
    "com.android.camera2",
    "com.google.android.camera",
    "org.codeaurora.snapcam",
    "com.android.mgc",
    "com.google.android.GoogleCameraEng",
    "com.ss.android.ugc.aweme",
    "com.samsung.android.scan3d"
    # gallery (currently empty),
    # email (empty)
    # sms (empty)
    # calendar (empty)
    # contacts (empty)
    # phone call (empty)
    # file selection
    "com.android.documentsui",
    "com.android.permissioncontroller",
}

OVERRIDE_CHILD_TEXT_CLASSES: Final[Set[str]] = {"TextInputLayout"}

TEXT_ATTRIBUTES: Final[Set[str]] = {"text", "content-desc"}

LOGIN_INTERFACE_KEYWORDS: Final[Set[str]] = {
    "username",
    "password",
    "email",
    "phone",
    "login",
    "sign in",
    "login with",
}
