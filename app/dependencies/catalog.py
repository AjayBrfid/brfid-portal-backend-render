from fastapi import Depends
from sqlalchemy.orm import Session

from app.dependencies.database import get_db
from app.services.catalog_service import MasterCatalogService


def get_master_catalog_service(session: Session = Depends(get_db)) -> MasterCatalogService:
    return MasterCatalogService(session)
