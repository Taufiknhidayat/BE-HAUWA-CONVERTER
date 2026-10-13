from app.schemas import Customer
from app.services.customers import find_marketplace_customer


def _cs(*names):
    return [Customer(id=i + 1, name=n) for i, n in enumerate(names)]


def test_shopee_matches_marketplace_shopee():
    found = find_marketplace_customer('shopee', _cs(
        'Marketplace - Shopee', 'Marketplace - Tiktok'))
    assert found.name == 'Marketplace - Shopee'


def test_tiktok_matches_marketplace_tiktok():
    found = find_marketplace_customer('tiktok', _cs(
        'Marketplace - Shopee', 'Marketplace - Tiktok'))
    assert found.name == 'Marketplace - Tiktok'


def test_matches_loosely_on_spacing_case_and_dashes():
    found = find_marketplace_customer('shopee', _cs('marketplace-shopee  Official'))
    assert found is not None
    assert find_marketplace_customer('tiktok', _cs('Marketplace - TikTok')) is not None


def test_not_found_returns_none():
    assert find_marketplace_customer('shopee', _cs('Hauwa Official')) is None
    assert find_marketplace_customer('tiktok', []) is None


def test_ambiguous_returns_none():
    assert find_marketplace_customer('shopee', _cs(
        'Marketplace - Shopee', 'Marketplace - Shopee 2')) is None


def test_unknown_platform_returns_none():
    assert find_marketplace_customer('lazada', _cs('Marketplace - Lazada')) is None