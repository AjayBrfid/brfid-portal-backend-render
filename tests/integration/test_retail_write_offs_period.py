"""GET /receiving/write-offs?period=... -- the frontend always sends `period`, but the router
never forwarded it to the service (which didn't even accept it), so the write-offs modal's
weekly/monthly/yearly filter did nothing server-side and always returned the store's entire
write-off history regardless of the selected period."""
from datetime import datetime, timedelta, timezone

from app.models.fulfillment import TransferOrder, TransferOrderSourceType
from app.models.retail import ReceivingItem
from tests.integration.helpers import auth_headers, create_sku_variant, create_store, create_user, create_warehouse, login


def _setup(db_session):
    warehouse = create_warehouse(db_session, code="WH-WO-01")
    store = create_store(db_session, code="STR-WO-01")
    _, variant = create_sku_variant(db_session, "SKU-WO-01", "SKU-WO-01-BLK-M")
    create_user(db_session, "store", store.id, "store-wo@test.com", "store-admin")
    db_session.commit()
    return warehouse, store, variant


def _write_off(db, warehouse, store, variant, created_at, note):
    to = TransferOrder(
        ref_code=f"TO-WO-{created_at.timestamp():.0f}", warehouse_id=warehouse.id, store_id=store.id,
        sku_variant_id=variant.id, quantity=5, source_type=TransferOrderSourceType.WAREHOUSE_STOCK,
    )
    db.add(to)
    db.flush()
    item = ReceivingItem(
        transfer_order_id=to.id, sku_variant_id=variant.id, expected_qty=5, received_qty=5,
        return_type="Write-off", issue_qty=5, issue_note=note, created_at=created_at,
    )
    db.add(item)
    db.flush()
    return item


def test_write_offs_default_period_is_weekly(client, db_session):
    warehouse, store, variant = _setup(db_session)
    _write_off(db_session, warehouse, store, variant, datetime.now(timezone.utc) - timedelta(days=2), "recent")
    _write_off(db_session, warehouse, store, variant, datetime.now(timezone.utc) - timedelta(days=20), "old")
    db_session.commit()

    token = login(client, "store", "store-wo@test.com")
    resp = client.get("/api/v1/retail/receiving/write-offs", headers=auth_headers(token))
    reasons = [w["reason"] for w in resp.json()["data"]]
    assert reasons == ["recent"]


def test_write_offs_monthly_period_includes_older_records(client, db_session):
    warehouse, store, variant = _setup(db_session)
    _write_off(db_session, warehouse, store, variant, datetime.now(timezone.utc) - timedelta(days=2), "recent")
    _write_off(db_session, warehouse, store, variant, datetime.now(timezone.utc) - timedelta(days=20), "old")
    _write_off(db_session, warehouse, store, variant, datetime.now(timezone.utc) - timedelta(days=200), "ancient")
    db_session.commit()

    token = login(client, "store", "store-wo@test.com")
    resp = client.get("/api/v1/retail/receiving/write-offs?period=monthly", headers=auth_headers(token))
    reasons = sorted(w["reason"] for w in resp.json()["data"])
    assert reasons == ["old", "recent"]


def test_write_offs_yearly_period_includes_everything_within_a_year(client, db_session):
    warehouse, store, variant = _setup(db_session)
    _write_off(db_session, warehouse, store, variant, datetime.now(timezone.utc) - timedelta(days=200), "ancient")
    _write_off(db_session, warehouse, store, variant, datetime.now(timezone.utc) - timedelta(days=500), "way_too_old")
    db_session.commit()

    token = login(client, "store", "store-wo@test.com")
    resp = client.get("/api/v1/retail/receiving/write-offs?period=yearly", headers=auth_headers(token))
    reasons = [w["reason"] for w in resp.json()["data"]]
    assert reasons == ["ancient"]


def test_write_offs_unrecognized_period_falls_back_gracefully(client, db_session):
    warehouse, store, variant = _setup(db_session)
    _write_off(db_session, warehouse, store, variant, datetime.now(timezone.utc) - timedelta(days=2), "recent")
    db_session.commit()

    token = login(client, "store", "store-wo@test.com")
    resp = client.get("/api/v1/retail/receiving/write-offs?period=not_a_real_period", headers=auth_headers(token))
    assert resp.status_code == 200
    assert [w["reason"] for w in resp.json()["data"]] == ["recent"]
