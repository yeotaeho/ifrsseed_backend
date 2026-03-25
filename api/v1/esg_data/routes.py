"""ESG Data API Router."""

from fastapi import APIRouter

from .ucm_router import ucm_router


router = APIRouter(prefix="/esg-data", tags=["ESG Data"])
router.include_router(ucm_router)

