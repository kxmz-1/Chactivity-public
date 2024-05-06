# Do monkey test for all apps in $APK_DIR
import json
import os
import sys
from typing import Dict, List, Union
import time
import subprocess
from adbutils import adb_path, adb

MONKEY_SEED = 1
MONKEY_EVENT_COUNT = 360000_00
MONKEY_THROTTLE = 1000
MONKEY_TIMEOUT = 3 * 60 * 60 + 30 * 60  # 3.5 hours
INIT_COMMANDS = [
    #    "adb -s {SERIAL} shell settings put global policy_control immersive.full=*" # useless for Android >= 11
    "adb -s {SERIAL} shell settings put global http_proxy 10.0.2.2:7890"
]
MONKEY_LOG_SUFFIX = ".monkey.log"
PARSED_LOG_SUFFIX = ".parsed.log"
BASE_PATH = "monkey_logs"

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)

from analyze_monkey_result import (
    get_activity_first_step,
    pre_process_monkey_log,
)
from app.base.device.adb_util import get_all_serial, try_install
from app.base.file_analyzer.apk_util import APK
from app.base.base.const import WHITELIST_APP_DURING_TESTING
from app.base.base.util import ensure_dir


try:
    serial = sys.argv[1]
except IndexError:
    serials = get_all_serial()
    if len(serials) == 1:
        serial = serials[0]
    else:
        print("Usage: python do_monkeys.py <serial of android device>")
        sys.exit(1)

apk_dir = os.environ.get("APK_DIR")
if apk_dir is None or not os.path.isdir(apk_dir):
    print(
        f"Environmental variable APK_DIR not correctly set. Current value: {repr(apk_dir)}"
    )
    sys.exit(2)
apk_files = [i for i in os.listdir(apk_dir) if i.endswith(".apk")]
ensure_dir(BASE_PATH)

if not apk_files:
    print(f"No apk file in APK_DIR {apk_dir}")
    sys.exit(3)


def adb_do_command(command: str) -> None:
    adb.device(serial=serial).shell(cmdargs=command, timeout=5)


for init_command in INIT_COMMANDS:
    adb_do_command(init_command)

for file in apk_files:
    apk_path = os.path.join(apk_dir, file)
    monkey_log_path = os.path.join(
        BASE_PATH,
        os.path.basename(apk_path) + "_" + str(int(time.time())) + MONKEY_LOG_SUFFIX,
    )
    parsed_log_path = (
        monkey_log_path.removesuffix(MONKEY_LOG_SUFFIX) + PARSED_LOG_SUFFIX
    )
    apk = APK(apk_path)
    all_activities = apk.activities
    home_activity = apk.home_activity
    package_name = apk.package_name
    try_install(serial, package_name, apk_path)
    adb_do_command(f"killall -9 com.android.commands.monkey")
    adb_do_command(f"am force-stop {package_name}")
    adb_do_command(f"am start -n {package_name}/{home_activity}")
    # check package name injection
    if any(i in package_name for i in "\"',;&: \t\r\n"):
        print(f"Package name {package_name} contains invalid characters.")
        sys.exit(4)
    adb_path_str: str = adb_path()  # type: ignore
    commands: List[Union[str, int]] = [
        adb_path_str,
        "-s",
        serial,
        "shell",
        "monkey",
        "-s",
        MONKEY_SEED,
        "-v",
        "-v",
        "-v",
        "-p",
        package_name,
        "--throttle",
        MONKEY_THROTTLE,
        "--ignore-crashes",
        "--ignore-timeouts",
        "--ignore-security-exceptions",
        "--ignore-native-crashes",
        MONKEY_EVENT_COUNT,
    ]
    for app in WHITELIST_APP_DURING_TESTING:
        commands.append("-p")
        commands.append(app)
    command_list: List[str] = [str(i) for i in commands]
    print(
        f"Monkey test for {package_name} began at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
    )
    print("Command:", " ".join(command_list))
    with open(monkey_log_path, "wb") as f:
        start_time = time.time()
        process = subprocess.Popen(command_list, shell=False, stdout=f, stderr=f)
        try:
            process.wait(timeout=MONKEY_TIMEOUT)
        except subprocess.TimeoutExpired:
            print(f"Monkey test for {package_name} timeout, killing process...")
            process.kill()
            process.wait(1)
        except KeyboardInterrupt:
            adb_do_command(f"killall -9 com.android.commands.monkey")
            raise
        adb_do_command(f"killall -9 com.android.commands.monkey")
        adb_do_command(f"killall -9 {package_name}")
        # stdout, stderr = process.communicate(timeout=MONKEY_TIMEOUT)
        return_code = process.returncode
        end_time = time.time()
        time_cost = end_time - start_time
        f.write(f"\n\n\nTime elapsed: {time_cost:.2f}\n".encode())
    monkey_content = pre_process_monkey_log(
        open(monkey_log_path, "r", encoding="utf8").read()
    )
    explored_activities = get_activity_first_step(monkey_content)
    with open(parsed_log_path, "w", encoding="utf8") as f:
        json.dump(
            {
                "package_name": package_name,
                "home_activity": home_activity,
                "explored_activities": explored_activities,
                "all_activities": all_activities,
                "unexplored_activities": [
                    i for i in all_activities if i not in explored_activities
                ],
                "monkey_log_path": monkey_log_path,
                "parsed_log_path": parsed_log_path,
                "time": time_cost,
                "return_code": return_code,
                "command": command_list,
            },
            f,
            indent=4,
            ensure_ascii=False,
        )
    print(
        f"Monkey test for {package_name} finished at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}"
    )
    time.sleep(10)
