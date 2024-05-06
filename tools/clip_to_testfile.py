"""
Generate test files from Sheets Copy.
Each line should be in format:
package_name\tactivity_name\tdescription\thuman_notice
where \t is tab character.
If description or human_notice is not available, leave it blank.
"""
from os.path import join, dirname
import json
import pyperclip

unittest_dir = join(dirname(dirname(__file__)), "unittest")
base_json_file = join(unittest_dir, "empty.json")
with open(base_json_file, "r", encoding="utf8") as f:
    base_json = json.load(f)
targets = pyperclip.paste().split("\n")
package_targets = {}
for line in targets:
    # parsing line to {package: [targets]}
    line = line.strip()
    if not line:
        continue
    pkg, target = line.split("\t", 1)
    package_targets.setdefault(pkg, []).append(target)

for package, targets in package_targets.items():
    filename = "gen_" + package + ".json"
    filename_without_desc = "gen_" + package + "_no_desc.json"
    file_content = json.loads(json.dumps(base_json))
    file_content["package_name"] = package
    for target in targets:
        # activity, description, human_notice for each target
        target = target.strip()
        description, human_notice = "", ""
        if "\t" in target:
            target, description = target.split("\t", 1)
        if "\t" in description:
            description, human_notice = description.split("\t", 1)
            file_content["known_activities"].setdefault(target, {}).update(
                {"human_notice": human_notice}
            )
        file_content["tasks"]["targets"].append({"activity_name": target})
        file_content["known_activities"].setdefault(target, {}).update(
            {"description": description}
        )
    with open(join(unittest_dir, filename), "w", encoding="utf8") as f:
        json.dump(file_content, f, indent=4, ensure_ascii=False)
    # file without description
    for target in targets:
        target = target.strip()
        if "\t" in target:
            target, description = target.split("\t", 1)
        file_content["known_activities"].setdefault(target, {}).pop("description", None)
    with open(join(unittest_dir, filename_without_desc), "w", encoding="utf8") as f:
        json.dump(file_content, f, indent=4, ensure_ascii=False)
    print(f"{package}: {len(targets)} targets")
