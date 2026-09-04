"""Turn chat conversations into padded batches of token ids for training."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Protocol, TypedDict

IGNORE_INDEX = -100


class ChatMessage(TypedDict):
    role: str
    content: str


class TokenizedBatch(TypedDict):
    """One training batch of token ids.

    Padding positions in ``labels`` are IGNORE_INDEX, so they do not
    affect the loss.
    """

    input_ids: list[list[int]]
    attention_mask: list[list[int]]
    labels: list[list[int]]


class ChatTokenizer(Protocol):
    """Tokenizer methods used to turn a chat into token ids.

    Hugging Face tokenizers satisfy this protocol.
    """

    pad_token_id: int | None

    def apply_chat_template(
        self,
        conversation: Sequence[ChatMessage],
        *,
        tokenize: bool = False,
        add_generation_prompt: bool = False,
    ) -> str: ...

    def encode(
        self,
        text: str,
        *,
        add_special_tokens: bool = True,
        truncation: bool = False,
        max_length: int | None = None,
    ) -> list[int]: ...


class DataLoader(Protocol):
    """Batches of token ids used to train a language model.

    ``len`` is the number of batches, not the number of conversations.
    """

    def __iter__(self) -> Iterator[TokenizedBatch]: ...

    def __len__(self) -> int: ...


def dummy_chat_examples() -> list[list[ChatMessage]]:
    """Return a few short chat conversations so you can train without real data."""
    return [
        [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What color is the sky?"},
            {"role": "assistant", "content": "The sky is blue."},
        ],
        [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is 2 + 2?"},
            {"role": "assistant", "content": "2 + 2 is 4."},
        ],
        [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Name one primary color."},
            {"role": "assistant", "content": "Red is a primary color."},
        ],
        [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Is water a liquid at room temperature?"},
            {"role": "assistant", "content": "Yes, water is a liquid at room temperature."},
        ],
    ]


class ChatDataLoader:
    """Padded batches of token ids from chat conversations.

    Tokenization happens once at construction. Padding positions in labels
    are IGNORE_INDEX, so they do not affect the training loss.
    """

    def __init__(
        self,
        tokenizer: ChatTokenizer,
        examples: Sequence[Sequence[ChatMessage]],
        *,
        batch_size: int = 2,
        max_length: int = 256,
    ) -> None:
        """
        Parameters
        ----------
        tokenizer : ChatTokenizer
            Must have ``pad_token_id`` set.
        max_length : int
            Truncate each conversation to this many tokens.

        Raises
        ------
        ValueError
            If ``batch_size`` is less than 1, ``pad_token_id`` is missing,
            ``examples`` is empty, or a conversation encodes to no tokens.
        """
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if tokenizer.pad_token_id is None:
            raise ValueError("tokenizer.pad_token_id must be set before loading data")
        if not examples:
            raise ValueError("examples must not be empty")

        self._batch_size = batch_size
        self._pad_token_id = tokenizer.pad_token_id
        self._rows = [
            _encode_chat(tokenizer, example, max_length=max_length) for example in examples
        ]

    def __len__(self) -> int:
        return (len(self._rows) + self._batch_size - 1) // self._batch_size

    def __iter__(self) -> Iterator[TokenizedBatch]:
        for start in range(0, len(self._rows), self._batch_size):
            yield _collate(
                self._rows[start : start + self._batch_size],
                pad_token_id=self._pad_token_id,
            )


def _encode_chat(
    tokenizer: ChatTokenizer,
    example: Sequence[ChatMessage],
    *,
    max_length: int,
) -> list[int]:
    text = tokenizer.apply_chat_template(
        list(example),
        tokenize=False,
        add_generation_prompt=False,
    )
    token_ids = tokenizer.encode(
        text,
        add_special_tokens=False,
        truncation=True,
        max_length=max_length,
    )
    if not token_ids:
        raise ValueError("tokenizer.encode returned an empty sequence")
    return token_ids


def _collate(rows: Sequence[list[int]], *, pad_token_id: int) -> TokenizedBatch:
    max_len = max(len(row) for row in rows)
    input_ids: list[list[int]] = []
    attention_mask: list[list[int]] = []
    labels: list[list[int]] = []
    for row in rows:
        pad = max_len - len(row)
        input_ids.append(row + [pad_token_id] * pad)
        attention_mask.append([1] * len(row) + [0] * pad)
        labels.append(row + [IGNORE_INDEX] * pad)
    return TokenizedBatch(
        input_ids=input_ids,
        attention_mask=attention_mask,
        labels=labels,
    )
