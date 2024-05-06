import sys
import os

parentdir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, parentdir)
from app.base.base.event_handler import Events, ee
from app.base.llm.llm import chat_class
from app.base.base.enrich import print


@ee.on(Events.onNotification)
def log(level, content):
    print(f"[{level}] {content}")


llm = chat_class()
llm.system("You are a bot.")
llm.user("hello " * 4096)
print(llm.ask())
print(llm.token_count)
