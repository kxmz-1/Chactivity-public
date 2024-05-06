import json
import sys
import os

success_count = 0
skip_count = 0

"""
{
  "tasks": {
    "type": "act2act",
    "targets": [
      "daldev.android.gradehelper.SubjectActivity",
      "daldev.android.gradehelper.CommitActivity",
      "daldev.android.gradehelper.settings.TermSettingsActivity",
      "daldev.android.gradehelper.settings.PreferenceActivity",
      "daldev.android.gradehelper.timetable.TimetableActivity",
      "daldev.android.gradehelper.timetable.TimetableManagerActivity",
      "daldev.android.gradehelper.utilities.gradehelper.GradingSystemChooserActivity",
      "daldev.android.gradehelper.settings.ThemeChooserActivity",
      "daldev.android.gradehelper.activity.HolidayManagerActivity"
    ]
  },
  "apk": "*APK_DIR*/school_planner.apk",
  "package_name": "daldev.android.gradehelper",
  "known_activities": {},
  "device_type": "android",
  "capabilities_mixin": {
    "appWaitForLaunch": true
  }
}
"""


def migrate_content(content: dict) -> tuple[dict, bool]:
    """
    Take current content as input, modify it in-place, and return a tuple of (new_content, is_success).
    """
    is_success = False
    if "targets" in content:
        content["tasks"]["targets"] = content["targets"]
        content["tasks"]["type"] = "act2act"
        del content["targets"]
        is_success = True
    if len(content["tasks"]["targets"]) > 0 and isinstance(
        content["tasks"]["targets"][0], str
    ):
        for i, target in enumerate(content["tasks"]["targets"]):
            content["tasks"]["targets"][i] = {
                "description": None,
                "name": target,
            }
        is_success = True
    if any("description" in target for target in content["tasks"]["targets"]):
        content["known_activities"] = content.get("known_activities", {})
        for target in content["tasks"]["targets"]:
            if "description" not in target:
                continue
            description = target["description"]
            if description:
                content["known_activities"].setdefault(
                    target["activity_name"], {}
                ).update({"description": target["description"]})
            target.pop("description")
        is_success = True
    return content, is_success


files = []
for file in sys.argv[1:]:
    if os.path.isdir(file):
        files.extend(
            os.path.join(file, f) for f in os.listdir(file) if f.endswith(".json")
        )
    else:
        files.append(file)

for file in files:
    if not os.path.exists(file):
        print(file, "does not exist.")
        continue
    try:
        with open(file, "r", encoding="utf8") as f:
            original_content = json.load(f)
    except json.JSONDecodeError:
        print(file, "is not a valid json file.")
        continue
    content, is_success = migrate_content(original_content)
    if not is_success:
        skip_count += 1
        continue
    success_count += 1
    with open(file, "w", encoding="utf8") as f:
        json.dump(content, f, indent=4, ensure_ascii=False)

if success_count + skip_count == 0:
    print("Usage: python tools/migrate_test_input_to_latest.py <json_file_or_path> ...")
    exit(1)
print(f"Success count: {success_count}")
print(f"Skip count: {skip_count}")
