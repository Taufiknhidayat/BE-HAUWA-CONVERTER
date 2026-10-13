from ...config import Settings
from .base import OdooError, OdooGateway
from .client import OdooClient
from .mock import MockOdooClient


def build_gateway(settings: Settings) -> OdooGateway:
    return MockOdooClient() if settings.odoo_mock else OdooClient(settings)


__all__ = ['MockOdooClient', 'OdooClient', 'OdooError', 'OdooGateway',
           'build_gateway']
