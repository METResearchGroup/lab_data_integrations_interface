import csv
import json
import shutil
import subprocess
import time
from pathlib import Path

import typer
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
from tqdm import tqdm

from lib.timestamp_utils import get_current_timestamp


class SocialMediaPost(BaseModel):
    id: str
    handle: str
    text: str
    post_timestamp: str


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


def write_new_posts_file(new_posts: list[SocialMediaPost], new_dir: Path) -> None:
    pass


## NEED TO IMPLEMENT RETRY + DEADLETTER STUFF
def generate_new_posts(
    prompt: tuple[str, str], examples_path: Path, total_samples: int
) -> list[SocialMediaPost]:
    system_prompt, user_prompt = prompt
    template = ChatPromptTemplate.from_messages(
        [
            ("system", system_prompt),
            ("human", user_prompt),
        ]
    )
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.9)
    chain = template | llm.with_structured_output(SocialMediaPost)

    new_posts = []
    for _ in tqdm(range(total_samples)):
        result = chain.invoke({})
        new_posts.append(result)

    return new_posts


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

    start = time.perf_counter()
    new_posts = generate_new_posts(prompt, examples_path, total_samples)
    elapsed = time.perf_counter() - start

    timestamp = get_current_timestamp()
    new_dir = examples_path.parent / timestamp

    copy_old_file(examples_path, new_dir)
    write_new_posts_file(new_posts, new_dir)
    write_to_metadata_json(elapsed, new_dir, examples_path, total_samples, timestamp)
    # write to deadletter file


if __name__ == "__main__":
    typer.run(main)
