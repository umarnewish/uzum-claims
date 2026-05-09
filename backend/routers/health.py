from fastapi import APIRouter, Depends

from backend.auth import get_current_user_id

router = APIRouter()


@router.get("/health", include_in_schema=False)
async def health():
    return {"status": "ok", "service": "uzum-claims"}


@router.get("/whoami")
async def whoami(user_id: int = Depends(get_current_user_id)):
    return {"user_id": user_id}
