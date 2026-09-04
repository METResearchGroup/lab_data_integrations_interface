"""LoRA fine-tuning for a Qwen language model.

LoRA is a method that trains a small set of extra weights and leaves the
original model weights frozen. Run from the repo root:

    uv run python -m ai_ml.model_training.llm.shared.train --max-steps 2
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ai_ml.model_training.llm.shared.dataloader import (
    ChatDataLoader,
    ChatMessage,
    dummy_chat_examples,
)
from ai_model.model_training.llm.shared.config import TrainConfig
from lib.timestamp_utils import get_current_timestamp

def train(
    config: TrainConfig,
    examples: Sequence[Sequence[ChatMessage]] | None = None,
) -> list[float]:
    """Fine-tune a Qwen model with LoRA and save the adapter.

    Writes the adapter and tokenizer to ``config.output_dir``. Prints the
    loss after each optimizer step. Uses ``dummy_chat_examples`` when
    ``examples`` is omitted.

    Returns
    -------
    list[float]
        Loss after each optimizer step, in order.
    """
    import torch  # pyright: ignore[reportMissingImports]
    from peft import LoraConfig, get_peft_model  # pyright: ignore[reportMissingImports]
    from transformers import (  # pyright: ignore[reportMissingImports]
        AutoModelForCausalLM,
        AutoTokenizer,
        set_seed,
    )

    set_seed(config.seed)
    device = _pick_device()
    tokenizer = AutoTokenizer.from_pretrained(config.model_id, use_fast=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(config.model_id, dtype=config.dtype)
    peft_model: Any = get_peft_model(
        model,
        LoraConfig(
            r=config.lora_r,
            lora_alpha=config.lora_alpha,
            lora_dropout=config.lora_dropout,
            bias=config.bias,
            task_type=config.task_type,
            target_modules=config.target_modules
        ),
    )
    peft_model.config.use_cache = False
    peft_model.to(device)
    peft_model.print_trainable_parameters()

    chats = examples if examples is not None else dummy_chat_examples()
    dataloader = ChatDataLoader(
        tokenizer,
        chats,
        batch_size=config.batch_size,
        max_length=config.max_seq_length,
    )

    optimizer = torch.optim.AdamW(
        (param for param in peft_model.parameters() if param.requires_grad),
        lr=config.learning_rate,
    )
    peft_model.train()
    losses: list[float] = []
    step = 0
    for epoch in range(config.num_epochs):
        for batch in dataloader:
            tensors = {key: torch.tensor(value, device=device) for key, value in batch.items()}
            loss = peft_model(**tensors).loss
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            losses.append(float(loss.item()))
            step += 1
            print(f"epoch={epoch} step={step} loss={loss.item():.4f}")
            if config.max_steps is not None and step >= config.max_steps:
                _save(peft_model, tokenizer, config.output_dir)
                return losses
    _save(peft_model, tokenizer, config.output_dir)
    return losses


def _pick_device() -> Any:
    """Prefer CUDA, then Apple MPS, then CPU."""
    import torch  # pyright: ignore[reportMissingImports]

    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def _save(model: Any, tokenizer: Any, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"saved adapter to {output_dir}")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fine-tune an LLM.")
    parser.add_argument("--model-id")
    parser.add_argument("--output-dir", type=Path, default=Path(f"/tmp/model-training/{get_current_timestamp()}"))
    parser.add_argument("--epochs", type=int)
    parser.add_argument("--max-steps", type=int)
    parser.add_argument("--batch-size", type=int)
    parser.add_argument("--max-seq-length", type=int)
    parser.add_argument("--learning-rate", type=float)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    train(
        TrainConfig(
            model_id=args.model_id,
            output_dir=args.output_dir,
            learning_rate=args.learning_rate,
            num_epochs=args.epochs,
            max_steps=args.max_steps,
            batch_size=args.batch_size,
            max_seq_length=args.max_seq_length,
        )
    )


if __name__ == "__main__":
    main()
