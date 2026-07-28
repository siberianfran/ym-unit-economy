"""
marja.app — движок юнит-экономики Ozon.

По образцу действующей ЯМ-юнитки (calc_single_sku). Отличия Ozon:
- три схемы: FBO / FBS / realFBS (маржа считается по всем сразу);
- комиссия зависит от категории × ценового диапазона × схемы;
- логистика: базовый тариф (цена×объём×направление) + наценка за нелокальность
  + доставка до места выдачи; обработка отправления только для FBS;
- тарифы сверены на 2026-07-27 (изменения Ozon 06.04 и 09.07.2026).

Актуальность: официальные таблицы комиссий и логистики Ozon большие и
меняются — их следует подгружать из выгрузок / Ozon Seller API, а не хардкодить.
Файл ozon_settings.json содержит дефолты и грубую аппроксимацию логистики
для прототипа.
"""

from __future__ import annotations
import json
import math
import os
from typing import Any

SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "ozon_settings.json")


def load_settings(path: str = SETTINGS_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _volume_l(l_cm: float, w_cm: float, h_cm: float) -> float:
    return (l_cm * w_cm * h_cm) / 1000.0  # см³ -> литры


def _volumetric_weight_kg(l_cm: float, w_cm: float, h_cm: float, divisor: int) -> float:
    return (l_cm * w_cm * h_cm) / float(divisor)


def estimate_base_logistics(volume_l: float, price_rub: float, s: dict) -> float:
    """Базовый тариф логистики Ozon по объёму.
    Приоритет — реальная таблица logistics_bands (лист «Логистика» файла цен);
    вне диапазона — запасная аппроксимация base_logistics.
    """
    bands = s.get("logistics_bands")
    if bands:
        for b in bands:  # отсортированы по возрастанию max_l
            if volume_l <= b["max_l"]:
                return b["rub"]
        # крупнее таблицы — экстраполяция по последнему тарифу за литр
        last = bands[-1]
        return round(last["rub"] + (volume_l - last["max_l"]) * s["base_logistics"]["over_190l_per_l_rub"], 2)
    bl = s["base_logistics"]
    rub = bl["over_190l_per_l_rub"] * volume_l
    for band in bl["bands_by_volume_l"]:
        if volume_l <= band["max_l"]:
            rub = band["rub"]
            break
    rub = max(rub, bl["min_rub"])
    if price_rub <= bl["cheap_price_threshold_rub"]:
        rub *= bl["cheap_discount"]
    return round(rub, 2)


def _price_band(price_rub: float) -> str:
    if price_rub <= 100:
        return "le100"
    if price_rub <= 300:
        return "le300"
    return "gt300"


def _commission_pct(category: str, scheme: str, s: dict, product_type: str = None,
                    price_rub: float = 1000) -> float:
    # 0) полный официальный каталог Ozon (категория × тип × схема × ценовой диапазон)
    cat_full = s.get("commission_catalog")
    if cat_full:
        alias = s.get("category_aliases", {}).get(category, category)
        cat = cat_full.get(alias) or cat_full.get(category)
        if cat:
            t = cat.get(product_type) or cat.get("_default")
            if t and scheme in t and t[scheme]:
                bands = t[scheme]
                band = _price_band(price_rub)
                return float(bands.get(band) or bands.get("gt300") or next(iter(bands.values())))
    # 1) реальный справочник комиссий (категория × тип × схема)
    comm = s.get("commissions")
    if comm:
        alias = s.get("category_aliases", {}).get(category, category)
        cat = comm.get(alias)
        if cat:
            if product_type and product_type in cat:
                rates = cat[product_type]
            elif "_default" in cat:
                rates = cat["_default"]
            else:
                rates = next(v for k, v in cat.items() if k != "_default")
            return float(rates[scheme])
    # 2) запасной простой справочник
    cats = s["categories"]
    cat = cats.get(category) or cats.get("Товары для дома (общ)")
    return float(cat[scheme])


def _fbs_processing_rub(volume_l: float, s: dict) -> float:
    mode = s["store_settings"].get("fbs_processing_mode", "sc_trust")
    if mode == "courier":
        c = s["fbs_courier"]
        liters = min(volume_l, c["per_liter_cap_l"])
        return round(c["call_rub"] + c["sort_per_shipment_rub"] + c["per_liter_rub"] * liters, 2)
    return float(s["fbs_processing_options"].get(mode, 10))


def calc_single_sku_ozon(
    *,
    length_cm: float,
    width_cm: float,
    height_cm: float,
    weight_kg: float,
    price_rub: float,
    cost_rub: float,
    category: str = "Товары для дома (общ)",
    product_type: str = None,
    name: str = "",
    sku: str = "",
    extra_cost_rub: float = 0.0,
    drr_pct: float | None = None,
    marketing_rub: float | None = None,
    returns_pct: float | None = None,
    nonlocal_surcharge_pct: float | None = None,
    tax_system: str | None = None,
    acquiring_rate: float | None = None,
    base_logistics_rub: dict | float | None = None,
    commission_override=None,
    settings: dict | None = None,
) -> dict:
    """Юнит-экономика одного SKU на Ozon по трём схемам.

    base_logistics_rub: если задан (из импорта Ozon) — используется как есть.
      Можно передать число (для всех схем) или dict {"FBO":.., "FBS":.., "realFBS":..}.
      Если None — берётся оценка estimate_base_logistics (заглушка).
    """
    s = settings or load_settings()
    ss = s["store_settings"]

    tax_system = tax_system or ss["tax_system"]
    tax_rate = float(s["tax_systems"].get(tax_system, 0.0))
    acq = float(acquiring_rate if acquiring_rate is not None else ss["acquiring_manual_rate"])
    drr = float(drr_pct if drr_pct is not None else ss["default_drr_pct"])
    ret = float(returns_pct if returns_pct is not None else ss["return_pct"])
    nonlocal_pct = float(
        nonlocal_surcharge_pct if nonlocal_surcharge_pct is not None
        else ss.get("nonlocal_surcharge_pct", 0.0)
    )
    last_mile = float(ss.get("last_mile_cap_rub", 25))
    return_proc = float(s.get("return_processing_agent_pvz_rub", 0))

    volume_l = _volume_l(length_cm, width_cm, height_cm)
    vol_weight = _volumetric_weight_kg(length_cm, width_cm, height_cm,
                                       s["base_logistics"]["volumetric_divisor"])
    charge_weight = max(weight_kg, vol_weight)

    def base_log(scheme: str) -> float:
        if isinstance(base_logistics_rub, dict):
            return float(base_logistics_rub.get(scheme,
                         estimate_base_logistics(volume_l, price_rub, s)))
        if isinstance(base_logistics_rub, (int, float)):
            return float(base_logistics_rub)
        return estimate_base_logistics(volume_l, price_rub, s)

    marketing = (marketing_rub if marketing_rub is not None else price_rub * drr)
    acquiring_rub = round(price_rub * acq, 2)
    tax_rub = round(price_rub * tax_rate, 2)

    results = {}
    for scheme in s["schemes"]:
        # индивидуальные условия магазина: commission_override = число или {scheme: rate}
        if commission_override is not None:
            commission_pct = float(commission_override[scheme] if isinstance(commission_override, dict)
                                   and scheme in commission_override else
                                   (commission_override if not isinstance(commission_override, dict) else
                                    _commission_pct(category, scheme, s, product_type, price_rub)))
        else:
            commission_pct = _commission_pct(category, scheme, s, product_type, price_rub)
        commission_rub = round(price_rub * commission_pct, 2)

        bl = base_log(scheme)
        nonlocal_rub = round(price_rub * nonlocal_pct, 2) if scheme == "FBO" else 0.0

        if scheme == "FBO":
            logistics_rub = round(bl + nonlocal_rub + last_mile, 2)
            processing_rub = 0.0
        elif scheme == "FBS":
            processing_rub = _fbs_processing_rub(volume_l, s)
            logistics_rub = round(bl + last_mile + processing_rub, 2)
        else:  # realFBS — продавец везёт сам (свой перевозчик)
            processing_rub = 0.0
            logistics_rub = round(float(ss.get("realfbs_carrier_rub", 0)), 2)

        # обратная логистика ~ прямая (без нелокальной наценки) × доля возвратов + обработка
        returns_reserve_rub = round((bl + return_proc) * ret, 2)

        total_expenses = round(
            commission_rub + logistics_rub + acquiring_rub
            + marketing + returns_reserve_rub + tax_rub
            + cost_rub + extra_cost_rub, 2
        )
        profit = round(price_rub - total_expenses, 2)
        margin = round(profit / price_rub * 100, 2) if price_rub else 0.0

        if margin >= 15:
            verdict = "✅ Хорошая маржа"
        elif margin >= 5:
            verdict = "⚠ Средняя маржа — риск"
        else:
            verdict = "❌ Убыточно / на грани"

        results[scheme] = {
            "commission_pct": commission_pct,
            "commission_rub": commission_rub,
            "base_logistics_rub": round(bl, 2),
            "nonlocal_surcharge_rub": nonlocal_rub,
            "last_mile_rub": last_mile if scheme != "realFBS" else 0.0,
            "fbs_processing_rub": processing_rub,
            "logistics_rub": logistics_rub,
            "acquiring_rub": acquiring_rub,
            "acquiring_rate": acq,
            "marketing_rub": round(marketing, 2),
            "returns_reserve_rub": returns_reserve_rub,
            "tax_rub": tax_rub,
            "tax_rate": tax_rate,
            "cost_rub": cost_rub,
            "extra_cost_rub": extra_cost_rub,
            "total_expenses_rub": total_expenses,
            "profit_rub": profit,
            "margin_pct": margin,
            "verdict": verdict,
        }

    return {
        "sku": sku,
        "name": name,
        "category": category,
        "price_rub": price_rub,
        "volume_l": round(volume_l, 3),
        "charge_weight_kg": round(charge_weight, 3),
        "by_scheme": results,
        "best_scheme": max(results, key=lambda k: results[k]["profit_rub"]),
    }


def calc_batch_ozon(sku_list: list[dict], settings: dict | None = None, **overrides) -> dict:
    s = settings or load_settings()
    results = []
    for row in sku_list:
        args = {**row, **overrides}
        results.append(calc_single_sku_ozon(settings=s, **args))
    summary = {
        "count": len(results),
        "profit_fbo": round(sum(r["by_scheme"]["FBO"]["profit_rub"] for r in results), 2),
        "profit_fbs": round(sum(r["by_scheme"]["FBS"]["profit_rub"] for r in results), 2),
        "profit_realfbs": round(sum(r["by_scheme"]["realFBS"]["profit_rub"] for r in results), 2),
    }
    return {"results": results, "summary": summary}


if __name__ == "__main__":
    demo = calc_single_sku_ozon(
        name="Стол обеденный дубовый", sku="OZ-STOL-01", category="Столы",
        length_cm=120, width_cm=70, height_cm=15, weight_kg=18,
        price_rub=15000, cost_rub=6000,
    )
    print(json.dumps(demo, ensure_ascii=False, indent=2))
