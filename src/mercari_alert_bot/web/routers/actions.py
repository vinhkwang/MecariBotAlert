from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Response, status

from mercari_alert_bot.application.services.operator_action_service import OperatorActionService
from mercari_alert_bot.domain.errors import (
    InvalidDomainValueError,
    KeywordRuleNotFoundError,
    NotificationDeliveryError,
)
from mercari_alert_bot.domain.models.keyword_rule import KeywordRuleId
from mercari_alert_bot.web.schemas.actions import KeywordImportRequest, KeywordImportResponse

EXPORT_MEDIA_TYPE: Final = "application/yaml"
EXPORT_HEADERS: Final = {"Content-Disposition": 'attachment; filename="keywords.yaml"'}
DELIVERY_FAILED_DETAIL: Final = "notification delivery failed"

actions_router: Final = APIRouter(prefix="/api")


def get_operator_action_service() -> OperatorActionService:
    raise RuntimeError("operator action service is not wired")


OperatorActionServiceDependency = Annotated[
    OperatorActionService, Depends(get_operator_action_service)
]


@actions_router.post("/actions/test-notification", status_code=status.HTTP_204_NO_CONTENT)
async def send_test_notification(service: OperatorActionServiceDependency) -> None:
    try:
        await service.send_test_notification()
    except NotificationDeliveryError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, DELIVERY_FAILED_DETAIL) from error


@actions_router.post("/actions/import-yaml")
async def import_keyword_rules(
    request: KeywordImportRequest, service: OperatorActionServiceDependency
) -> KeywordImportResponse:
    try:
        result = await service.import_keyword_rules(request.document_text)
    except InvalidDomainValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(error)) from error
    return KeywordImportResponse(
        imported_rule_count=result.imported_rule_count,
        skipped_rule_count=result.skipped_rule_count,
    )


@actions_router.get("/actions/export-yaml")
async def export_keyword_rules(service: OperatorActionServiceDependency) -> Response:
    return Response(
        await service.export_keyword_rules(),
        media_type=EXPORT_MEDIA_TYPE,
        headers=EXPORT_HEADERS,
    )


@actions_router.post("/keywords/{rule_id}/reset-baseline", status_code=status.HTTP_204_NO_CONTENT)
async def reset_rule_baseline(rule_id: int, service: OperatorActionServiceDependency) -> None:
    try:
        await service.reset_rule_baseline(KeywordRuleId(rule_id))
    except KeywordRuleNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
