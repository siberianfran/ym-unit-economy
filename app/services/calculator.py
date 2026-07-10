"""Ядро расчёта юнит-экономики Я.Маркет — та же логика, что в предыдущих версиях."""
import math
from app.seed import LOGISTICS, ACQUIRING_OPTIONS


def _volume_l(l, w, h):
    return int(math.ceil((l * w * h) / 1000))


def _middle_mile(v, tiers):
    if v <= tiers["tier1_max_l"]: return float(tiers["tier1_rate"])
    if v <= tiers["tier2_max_l"]:
        return tiers["tier1_rate"] + tiers["tier2_per_l"] * (v - tiers["tier1_max_l"])
    if v <= tiers["tier3_max_l"]:
        return (tiers["tier1_rate"]
                + tiers["tier2_per_l"] * (tiers["tier2_max_l"] - tiers["tier1_max_l"])
                + tiers["tier3_per_l"] * (v - tiers["tier2_max_l"]))
    return (tiers["tier1_rate"]
            + tiers["tier2_per_l"] * (tiers["tier2_max_l"] - tiers["tier1_max_l"])
            + tiers["tier3_per_l"] * (tiers["tier3_max_l"] - tiers["tier2_max_l"])
            + tiers["tier4_per_l"] * (v - tiers["tier3_max_l"]))


def calc_one(sku_dict, store, categories,
             tax_rate_override=None, acquiring_override=None, drr_override=None):
    """Расчёт по одному SKU.

    sku_dict: SKU в виде dict (sku, category, model, размеры, цена, себестоимость, drr_pct)
    store: dict настроек магазина (tax_rate, acquiring_rate, return_pct, return_cost_rub, default_drr_pct)
    categories: dict {name -> {fby_rate, fbs_rate}}
    """
    log = LOGISTICS
    tiers = log["middle_mile"]

    price = float(sku_dict.get("price_rub") or 0)
    cost = float(sku_dict.get("cost_rub") or 0)
    L = float(sku_dict.get("length_cm") or 0)
    W = float(sku_dict.get("width_cm") or 0)
    H = float(sku_dict.get("height_cm") or 0)
    weight = float(sku_dict.get("weight_kg") or 0)
    model = str(sku_dict.get("model") or "FBS").upper()
    cat_name = str(sku_dict.get("category") or "Товары для дома (общ)")

    drr = drr_override if drr_override is not None else (
        sku_dict.get("drr_pct") if sku_dict.get("drr_pct") is not None else store.get("default_drr_pct", 0.10)
    )
    tax = tax_rate_override if tax_rate_override is not None else store.get("tax_rate", 0)
    acq = acquiring_override if acquiring_override is not None else store.get("acquiring_rate", 0.023)

    # Комиссия по категории
    cat = categories.get(cat_name) or {"fby_rate": 0.18, "fbs_rate": 0.25}
    cat_rate = cat["fby_rate"] if model == "FBY" else cat["fbs_rate"]

    volume = _volume_l(L, W, H)
    cheap = price <= log["cheap_price_threshold_rub"] and volume <= log["cheap_volume_threshold_l"]

    if cheap:
        commission = price * (log["cheap_rate_fby"] if model == "FBY" else log["cheap_rate_fbs"])
        middle_mile = 0.0
        delivery = 0.0
    else:
        commission = price * cat_rate
        middle_mile = min(tiers["cap_rub"], _middle_mile(volume, tiers))
        delivery = min(log["delivery_cap_rub"], price * log["delivery_pct"])

    acquiring = price * acq

    fbs_processing = 0.0
    if model == "FBS":
        is_large = weight > log["fbs_large_weight_kg"] or (L + W + H) > log["fbs_large_sum_sides_cm"]
        fbs_processing = (log["fbs_processing_base_rub"] + log["fbs_processing_per_kg_rub"] * weight) if is_large else log["fbs_processing_base_rub"]

    advertising = price * drr
    returns_reserve = store.get("return_pct", 0.05) * store.get("return_cost_rub", 200)
    tax_rub = price * tax

    total = commission + middle_mile + delivery + acquiring + fbs_processing + advertising + returns_reserve + tax_rub + cost
    profit = price - total
    margin = (profit / price) if price > 0 else 0

    return {
        "id": sku_dict.get("id"),
        "sku": sku_dict.get("sku"),
        "name": sku_dict.get("name") or "",
        "category": cat_name,
        "model": model,
        "price_rub": round(price, 2),
        "cost_rub": round(cost, 2),
        "drr_pct": round(drr, 4),
        "volume_l": volume,
        "is_cheap": cheap,
        "commission_rub": round(commission, 2),
        "middle_mile_rub": round(middle_mile, 2),
        "delivery_rub": round(delivery, 2),
        "acquiring_rub": round(acquiring, 2),
        "acquiring_rate": round(acq, 4),
        "fbs_processing_rub": round(fbs_processing, 2),
        "advertising_rub": round(advertising, 2),
        "returns_reserve_rub": round(returns_reserve, 2),
        "tax_rub": round(tax_rub, 2),
        "tax_rate": round(tax, 4),
        "total_expenses_rub": round(total, 2),
        "profit_rub": round(profit, 2),
        "margin_pct": round(margin * 100, 2),
        "verdict": (
            "✅ Хорошая маржа" if margin >= 0.15 else
            "⚠ Средняя маржа — риск" if margin >= 0.05 else
            "❌ Убыточно"
        ),
    }


def summarize(results):
    if not results:
        return {"total_sku": 0, "profitable_15plus": 0, "profitable_5_15": 0, "losing": 0, "avg_margin_pct": 0}
    avg = sum(r["margin_pct"] for r in results) / len(results)
    return {
        "total_sku": len(results),
        "profitable_15plus": sum(1 for r in results if r["margin_pct"] >= 15),
        "profitable_5_15":   sum(1 for r in results if 5 <= r["margin_pct"] < 15),
        "losing":            sum(1 for r in results if r["margin_pct"] < 0),
        "avg_margin_pct": round(avg, 2),
    }
