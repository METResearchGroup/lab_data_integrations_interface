import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from faker import Faker

from collector.models import GeneratedSocialMediaPost, LlmBatchedPosts
from collector.upsampler import (
    append_posts_to_csv,
    extract_examples,
    generate_chat_prompt,
    get_examples_dicts,
    run_upsampling,
    store_example_posts,
    validate_sample_count,
    write_deadletter_json,
    write_to_metadata_json,
)

fake = Faker()


# Fixtures
@pytest.fixture
def example_rows() -> list[dict[str, str]]:
    return [
        {"post_id": fake.uuid4(), "handle": fake.user_name(), "post": fake.sentence(), "post_timestamp": fake.iso8601()}
        for _ in range(3)
    ]


@pytest.fixture
def examples_csv(tmp_path, example_rows) -> Path:
    path = tmp_path / "posts.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["post_id", "handle", "post", "post_timestamp"])
        writer.writeheader()
        writer.writerows(example_rows)
    return path


@pytest.fixture
def generated_post() -> GeneratedSocialMediaPost:
    return GeneratedSocialMediaPost(text=fake.sentence(), generation_timestamp=fake.iso8601())


@pytest.fixture
def generated_posts() -> list[GeneratedSocialMediaPost]:
    return [GeneratedSocialMediaPost(text=fake.sentence(), generation_timestamp=fake.iso8601()) for _ in range(5)]


@pytest.fixture
def prompt() -> tuple[str, str]:
    return (fake.sentence(), fake.paragraph())


@pytest.fixture
def fake_llm_batch(generated_posts) -> MagicMock:
    """Mock _run_batch to return LlmBatchedPosts with Faker-generated posts."""
    mock = MagicMock(return_value=[LlmBatchedPosts(posts=[p.text for p in generated_posts])])
    return mock


# validate_sample_count
def test_validate_sample_count_valid():
    validate_sample_count(100, 10)


def test_validate_sample_count_invalid_raises():
    with pytest.raises(typer.BadParameter):
        validate_sample_count(101, 10)


def test_validate_sample_count_error_includes_suggestions():
    with pytest.raises(typer.BadParameter, match="100"):
        validate_sample_count(101, 10)



# extract_examples
def test_extract_examples_returns_posts(example_rows):
    examples = extract_examples([{"post_id": r["post_id"], "post_handle": r["handle"], "post": r["post"], "post_timestamp": r["post_timestamp"]} for r in example_rows])
    assert examples == [r["post"] for r in example_rows]


def test_extract_examples_empty():
    assert extract_examples([]) == []


# generate_chat_prompt
def test_generate_chat_prompt_returns_tuple():
    examples = [fake.sentence() for _ in range(3)]
    result = generate_chat_prompt(examples, n_per_call=5)
    assert isinstance(result, tuple) and len(result) == 2


def test_generate_chat_prompt_user_prompt_contains_examples():
    examples = [fake.sentence() for _ in range(3)]
    _, user_prompt = generate_chat_prompt(examples, n_per_call=5)
    for example in examples:
        assert example in user_prompt


def test_generate_chat_prompt_user_prompt_contains_n():
    _, user_prompt = generate_chat_prompt([fake.sentence()], n_per_call=7)
    assert "7" in user_prompt


# get_examples_dicts
def test_get_examples_dicts_reads_correct_fields(examples_csv, example_rows):
    result = get_examples_dicts(examples_csv, num_posts=len(example_rows))
    assert result[0]["post_id"] == example_rows[0]["post_id"]
    assert result[0]["post_handle"] == example_rows[0]["handle"]
    assert result[0]["post"] == example_rows[0]["post"]
    assert result[0]["post_timestamp"] == example_rows[0]["post_timestamp"]


def test_get_examples_dicts_respects_limit(examples_csv):
    result = get_examples_dicts(examples_csv, num_posts=1)
    assert len(result) == 1


def test_get_examples_dicts_returns_all_when_limit_exceeds_rows(examples_csv, example_rows):
    result = get_examples_dicts(examples_csv, num_posts=999)
    assert len(result) == len(example_rows)


# append_posts_to_csv
def test_append_posts_to_csv_writes_rows(tmp_path, generated_posts):
    path = tmp_path / "posts.csv"
    path.write_text("text,generation_timestamp\n")
    append_posts_to_csv(generated_posts, path)
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(generated_posts)
    assert rows[0]["text"] == generated_posts[0].text


def test_append_posts_to_csv_accumulates_on_multiple_calls(tmp_path, generated_posts):
    path = tmp_path / "posts.csv"
    path.write_text("text,generation_timestamp\n")
    append_posts_to_csv(generated_posts, path)
    append_posts_to_csv(generated_posts, path)
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(generated_posts) * 2


# write_deadletter_json
def test_write_deadletter_json_creates_file_on_failures(tmp_path, prompt):
    failures = [{"error": fake.sentence()}]
    write_deadletter_json(failures, prompt, tmp_path)
    assert (tmp_path / "deadletter.json").exists()


