"""
LLM interaction wrapper
"""
import json
from app.base.base.event_handler import Events, ee, send_notification
from app.base.base.config import config
from app.base.base.enrich import debug_print, debug_print_no
from app.base.llm.secret_manager import hide_secrets
from abc import ABC, abstractmethod
from typing import (
    Any,
    Callable,
    ClassVar,
    List,
    Dict,
    Literal,
    Optional,
    Self,
    Set,
    Tuple,
    Type,
    TypeAlias,
    TypedDict,
    Union,
    final,
)
import openai
from openai.types.chat.chat_completion_message import (
    FunctionCall,
)
from openai.types.chat import (
    ChatCompletionMessageParam as SingleContextType,
    ChatCompletionMessageToolCall,
)
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_role import ChatCompletionRole
from tenacity import RetryCallState, Retrying, stop_after_attempt, wait_random
from cachier import cachier

client = openai.OpenAI(
    api_key=config.llm.openai.api_key,
    base_url=config.llm.openai.api_base,
)


class ParsedFuncitonCall(TypedDict):
    name: str
    arguments: dict[str, Any]


def clean_paragraph(p: str) -> str:
    """
    Make every line in a paragraph striped and non-empty
    """
    return "\n".join(
        [i.strip() for i in p.replace("\r\n", "\n").split("\n") if i.strip() != ""]
    )


def parse_function_call(
    function_call: ChatCompletionMessageToolCall,
) -> ParsedFuncitonCall:
    name = function_call.function.name
    arguments = json.loads(function_call.function.arguments)
    function_call_parsed: ParsedFuncitonCall = {
        "name": name,
        "arguments": arguments,
    }
    return function_call_parsed


def function_call_to_string(function_call: ChatCompletionMessageToolCall) -> str:
    function_call_parsed = parse_function_call(function_call)
    return json.dumps(function_call_parsed, indent=4, ensure_ascii=False)


def function_calls_to_string(
    function_calls: List[ChatCompletionMessageToolCall],
) -> str:
    function_calls_parsed = [parse_function_call(i) for i in function_calls]
    return json.dumps(function_calls_parsed, indent=4, ensure_ascii=False)


def string_to_function_call(string: str) -> ParsedFuncitonCall:
    return json.loads(string)


def string_to_function_calls(string: str) -> List[ParsedFuncitonCall]:
    return json.loads(string)


def cache_hash_context(args, kwargs) -> str:
    """
    Hash the context for caching
    """
    return str(args) + str(kwargs)


@cachier(
    hash_func=cache_hash_context,
)
def cache(context: List[SingleContextType]) -> Union[str, Literal[False]]:
    """
    Cache valid LLM response, return False if invalid.
    All entries must be manually added by `cache.precache_value(context, value_to_cache=answer)`
    """
    return False


