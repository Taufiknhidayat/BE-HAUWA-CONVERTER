from functools import lru_cache

from ..config import get_settings
from ..integrations.odoo import OdooGateway, build_gateway


@lru_cache
def get_odoo() -> OdooGateway:
    return build_gateway(get_settings())
