import csv
import json
import shutil
import subprocess
import time
from pathlib import Path

import typer
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from tqdm import tqdm

from collector.circuit_breaker import CircuitBreaker
from collector.constants import DEFAULT_MODEL, MODEL_TEMPERATURE
from collector.models import SocialMediaPost
from lib.timestamp_utils import get_current_timestamp

load_dotenv()


def get_git_hash() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()


def generate_chat_prompt(examples: list[str]) -> tuple[str, str]:
    system_prompt = """
                    You are generating synthetic social media posts for a research dataset.
                    Given real example posts, generate exactly one new post that matches
                    their topic, tone, and writing style — but is not a copy or paraphrase
                    of any single example. Posts should be under 300 characters.
                    """
    user_prompt = f"""
                    Here are example posts:\n\n{examples}\n\n
                    Generate one new post in the same style.
                    """
    return (system_prompt, user_prompt)


def get_examples_dict(examples_path: Path) -> list[dict[str, str]]:
    """Returns at most the first 5 posts in the CSV file."""
    examples = []
    with open(examples_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            examples.append(
                {
                    "post_id": row["post_id"],
                    "post_handle": row["handle"],
                    "post": row["post"],
                    "post_timestamp": row["post_timestamp"],
                }
            )
            if len(examples) == 5:
                break
    return examples


def get_chain(prompt: tuple[str, str]):
    system_prompt, user_prompt = prompt
    template = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
    )
    llm = ChatOpenAI(model=DEFAULT_MODEL, temperature=MODEL_TEMPERATURE)
    return template | llm.with_structured_output(SocialMediaPost)


def generate_new_post(chain) -> SocialMediaPost:
    return chain.invoke({})


def run_upsampling(prompt: tuple[str, str], total_samples: int, new_dir: Path) -> None:
    new_dir.mkdir(parents=True, exist_ok=True)

    chain = get_chain(prompt)
    breaker = CircuitBreaker()
    failures: list[dict[str, str]] = []

    with open(new_dir / "new_posts.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "handle", "text", "post_timestamp"])
        writer.writeheader()
        for _ in tqdm(range(total_samples)):
            if breaker.is_open:
                failures.append({"error": "circuit breaker open, stopping early"})
                break
            try:
                post = generate_new_post(chain)
                writer.writerow(post.model_dump())
                f.flush()
                breaker.record_success()
            except Exception as e:
                failures.append({"error": str(e)})
                breaker.record_failure()

    write_deadletter_json(failures, prompt, new_dir)


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


def copy_old_file(examples_path: Path, new_dir: Path) -> None:
    new_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(examples_path, new_dir / examples_path.name)


def write_to_metadata_json(
    elapsed: float, new_dir: Path, examples_path: Path, total_samples: int, timestamp: str
) -> None:
    metadata = {
        "git_commit_hash": get_git_hash(),
        "timestamp": timestamp,
        "cli_args": {
            "examples_path": str(examples_path),
            "total_samples": str(total_samples),
        },
        "runtime_seconds": round(elapsed, 4),
    }
    new_dir.mkdir(parents=True, exist_ok=True)
    with open(new_dir / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)


def extract_examples(examples_dict: list[dict[str, str]]) -> list[str]:
    return [ex_dict["post"] for ex_dict in examples_dict]


def main(
    examples_path: Path = typer.Option(
        ..., help="Full path to examples CSV file (e.g. /folder/to/file.csv)"
    ),
    total_samples: int = typer.Option(
        10, help="Total number of samples to generate (max 40)", max=40
    ),
):
    examples_dict = get_examples_dict(examples_path)

    examples = extract_examples(examples_dict)
    prompt = generate_chat_prompt(examples)

    timestamp = get_current_timestamp()
    new_dir = examples_path.parent / timestamp

    start = time.perf_counter()
    run_upsampling(prompt, total_samples, new_dir)
    elapsed = time.perf_counter() - start

    copy_old_file(examples_path, new_dir)
    write_to_metadata_json(elapsed, new_dir, examples_path, total_samples, timestamp)


if __name__ == "__main__":
    typer.run(main)
