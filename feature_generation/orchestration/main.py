from typing import Callable

from typing_extensions import Iterable

def decorator_for_handling_retries_and_writes_and_metadata_updates():
    pass

@decorator_for_handling_retries_and_writes_and_metadata_updates
def jev_feature_generator():
    return


feature_to_generator_registry: dict[str, Callable] = {
    "jev": jev_feature_generator
}

class FeatureGenerationRunMetadata:
    feature_metadata = []

def dequeue() -> Iterable[str]:
    return []

def filter_pending_posts(pending_posts: Iterable[str]):
    return pending_posts

def update_post_statuses(
    candidate_posts: Iterable[str],
    run_metadata: FeatureGenerationRunMetadata
):
    """Once posts are loaded, mark them as 'in-progress' in DynamoDB
    for the given integration run(s)."""
    del candidate_posts
    del run_metadata
    return None

def load_posts():
    pending_posts: Iterable[str] = dequeue()
    # TODO: probably should filter separately for each integration TBH.
    # Can still return as a single list, albeit with a boolean column for
    # each integration that can then be used later.
    filtered_pending_posts: Iterable[str] = filter_pending_posts(pending_posts)
    return filtered_pending_posts

def run_feature_generator(
    feature_metadata: dict,
    candidate_posts: Iterable[str]
):
    feature_name: str = feature_metadata["name"]
    generator_func: Callable = feature_to_generator_registry[feature_name]
    generator_func(candidate_posts)


def run_single_feature_generation_run(
    feature_metadata: dict,
    candidate_posts: Iterable[str]
):
    del candidate_posts
    run_feature_generator(
        feature_metadata=feature_metadata
    )
    return

def close_feature_generation_run():
    return None


def main():
    run_metadata = FeatureGenerationRunMetadata()
    candidate_posts: Iterable[str] = load_posts()
    update_post_statuses(
        candidate_posts=candidate_posts,
        run_metadata=run_metadata
    )
    for feature_metadata in run_metadata.feature_metadata:
        run_single_feature_generation_run(
            feature_metadata=feature_metadata,
            candidate_posts=candidate_posts
        )
    close_feature_generation_run()