class Chat(ABC):
    """
    A LLM chat session
    """

    CONNECT_ERROR: ClassVar[Set[Type[Exception]]]
    last_answer: str
    last_chat: Any
    last_is_function_call: bool

    def __init__(self):
        self.prompts: List[SingleContextType] = []
        self._temperature: float = config.llm.temperature
        self._model: str = config.llm.model
        self.error_count: int = 0
        self.token_count: int = 0
        self.ask_extra_kwargs: Dict[str, Any] = {}

    @final
    def message(self, role: ChatCompletionRole, msg: Union[str, list]) -> Self:
        """
        Add a message to the chat session
        :param role: the role of the message (defined in ChatCompletionRole)
        :param msg: the message content
        """
        self.prompts.append({"role": role, "content": msg})  # type: ignore
        ee.emit(Events.onChatMessage, role, msg)
        return self

    @final
    def system(self, msg: str) -> Self:
        """
        Add a system message to the chat session
        """
        return self.message("system", msg)

    @final
    def user(self, msg: str) -> Self:
        """
        Add a user message to the chat session
        """
        return self.message("user", msg)

    @final
    def assistant(self, msg: str) -> Self:
        """
        Add an assistant message to the chat session
        """
        return self.message("assistant", msg)

    @final
    def temperature(self, temperature: float) -> Self:
        """
        Set the temperature of the chat session
        :param temperature: the temperature
        """
        self._temperature = temperature
        return self

    @final
    def model(self, model: str) -> Self:
        """
        Set the model of the chat session
        :param model: the model codename
        """
        self._model = model
        return self

    @abstractmethod
    def ask(
        self,
        save_to_context: bool = False,
        no_clean: bool = False,
        use_cache: bool = config.llm.enable_cache,
    ) -> str:
        """
        Get the completion current session
        :param save_to_context: whether to save the completion to the context
        """
        raise NotImplementedError

    @final
    def clean(self) -> Self:
        """
        Use clean_paragraph to clean every paragraph in the chat session
        And: remove secrets
        """

        def make_clear_text(text: Optional[str]) -> str:
            assert isinstance(text, str)
            return hide_secrets(clean_paragraph(text))

        for message in self.prompts:
            if isinstance(message["content"], list):
                for message_inner in message["content"]:
                    if message_inner["type"] == "text":
                        message_inner["text"] = make_clear_text(message_inner["text"])
                continue
            message["content"] = make_clear_text(message["content"])
        return self

    @final
    def retry_with_reinforcement(
        self,
        success_function: Callable[[str], bool],
        error_prompt: str,
        max_try: int = 2,
        save_to_context: bool = False,
        ask_extra_kwargs: Dict[str, Any] = {},
    ) -> str:
        """
        If LLM didn't reply in the correct format in the first time, ask again with error_prompt.
        Might be used with `pop_error_count()` to get the error count.
        """
        assert max_try >= 1, ValueError("max_try should be at least 1")
        ret = ""
        remind_at_error_count = 1
        inserted_error_prompt = False
        for i in range(max_try):
            if i == remind_at_error_count:  # only remind LLM once
                self.user(error_prompt)
                inserted_error_prompt = True
            ret = self.ask(**ask_extra_kwargs)
            if success_function(ret):
                if inserted_error_prompt:  # remove the remind message
                    self.remove_last(1)
                if save_to_context:
                    self.assistant(ret)
                return ret
            self.error_count += 1
        if inserted_error_prompt:
            self.remove_last(1)
        self.assistant(ret)
        raise ValueError(f"LLM cannot give correct reply in {max_try} tries.")

    @final
    def add_to_cache(self):
        if len(self.prompts) == 0:
            return
        prompts = self.prompts
        if (
            prompts[-1]["role"] == "assistant"
            and prompts[-1]["content"] == self.last_answer
        ):
            prompts = prompts[:-1]
        if not cache(prompts):
            debug_print_no(
                f"new cache size {len(str(prompts))} -> {len(self.last_answer)}"
            )
        cache.precache_value(prompts, value_to_cache=self.last_answer)

    @final
    def pop_error_count(self) -> int:
        """
        Pop the error count and return it
        """
        ret = self.error_count
        self.error_count = 0
        return ret

    @final
    def add_token_count(self, token_count: int) -> Self:
        """
        Indicate addition of total token cost (input + output) of this chat session
        """
        self.token_count += token_count
        return self

    @final
    def pop_token_count(self) -> int:
        """
        Pop the token count and return it
        """
        ret = self.token_count
        self.token_count = 0
        return ret

    @final
    def remove_last(self, count: int = 1) -> Self:
        """
        Remove the last `count` message
        """
        self.prompts = self.prompts[:-count]
        return self

    @final
    def update_ask_kwarg(self, **kwargs) -> Self:
        """
        Update the ask kwargs
        """
        self.ask_extra_kwargs.update(kwargs)
        return self

    @final
    def reset_ask_kwarg(self) -> Self:
        """
        Reset the ask kwargs
        """
        self.ask_extra_kwargs = {}
        return self


