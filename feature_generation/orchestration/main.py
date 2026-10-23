from typing_extensions import Iterable

class FeatureGenerationRunMetadata:
    feature_generation_runs = []

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

def run_single_feature_generation_run(candidate_posts: Iterable[str]):
    del candidate_posts
    # update_run_metadata()
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
    for feature_generation_run in run_metadata.feature_generation_runs:
        run_single_feature_generation_run(candidate_posts=candidate_posts)
    close_feature_generation_run()
