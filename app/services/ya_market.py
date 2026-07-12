"""Клиент Yandex.Market Partner API."""
from __future__ import annotations
import httpx
from typing import Any

BASE_URL = "https://api.partner.market.yandex.ru"


def _num(v):
    """Мягкое приведение к float."""
    try:
        if v is None or v == "": return 0.0
        return float(v)
    except (ValueError, TypeError):
        return 0.0


class YaMarketClient:
    def __init__(self, api_token: str, business_id: int | None = None,
                 campaign_id: int | None = None, timeout: float = 60.0):
        self.token = api_token
        self.business_id = business_id
        self.campaign_id = campaign_id
        self._client = httpx.Client(
            base_url=BASE_URL,
            headers={
                "Api-Key": api_token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            timeout=timeout,
        )

    def __enter__(self): return self
    def __exit__(self, *a): self._client.close()
    def close(self): self._client.close()

    def list_campaigns(self) -> list[dict]:
        r = self._client.get("/campaigns")
        r.raise_for_status()
        return r.json().get("campaigns", [])

    def list_offer_mappings(self, page_token: str | None = None, limit: int = 200) -> dict:
        if not self.business_id:
            raise ValueError("business_id обязателен")
        params = {"limit": limit}
        if page_token: params["page_token"] = page_token
        # Пустое тело + все поля офферов включая габариты
        r = self._client.post(
            f"/businesses/{self.business_id}/offer-mappings",
            params=params, json={},
        )
        r.raise_for_status()
        return r.json().get("result", {})

    def iterate_all_offers(self) -> list[dict]:
        all_items = []
        page_token = None
        while True:
            data = self.list_offer_mappings(page_token=page_token)
            items = data.get("offerMappings", [])
            all_items.extend(items)
            page_token = data.get("paging", {}).get("nextPageToken")
            if not page_token: break
        return all_items

    def get_prices(self, offer_ids: list[str]) -> list[dict]:
        if not self.campaign_id:
            raise ValueError("campaign_id обязателен")
        r = self._client.post(
            f"/campaigns/{self.campaign_id}/offer-prices",
            json={"offerIds": offer_ids},
        )
        r.raise_for_status()
        return r.json().get("result", {}).get("offers", [])

    def iterate_all_stocks(self) -> list[dict]:
        if not self.campaign_id:
            raise ValueError("campaign_id обязателен")
        all_items: list[dict] = []
        page_token: str | None = None
        while True:
            params = {"limit": 200}
            if page_token: params["page_token"] = page_token
            r = self._client.post(
                f"/campaigns/{self.campaign_id}/offers/stocks",
                params=params, json={},
            )
            r.raise_for_status()
            data = r.json().get("result", {})
            items = data.get("warehouses", []) or data.get("offers", [])
            for wh in items:
                if "offers" in wh:
                    for off in wh["offers"]:
                        all_items.append(off)
                elif "offerId" in wh:
                    all_items.append(wh)
            page_token = (data.get("paging") or {}).get("nextPageToken")
            if not page_token: break
        return all_items


def _extract_dims(offer: dict) -> tuple[float, float, float, float]:
    """Достаёт (length_cm, width_cm, height_cm, weight_kg) из offer.
    Пробует несколько путей: weightDimensions, dimensions, отдельные поля."""
    # Основной путь: weightDimensions
    wd = offer.get("weightDimensions") or offer.get("weight_dimensions") or {}
    if isinstance(wd, dict) and any(wd.get(k) for k in ("length","width","height","weight")):
        return (_num(wd.get("length")), _num(wd.get("width")),
                _num(wd.get("height")), _num(wd.get("weight")))
    # Альтернатива: dimensions
    d = offer.get("dimensions") or {}
    if isinstance(d, dict) and any(d.get(k) for k in ("length","width","height")):
        return (_num(d.get("length")), _num(d.get("width")),
                _num(d.get("height")), _num(offer.get("weight")))
    # Плоские поля
    return (
        _num(offer.get("length")),
        _num(offer.get("width")),
        _num(offer.get("height")),
        _num(offer.get("weight")),
    )


def _extract_price(offer: dict) -> float:
    """Ищет цену в offer.basicPrice.value или offer.price.value."""
    for key in ("basicPrice", "price", "purchasePrice"):
        p = offer.get(key)
        if isinstance(p, dict) and p.get("value") is not None:
            return _num(p.get("value"))
    return 0.0


def offer_to_sku_dict(offer_mapping: dict) -> dict:
    offer = offer_mapping.get("offer", {}) or {}
    mapping = offer_mapping.get("mapping", {}) or {}
    category = mapping.get("marketCategoryName") or offer.get("marketCategoryName") or ""
    our_category = _map_ya_category(category)
    L, W, H, wg = _extract_dims(offer)
    return {
        "sku": str(offer.get("offerId") or ""),
        "name": str(offer.get("name") or "")[:500],
        "category": our_category,
        "model": "FBS",
        "length_cm": L,
        "width_cm":  W,
        "height_cm": H,
        "weight_kg": wg,
        "price_rub": _extract_price(offer),
        "cost_rub":  0,
    }


def stock_record_to_total(rec: dict) -> tuple[str, int]:
    oid = str(rec.get("offerId") or "")
    total = 0
    for stk in rec.get("stocks", []):
        if str(stk.get("type") or "").upper() in ("FIT", "AVAILABLE", "AVAILABLE_STOCK"):
            total += int(stk.get("count") or 0)
    for wh in rec.get("warehouses", []):
        for stk in wh.get("stocks", []):
            if str(stk.get("type") or "").upper() in ("FIT", "AVAILABLE", "AVAILABLE_STOCK"):
                total += int(stk.get("count") or 0)
    return oid, total


def _map_ya_category(cat: str) -> str:
    c = (cat or "").lower()
    if "групп" in c and "обеденн" in c:  return "Комплекты кухонные"
    if "комплект" in c and ("стул" in c or "кухн" in c): return "Комплекты кухонные"
    if "стол" in c and "кухонн" in c:    return "Столы кухонные"
    if "стол" in c and "барн" in c:      return "Столы кухонные"
    if "стол" in c and "журнальн" in c:  return "Столы журнальные"
    if "стол" in c and ("обеденн" in c or "офисн" in c): return "Столы обеденные"
    if "стол" in c:                       return "Столы обеденные"
    if "стул" in c and "барн" in c:      return "Стулья барные"
    if "стул" in c and "кухонн" in c:    return "Стулья кухонные"
    if "табурет" in c or "стул" in c:    return "Стулья"
    if "кресл" in c:                      return "Кресла компьютерные"
    return "Товары для дома (общ)"
