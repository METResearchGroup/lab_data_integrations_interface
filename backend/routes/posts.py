from fastapi import APIRouter

router = APIRouter()

@router.get("/posts", status_code=200)
def get_posts():
    return 
