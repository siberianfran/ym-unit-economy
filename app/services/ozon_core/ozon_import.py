"""
marja.app — импорт отчёта Ozon «Начисления» в статьи юнит-экономики.

Отчёт Ozon по начислениям — это реестр транзакций: каждая строка = один тип
начисления (комиссия, логистика, эквайринг, реклама, возврат, ...) по заказу/SKU.
Импортёр сворачивает его по SKU в те же статьи, что считает движок ozon_unit,
чтобы «факт» из отчёта совпадал с расчётом.

Лист: «Начисления». Заголовки в строке 2, данные с 3.
Колонки: ID начисления, Дата, Группа услуг, Тип начисления, Артикул, SKU,
Название, Количество, Цена продавца, Дата заказа, Платформа, Схема работы,
Вознаграждение Ozon %, Индекс локализации %, Среднее время доставки, Сумма итого руб.
"""

from __future__ import annotations
import collections
import json
import openpyxl

# (Группа услуг, Тип начисления) -> статья движка. None-ключ второго уровня = вся группа.
LINE_MAP = {
    ("Продажи", "Выручка"): "revenue",
    ("Продажи", "Баллы за скидки"): "points_revenue",
    ("Продажи", "Программы партнёров"): "partner_programs",
    ("Вознаграждение Ozon", "Вознаграждение за продажу"): "commission",
    ("Вознаграждение Ozon", "Возврат вознаграждения"): "commission",
    ("Продвижение и реклама", None): "marketing",
    ("Услуги доставки", "Логистика"): "logistics",
    ("Услуги доставки", "Логистика - отмена начисления"): "logistics",
    ("Услуги доставки", "Обратная логистика"): "return_logistics",
    ("Услуги доставки", "Доставка курьером Pick-up"): "logistics",
    ("Услуги доставки", "Обработка отправления Pick-up"): "fbs_processing",
    ("Услуги доставки", "Обработка отправления Pick-up - отмена начисления"): "fbs_processing",
    ("Услуги доставки", "Обработка отправления Drop-off (СЦ)"): "fbs_processing",
    ("Услуги доставки", "Организация выезда курьера"): "fbs_processing",
    ("Услуги доставки", "Обработка нестандартного товара"): "logistics",
    ("Услуги доставки", "Доставка до места выдачи силами Ozon"): "last_mile",
    ("Услуги партнёров", "Эквайринг"): "acquiring",
    ("Услуги партнёров", "Доставка до места выдачи"): "last_mile",
    ("Услуги партнёров", "Обработка возвратов, отмен и невыкупов партнёрами"): "return_logistics",
    ("Услуги партнёров", "Временное размещение товара партнерами"): "storage",
    ("Возвраты", None): "returns",
    ("Другие услуги и штрафы", None): "penalties",
    ("Услуги FBO", None): "fbo_services",
}

# Статьи-доходы (положительные), остальное — расходы.
REVENUE_LINES = {"revenue", "points_revenue", "partner_programs"}

COL = {"group": 2, "type": 3, "art": 4, "sku": 5, "name": 6, "qty": 7,
       "price": 8, "scheme": 11, "ozon_pct": 12, "il": 13, "sum": 15}


def _line_for(group, typ):
    if (group, typ) in LINE_MAP:
        return LINE_MAP[(group, typ)]
    if (group, None) in LINE_MAP:
        return LINE_MAP[(group, None)]
    return "прочее"


def import_nachisleniya(path: str, sheet: str = "Начисления") -> dict:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[sheet]
    per_sku = collections.defaultdict(lambda: {
        "sku": "", "name": "", "article": "", "scheme": "", "qty_sold": 0,
        "lines": collections.defaultdict(float)})
    totals = collections.defaultdict(float)
    grand = 0.0
    for r in ws.iter_rows(min_row=3, values_only=True):
        if r[COL["sum"]] is None and r[COL["group"]] is None:
            continue
        group, typ = r[COL["group"]], r[COL["type"]]
        sku = str(r[COL["sku"]] or "").strip()
        amt = float(r[COL["sum"]] or 0)
        line = _line_for(group, typ)
        rec = per_sku[sku]
        rec["sku"] = sku
        if r[COL["name"]]:
            rec["name"] = r[COL["name"]]
        if r[COL["art"]]:
            rec["article"] = r[COL["art"]]
        if r[COL["scheme"]]:
            rec["scheme"] = r[COL["scheme"]]
        if group == "Продажи" and typ == "Выручка":
            rec["qty_sold"] += int(r[COL["qty"]] or 0)
        rec["lines"][line] += amt
        totals[line] += amt
        grand += amt
    # финализируем: считаем нетто по каждому SKU
    result = []
    for sku, rec in per_sku.items():
        lines = {k: round(v, 2) for k, v in rec["lines"].items()}
        net = round(sum(lines.values()), 2)
        revenue = round(sum(v for k, v in lines.items() if k in REVENUE_LINES), 2)
        result.append({
            "sku": sku, "name": rec["name"], "article": rec["article"],
            "scheme": rec["scheme"],
            "qty_sold": rec["qty_sold"], "revenue_rub": revenue,
            "net_rub": net,
            "margin_pct": round(net / revenue * 100, 2) if revenue else None,
            **lines,
        })
    result.sort(key=lambda x: x["net_rub"])
    return {
        "rows": result,
        "totals_by_line": {k: round(v, 2) for k, v in totals.items()},
        "grand_total_rub": round(grand, 2),
        "sku_count": len(result),
    }


if __name__ == "__main__":
    import sys
    data = import_nachisleniya(sys.argv[1])
    print("SKU:", data["sku_count"], "| Итого:", data["grand_total_rub"])
    print(json.dumps(data["totals_by_line"], ensure_ascii=False, indent=2))
