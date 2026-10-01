from typing import Annotated

from fastapi import APIRouter, Depends, Query

from mercari_alert_bot.application.services.system_status_service import SystemStatusService
from mercari_alert_bot.web.dependencies import provide_system_status_service
from mercari_alert_bot.web.schemas.status import RecentListingResponse, SystemStatusResponse

router = APIRouter(prefix="/api")


@router.get("/status")
async def read_system_status(
    service: Annotated[SystemStatusService, Depends(provide_system_status_service)],
) -> SystemStatusResponse:
    return SystemStatusResponse.from_status(await service.describe_system_status())


@router.get("/listings")
async def read_recent_listings(
    service: Annotated[SystemStatusService, Depends(provide_system_status_service)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[RecentListingResponse]:
    entries = await service.list_recent_listings(limit)
    return [RecentListingResponse.from_entry(entry) for entry in entries]
