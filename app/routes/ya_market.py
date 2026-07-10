"""Endpoints для интеграции с Yandex.Market API."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import httpx
from app.database import get_db
from app.deps import get_workspace_for_user
from app.models import Workspace, MarketplaceAccount, Sku
from app.services.ya_market import YaMarketClient, offer_to_sku_dict

router = APIRouter(prefix="/api/workspaces/{workspace_id}/ya-market", tags=["ya_market"])


def _get_account(db: Session, workspace_id: int) -> MarketplaceAccount:
    acc = db.query(MarketplaceAccount).filter_by(
        workspace_id=workspace_id, marketplace="ya_market"
    ).first()
    if not acc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
            "Нет подключённого Ya.Market аккаунта. Добавь через POST /marketplace-accounts")
    return acc


@router.get("/campaigns")
def list_campaigns(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    """Список магазинов в подключённом кабинете."""
    acc = _get_account(db, ws.id)
    try:
        with YaMarketClient(acc.api_token) as cl:
            return {"campaigns": cl.list_campaigns()}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
            f"Ya.Market вернул {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Ошибка связи с Ya.Market: {e}")


@router.post("/import-offers")
def import_offers(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    """Импортировать все карточки товаров из Ya.Market в наш каталог."""
    acc = _get_account(db, ws.id)
    if not acc.business_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
            "У аккаунта не указан business_id. Обнови через API.")
    try:
        with YaMarketClient(acc.api_token, business_id=acc.business_id, campaign_id=acc.campaign_id) as cl:
            offers = cl.iterate_all_offers()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY,
            f"Ya.Market вернул {e.response.status_code}: {e.response.text[:300]}")
    except Exception as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Ошибка: {e}")

    created = updated = 0
    for offer_mapping in offers:
        item = offer_to_sku_dict(offer_mapping)
        if not item["sku"]: continue
        existing = db.query(Sku).filter_by(workspace_id=ws.id, sku=item["sku"]).first()
        if existing:
            # Обновим только цена/габариты/название/категорию — себестоимость не трогаем
            saved_cost = float(existing.cost_rub)
            for k, v in item.items():
                if k == "cost_rub" and saved_cost > 0:
                    continue  # оставляем ранее заполненную себестоимость
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
        "hint": "Себестоимость Я.Маркет не отдаёт — заполни вручную",
    }


@router.post("/sync-prices")
def sync_prices(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    """Синхронизировать цены с Ya.Market (не трогая себестоимость и категории)."""
    acc = _get_account(db, ws.id)
    if not acc.campaign_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "У аккаунта не указан campaign_id.")
    skus = db.query(Sku).filter_by(workspace_id=ws.id).all()
    if not skus:
        return {"updated": 0, "hint": "SKU нет — сначала импортируй карточки"}
    offer_ids = [s.sku for s in skus]
    try:
        with YaMarketClient(acc.api_token, campaign_id=acc.campaign_id) as cl:
            # Ya.Market API принимает до 500 offer_ids за раз
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
