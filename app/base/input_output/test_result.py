"""
Represent the result of a step, an activity or a package in testing
"""
from enum import Flag, auto
import os
import time
from typing import List, Dict, Optional, Self
from jinja2 import Template
from app.base.core.record import Record
from app.base.base.util import get_short_activity_name


class TestingResults(Flag):
    FINISHED = auto()
    UNFINISHED = auto()
    FAILED = auto()
    RETURN_FAILED = FAILED | FINISHED
    SUCCESSFUL = auto()
    RETURN_SUCCESSFUL = SUCCESSFUL | FINISHED
    BADGOAL = auto()
    RETURN_BADGOAL = BADGOAL | RETURN_FAILED
    ERROR = auto()  # an unexpected unrecoverable error occurred
    RETURN_ERROR = ERROR | RETURN_FAILED
    MAX_STEP_REACHED = auto()
    RETURN_MAX_STEP_REACHED = MAX_STEP_REACHED | RETURN_FAILED
    MAX_TIME_REACHED = auto()
    RETURN_MAX_TIME_REACHED = MAX_TIME_REACHED | RETURN_FAILED
    MAX_LLM_ERROR_REACHED = auto()
    RETURN_MAX_LLM_ERROR_REACHED = MAX_LLM_ERROR_REACHED | RETURN_FAILED
    LLM_REPLY_WRONG_RETRY = auto()
    RETURN_LLM_REPLY_WRONG_RETRY = LLM_REPLY_WRONG_RETRY | UNFINISHED
    SESSION_DIED = auto()
    RETURN_SESSION_DIED = SESSION_DIED | RETURN_FAILED
    STEP_NORMALLY_FINISHED = auto()
    RETURN_STEP_NORMALLY_FINISHED = STEP_NORMALLY_FINISHED | UNFINISHED
    NETWORK_ERROR = auto()
    RETURN_NETWORK_ERROR = NETWORK_ERROR | RETURN_FAILED


TESTING_RESULT_FAIL_REASON_BITS: List[TestingResults] = [
    bit ^ TestingResults.RETURN_FAILED
    for _, bit in TestingResults.__members__.items()
    if (TestingResults.RETURN_FAILED in bit) and (bit != TestingResults.RETURN_FAILED)
]

# load file test_record
with open(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_record.jinja2"),
    "r",
    encoding="utf8",
) as f:
    package_test_result_template = Template(f.read())


class ActivityTestResult:
    def __init__(
        self,
        activity_name: str,
        device_serial: str,
        package_name: str,
        package_version: Optional[str] = None,
    ) -> None:
        self.activity_name: str = activity_name
        self.device_serial: str = device_serial
        self.status: TestingResults = TestingResults.UNFINISHED
        self.package_name: str = package_name
        self.record: Record = Record(
            package_name=package_name, package_version=package_version
        )
        self.llm_reply_wrong_retry_count: int = 0
        self.start()

    def start(self) -> Self:
        self.record.start()
        self.status = TestingResults.UNFINISHED
        return self

    def end(self, status: TestingResults) -> Self:
        self.record.end()
        self.status = status | TestingResults.FINISHED
        return self

    @property
    def finished(self) -> bool:
        return bool(self.status & TestingResults.FINISHED)

    @property
    def successful(self) -> bool:
        return bool(self.status & TestingResults.SUCCESSFUL)

    @property
    def failed(self) -> bool:
        return bool(self.status & TestingResults.FAILED)

    @property
    def step_count(self) -> int:
        return len(self.record)

    def __len__(self) -> int:
        return self.step_count

    @property
    def total_time(self) -> float:
        return self.record.total_time

    @property
    def result_symbol(self) -> str:
        if self.finished:
            if self.successful and not self.failed:
                return "\N{White Heavy Check Mark}"
            elif self.failed and not self.successful:
                return "\N{Cross Mark}"
            else:
                return "\N{White Question Mark Ornament}(%s)" % self.status
        else:
            return "\N{Hourglass with Flowing Sand}"

    @property
    def fail_reasons(self) -> List[str]:
        error_texts: List[str] = [
            i.name for i in TESTING_RESULT_FAIL_REASON_BITS if self.status & i
        ]
        return error_texts

    def get_result_bool(self) -> bool:
        return self.successful and not self.failed


class PackageTestResult:
    def __init__(self, package: str):
        self.package_name: str = package
        self.activity_results: List[ActivityTestResult] = []
        self.start_time: float = 0.0
        self.start()

    def start(self) -> Self:
        self.start_time = time.time()
        return self

    def append(self, activity_result: ActivityTestResult) -> Self:
        assert activity_result.package_name == self.package_name
        self.activity_results.append(activity_result)
        return self

    def end(self) -> Self:
        self.end_time = time.time()
        return self

    @property
    def total_time(self) -> float:
        return self.end_time - self.start_time

    @property
    def total_steps(self) -> int:
        return sum(
            activity_result.step_count for activity_result in self.activity_results
        )

    @property
    def result_dict(self) -> dict:
        return {
            "total_time": self.total_time,
            "total_steps": self.total_steps,
            "activity_results": [
                {
                    "activity_name": activity_result.activity_name,
                    "device_serial": activity_result.device_serial,
                    "status": activity_result.status,
                    "record": activity_result.record.to_dict(),
                    "total_time": activity_result.total_time,
                    "step_count": activity_result.step_count,
                    "result_symbol": activity_result.result_symbol,
                }
                for activity_result in self.activity_results
            ],
        }

    @property
    def finished(self) -> bool:
        return all(
            activity_result.finished for activity_result in self.activity_results
        )

    @property
    def markdown_table(self) -> str:
        assert self.finished
        return (
            package_test_result_template.render(
                columns=[
                    {
                        "result": activity_result.result_symbol
                        + (
                            ("(%s)" % r"\|".join(activity_result.fail_reasons))
                            if activity_result.failed
                            else ""
                        ),
                        "package_name": activity_result.package_name,
                        "device": activity_result.device_serial,
                        "target": get_short_activity_name(
                            package_name=self.package_name,
                            activity_name=activity_result.activity_name,
                        ),
                        "time": f"{activity_result.total_time:.2f}",
                        "steps": activity_result.step_count,
                        "llm_error": activity_result.llm_reply_wrong_retry_count,
                    }
                    for activity_result in self.activity_results
                ]
            )
            + "\n"
        )

    @property
    def successful_count(self) -> int:
        return len(
            [
                1
                for activity_result in self.activity_results
                if activity_result.successful
            ]
        )

    @property
    def all_count(self) -> int:
        return len(self.activity_results)

    @property
    def successful_out_of_all(self) -> str:
        return f"{self.successful_count}/{self.all_count}"

    def __bool__(self) -> bool:
        raise RuntimeError(
            f"{repr(self.__class__)} should not be used as boolean value."
        )


def unittest():
    package = "com.test.package"
    activity = "com.test.package.MainActivity"
    activityTestResult = ActivityTestResult(
        device_serial="emulator-1234",
        activity_name=activity,
        package_name=package,
    )
    activityTestResult.start()
    activityTestResult.end(TestingResults.RETURN_BADGOAL)
    packageTestResult = PackageTestResult(package=package)
    packageTestResult.append(activityTestResult)
    packageTestResult.append(activityTestResult)
    packageTestResult.append(activityTestResult)
    packageTestResult.start()
    packageTestResult.end()
    print(repr(packageTestResult.markdown_table))
