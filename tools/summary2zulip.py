"""
Report results to Zulip after each GitHub Action run (CI).
"""

import os
import traceback
import requests

UNKNOWN = "unknown"


def get_balance():
    headers = {
        "Authorization": f'Bearer {os.environ.get("OHMYGPT_MANAGEMENT_KEY")}',
        "Content-Type": "application/json",
    }

    response = requests.post(
        "https://api.openai.com/api/v1/user/admin/balance", json={}, headers=headers
    )

    if response.status_code == 200:
        try:
            resp = response.json()
        except:
            return "[FAILED] Remote server error, not JSON response\n" + response.text
        if resp.get("statusCode") == 401:
            return "[FAILED] Invalid account token"
        elif resp.get("statusCode") != 200:
            return "[FAILED] Some error happened\n" + str(resp)
        else:
            balance = resp["data"]["balance"]
            free_balance = resp["data"]["free_balance"]
            cny = float(balance) / 34000
            return (
                f"Account {balance}(\N{Yen sign}{cny:.2f}) / Daily free {free_balance}"
            )
    else:
        return f"[FAILED] Remote server error, HTTP {response.status_code}"


# Get the file path from the environment variable
summary_file = os.environ.get("GITHUB_STEP_SUMMARY")

# Read the text content of the summary file
try:
    if summary_file is None:
        raise FileNotFoundError
    with open(summary_file, "r") as file:
        test_result_in_summary = file.read()
except FileNotFoundError:
    test_result_in_summary = (
        f"[FAILED] Summary file not found, environment variable is {repr(summary_file)}"
    )

# Zulip API endpoint
zulip_url = "https://example.zulipchat.com/api/v1/messages"

# Zulip bot credentials
bot_email = "test_result_bot-bot@example.zulipchat.com"
bot_api_key = os.environ.get("ZULIP_RESULT_BOT_KEY")

# ref: https://docs.github.com/en/actions/learn-github-actions/variables#default-environment-variables
github_ref = os.environ.get("GITHUB_REF") or UNKNOWN
github_sha = os.environ.get("GITHUB_SHA") or UNKNOWN
github_actor = os.environ.get("GITHUB_ACTOR") or UNKNOWN
github_commit_url = f"https://github.com/kxmz-1/Chactivity/commit/{github_sha}"
github_commit_anchor = (
    f"[{github_sha[:11]}]({github_commit_url})" if github_sha != UNKNOWN else UNKNOWN
)
github_server_url = os.environ.get("GITHUB_SERVER_URL") or UNKNOWN
github_repository = os.environ.get("GITHUB_REPOSITORY") or UNKNOWN
github_run_id = os.environ.get("GITHUB_RUN_ID") or UNKNOWN
github_run_url = (
    f"{github_server_url}/{github_repository}/actions/runs/{github_run_id}"
    if github_run_id != UNKNOWN
    else UNKNOWN
)
github_run_url_anchor = (
    f"[{github_run_id}]({github_run_url})" if github_run_id != UNKNOWN else UNKNOWN
)

try:
    balance_str = get_balance()
except Exception as e:
    balance_str = "[FAILED] Script error\n" + traceback.format_exc()

msg_prefix = f"""
**Test Result**
- by {github_actor}
- on {github_ref} ({github_commit_anchor}) (run: {github_run_url_anchor})
- OhMyGPT Balance: {balance_str}
---
""".strip()

# Zulip message parameters
message_data = {
    "type": "stream",
    "to": "test-result",
    "topic": "Test Result",
    "content": msg_prefix + "\n" + test_result_in_summary,
}

# Exit if API key is not set
if bot_api_key is None:
    print("Zulip API key is not set. No message sent.")
    exit(1)

# Send the message using the Zulip API
response = requests.post(zulip_url, auth=(bot_email, bot_api_key), data=message_data)

# Check the response status
if response.status_code == 200:
    print("Message sent successfully.")
else:
    print("Failed to send message:", response.text)
    print("Message content:")
    print(message_data)
    exit(2)
