import csv
import json
import subprocess
import time
from pathlib import Path
from typing import cast

import typer
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from tqdm import tqdm

from collector.column_name_conversion import COLUMN_NAME_CONVERSION
from collector.constants import (
    DEFAULT_EXAMPLE_POSTS,
    DEFAULT_GENERATED_POSTS,
    DEFAULT_MODEL,
    DEFAULT_N_PER_CALL,
    MAX_CONCURRENCY,
    MAX_GENERATED_POSTS,
    MODEL_TEMPERATURE,
)
from collector.metrics import print_running_gini, write_metrics_json
from collector.models import GeneratedSocialMediaPost, LlmBatchedPosts
from collector.prompts import BATCH_USER_PROMPT_TEMPLATE, SYSTEM_PROMPT
from collector.retry import retry_llm_completion
from lib.load_env_vars import EnvVarsContainer
from lib.timestamp_utils import get_current_timestamp


def get_git_hash() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()


def generate_chat_prompt(examples: list[str], n_per_call: int) -> tuple[str, str]:
    return (SYSTEM_PROMPT, BATCH_USER_PROMPT_TEMPLATE.format(examples=examples, n=n_per_call))


def _get_field_value(field_name: str, row: dict) -> str | None:
    """Get a value for a specific field in the .csv file.
    The field can be mapped to the canonical field names using the column_name_conversion dict.
    """
    return next((row[key] for key in COLUMN_NAME_CONVERSION[field_name] if key in row), None)


def get_examples_dicts(
    examples_path: Path, num_posts: int, examples_offset: int = 0
) -> list[dict[str, str]]:
    """Returns at most num_posts posts from the CSV file, starting at row examples_offset."""
    examples = []
    with open(examples_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for _ in range(examples_offset):
            next(reader, None)
        for row in reader:
            examples.append(
                {
                    "post_id": _get_field_value("post_id", row),
                    "post_handle": _get_field_value("post_handle", row),
                    "post": _get_field_value("post", row),
                    "post_timestamp": _get_field_value("post_timestamp", row),
                }
            )
            if len(examples) == num_posts:
                break
    return examples


def get_chain(prompt: tuple[str, str]) -> Runnable:
    system_prompt, user_prompt = prompt
    template = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
    )
    EnvVarsContainer.get_env_var("OPENAI_API_KEY", required=True)
    llm = ChatOpenAI(model=DEFAULT_MODEL, temperature=MODEL_TEMPERATURE)
    return template | llm.with_structured_output(LlmBatchedPosts)


def append_posts_to_csv(posts: list[GeneratedSocialMediaPost], path: Path) -> None:
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text", "generation_timestamp"])
        writer.writerows(post.model_dump() for post in posts)


@retry_llm_completion()
def _run_batch(chain: Runnable, chunk_inputs: list[dict]) -> list[LlmBatchedPosts]:
    return cast(
        list[LlmBatchedPosts],
        chain.batch(chunk_inputs, config=RunnableConfig(max_concurrency=MAX_CONCURRENCY)),
    )


def run_upsampling(
    prompt: tuple[str, str],
    total_samples: int,
    new_dir: Path,
    n_per_call: int,
    ground_truth_posts: list[str],
) -> None:
    new_dir.mkdir(parents=True, exist_ok=True)
    csv_path = new_dir / "new_posts.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=["text", "generation_timestamp"]).writeheader()

    chain = get_chain(prompt)
    num_calls_float = total_samples / n_per_call
    if not num_calls_float.is_integer():
        raise ValueError(
            f"total_samples ({total_samples}) must be divisible by n_per_call ({n_per_call})"
        )
    num_calls = int(num_calls_float)
    failures: list[dict[str, str]] = []
    all_generated_texts: list[str] = []

    for call_number, i in enumerate(tqdm(range(0, num_calls, MAX_CONCURRENCY)), start=1):
        # calculate size of each chunk (MAX_CONCURRENCY for all except for remainder chunk)
        chunk_inputs = [{}] * min(MAX_CONCURRENCY, num_calls - i)
        try:
            results = _run_batch(chain, chunk_inputs)
            posts = [
                GeneratedSocialMediaPost(text=text, generation_timestamp=get_current_timestamp())
                for result in results
                for text in result.posts
                if text.strip()
            ]
            append_posts_to_csv(posts, csv_path)
            all_generated_texts.extend(post.text for post in posts)
            print_running_gini(ground_truth_posts, all_generated_texts, call_number)
        except Exception as e:
            failures.append({"error": str(e)})

    write_deadletter_json(failures, prompt, new_dir)
    if len(all_generated_texts) > 0:
        write_metrics_json(ground_truth_posts, all_generated_texts, new_dir)


