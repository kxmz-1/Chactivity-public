"""
Manage available devices and dispatch jobs (test task) to them.
"""
from abc import ABC, abstractmethod
from functools import wraps
from queue import Queue
from threading import Lock, Thread
from app.base.base.enrich import print
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Self,
    Sequence,
    Set,
    Tuple,
    overload,
)
from adbutils import adb
from app.base.base.event_handler import ee, Events, send_notification
from rich import traceback
from app.base.base.enrich import debug_print, debug_print_no

ALL_DEVICE = ["all"]


class Device(ABC):
    serial: str
    appium_capabilities: dict
    device_types: List[str] = []

    @classmethod
    @abstractmethod
    def get_device_list(cls) -> List[Self]:
        raise NotImplementedError

    @classmethod
    @abstractmethod
    def get_device(cls, serial: str) -> Self:
        raise NotImplementedError

    def __init__(self, serial: str):
        self.serial = serial

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.serial})"


class AndroidDevice(Device):
    serial_to_device: Dict["str", "AndroidDevice"] = dict()
    appium_capabilities = {
        "platformName": "Android",
        "automationName": "uiautomator2",
        "deviceName": "Android",
    }
    device_types = ["android"]

    @classmethod
    def get_device(cls, serial: str) -> Self:
        if serial in cls.serial_to_device:
            return cls.serial_to_device[serial]
        else:
            device = cls(serial)
            cls.serial_to_device[serial] = device
            return device

    @classmethod
    def get_device_list(cls) -> List[Self]:
        return [cls.get_device(x.serial) for x in adb.device_list()]


true_lambda = lambda x: True


def make_job_args_part_str(args: tuple, kwargs: dict) -> str:
    res = f"({', '.join(list(args) + ['%s=%s' % (ii,jj) for (ii,jj) in kwargs.items()])})".replace(
        "[", "\\["
    ).replace(
        "]", "\\]"
    )
    return res


def make_job_function_str(func: Callable, args: tuple, kwargs: dict) -> str:
    # deep copy
    args = tuple(x for x in args)
    kwargs = {k: v for k, v in kwargs.items()}
    return f"{func.__name__}{make_job_args_part_str(args, kwargs)}"


