import json
import sys
import os
from pprint import pprint
import time
from typing import List
import libchecker

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)
from app.base.file_analyzer.apk_util import APK

filenames = sys.argv[1:]
if not filenames:
    print("Usage: python tools/analyze_apk.py <apk_path> <apk_path> ...")
    exit(1)

ENCODING = "utf-8"
response_package = ""
response_activity = ""
for input_name in filenames:
    if os.path.isdir(input_name):
        files = [
            os.path.join(input_name, f)
            for f in os.listdir(input_name)
            if f.endswith(".apk")
        ]
    else:
        files = [input_name]
    for file in files:
        print()
        print("Analyzing %s" % file)
        apk = APK(file)
        details = apk.details()
        details.update({"version": apk.manifest_dict["@android:versionName"]})

        # Package info from apk using pylibchecker

        # apk_libs = apk.library_filenames
        # apk_lib_checkers = libchecker.query_many(apk_libs, libchecker.RuleType.NATIVE)
        # labels = list(set([lib.label for lib in apk_lib_checkers]))
        # details.update({"lib_labels": labels})
        # responses = libchecker.query_many(
        #     apk.dex_classes_for_libchecker, libchecker.RuleType.DEX
        # )
        # details.update({"class_labels": list(set([lib.label for lib in responses]))})

        # Jetpack Compose detection

        # JETPACK_COMPOSE_FILES = (
        #     "META-INF/androidx.compose.runtime_runtime.version",
        #     "META-INF/androidx.compose.ui_ui.version",
        #     "META-INF/androidx.compose.ui_ui-tooling-preview.version",
        #     "META-INF/androidx.compose.foundation_foundation.version",
        #     "META-INF/androidx.compose.animation_animation.version",
        # )
        # for jetpack_file in apk.zipfile.namelist():
        #     if jetpack_file in JETPACK_COMPOSE_FILES:
        #         details.update({"jetpack_compose": True})
        #         print("Jetpack Compose")
        #         print(apk.package_name)
        #         break

        # filename	display_name	package_name	version_str	ui_framework
        # response_package = (
        #     response_package
        #     + os.path.basename(file)
        #     + "\t"
        #     + details["app_name"]
        #     + "\t"
        #     + details["package_name"]
        #     + "\t"
        #     + details["version"]
        #     + "\t"
        #     + str(details["lib_labels"] + details["class_labels"])
        #     + "\n"
        # )

        # package	activity
        # for activity in details["activities"]:
        #     response_activity = (
        #         response_activity + details["package_name"] + "\t" + activity + "\n"
        #     )

        # Output
        # pprint(details)
        # with open(file + ".json", "w", encoding=ENCODING) as f:
        #     json.dump(details, f, indent=4, ensure_ascii=False)
        # with open(file + ".xml", "w", encoding=ENCODING) as f:
        #     f.write(str(apk.orig_manifest))

if response_package:
    with open(f"apk_info_{time.time()}.txt", "w", encoding=ENCODING) as f:
        f.write(response_package)
if response_activity:
    with open(f"apk_activity_{time.time()}.txt", "w", encoding=ENCODING) as f:
        f.write(response_activity)
