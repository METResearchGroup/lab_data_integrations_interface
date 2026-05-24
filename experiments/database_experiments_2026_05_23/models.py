"""Pydantic models for mock Bluesky-shaped benchmark data.

Run from repo root:
    PYTHONPATH=. uv run python -c "from experiments.database_experiments_2026_05_23.models import UserModel"
"""

from pydantic import BaseModel


class UserModel(BaseModel):
    user_id: str
    created_at: str


class PostModel(BaseModel):
    post_id: str
    author_id: str
    created_at: str
    text: str


class LikeModel(BaseModel):
    like_id: str
    author_id: str
    post_id: str
    created_at: str


class FollowModel(BaseModel):
    follower_id: str
    followee_id: str
