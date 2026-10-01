from typing import Annotated, Final

from fastapi import APIRouter, Depends

from mercari_alert_bot.application.services.polling_settings_service import (
    PollingSettingsService,
)
from mercari_alert_bot.web.dependencies import provide_polling_settings_service
from mercari_alert_bot.web.schemas.polling_settings import PollingSettingsSchema

router: Final = APIRouter(prefix="/api/settings")


PollingSettingsServiceDependency = Annotated[
    PollingSettingsService, Depends(provide_polling_settings_service)
]


@router.get("")
def read_polling_settings(service: PollingSettingsServiceDependency) -> PollingSettingsSchema:
    return PollingSettingsSchema.from_polling_settings(service.current_polling_settings)


@router.put("")
async def replace_polling_settings(
    body: PollingSettingsSchema, service: PollingSettingsServiceDependency
) -> PollingSettingsSchema:
    saved_polling_settings = await service.update_polling_settings(body.to_polling_settings())
    return PollingSettingsSchema.from_polling_settings(saved_polling_settings)
