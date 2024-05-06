"""
Where everything starts.
"""
import os
from queue import Empty, Queue
import subprocess
import sys
from threading import Lock
import time
from app.base.base.config import config
from app.base.device.device_util import ALL_DEVICE, Device, device_manager, all_jobs
from app.base.input_output.test_input_data import Task, TestInputData
from app.base.input_output.test_result import (
    PackageTestResult,
)
import typer
from pathlib import Path
from app.base.base.event_handler import ee, Events, send_notification
from rich import traceback
from typing import Dict, Literal, Optional, List, Set, Union
from typing_extensions import Annotated
from app.base.base.logger import (
    write_github_summary,
    write_profiler_result,
    get_profiler,
    init as logger_init,
)
from os import _exit

app = typer.Typer(no_args_is_help=True)
logger_init()


def do_failfast(return_code: int = 3):
    _exit(return_code)


def parallel_run(
    devices: List[Device],
    same_device_for_one_app: bool = True,
    device: Optional[Device] = None,
    force_use_this_device: bool = False,
    tasks: List[Task] = [],
    lock: Optional[Lock] = None,
):
    assert len(set(str(i.extra_kwargs) for i in tasks)) == 1  # all tasks must not be same
    from app.core.test_types.test_manager import TestManager

    ee.emit(
        Events.onNotification,
        "info|single_job_test_init",
        "Initializing parallel_run...\nAvailable devices: %s"
        % device_manager.all_devices,
    )

    def run_on_device(device: Device, result_queue: Queue, targets_inside: List[Task]):
        def core():
            detail_written: bool = False
            package_test_result: Optional[PackageTestResult] = None

            def write_github_summary_by_package_test_result(
                package_test_result: PackageTestResult,
            ):
                github_summary_content = package_test_result.markdown_table + "\n"
                write_github_summary(content=github_summary_content)

            @ee.on(Events.KeyboardInterrupt)
            def on_keyboard_interrupt():
                nonlocal detail_written, package_test_result
                if package_test_result is not None and (not detail_written):
                    package_test_result.end()
                    write_github_summary_by_package_test_result(
                        package_test_result=package_test_result
                    )
                raise KeyboardInterrupt

            def core_core():
                nonlocal detail_written, package_test_result
                kwargs = tasks[0].extra_kwargs.copy()
                chactivity = TestManager.get(tasks[0].task_type)().global_init_by_task(
                    device=device, task=tasks[0]
                )

                ee.emit(
                    Events.onNotification,
                    "success|single_job_test_init",
                    "Connected. Ready to test.",
                )
                package_test_result = PackageTestResult(package=chactivity.aut_package_name)
                chactivity.do_test_for_all_targets(targets_inside, package_test_result=package_test_result)
                ee.emit(
                    Events.onNotification,
                    "success|single_job_test_result",
                    f"All tests finished. | Successful {package_test_result.successful_out_of_all} | Time elapsed: {package_test_result.total_time:.0f}",
                )
                write_github_summary_by_package_test_result(
                    package_test_result=package_test_result
                )
                detail_written = True
                result_queue.put(package_test_result)

            try:
                profiler = get_profiler()
                with profiler:
                    core_core()
                write_profiler_result(profiler=profiler, prefix="full-")
            finally:
                ee.emit(Events.onPackageTestFinished)

        if lock:
            with lock:
                core()
        else:
            core()

    if same_device_for_one_app:
        targets = [
            tasks,
        ]
    else:
        targets = [
            [
                target,
            ]
            for target in tasks
        ]
    if force_use_this_device:
        assert device
        devices = [device]
    for outside_targets in targets:
        device_manager.dispatch_job(
            devices=devices,
            func=run_on_device,
            dispatch_job_force_using_this_device=force_use_this_device,
            kwargs={"targets_inside": outside_targets},
        )


def _wait_for_jobs(check_interval: float = 1.0) -> None:
    """
    Wait for device_manager idle, check every check_interval seconds
    :param check_interval: The interval (in seconds) between each check
    """
    while not device_manager.finished:
        device_manager.try_dispatch_unstarted()
        time.sleep(check_interval)


def _post_run_json_wait_and_exit(no_exit: bool = False) -> None:
    """
    Wait for all job done, then exit with code 2 if no successful test, otherwise return None
    """
    try:
        _wait_for_jobs()
        successful_count = 0
        for job in all_jobs:
            try:
                job_result: PackageTestResult = device_manager.get_job_result(
                    job=job, block=False
                )
            except Empty:
                ee.emit(
                    Events.onNotification,
                    "error|json_job_finish_with_error",
                    "Job %s is finished with an error :(" % job,
                )
            else:
                successful_count += job_result.successful_count
        if successful_count == 0:
            if not config.app.exit_on_all_failed:
                send_notification(
                    "warning|exit",
                    "No successful test, but no exit because config disabled it.",
                )
            elif no_exit:
                send_notification(
                    "warning|exit",
                    "No successful test, but no exit because no_exit=True",
                )
            else:
                send_notification(
                    "warning|exit", "No successful test, exit with code 2"
                )
                exit(2)
    except KeyboardInterrupt:
        ee.emit(Events.KeyboardInterrupt)
        raise


