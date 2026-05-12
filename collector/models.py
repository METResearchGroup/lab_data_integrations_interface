from pydantic import BaseModel


class SocialMediaPost(BaseModel):
    id: str
    handle: str
    text: str
    post_timestamp: str
