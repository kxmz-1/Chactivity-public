# Chactivity

## Paper

See `Chactivity-paper-master` in this repo.

## Environment

- Windows 10+ / Linux
- Python 3.11
- Appium 2.0+
- Android Emulator / Real Device (9+ suggested)

## Usage

```bash
# First, manually install Python & Poetry & Python Packages
# See https://python-poetry.org/docs/#installation
# Then, install dependencies
poetry install
# Launch emulator / real device
nohup emulator @Android_9_AVD -no-qt -no-audio -no-window -no-snapstorage -gpu swiftshader_indirect >/dev/null &  # for linux
start /min emulator @Pixel_2_API_29 -no-audio -no-window -no-snapstorage -netspeed full -netdelay none  # for windows
# Connect to device using adb
adb devices
# Launch appium server (allow adb command execution)
appium --relaxed-security
# Run
poetry run python cli.py run-json -s emulator-5554,emulator-5556 --files unittest/ci.json
# See unittest/ for more information
```
