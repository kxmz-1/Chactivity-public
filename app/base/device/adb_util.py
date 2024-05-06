"""
Useful functions related to adb.
"""
from typing import List, Optional, Tuple
from adbutils import adb


INSTALL_SUCCESSFUL = 0
ALREADY_INSTALLED = 1
INSTALL_FAILED = 2
ADB_COMMAND_TIMEOUT: float = 10.0


def is_install(serial: str, package_name: str) -> bool:
    """
    Check if the specific package is installed on the specific device.
    """
    d = adb.device(serial=serial)
    return d.app_info(package_name) is not None


def try_install(serial: str, package_name: Optional[str], apk_file: str):
    """
    Install an apk file to the specific device if not installed.
    May raise Exception.
    :param serial: The serial of target device
    :param package_name: The package name of the target app, use None to skip the check of already installed
    :param apk_file: The path to the apk file
    :return: INSTALL_SUCCESSFUL if installed, ALREADY_INSTALLED if already installed, INSTALL_FAILED if failed
    """
    if package_name is None or not is_install(serial, package_name):
        d = adb.device(serial=serial)
        d.install(apk_file, silent=True)
        return INSTALL_SUCCESSFUL
    return ALREADY_INSTALLED


def get_all_serial() -> List[str]:
    """
    Get all serial of currently connected devices
    """
    return [x.serial for x in adb.device_list()]


def get_installed_packages(
    serial: str, timeout: Optional[float] = ADB_COMMAND_TIMEOUT
) -> List[str]:
    """
    Get all installed app's package name using adb shell.
    :param serial: The serial of target device
    :return: Package names of installed packages
    """
    res: str = adb.device(serial=serial).shell(
        cmdargs="pm list packages", timeout=timeout
    )  # type: ignore
    lines = res.strip().replace("\r\n", "\n").split("\n")
    packages = [line.removeprefix("package:") for line in lines if line]
    return packages


def get_device_size(
    serial: str, timeout: Optional[float] = ADB_COMMAND_TIMEOUT
) -> Tuple[int, int]:
    """
    Get device size using adb shell.
    :param serial: The serial of target device
    :return: device size in tuple
    """
    res: str = adb.device(serial=serial).shell(cmdargs="wm size", timeout=timeout).strip().split("\n")  # type: ignore
    size_str = res[-1].strip("\r\n Override size: Physical size: ")
    x, y = [int(i) for i in size_str.split("x")]
    return (x, y)