ChatTypes: List[Type[Chat]] = list()


def register_chat_type(chat_type: Type[Chat]) -> Type[Chat]:
    """
    Register a chat type
    """
    ChatTypes.append(chat_type)
    return chat_type


@register_chat_type
class OpenAIChat(Chat):
    CONNECT_ERROR = {openai.APIConnectionError}
    _override_model: Optional[str] = None
    TOKEN_MODEL_UPDATE: Dict[str, str] = {}
    last_is_function_call: bool

    def ask(
        self, save_to_context=False, no_clean=False, use_cache=config.llm.enable_cache
    ) -> str:
        # wtf is this
        self._override_model = None
        if not no_clean:
            self.clean()
        cache_hit = False
        answer: Optional[str] = None
        if use_cache:
            cached = cache(self.prompts)
            if cached:
                cache_hit = True
                answer = cached
                debug_print_no("Cache hit!")
            else:
                debug_print_no(self.prompts)
                debug_print_no("Cache not found!")
                # traceback.print_stack()
        if not cache_hit:

            def if_large_token_update_to_16k(r: RetryCallState):
                if not r.outcome:
                    return
                error: BaseException = r.outcome.exception()
                if isinstance(error, openai.BadRequestError):
                    self._override_model = self.TOKEN_MODEL_UPDATE.get(
                        self._model, None
                    )
                    if self._override_model is not None:
                        send_notification(
                            "warn|token_model_update",
                            f'Token too long ("{error}"), update model to {self._override_model}',
                        )
                    else:
                        send_notification(
                            "warn|token_model_update",
                            f'Token too long ("{error}"), but no model update found for "{self._model}"',
                        )

            for attempt in Retrying(
                stop=stop_after_attempt(3),
                wait=wait_random(min=1, max=5),
                reraise=True,
                before_sleep=if_large_token_update_to_16k,
            ):
                with attempt:
                    model = self._override_model or self._model
                    chat: ChatCompletion = client.chat.completions.create(  # type: ignore
                        model=model,
                        messages=self.prompts,
                        temperature=self._temperature,
                        **self.ask_extra_kwargs,
                    )
                    self.last_chat = chat
                    self.last_is_function_call = False
                    if chat.choices[0].message.tool_calls:
                        self.last_is_function_call = True
                        tool_calls = chat.choices[0].message.tool_calls
                        answer = function_calls_to_string(tool_calls)
                        # if len(tool_calls) > 1:
                        #     send_notification(
                        #         "warning|llm_debug_multi_function_call", f"Multiple function call returned！\n{answer}"
                        #     )
                    else:
                        answer_from_content: Optional[str] = chat.choices[
                            0
                        ].message.content  # None for function call
                        answer = answer_from_content
                    tokens: int = chat.usage.total_tokens if chat.usage else 0
                    self.add_token_count(tokens)
                    if tokens > config.llm.warn_on_token_count:
                        ee.emit(
                            Events.onNotification,
                            "warn|token_count",
                            f"Token count is {tokens}, which is higher than the warn threshold {config.llm.warn_on_token_count}.",
                        )
                        ee.emit(
                            Events.onNotification,
                            "warn|token_count_detail",
                            str(
                                self.prompts
                                + [{"role": "assistant", "content": answer}]
                            ),
                        )
        assert answer is not None
        if save_to_context:
            self.assistant(answer)
        self.last_answer = answer
        return answer


def get_llm_connection_error_types() -> Tuple[Type[Exception], ...]:
    """
    Get all connect error types
    """
    errs: Set[Type[Exception]] = set()
    for i in ChatTypes:
        errs.update(i.CONNECT_ERROR)
    return tuple(errs)


def _get_chat_class() -> type[Chat]:
    """
    Get the chat session
    """
    return OpenAIChat


chat_class = _get_chat_class()
