from decimal import Decimal

from app.services.vendor.goods_service import compute_stock_status


def test_compute_stock_status_out_of_stock():
    assert compute_stock_status(Decimal("0")) == "Out of Stock"


def test_compute_stock_status_low_stock():
    assert compute_stock_status(Decimal("49")) == "Low Stock"


def test_compute_stock_status_in_stock():
    assert compute_stock_status(Decimal("50")) == "In Stock"
