chcp 65001
poetry run python cli.py run-json -s all -f unittest\ci_schoolplanner.json --same-device --same-device-all --failfast --rounds 2
REM poetry run python cli.py run-json -s all -f unittest\ci.json
REM poetry run python cli.py run-json -f unittest\ci1.json --same-device --same-device-all

set /A err=%ERRORLEVEL%
poetry run python tools/summary2zulip.py
set /A err=%ERRORLEVEL%+%err%
exit /B %err%