class Job:
    @staticmethod
    def wrap_function_with_error_handling(func: Callable) -> Callable:
        @wraps(func)
        def wrapped(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                send_notification(
                    "error",
                    f"Unknown exception {e} in Job {make_job_function_str(func, args, kwargs)}!",
                )
                ee.emit(
                    Events.onNotification,
                    "info",
                    content="",
                    extra_rich_printable_stuff=[
                        traceback.Traceback(show_locals=True),
                    ],
                    no_content=True,
                )
                ee.emit(Events.failFast)
                raise e

        return wrapped

    def __init__(self, device: Device, func, *args, **kwargs):
        self.device: Device = device
        self.func = func
        self.args = args
        self.kwargs = kwargs
        self.function_str = make_job_function_str(self.func, self.args, self.kwargs)
        self.result_queue = Queue()
        self.results: List = []
        kwargs = self.kwargs.copy()
        kwargs.update({"device": self.device})
        kwargs.update({"result_queue": self.result_queue})
        self.repr = self.function_str
        self.thread = Thread(
            name=self.repr,
            target=self.wrap_function_with_error_handling(self.func),
            args=args,
            kwargs=kwargs,
        )
        self.thread.daemon = True
        self.thread.start()
        ee.emit(
            Events.onNotification,
            "info",
            "Job " + f"{self.function_str} " + f"started running on {self.device}",
        )
        all_jobs.append(self)

    @property
    def is_alive(self) -> bool:
        return self.thread.is_alive()

    @property
    def wait_for_return_value(self) -> Any:
        return self.result_queue.get()

    def __repr__(self) -> str:
        return self.repr


all_jobs: List[Job] = []


class PendingJob:
    devices: Optional[List[Device]]
    func: Callable
    args: list
    kwargs: dict
    dispatch_job_force_using_this_device: bool

    def __init__(
        self,
        devices: Optional[List[Device]],
        func: Callable,
        args: Optional[list] = None,
        kwargs: Optional[dict] = None,
        dispatch_job_force_using_this_device: bool = False,
    ):
        self.devices = devices
        self.func = func
        self.args = args if args is not None else []
        self.kwargs = kwargs if kwargs is not None else {}
        self.dispatch_job_force_using_this_device = dispatch_job_force_using_this_device

    def __repr__(self):
        return f"<{self.__class__.__name__} - {self.__dict__}>"


class DeviceManager:
    device_providers: List[Callable[[], Sequence[Device]]] = []
    pick_device_lock: Lock = Lock()

    def register_device_provider(
        self, device_provider: Callable[[], Sequence[Device]]
    ) -> Self:
        self.device_providers.append(device_provider)
        return self

    @property
    def all_devices(self) -> List[Device]:
        devices: List[Device] = []
        for provider in self.device_providers:
            devices.extend(provider())
        return devices

    def query_devices(
        self, serials: List[str], device_type: Optional[str] = None
    ) -> List[Device]:
        """
        Return all device with serial in serials, or all devices if serials is ALL_DEVICE
        Filter out only devices of device_type if device_type is not None
        """
        return [
            device
            for device in self.all_devices
            if device.serial in serials
            or serials == ALL_DEVICE
            and (device_type is None or device_type in device.device_types)
        ]

    running_jobs: List[Job] = []
    finished_jobs: List[Job] = []
    running_devices: Set[Device] = set()

    def _update_job_status(self) -> Self:
        for job in self.running_jobs:
            if not job.is_alive:
                self.running_jobs.remove(job)
                self.finished_jobs.append(job)
                self.mark_device_available(job.device)
        return self

    def mark_device_available(self, device: Optional[Device] = None) -> Self:
        if device is None:
            for device in list(
                self.running_devices
            ):  # make a copy of the set so that we can remove sth. from the original set
                self.mark_device_available(device)
            return self
        if device in self.running_devices:
            self.running_devices.remove(device)
            ee.emit(Events.onDeviceReAvailable, device)
        return self

    def mark_device_unavailable(self, device: Device) -> Self:
        if device not in self.running_devices:
            self.running_devices.add(device)
        return self

    dispatch_queue: List[PendingJob] = []

    def dispatch_job(
        self,
        devices: Optional[List[Device]],
        func: Callable,
        args: list = [],
        kwargs: dict = {},
        dispatch_job_force_using_this_device: bool = False,
    ) -> Optional[Job]:
        self.dispatch_queue.append(
            PendingJob(
                devices, func, args, kwargs, dispatch_job_force_using_this_device
            )
        )
        return self.try_dispatch_unstarted()

    def is_device_idle(self, device: Optional[Device]) -> bool:
        return device not in self.running_devices and device in self.all_devices

    def try_dispatch_unstarted(self) -> Optional[Job]:
        self._update_job_status()

        def do_dispatch_sth(device: Device, pending_job: PendingJob) -> Job:
            self.mark_device_unavailable(device)
            self.dispatch_queue.remove(pending_job)
            ee.emit(Events.onDeviceOccupied, device)
            job = Job(device, pending_job.func, *pending_job.args, **pending_job.kwargs)
            if not pending_job.dispatch_job_force_using_this_device:
                # don't add the ones' force using this device, so that the device won't be released in sub-jobs
                self.running_jobs.append(job)
            return job

        for pending_job in self.dispatch_queue:
            device = self.get_and_lock_device(
                pending_job.devices,
                dispatch_job_force_using_this_device=pending_job.dispatch_job_force_using_this_device,
            )
            return do_dispatch_sth(device, pending_job)
        return None

    @overload
    def get_and_lock_device(
        self,
        devices: Optional[List[Device]],
        dispatch_job_force_using_this_device: bool = False,
    ) -> Device:
        ...

    @overload
    def get_and_lock_device(
        self,
        devices: List[Device],
        dispatch_job_force_using_this_device: Literal[True] = True,
    ) -> Device:
        ...

    def get_and_lock_device(
        self,
        devices: Optional[List[Device]] = None,
        dispatch_job_force_using_this_device: bool = False,
    ) -> Device:
        """
        Lock a device and return it. May deadlock if no device is available currently.
        """
        if dispatch_job_force_using_this_device:
            assert devices
            return devices[0]
        # if len(self.running_devices) >= len(self.devices):
        #     return None
        with self.pick_device_lock:
            while True:
                if devices is None or devices == ALL_DEVICE:
                    devices = self.all_devices
                for device in devices:
                    if self.is_device_idle(device):
                        self.mark_device_unavailable(device)
                        return device

    def get_job_result(
        self, job: Job, block: bool = True, timeout: Optional[float] = None
    ):
        if job.results:
            return job.results[0]
        job_result = job.result_queue.get(block=block, timeout=timeout)
        job.results.append(job_result)
        return job_result

    @property
    def finished(self):
        self._update_job_status()
        debug_print_no(
            "DeviceManager check: ",
            len(self.dispatch_queue),
            len(self.running_jobs),
            len(self.running_devices),
        )
        return (
            len(self.dispatch_queue) == 0
            and len(self.running_jobs) == 0
            and len(self.running_devices) == 0
        )


device_manager = DeviceManager()
device_manager.register_device_provider(AndroidDevice.get_device_list)


@ee.on(Events.onDeviceReAvailable)
def on_device_re_available(device: Device):
    device_manager.try_dispatch_unstarted()


@ee.on(Events.KeyboardInterrupt)
def on_keyboard_interrupt():
    device_manager.dispatch_queue.clear()
