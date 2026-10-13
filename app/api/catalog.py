from fastapi import APIRouter, Depends, Query

from ..integrations.odoo import OdooGateway
from ..schemas import Customer, ProductRef
from .deps import get_odoo

router = APIRouter(prefix='/api', tags=['catalog'])


@router.get('/products', response_model=list[ProductRef])
def products(q: str = Query(''), odoo: OdooGateway = Depends(get_odoo)):
    return odoo.search_products(q)


@router.get('/customers', response_model=list[Customer])
def customers(q: str = Query(''), odoo: OdooGateway = Depends(get_odoo)):
    return odoo.search_customers(q)
