"""Endpoints для интеграции с Yandex.Market API."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import httpx
from app.database import get_db
from app.deps import get_workspace_for_user
from app.models import Workspace, MarketplaceAccount, Sku
from app.services.ya_market import YaMarketClient, offer_to_sku_dict, stock_record_to_total

router = APIRouter(prefix="/api/workspaces/{workspace_id}/ya-market", tags=["ya_market"])


def _get_account(db: Session, workspace_id: int) -> MarketplaceAccount:
    acc = db.query(MarketplaceAccount).filter_by(
        workspace_id=workspace_id, marketplace="ya_market"
    ).first()
    if not acc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
            "Нет подключённого Ya.Market аккаунта.")
    return acc


@router.get("/campaigns")
def list_campaigns(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    acc = _get_account(db, ws.id)
    try:
        with YaMarketClient(acc.api_token) as cl:
            return {"campaigns": cl.list_campaigns()}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
            f"Ya.Market {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Ошибка: {e}")


@router.post("/import-offers")
def import_offers(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    acc = _get_account(db, ws.id)
    if not acc.business_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нет business_id.")
    try:
        with YaMarketClient(acc.api_token, business_id=acc.business_id, campaign_id=acc.campaign_id) as cl:
            offers = cl.iterate_all_offers()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
            f"Ya.Market {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Ошибка: {e}")

    created = updated = 0
    for offer_mapping in offers:
        item = offer_to_sku_dict(offer_mapping)
        if not item["sku"]: continue
        existing = db.query(Sku).filter_by(workspace_id=ws.id, sku=item["sku"]).first()
        if existing:
            saved_cost = float(existing.cost_rub)
            for k, v in item.items():
                if k == "cost_rub" and saved_cost > 0:
                    continue
                setattr(existing, k, v)
            updated += 1
        else:
            db.add(Sku(workspace_id=ws.id, **item))
            created += 1
    db.commit()
    return {
        "total_offers_from_ya_market": len(offers),
        "created_in_our_db": created,
        "updated_in_our_db": updated,
    }


@router.post("/sync-prices")
def sync_prices(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    acc = _get_account(db, ws.id)
    if not acc.campaign_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нет campaign_id.")
    skus = db.query(Sku).filter_by(workspace_id=ws.id).all()
    if not skus:
        return {"updated": 0}
    offer_ids = [s.sku for s in skus]
    try:
        with YaMarketClient(acc.api_token, campaign_id=acc.campaign_id) as cl:
            price_map: dict[str, float] = {}
            for i in range(0, len(offer_ids), 500):
                chunk = offer_ids[i:i+500]
                offers_prices = cl.get_prices(chunk)
                for op in offers_prices:
                    oid = op.get("offerId")
                    p = (op.get("price") or {}).get("value")
                    if oid and p is not None:
                        price_map[oid] = float(p)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
            f"Ya.Market {e.response.status_code}: {e.response.text[:300]}")

    updated = 0
    for s in skus:
        if s.sku in price_map and float(s.price_rub) != price_map[s.sku]:
            s.price_rub = price_map[s.sku]
            updated += 1
    db.commit()
    return {"updated": updated, "matched": len(price_map), "total_skus": len(skus)}


@router.post("/sync-stocks")
def sync_stocks(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    """Тянет остатки FBY+FBS+FBW из Ya.Market и складывает в поле stock_total."""
    acc = _get_account(db, ws.id)
    if not acc.campaign_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Нет campaign_id.")
    try:
        with YaMarketClient(acc.api_token, campaign_id=acc.campaign_id) as cl:
            records = cl.iterate_all_stocks()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
            f"Ya.Market {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Ошибка: {e}")

    stock_map: dict[str, int] = {}
    for rec in records:
        oid, total = stock_record_to_total(rec)
        if oid:
            stock_map[oid] = stock_map.get(oid, 0) + total

    skus = db.query(Sku).filter_by(workspace_id=ws.id).all()
    updated = 0
    for s in skus:
        new_val = stock_map.get(s.sku, 0)
        if (getattr(s, "stock_total", 0) or 0) != new_val:
            s.stock_total = new_val
            updated += 1
    db.commit()
    return {
        "updated": updated,
        "matched_offers": len(stock_map),
        "total_skus": len(skus),
        "in_stock": sum(1 for s in skus if (s.stock_total or 0) > 0),
    }
