"""Structured chat completions via LangChain + OpenAI.

Run from the repo root:

    PYTHONPATH=. uv run python ml_tooling/llm/llm.py

Requires ``OPENAI_API_KEY`` in ``.env`` or the environment.
"""

from __future__ import annotations

from typing import TypeVar

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from lib.load_env_vars import EnvVarsContainer

DEFAULT_MODEL = "gpt-5.4-nano"
DEFAULT_TEMPERATURE = 0.0

T = TypeVar("T", bound=BaseModel)


def build_structured_chat_chain(
    *,
    output_schema: type[T],
    system_prompt: str,
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
) -> Runnable:
    """Build a LangChain runnable that returns Pydantic structured output."""
    EnvVarsContainer.get_env_var("OPENAI_API_KEY", required=True)
    template = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", "{user_prompt}"),
        ]
    )
    llm = ChatOpenAI(model=model, temperature=temperature)
    return template | llm.with_structured_output(output_schema)


def structured_chat_completion(
    *,
    user_prompt: str,
    output_schema: type[T],
    system_prompt: str = "You are a helpful assistant.",
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
) -> T:
    """Run a single structured chat completion and return the parsed schema."""
    chain = build_structured_chat_chain(
        output_schema=output_schema,
        system_prompt=system_prompt,
        model=model,
        temperature=temperature,
    )
    return chain.invoke({"user_prompt": user_prompt})


if __name__ == "__main__":

    class _SampleSentimentResult(BaseModel):
        sentiment: str
        confidence: float

    result = structured_chat_completion(
        user_prompt="I absolutely loved this movie!",
        output_schema=_SampleSentimentResult,
        system_prompt=(
            "Classify the sentiment of the user's text. "
            "Return sentiment as one of: positive, negative, neutral."
        ),
    )
    print(result.model_dump())
