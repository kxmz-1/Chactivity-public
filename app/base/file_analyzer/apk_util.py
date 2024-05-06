"""
APK utilities
"""
from typing import Any, List, Optional, Tuple, Union
from pathlib import Path
from apkutils3 import APK as apkutils_APK
from app.base.base.util import flatten, make_sth_a_list_if_it_is_not_a_list
from app.base.base.const import NAME_ATTRIBUTE_NAME
from app.base.base.enrich import print


def get_apks(path: Union[str, Path]) -> List[str]:
    """
    get all apk files in the path folder and its sub-folders
    """
    if isinstance(path, str):
        path = Path(path)
    matches = path.glob("**/*.apk")
    return [str(x) for x in matches]


class APK(apkutils_APK):
    """
    Wrapper of apkutils_APK
    """

    def __init__(self, apk_path):
        super().__init__(apk_path=apk_path)
        assert self.home_activity is not None, f"home_activity is None for {apk_path}"

    def __repr__(self) -> str:
        return f"APK({self.package_name})"

    def details(self) -> dict:
        """
        return details of the apk
        """
        return {
            "apk_path": self.apk_path,
            "package_name": self.package_name,
            "home_activity": self.home_activity,
            "activities": self.activities,
            "exported_activities": self.exported_activities,
            "app_name": self.app_name,
        }
