# Take a monkey log as input, output event count to achieve to every occured activities.
import sys
from typing import Dict, List
import re

regex_for_activity_name = re.compile(r"cmp=([^/]+)/([^ ]+)")


def get_full_activity_name(package: str, activity: str) -> str:
    # don't remove this, as this is a standalone script
    if activity.startswith("."):
        return package + activity
    else:
        return activity


def get_activity_first_step(monkey_content: str) -> Dict[str, int]:
    activitiy_first_step: Dict[str, int] = {}
    event_count = 0
    for line in monkey_content.splitlines():
        if line.startswith(":"):
            event_count += 1
        #     // Allowing start of Intent { act=android.intent.action.MAIN cat=[android.intent.category.LAUNCHER] cmp=com.android.settings/.Settings } in package com.android.settings
        if line.strip().startswith("// Allowing start of Intent"):
            re_match = regex_for_activity_name.search(line)
            if re_match is None:
                print("Warning: cannot parse line:", line)
                continue
            package, activity = re_match.group(1), re_match.group(2)
            activity_name = get_full_activity_name(package, activity)
            if activity_name not in activitiy_first_step and event_count > 0:
                activitiy_first_step[activity_name] = event_count
    return activitiy_first_step


def pre_process_monkey_log(monkey_content: str) -> str:
    lines = monkey_content.splitlines()
    # filter until the first line begins with `:Switch:`
    for i, line in enumerate(lines):
        if line.startswith(":Switch:"):
            lines = lines[i + 1 :]
            break
    return "\n".join(lines)


def generate_result_for_file(monkey_log_file: str) -> str:
    ret = ""
    # read the lines
    content = pre_process_monkey_log(open(monkey_log_file, encoding="utf-8").read())
    # count the event count
    activity_first_step = get_activity_first_step(content)
    # print the result
    ret += f"- Step count for every new activity for {monkey_log_file}:"

    for activity_name, count in activity_first_step.items():
        ret += f"{activity_name}: {count}"
    if not activity_first_step:
        ret += "No activities found. Too few steps?"
    return ret


if __name__ == "__main__":
    monkey_log_files: List[str] = sys.argv[1:]

    if not monkey_log_files:
        print("ADB command: monkey -s 114514 -v -v -v 100 > log1.txt")
        print("Usage: python tools/analyze_monkey_log.py log1.txt log2.txt ...")
        exit(1)

    for monkey_log_file in monkey_log_files:
        print(generate_result_for_file(monkey_log_file), end="\n\n")