def write_deadletter_json(
    failures: list[dict[str, str]], prompt: tuple[str, str], new_dir: Path
) -> None:
    """Write failures to deadletter.json. No file created if there are no failures.

    Example deadletter.json:
        {
          "prompt": {
            "system": "You are generating synthetic social media posts...",
            "human": "Here are example posts:\\n\\n['post 1', 'post 2']\\n\\nGenerate one new post."
          },
          "num_failures": 2,
          "failures": [
            {"error": "Connection timeout after 30s"},
            {"error": "ValidationError: field 'text' is required"}
          ]
        }
    """
    if not failures:
        return
    system_prompt, user_prompt = prompt
    with open(new_dir / "deadletter.json", "w") as f:
        json.dump(
            {
                "prompt": {"system": system_prompt, "human": user_prompt},
                "num_failures": len(failures),
                "failures": failures,
            },
            f,
            indent=2,
        )


def store_example_posts(examples_dict: list[dict[str, str]], new_dir: Path) -> None:
    new_dir.mkdir(parents=True, exist_ok=True)
    with open(new_dir / "examples.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["post_id", "post_handle", "post", "post_timestamp"])
        writer.writeheader()
        writer.writerows(examples_dict)


def write_to_metadata_json(
    elapsed: float,
    new_dir: Path,
    examples_path: Path,
    num_examples: int,
    examples_offset: int,
    total_samples: int,
    n_per_call: int,
    timestamp: str,
) -> None:
    metadata = {
        "git_commit_hash": get_git_hash(),
        "timestamp": timestamp,
        "cli_args": {
            "examples_path": str(examples_path),
            "num_examples": num_examples,
            "examples_offset": examples_offset,
            "total_samples": total_samples,
            "n_per_call": n_per_call,
        },
        "runtime_seconds": round(elapsed, 4),
    }
    new_dir.mkdir(parents=True, exist_ok=True)
    with open(new_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)


def validate_sample_count(total_samples: int, n_per_call: int) -> None:
    if total_samples % n_per_call != 0:
        raise typer.BadParameter(
            f"--total-samples ({total_samples}) must be divisible by --n-per-call ({n_per_call}). "
            f"Try {(total_samples // n_per_call) * n_per_call} or "
            f"{(total_samples // n_per_call + 1) * n_per_call}."
        )


def extract_examples(examples_dict: list[dict[str, str]]) -> list[str]:
    return [ex_dict["post"] for ex_dict in examples_dict]


def main(
    examples_path: Path = typer.Option(
        ..., help="Full path to examples CSV file (e.g. /folder/to/file.csv)"
    ),
    num_examples: int = typer.Option(
        DEFAULT_EXAMPLE_POSTS,
        help=f"Number of posts to use as examples for LLM (default {DEFAULT_EXAMPLE_POSTS})",
    ),
    examples_offset: int = typer.Option(
        0, help="Row offset into the examples CSV to start reading from (default 0)"
    ),
    total_samples: int = typer.Option(
        DEFAULT_GENERATED_POSTS,
        help=f"Total number of samples to generate (max {MAX_GENERATED_POSTS})",
        max=MAX_GENERATED_POSTS,
    ),
    n_per_call: int = typer.Option(
        DEFAULT_N_PER_CALL,
        help=f"Number of posts to generate per LLM call (default {DEFAULT_N_PER_CALL})",
    ),
):
    validate_sample_count(total_samples, n_per_call)

    examples_dicts = get_examples_dicts(examples_path, num_examples, examples_offset)

    examples = extract_examples(examples_dicts)
    prompt = generate_chat_prompt(examples, n_per_call)

    timestamp = get_current_timestamp()
    new_dir = examples_path.parent / timestamp

    start = time.perf_counter()
    run_upsampling(prompt, total_samples, new_dir, n_per_call, examples)
    elapsed = time.perf_counter() - start

    store_example_posts(examples_dicts, new_dir)
    write_to_metadata_json(
        elapsed,
        new_dir,
        examples_path,
        num_examples,
        examples_offset,
        total_samples,
        n_per_call,
        timestamp,
    )


if __name__ == "__main__":
    typer.run(main)
