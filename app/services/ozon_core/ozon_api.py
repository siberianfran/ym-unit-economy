"""
marja.app — клиент Ozon Seller API (real-time данные по магазину).

Авторизация: заголовки Client-Id и Api-Key (ключи задаёт магазин в профиле).
База: https://api-seller.ozon.ru

Методы:
- finance_transactions(from, to)  -> POST /v3/finance/transaction/list
- finance_realization(year, month)-> POST /v1/finance/realization
- product_list()                  -> POST /v2/product/list
- product_info(product_ids)       -> POST /v3/product/info/list  (габариты)
- product_prices(offer_ids)       -> POST /v4/product/info/prices (комиссии, цена)

normalize_transactions(...) сворачивает операции в ту же структуру статей,
что и импорт отчёта «Начисления», чтобы P&L и сверка работали одинаково
для файлов и для API.
"""
from __future__ import annotations
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

BASE = "https://api-seller.ozon.ru"

# operation_type / услуга Ozon API -> статья движка (как в ozon_import.LINE_MAP)
OP_LINE = {
    "OperationAgentDeliveredToCustomer": "logistics",
    "OperationItemReturn": "returns",
    "OperationReturnGoodsFBSofRMS": "return_logistics",
    "MarketplaceServiceItemFulfillment": "fbs_processing",
    "MarketplaceServiceItemDelivToCustomer": "logistics",
    "MarketplaceServiceItemDirectFlowLogistic": "logistics",
    "MarketplaceServiceItemReturnFlowLogistic": "return_logistics",
    "MarketplaceServiceItemDropoffPPZ": "fbs_processing",
    "MarketplaceServiceItemDropoffSC": "fbs_processing",
    "MarketplaceRedistributionOfAcquiringOperation": "acquiring",
    "MarketplaceServiceItemLastMile": "last_mile",
    "OperationMarketplaceServicePremiumCashback": "marketing",
    "MarketplaceMarketingActionCostOperation": "marketing",
    "OperationMarketplaceServicePremiumSubscribtion": "marketing",
}


class OzonAPIError(RuntimeError):
    pass


class OzonSellerAPI:
    def __init__(self, client_id: str, api_key: str, timeout: int = 60):
        self.client_id = str(client_id)
        self.api_key = api_key
        self.timeout = timeout

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            BASE + path,
            data=json.dumps(body).encode("utf-8"),
            headers={"Client-Id": self.client_id, "Api-Key": self.api_key,
                     "Content-Type": "application/json"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise OzonAPIError(f"{path} HTTP {e.code}: {e.read().decode('utf-8')[:300]}")
        except urllib.error.URLError as e:
            raise OzonAPIError(f"{path} сеть: {e}")

    # ---- финансы ----
    def finance_transactions(self, date_from: str, date_to: str, page_size: int = 1000) -> list[dict]:
        ops, page = [], 1
        while True:
            r = self._post("/v3/finance/transaction/list", {
                "filter": {"date": {"from": date_from, "to": date_to},
                           "transaction_type": "all"},
                "page": page, "page_size": page_size})
            res = r.get("result", {})
            ops.extend(res.get("operations", []))
            if page >= res.get("page_count", 1):
                break
            page += 1
            time.sleep(0.2)
        return ops

    def finance_realization(self, year: int, month: int) -> dict:
        return self._post("/v1/finance/realization", {"year": year, "month": month})

    # ---- товары ----
    def product_list(self, limit: int = 1000) -> list[dict]:
        items, last_id = [], ""
        while True:
            r = self._post("/v2/product/list",
                           {"filter": {"visibility": "ALL"}, "last_id": last_id, "limit": limit})
            res = r.get("result", {})
            items.extend(res.get("items", []))
            last_id = res.get("last_id", "")
            if not last_id or len(res.get("items", [])) < limit:
                break
        return items

    def product_info(self, product_ids: list[int]) -> list[dict]:
        r = self._post("/v3/product/info/list", {"product_id": product_ids})
        return r.get("items", r.get("result", {}).get("items", []))

    def product_prices(self, offer_ids: list[str]) -> list[dict]:
        r = self._post("/v4/product/info/prices",
                       {"filter": {"offer_id": offer_ids, "visibility": "ALL"}, "limit": 1000})
        return r.get("result", {}).get("items", [])


def normalize_transactions(operations: list[dict]) -> dict:
    """Свернуть операции API в структуру, совместимую с ozon_import (по SKU)."""
    import collections
    per_sku = collections.defaultdict(lambda: collections.defaultdict(float))
    meta = {}
    grand = 0.0
    for op in operations:
        amount = float(op.get("amount", 0) or 0)
        grand += amount
        items = op.get("items") or []
        sku = str(items[0]["sku"]) if items else ""
        if items:
            meta.setdefault(sku, items[0].get("name", ""))
        otype = op.get("operation_type", "")
        # выручка / комиссия
        acc = float(op.get("accruals_for_sale", 0) or 0)
        comm = float(op.get("sale_commission", 0) or 0)
        if acc:
            per_sku[sku]["revenue"] += acc
        if comm:
            per_sku[sku]["commission"] += comm
        # услуги
        for s in op.get("services", []) or []:
            line = OP_LINE.get(s.get("name", ""), "прочее")
            per_sku[sku][line] += float(s.get("price", 0) or 0)
        base_line = OP_LINE.get(otype)
        if base_line and not op.get("services"):
            per_sku[sku][base_line] += amount
    rows = []
    for sku, lines in per_sku.items():
        rows.append({"sku": sku, "name": meta.get(sku, ""),
                     **{k: round(v, 2) for k, v in lines.items()}})
    return {"rows": rows, "grand_total_rub": round(grand, 2), "sku_count": len(rows)}
