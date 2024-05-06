"""
Logger module for logging and printing
"""
import os
from threading import current_thread
import time
from typing import TYPE_CHECKING, Dict, Final, Literal
from datetime import datetime

from rich.panel import Panel
from rich.markdown import Markdown

from app.base.base.config import config
from app.base.base.const import WRITE_GITHUB_SUMMARY_LOCK
from app.base.base.event_handler import Events, ee, send_notification
from app.base.llm.custom_typing import ChatCompletionRole
from app.base.base.util import ensure_file, get_readable_time
from app.base.base.enrich import print


main_thread_name: Final[str] = current_thread().name
github_summary_file: Final[str] = os.getenv(
    "GITHUB_STEP_SUMMARY",
    get_readable_time(f)
    if (f := config.app.log.github_step_summary_fallback_file)
    else "",
)  # env -> config -> disable
known_thread_mapping: Dict[str, str] = {}


def add_thread_info(content_arg: int = 1, content_kwarg: str = "content"):
    def decorator(func):
        def wrapper(*args, **kwargs):
            current_thread_name = current_thread().name
            if main_thread_name != current_thread_name:
                if current_thread_name not in known_thread_mapping:
                    known_thread_mapping[
                        current_thread_name
                    ] = f"Thread {len(known_thread_mapping) + 1}"
                    send_notification(
                        "info|thread_mapping",
                        f"Thread rename: [bold red]{current_thread_name}[/bold red] -> [bold red]{known_thread_mapping[current_thread_name]}[/bold red]",
                    )
                thread_prefix = f"[bold red]{known_thread_mapping[current_thread_name]}[/bold red]:\n"
                # thread_prefix = "Thread [bold red]%s[/bold red]:\n" % current_thread_name
                args = list(args)
                if len(args) > content_arg:
                    args[content_arg] = thread_prefix + str(args[content_arg])
                elif content_kwarg in kwargs:
                    kwargs[content_kwarg] = thread_prefix + str(kwargs[content_kwarg])
                else:
                    print(
                        "Warning: no content_arg or content_kwarg found when adding thread info"
                    )
            return func(*args, **kwargs)

        return wrapper

    return decorator


def print_omit_message(message_type: str):
    if config.app.log.print_omit_message:
        print_with_log_to_file(f"Omitted {message_type}.")


@add_thread_info()
def print_chat_message(role: ChatCompletionRole, content: str):
    color = {
        "system": "magenta3",
        "user": "royal_blue1",
        "assistant": "yellow3",
    }
    if (
        role in ["user", "system"] and not config.app.log.include_every_llm_context
    ) or (role == "assistant" and not config.app.log.include_every_llm_response):
        print_omit_message(role)
    else:
        print(
            Panel(
                Markdown(content),
                title=role,
                border_style=color.get(role, "purple"),
            )
        )


if config.app.log.log_file:
    logfile = open(
        ensure_file(get_readable_time(config.app.log.log_file)),
        "w",
        encoding="utf8",
    )
else:
    logfile = None


def print_with_log_to_file(content: str):
    print(content)
    if logfile:
        print(content, file=logfile, flush=True)


@add_thread_info()
def handle_notification(
    level: str,
    content: str,
    *,
    extra_rich_printable_stuff: list = [],
    no_content: bool = False,
):
    log_level, *flags = level.split("|")
    color = {
        "info": "blue",
        "error": "red",
        "warning": "dark_orange3",
        "success": "green",
    }

    for omit_flag in config.app.log.omit_flags:
        if omit_flag in flags:
            print_omit_message(omit_flag)
            return

    args = []
    if not no_content:
        args.append(
            Panel(
                content,
                title="Notification",
                subtitle=log_level,
                border_style=color.get(log_level.lower(), "blue"),
            )
        )
    args.extend(extra_rich_printable_stuff)
    print_with_log_to_file(*args)


def write_github_summary(content: str):
    """
    Write sth to GitHub Actions summary file (or console when summary file not available)
    """
    with WRITE_GITHUB_SUMMARY_LOCK:
        if github_summary_file:
            with open(ensure_file(github_summary_file), "a", encoding="utf8") as f:
                f.write(content)
        else:
            ee.emit(Events.onNotification, "info|github_summary", content)


def _fake_write_profiler_result(*args, **kwargs):
    pass


def _fake_get_profiler():
    class dummy_profiler:
        def __enter__(self):
            pass

        def __exit__(self, *args):
            pass

    return dummy_profiler()


write_profiler_result, get_profiler = _fake_write_profiler_result, _fake_get_profiler


if config.app.enable_profiler or TYPE_CHECKING:
    from pyinstrument import Profiler

    def _real_write_profiler_result(
        profiler: Profiler,
        unicode: bool = True,
        color: bool = False,
        to_console: bool = False,
        to_file: bool = True,
        format: Literal["txt", "html"] = "txt",
        prefix: str = "",
    ):
        """
        Dump profiler result to console and/or file
        """
        if format == "txt":
            content = profiler.output_text(unicode=unicode, color=color)
        elif format == "html":
            content = profiler.output_html()
        else:
            raise ValueError("format must be txt or html")
        if to_console:
            print()
            print("=========  BEGIN PROFILER RESULT  =========")
            print(content)
            print("=========   END PROFILER RESULT   =========")
            print()
        if to_file:
            filename = os.path.join(
                config.app.profiler_target_folder,
                f"{prefix}{get_readable_time(format='%Y-%m-%d_%H.%M.%S')}.{format}",
            )
            with open(
                ensure_file(filename),
                "w",
                encoding="utf8",
            ) as f:
                f.write(content)

    def _real_get_profiler():
        return Profiler(async_mode="disabled")

    write_profiler_result, get_profiler = (
        _real_write_profiler_result,
        _real_get_profiler,
    )


def init():
    ee.on(Events.onChatMessage)(print_chat_message)
    ee.on(Events.onNotification)(handle_notification)
