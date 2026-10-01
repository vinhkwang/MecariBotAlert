from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Response, status

from mercari_alert_bot.application.services.keyword_rule_service import KeywordRuleService
from mercari_alert_bot.domain.errors import InvalidDomainValueError, KeywordRuleNotFoundError
from mercari_alert_bot.domain.models.keyword_rule import KeywordRuleId
from mercari_alert_bot.web.dependencies import provide_keyword_rule_service
from mercari_alert_bot.web.schemas.keyword_rule_schemas import (
    KeywordRuleCreateRequest,
    KeywordRuleResponse,
    KeywordRuleUpdateRequest,
)

router: Final = APIRouter(prefix="/api/keywords", tags=["keywords"])

KeywordRuleServiceDependency = Annotated[KeywordRuleService, Depends(provide_keyword_rule_service)]


@contextmanager
def translate_domain_errors() -> Iterator[None]:
    try:
        yield
    except KeywordRuleNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except InvalidDomainValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error


@router.get("")
async def list_keywords(service: KeywordRuleServiceDependency) -> list[KeywordRuleResponse]:
    rules = await service.list_rules()
    return [KeywordRuleResponse.from_dto(rule) for rule in rules]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_keyword(
    request: KeywordRuleCreateRequest, service: KeywordRuleServiceDependency
) -> KeywordRuleResponse:
    with translate_domain_errors():
        rule = await service.create_rule(request.name, request.query, is_enabled=request.is_enabled)
    return KeywordRuleResponse.from_dto(rule)


@router.patch("/{rule_id}")
async def update_keyword(
    rule_id: int, request: KeywordRuleUpdateRequest, service: KeywordRuleServiceDependency
) -> KeywordRuleResponse:
    with translate_domain_errors():
        rule = await service.update_rule(
            KeywordRuleId(rule_id),
            name=request.name,
            query=request.query,
            is_enabled=request.is_enabled,
        )
    return KeywordRuleResponse.from_dto(rule)


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_keyword(rule_id: int, service: KeywordRuleServiceDependency) -> Response:
    with translate_domain_errors():
        await service.delete_rule(KeywordRuleId(rule_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{rule_id}/reset-baseline")
async def reset_keyword_baseline(
    rule_id: int, service: KeywordRuleServiceDependency
) -> KeywordRuleResponse:
    with translate_domain_errors():
        rule = await service.reset_rule_baseline(KeywordRuleId(rule_id))
    return KeywordRuleResponse.from_dto(rule)
