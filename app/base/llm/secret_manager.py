"""
Hide & fill secrets during LLM interaction
"""
from typing import Final, List, Optional

from app.base.base.config import config

DUMMY_EMAIL: Final[str] = "user@example.com"


class Secret:
    def __init__(
        self,
        name: str,
        value: str,
        prompt: str,
        private_to_llm: bool = True,
        keyword: Optional[str] = None,
    ):
        self.name = name
        self.value = value
        self.keyword = f"${name.upper()}$" if keyword is None else keyword
        self.prompt = prompt.format(keyword=self.keyword, email=DUMMY_EMAIL)
        self.private_to_llm = private_to_llm


secrets: List[Secret] = [
    Secret(
        "username",
        config.testing.username,
        "If you need to login, use {keyword} as username in your text EXTRA. Use `{email}` instead of this if email is required.",
        True,
    ),
    Secret(
        "password",
        config.testing.password,
        "If you need to login, use {keyword} as password in your text EXTRA.",
        True,
    ),
    Secret(
        "email",
        config.testing.email,
        "If you need to login or fill in your email, use {keyword} as email in your text EXTRA.",
        True,
        keyword=DUMMY_EMAIL,
    ),
]


def get_prompts_for_secrets() -> List[str]:
    return [secret.prompt for secret in secrets]


def fill_secrets(s: str) -> str:
    for secret in secrets:
        s = s.replace(secret.keyword, secret.value)
    return s


def hide_secrets(s: str) -> str:
    for secret in sorted(secrets, key=lambda x: len(x.value), reverse=True):
        # replace the longest first to avoid replacing substrings
        if secret.private_to_llm:
            s = s.replace(secret.value, secret.keyword)
    return s


def unittest():
    secret_content = "\n".join([secret.value for secret in secrets])
    hide_secret_content = hide_secrets(secret_content)
    recover_secret_content = fill_secrets(hide_secret_content)
    print(secret_content, end="\n\n")
    print(hide_secret_content, end="\n\n")
    print(recover_secret_content, end="\n\n")
    assert secret_content == recover_secret_content
    for secret in secrets:
        assert secret.keyword not in hide_secret_content
        assert secret.keyword in recover_secret_content
    exit(0)
