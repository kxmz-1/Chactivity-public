"""
Manage config & read config from file
"""
from functools import partial
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Literal, Union, Optional
from tomllib import load as toml_load
import dacite
from mergedeep import merge


@dataclass
class AppiumConfig:
    capabilities: dict
    server: str = "http://localhost:4723"


@dataclass
class LLMConfig:
    temperature: float
    model: str
    warn_on_token_count: int = 6000
    enable_cache: bool = False

    @dataclass
    class OpenAIConfig:
        api_key: Optional[str] = os.environ.get("OPENAI_API_KEY")
        api_base: Optional[str] = os.environ.get("OPENAI_API_BASE")

    openai: OpenAIConfig = field(default_factory=OpenAIConfig)


@dataclass
class AppConfig:
    @dataclass
    class CoreConfig:
        context_history_length: int
        max_step: int = 30
        max_time: float = 300.0
        show_badgoal_prompt_at_least_after: int = 10
        abort_activity_test_on_llm_error_count: int = 3
        persist_knowledge_path: str = "~/persist_knowledge"
        wipe_persist_knowledge: bool = True
        wait_time_between_steps: float = 3
        analyze_before_function_call: bool = True
        find_a_good_start: bool = True
        enable_description_generation: bool = True
        filter_continuous_same_elements: bool = True
        filter_by_global_weight: bool = True
        filter_by_status_weight: bool = True

    core: CoreConfig

    @dataclass
    class LogConfig:
        include_every_llm_context: bool = False
        include_every_llm_response: bool = False
        print_omit_message: bool = (
            True  # set if `Omitted xxx to reduce noise` will be printed
        )
        omit_flags: List[str] = field(default_factory=list)
        # set a valid string to specify the log file location, set to false to disable logging to file
        # strftime placeholders supported.
        detail_step_log_file: Union[
            Literal[False], str
        ] = "results/detail_step_log/%Y-%m-%d %H.%M.%S.md"
        result_json_file: Union[
            Literal[False], str
        ] = "results/json/%Y-%m-%d %H.%M.%S.json"
        log_file: Union[Literal[False], str] = "results/logs/log_%Y-%m-%d_%H.%M.%S.txt"
        github_step_summary_fallback_file: Union[
            Literal[False], str
        ] = "results/summary/summary_%Y-%m-%d_%H.%M.%S.md"

    log: LogConfig
    enable_profiler: bool = False
    profiler_target_folder: str = "."
    exit_on_all_failed: bool = False


@dataclass
class TestingConfig:
    username: str
    password: str
    email: str
    phone_region: Optional[str]
    phone_number_without_region: Optional[str]
    home_address: Optional[str]
    region: Optional[str]


@dataclass
class _Config:
    appium: AppiumConfig
    llm: LLMConfig
    app: AppConfig
    testing: TestingConfig


config_data: dict = {}


def load_config(path: str, non_exist_ok: bool = False):
    global config_data
    path_instance = Path(path)
    if not path_instance.is_file():
        if non_exist_ok:
            return
        raise FileNotFoundError(f'Config file "{path}" not found')
    config_data_new = toml_load(open(path_instance, "rb"))
    merge(config_data, config_data_new)


load_config("./config.toml")
load_config("./config/override.toml", non_exist_ok=True)
load_config("./config.override.toml", non_exist_ok=True)

config: _Config = dacite.from_dict(data_class=_Config, data=config_data)