def test_write_deadletter_json_correct_structure(tmp_path, prompt):
    failures = [{"error": fake.sentence()}, {"error": fake.sentence()}]
    write_deadletter_json(failures, prompt, tmp_path)
    data = json.loads((tmp_path / "deadletter.json").read_text())
    assert data["num_failures"] == 2
    assert len(data["failures"]) == 2
    assert "system" in data["prompt"]
    assert "human" in data["prompt"]


def test_write_deadletter_json_no_file_when_no_failures(tmp_path, prompt):
    write_deadletter_json([], prompt, tmp_path)
    assert not (tmp_path / "deadletter.json").exists()


# store_example_posts
def test_store_example_posts_creates_csv(tmp_path, example_rows):
    dicts = [{"post_id": r["post_id"], "post_handle": r["handle"], "post": r["post"], "post_timestamp": r["post_timestamp"]} for r in example_rows]
    store_example_posts(dicts, tmp_path)
    assert (tmp_path / "examples.csv").exists()


def test_store_example_posts_correct_rows(tmp_path, example_rows):
    dicts = [{"post_id": r["post_id"], "post_handle": r["handle"], "post": r["post"], "post_timestamp": r["post_timestamp"]} for r in example_rows]
    store_example_posts(dicts, tmp_path)
    with open(tmp_path / "examples.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == len(example_rows)
    assert rows[0]["post"] == example_rows[0]["post"]


# write_to_metadata_json
def test_write_to_metadata_json_creates_file(tmp_path, examples_csv):
    write_to_metadata_json(1.23, tmp_path, examples_csv, 100, fake.iso8601())
    assert (tmp_path / "metadata.json").exists()


def test_write_to_metadata_json_correct_keys(tmp_path, examples_csv):
    write_to_metadata_json(1.23, tmp_path, examples_csv, 100, fake.iso8601())
    data = json.loads((tmp_path / "metadata.json").read_text())
    assert "git_commit_hash" in data
    assert "timestamp" in data
    assert "runtime_seconds" in data
    assert "examples_path" in data["cli_args"]
    assert "total_samples" in data["cli_args"]


def test_write_to_metadata_json_cli_args_are_strings(tmp_path, examples_csv):
    write_to_metadata_json(1.23, tmp_path, examples_csv, 100, fake.iso8601())
    data = json.loads((tmp_path / "metadata.json").read_text())
    assert isinstance(data["cli_args"]["examples_path"], str)
    assert isinstance(data["cli_args"]["total_samples"], str)



# run_upsampling
def _make_fake_batch_result(n: int) -> list[LlmBatchedPosts]:
    return [LlmBatchedPosts(posts=[fake.sentence() for _ in range(n)])]


@pytest.fixture
def upsampling_mocks():
    with (
        patch("collector.upsampler.get_chain", return_value=MagicMock()),
        patch("collector.upsampler._run_batch", side_effect=lambda chain, inputs: _make_fake_batch_result(len(inputs))),
        patch("collector.upsampler.print_running_gini") as mock_print_gini,
        patch("collector.upsampler.write_metrics_json") as mock_write_metrics,
    ):
        yield {"print_running_gini": mock_print_gini, "write_metrics_json": mock_write_metrics}


def test_run_upsampling_creates_csv_with_header(tmp_path, prompt, upsampling_mocks):
    run_upsampling(prompt, 10, tmp_path, 10, [fake.sentence()])
    with open(tmp_path / "new_posts.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert set(reader.fieldnames or []) == {"text", "generation_timestamp"}


def test_run_upsampling_writes_generated_posts(tmp_path, prompt, upsampling_mocks):
    run_upsampling(prompt, 10, tmp_path, 10, [fake.sentence()])
    with open(tmp_path / "new_posts.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) > 0


def test_run_upsampling_calls_print_running_gini_per_batch(tmp_path, prompt, upsampling_mocks):
    run_upsampling(prompt, 10, tmp_path, 10, [fake.sentence()])
    assert upsampling_mocks["print_running_gini"].call_count >= 1


def test_run_upsampling_calls_write_metrics_json(tmp_path, prompt, upsampling_mocks):
    run_upsampling(prompt, 10, tmp_path, 10, [fake.sentence()])
    upsampling_mocks["write_metrics_json"].assert_called_once()


def test_run_upsampling_continues_on_batch_failure(tmp_path, prompt):
    with (
        patch("collector.upsampler.get_chain", return_value=MagicMock()),
        patch("collector.upsampler._run_batch", side_effect=Exception("LLM error")),
        patch("collector.upsampler.print_running_gini"),
        patch("collector.upsampler.write_metrics_json") as mock_write_metrics,
    ):
        run_upsampling(prompt, 10, tmp_path, 10, [fake.sentence()])
        assert (tmp_path / "deadletter.json").exists()
        mock_write_metrics.assert_not_called()
