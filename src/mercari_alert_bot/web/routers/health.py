from fastapi import APIRouter

from mercari_alert_bot.web.schemas.health import HealthResponse

router = APIRouter()


@router.get("/healthz")
async def read_health() -> HealthResponse:
    return HealthResponse(status="ok")
