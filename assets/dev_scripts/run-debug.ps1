# chcp 65001
$env:http_proxy="http://127.0.0.1:61326"
$env:https_proxy="http://127.0.0.1:61326"

git log -1 --pretty=format:"%s" > local-commit_message.txt
$c = "localtest"
$data = Get-Content -Path local-commit_message.txt -TotalCount 1

git add .
if ( $data -eq $c ){
    git commit --amend -m $c
 } else {
    git commit -m $c
 }
git push s -f

ssh -tt 127.0.0.1 "chcp 65001&set http_proxy=http://127.0.0.1:7890&set https_proxy=http://127.0.0.1:7890&set OPENAI_API_KEY=sk-puRK48ecziRvUi4EbHCQf1SHGgbpQYqQZhgFkQSR5i9gkEW15&set OPENAI_API_BASE=https://api.openai.com/v1&set PYTHONIOENCODING=utf-8&set PYTHONUTF8=1&set APK_DIR=E:\WSL\apks&pushd E:\actions-runner\Chat&git fetch --all&git reset --hard origin/master&unittest\ci.bat"
