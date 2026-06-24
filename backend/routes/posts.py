from fastapi import APIRouter

# from data_platform.aws.athena import Athena
# from data_platform.aws.constants import DEFAULT_DATABASE, DEFAULT_WORKGROUP

router = APIRouter()


@router.get("/posts/recent", status_code=200)
def get_recent_posts(dataset_id: str, run_dir: str | None = None, limit: int = 100):
    """Return up to `limit` posts from today, ordered by created_at descending."""
    # athena = Athena()
    # TODO: build SQL, run query, fetch rows, return list of post dicts
    raise NotImplementedError


@router.get("/posts/top-authors", status_code=200)
def get_top_authors(dataset_id: str, run_dir: str | None = None, limit: int = 100):
    """Return the top `limit` authors by post count over the past 7 days."""
    # athena = Athena()
    # TODO: build SQL, run query, fetch rows, return list of {author_handle, post_count}
    raise NotImplementedError


@router.get("/posts/keyword-count", status_code=200)
def get_keyword_count(dataset_id: str, keyword: str, run_dir: str | None = None):
    """Return how many posts contain `keyword` in their text over the past 7 days."""
    # athena = Athena()
    # TODO: build SQL, run query, fetch single count row, return {keyword, count}
    raise NotImplementedError
