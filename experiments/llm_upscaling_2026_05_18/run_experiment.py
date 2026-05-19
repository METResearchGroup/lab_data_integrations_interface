import csv
import math
from pathlib import Path
from typing import cast

import numpy as np
from dotenv import load_dotenv
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from rich.console import Console
from rich.table import Table
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm

from collector.constants import DEFAULT_MODEL, MODEL_TEMPERATURE
from collector.models import LlmBatchedPosts
from collector.prompts import BATCH_USER_PROMPT_TEMPLATE, SYSTEM_PROMPT

load_dotenv()

N_VALUES = [1, 10, 25, 50, 100]
TOTAL_POSTS = 100
EXAMPLES_PATH = Path("experimentation/posts.csv")
RESULTS_DIR = Path("experiments/llm_upscaling_2026_05_18/results")


def load_examples(path: Path, n: int = 5) -> list[str]:
    examples = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            examples.append(row["post"])
            if len(examples) == n:
                break
    return examples


def build_chain(examples: list[str], n_per_call: int):
    user_prompt = BATCH_USER_PROMPT_TEMPLATE.format(examples=examples, n=n_per_call)
    template = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            ("human", user_prompt),
        ]
    )
    llm = ChatOpenAI(model=DEFAULT_MODEL, temperature=MODEL_TEMPERATURE)
    return template | llm.with_structured_output(LlmBatchedPosts)


def generate_posts(examples: list[str], n_per_call: int) -> list[str]:
    chain = build_chain(examples, n_per_call)
    num_calls = math.ceil(TOTAL_POSTS / n_per_call)
    results = cast(list[LlmBatchedPosts], chain.batch([{}] * num_calls, config=RunnableConfig(max_concurrency=10)))
    return [post for result in results for post in result.posts]


def save_posts(posts: list[str], n: int) -> None:
    out_dir = RESULTS_DIR / f"n{n}"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "posts.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["text"])
        writer.writeheader()
        writer.writerows({"text": p} for p in posts)


def gini(array: np.ndarray) -> float:
    array = array.flatten().astype(float)
    if np.amin(array) < 0:
        array -= np.amin(array)
    if np.all(array == 0):
        return 0.0
    array = np.sort(array)
    n = array.shape[0]
    index = np.arange(1, n + 1)
    return float((np.sum((2 * index - n - 1) * array)) / (n * np.sum(array)))


def compute_metrics(posts: list[str], examples: list[str]) -> dict:
    vectorizer = TfidfVectorizer()
    X_all = np.asarray(vectorizer.fit_transform(examples + posts).todense())
    X_examples = X_all[: len(examples)]
    X_generated = X_all[len(examples) :]

    mean_gini = float(np.mean([gini(X_generated[i]) for i in range(len(posts))]))

    sim_matrix = cosine_similarity(X_generated)
    upper = sim_matrix[np.triu_indices(len(posts), k=1)]
    mean_cos_sim = float(upper.mean())

    mean_sim_to_examples = float(cosine_similarity(X_generated, X_examples).mean())

    return {"mean_gini": mean_gini, "mean_cos_sim": mean_cos_sim, "mean_sim_to_examples": mean_sim_to_examples}


def print_results(rows: list[dict]) -> None:
    console = Console()
    table = Table(title="LLM Upscaling Experiment — N posts per call vs diversity")
    table.add_column("N (posts/call)", justify="right")
    table.add_column("LLM Calls", justify="right")
    table.add_column("Mean Gini", justify="right")
    table.add_column("Mean Pairwise Cosine Sim", justify="right")
    table.add_column("Mean Cosine Sim to Examples", justify="right")

    for row in rows:
        table.add_row(
            str(row["n"]),
            str(row["llm_calls"]),
            f"{row['mean_gini']:.4f}",
            f"{row['mean_cos_sim']:.4f}",
            f"{row['mean_sim_to_examples']:.4f}",
        )

    console.print(table)


def main() -> None:
    examples = load_examples(EXAMPLES_PATH)

    rows = []
    for n in tqdm(N_VALUES, desc="Conditions"):
        posts = generate_posts(examples, n)
        save_posts(posts, n)
        metrics = compute_metrics(posts, examples)
        rows.append({"n": n, "llm_calls": math.ceil(TOTAL_POSTS / n), **metrics})

    print_results(rows)


if __name__ == "__main__":
    main()
