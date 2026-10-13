from fastapi import APIRouter, Depends

from ..integrations.odoo import OdooGateway
from ..schemas import Health
from .deps import get_odoo

router = APIRouter(prefix='/api', tags=['health'])


@router.get('/health', response_model=Health)
def health(odoo: OdooGateway = Depends(get_odoo)):
    return odoo.health()
