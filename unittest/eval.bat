chcp 65001
poetry run python cli.py run-json -s all -f unittest\gen_com.quizlet.quizletandroid_no_desc.json --same-device --same-device-all --failfast --rounds 3
poetry run python cli.py run-json -s all -f unittest\gen_com.spotify.music_no_desc.json --same-device --same-device-all --failfast --rounds 3