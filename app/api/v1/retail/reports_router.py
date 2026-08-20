from fastapi import APIRouter, Depends

from app.dependencies.auth import require_portal
from app.dependencies.retail import get_retail_reports_service
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.retail.reports_service import RetailReportsService

router = APIRouter(prefix="/reports", tags=["retail-reports"])
_portal = require_portal("store")


@router.get("/topics", response_model=ApiResponse[list[dict]])
def list_topics(service: RetailReportsService = Depends(get_retail_reports_service), _: User = Depends(_portal)):
    return ApiResponse(data=service.list_topics())


@router.get("/sales", response_model=ApiResponse[dict])
def get_sales(
    period: str = "weekly", service: RetailReportsService = Depends(get_retail_reports_service), user: User = Depends(_portal)
):
    return ApiResponse(data=service.get_sales(user.entity_id, period))


@router.get("/profit", response_model=ApiResponse[dict])
def get_profit(
    period: str = "weekly", service: RetailReportsService = Depends(get_retail_reports_service), user: User = Depends(_portal)
):
    return ApiResponse(data=service.get_profit(user.entity_id, period))


@router.get("/warehouse-relations", response_model=ApiResponse[dict])
def get_warehouse_relations(
    period: str = "weekly", service: RetailReportsService = Depends(get_retail_reports_service), user: User = Depends(_portal)
):
    return ApiResponse(data=service.get_warehouse_relations(user.entity_id, period))


# Generic tabular report, backing every other topic key (pr/shipment/stock/discount/
# replenishment) - must stay registered AFTER the literal routes above so those match first.
@router.get("/{topic_key}", response_model=ApiResponse[dict])
def get_topic_report(
    topic_key: str, period: str = "weekly",
    service: RetailReportsService = Depends(get_retail_reports_service), user: User = Depends(_portal),
):
    return ApiResponse(data=service.get_topic_report(user.entity_id, topic_key, period))