device_selected: Dict[str, Device] = {}


def _run_json_dispatch_test(
    test_input_file: Union[str, Path],
    devices: List[str],
    same_device_for_one_app: bool,
    same_device_for_all_apps: bool,
    same_device_lock: Lock,
) -> None:
    """
    Get the test input data from the json file and dispatch the test using parallel_run
    """
    test_input = TestInputData(test_input_file)
    # As they are non-blocking, we can run them in parallel
    device_objects: List[Device] = device_manager.query_devices(
        devices, test_input.device_types
    )
    if same_device_for_all_apps:
        device_same_unique_key = str((devices, test_input.device_types))
        picked_device = device_selected.setdefault(
            device_same_unique_key, device_manager.get_and_lock_device(device_objects)
        )
        parallel_run(
            devices=[
                picked_device,
            ],
            device=picked_device,
            lock=same_device_lock,
            force_use_this_device=True,
            tasks=test_input.tasks,
            same_device_for_one_app=same_device_for_one_app,
        )
    else:
        parallel_run(
            devices=device_objects,
            tasks=test_input.tasks,
            same_device_for_one_app=same_device_for_one_app,
        )


@app.command()
def run_json(
    files: Annotated[List[Path], typer.Option("--files", "-f")],
    devices: Annotated[List[str], typer.Option("--device", "-s")] = ALL_DEVICE,
    same_device_for_one_app: Annotated[
        bool,
        typer.Option(
            "--same-device/--no-same-device",
            help="Run all activities in one app on the same device",
        ),
    ] = True,
    same_device_for_all_apps: Annotated[
        bool,
        typer.Option(
            "--same-device-all/--no-same-device-all",
            help="Run all tests on the same device",
        ),
    ] = False,
    failfast: Annotated[
        bool,
        typer.Option(
            "--failfast/--no-failfast",
            help="Stop the test run on the first unknown error in a Job.",
        ),
    ] = False,
    rounds: Annotated[
        int,
        typer.Option(
            "--rounds",
            help="Run the test for multiple times",
        ),
    ] = 1,
):
    """
    run automatic Android UI testing against activity(s) in json file(s)
    """
    if failfast:
        ee.on(Events.failFast)(do_failfast)
    if same_device_for_all_apps and not same_device_for_one_app:
        raise ValueError(
            "same_device_for_one_app must be true when same_device_for_all_apps is true"
        )
    for _ in range(rounds):
        same_device_lock = Lock()
        package_test_finished_count: int = 0

        if same_device_for_all_apps:

            @ee.on(Events.onPackageTestFinished)
            def on_package_test_finished():
                # release device when everything on this device is finished
                nonlocal package_test_finished_count
                package_test_finished_count += 1
                if package_test_finished_count == len(files):
                    device_manager.mark_device_available()

        for file in files:
            _run_json_dispatch_test(
                test_input_file=file,
                devices=devices,
                same_device_for_one_app=same_device_for_one_app,
                same_device_for_all_apps=same_device_for_all_apps,
                same_device_lock=same_device_lock,
            )
        _post_run_json_wait_and_exit(no_exit=False)

        if same_device_for_all_apps:
            ee.remove_listener(
                Events.onPackageTestFinished,
                on_package_test_finished,  # pyright: ignore[reportUnboundVariable]
            )
    _post_run_json_wait_and_exit(
        no_exit=False
    )  # This line is useless if the above no_exit == False


@app.command()
def tool(
    tool_name: str,
    args: Annotated[Optional[List[str]], typer.Argument()] = None,
):
    """
    Run a tool in tools/ folder.
    e.g. python cli.py tool -- do_monkeys -h
    """
    base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools")
    tools = [
        file.removesuffix(".py")
        for file in os.listdir(base_path)
        if file.endswith(".py")
    ]
    if tool_name not in tools:
        print(f'Tool "{tool_name}" not found.\nValid tools: {tools}')
        raise ValueError(f'Tool "{tool_name}" not found.')
    if args is None:
        args = []
    proc = subprocess.run(
        [sys.executable, os.path.join(base_path, tool_name) + ".py", *args]
    )
    exit(proc.returncode)


@app.callback()
def callback():
    """
    Run Chatty for mobile app UI testing.
    """


if __name__ == "__main__":
    traceback.install()
    app()
