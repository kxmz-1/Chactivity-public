pushd E:\WSL\Programs\Android_Sdk\emulator
set http_proxy=http://127.0.0.1:7890

REM BELOW: GOOGLE PLAY UNAVAILABLE
start /min emulator @Pixel_5_API_30 -no-audio -no-window -no-snapstorage -netspeed full -netdelay none
start /min emulator @Copy_2_of_Pixel_5_API_30 -no-audio -no-window -no-snapstorage -netspeed full -netdelay none

REM BELOW: GOOGLE PLAY AVAILABLE
start /min emulator @Pixel_2_API_33 -no-audio -no-window -no-snapstorage -netspeed full -netdelay none
start /min emulator @Pixel_2_API_29 -no-audio -no-window -no-snapstorage -netspeed full -netdelay none

start /min appium --relaxed-security
