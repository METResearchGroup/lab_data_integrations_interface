"""Readability and diversity metrics for LLM-generated social media posts."""

from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import spacy
from openai import OpenAI
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

EMBEDDING_MODEL = "text-embedding-3-small"
CACHE_FILE_PATH = Path(__file__).parent.parent / "data" / "embeddings_cache.parquet"

_embedding_cache: dict[str, list[float]] | None = None

VOWEL_GROUP_RE = re.compile(r"[aeiouy]+", re.IGNORECASE)
NON_LETTER_RE = re.compile(r"[^a-z]")


@lru_cache(maxsize=1)
def _nlp() -> spacy.language.Language:
    """Minimal English pipeline for deterministic token/sentence boundaries."""
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


def _safe_divide(a: float, b: float) -> float:
    return a / b if b != 0 else 0.0


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _get_cache() -> dict[str, list[float]]:
    """
    Loads embeddings into memory and returns the embeddings
    """
    global _embedding_cache
    if _embedding_cache is None:
        if CACHE_FILE_PATH.exists():
            df = pd.read_parquet(CACHE_FILE_PATH)
            _embedding_cache = dict(zip(df["hash"], df["embedding"]))
        else:
            _embedding_cache = {}
    return _embedding_cache


def check_if_embedding_exists(text_hash: str) -> bool:
    return text_hash in _get_cache()


def load_embedding(text_hash: str) -> np.ndarray:
    return np.array(_get_cache()[text_hash])


def create_embedding(text: str) -> np.ndarray:
    response = OpenAI().embeddings.create(input=[text], model=EMBEDDING_MODEL)
    return np.array(response.data[0].embedding)


def save_embedding(text_hash: str, text: str, embedding: np.ndarray) -> None:
    cache = _get_cache()
    cache[text_hash] = embedding.tolist()
    CACHE_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    new_row = pd.DataFrame([{
        "hash": text_hash,
        "text": text,
        "embedding": embedding.tolist(),
        "metadata": json.dumps({"model": EMBEDDING_MODEL}),
    }])
    if CACHE_FILE_PATH.exists():
        df = pd.concat([pd.read_parquet(CACHE_FILE_PATH), new_row], ignore_index=True)
    else:
        df = new_row
    df.to_parquet(CACHE_FILE_PATH, index=False)


def get_embedding(text: str) -> np.ndarray:
    text_hash = hash_text(text)
    if check_if_embedding_exists(text_hash):
        return load_embedding(text_hash)
    embedding = create_embedding(text)
    save_embedding(text_hash, text, embedding)
    return embedding


def _mean_pairwise_cosine(matrix: np.ndarray) -> float:
    n = len(matrix)
    if n < 2:
        return 0.0
    sim = cosine_similarity(matrix)
    i, j = np.triu_indices(n, k=1)
    return float(np.mean(sim[i, j]))


def _mean_cross_cosine(matrix_a: np.ndarray, matrix_b: np.ndarray) -> float:
    return float(np.mean(cosine_similarity(matrix_a, matrix_b)))


def _count_syllables(word: str) -> int:
    w = NON_LETTER_RE.sub("", word.lower())
    if not w:
        return 0
    groups = VOWEL_GROUP_RE.findall(w)
    syllables = len(groups)
    if w.endswith("e") and syllables > 1:
        syllables -= 1
    return max(1, syllables)


def _readability_counts(text: str) -> tuple[int, int, int]:
    doc = _nlp()(text)
    words = [token.text for token in doc if token.is_alpha]
    sentence_count = sum(1 for sent in doc.sents if sent.text.strip())
    if sentence_count == 0:
        sentence_count = 1
    word_count = len(words)
    syllable_count = sum(_count_syllables(word) for word in words)
    return word_count, sentence_count, syllable_count


