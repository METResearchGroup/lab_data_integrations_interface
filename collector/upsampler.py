import json
import shutil
import subprocess
import time
import typer

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pathlib import Path
from pydantic import BaseModel
from tqdm import tqdm

from lib.timestamp_utils import get_current_timestamp

class SocialMediaPost(BaseModel):
    id: str
    handle: str
    text: str
    post_timestamp: str


def get_git_hash():
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    ).stdout.strip()

def generate_chat_prompt():
    pass

def get_examples_dict(examples_path):
    """
    Get at most 5 rows from examples_path
    """

def write_new_posts_file(examples_dict, new_dir):
    pass

def generate_new_posts(examples_path, total_samples):
    pass

def copy_old_file(examples_path, new_dir):
    new_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(examples_path, new_dir / examples_path.name)

def write_to_metadata_json(elapsed, new_dir, examples_path, total_samples, timestamp):
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



def main(
    examples_path: Path = typer.Option(
        ..., help="Full path to examples CSV file (e.g. /folder/to/file.csv)"
    ),
    total_samples: int = typer.Option(
        10, help="Total number of samples to generate (max 40)", max=40
    ),
):
    examples_dict = get_examples_dict(examples_path)
    
    prompt = generate_chat_prompt()

    start = time.perf_counter()
    new_posts = generate_new_posts(examples_path, total_samples)
    elapsed = time.perf_counter() - start

    timestamp = get_current_timestamp()
    new_dir = examples_path.parent / timestamp

    copy_old_file(examples_path, new_dir)
    write_new_posts_file(examples_dict, new_dir)
    write_to_metadata_json(elapsed, new_dir, examples_path, total_samples, timestamp)
    # write to deadletter file

if __name__ == "__main__":
    typer.run(main)
