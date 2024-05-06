"""
Wrapper for Python module `rich`
"""
from functools import wraps
from threading import Lock
from rich.console import Console
from rich import (
    print as _rich_print,
    reconfigure as _rich_reconfigure,
    get_console as _rich_get_console,
)
from os import environ

if environ.get("FORCE_COLOR"):
    # workaround for rich bug, see https://github.com/Textualize/rich/issues/2622
    _rich_reconfigure(legacy_windows=False)

console = _rich_get_console()
orig_print = print
print = _rich_print
debug_print = print  # only an alias
debug_orig_print = orig_print
debug_print_no = (
    lambda *args, **kwargs: None
)  # an empty function to temporarily disable debug_print
debug_orig_print_no = debug_print_no
if False:
    print = orig_print
    debug_print = orig_print

THREADED_PRINT_LOCK = Lock()


def require_threaded_print(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        with THREADED_PRINT_LOCK:
            return func(*args, **kwargs)

    return wrapper


print = require_threaded_print(print)
debug_print = require_threaded_print(debug_print)
orig_print = require_threaded_print(orig_print)
debug_orig_print = require_threaded_print(debug_orig_print)
debug_print_no = require_threaded_print(debug_print_no)