class CalculateMetric(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def describe(self) -> str: ...

    @abstractmethod
    def calculate(self, text: str) -> float: ...


class FleschKincaidGradeMetric(CalculateMetric):
    @property
    def name(self) -> str:
        return "flesch_kincaid_grade"

    def describe(self) -> str:
        return (
            "Flesch-Kincaid Grade Level: 0.39*(words/sentences) + "
            "11.8*(syllables/words) - 15.59, using spaCy sentence and token boundaries."
        )

    def calculate(self, text: str) -> float:
        words, sentences, syllables = _readability_counts(text)
        if words == 0:
            return 0.0
        return float(
            0.39 * _safe_divide(float(words), float(sentences))
            + 11.8 * _safe_divide(float(syllables), float(words))
            - 15.59
        )


class FleschReadingEaseMetric(CalculateMetric):
    @property
    def name(self) -> str:
        return "flesch_reading_ease"

    def describe(self) -> str:
        return (
            "Flesch Reading Ease: 206.835 - 1.015*(words/sentences) - "
            "84.6*(syllables/words), using spaCy sentence and token boundaries."
        )

    def calculate(self, text: str) -> float:
        words, sentences, syllables = _readability_counts(text)
        if words == 0:
            return 0.0
        return float(
            206.835
            - 1.015 * _safe_divide(float(words), float(sentences))
            - 84.6 * _safe_divide(float(syllables), float(words))
        )


def _gini(array: np.ndarray) -> float:
    array = array.flatten().astype(float)
    if np.amin(array) < 0:
        array -= np.amin(array)
    if np.all(array == 0):
        return 0.0
    array = np.sort(array)
    n = array.shape[0]
    index = np.arange(1, n + 1)
    return float((np.sum((2 * index - n - 1) * array)) / (n * np.sum(array)))


def _mean_gini_for_group(tfidf_matrix, start: int, count: int) -> float:
    return float(np.mean([_gini(tfidf_matrix[start + i].toarray().ravel()) for i in range(count)]))


def _compute_group_metrics(posts: list[str], tfidf_matrix, tfidf_start: int) -> dict:
    gini_scores = [
        _gini(tfidf_matrix[tfidf_start + i].toarray().ravel()) for i in range(len(posts))
    ]
    reading_ease = FleschReadingEaseMetric()
    kincaid_grade = FleschKincaidGradeMetric()
    return {
        "mean_post_length": round(float(np.mean([len(p) for p in posts])), 4),
        "mean_post_reading_ease": round(
            float(np.mean([reading_ease.calculate(p) for p in posts])), 4
        ),
        "mean_post_reading_grade_level": round(
            float(np.mean([kincaid_grade.calculate(p) for p in posts])), 4
        ),
        "mean_gini": round(float(np.mean(gini_scores)), 4),
    }


def print_running_gini(
    ground_truth_posts: list[str], generated_posts: list[str], call_number: int
) -> None:
    """Print mean_gini for both groups to terminal after each LLM batch call."""
    all_posts = ground_truth_posts + generated_posts
    X = TfidfVectorizer().fit_transform(all_posts)
    n_gt = len(ground_truth_posts)
    n_gen = len(generated_posts)
    gt_gini = _mean_gini_for_group(X, 0, n_gt)
    gen_gini = _mean_gini_for_group(X, n_gt, n_gen)
    print(
        f"[call {call_number}] mean_gini — "
        f"ground_truth: {gt_gini:.4f} | "
        f"generated ({n_gen} posts so far): {gen_gini:.4f}"
    )


def write_metrics_json(
    ground_truth_posts: list[str], generated_posts: list[str], output_dir: Path
) -> None:
    """Compute and write final metrics.json."""
    all_posts = ground_truth_posts + generated_posts
    X = TfidfVectorizer().fit_transform(all_posts)
    n_gt = len(ground_truth_posts)

    gt_embeddings = np.array([get_embedding(p) for p in ground_truth_posts])
    gen_embeddings = np.array([get_embedding(p) for p in generated_posts])

    metrics = {
        "ground_truth": _compute_group_metrics(ground_truth_posts, X, 0),
        "generated": _compute_group_metrics(generated_posts, X, n_gt),
        "embedding_similarities": {
            "within_sample": round(_mean_pairwise_cosine(gt_embeddings), 4),
            "within_generation": round(_mean_pairwise_cosine(gen_embeddings), 4),
            "inter_data": round(_mean_cross_cosine(gt_embeddings, gen_embeddings), 4),
        },
    }
    with open(output_dir / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
