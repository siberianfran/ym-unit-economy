"""
marja.app — сопоставление себестоимости (COGS) к SKU отчёта Ozon.

Источник — файл цен продавца (несколько листов-сценариев: Ozon FBS, Ozon FBO,
КомплектМ, ИУ, цены март). Себестоимость за комплект = COGS на 1 проданную
единицу Ozon (1 заказ = 1 комплект).

Матчинг: 1) точно по Ozon SKU (ID); 2) запасной — по токену модели в артикуле
(напр. «BXF Стул 0002407 4шт» -> модель 2407, 4 шт -> DL-2407 4шт).

Разные листы могут давать разную себестоимость одной модели — берём по
приоритету листов (по умолчанию магазин FBS -> лист «Ozon FBS» первым).
"""
from __future__ import annotations
import re
import openpyxl

SHEET_PRIORITY = ["Ozon FBS", "КомплектМ", "ИУ", "цены март", "Ozon FBO"]
_ID = re.compile(r"^\d{9,10}(\.0)?$")
_MODEL = re.compile(r"(?:DL|DC)[-\s]?(\d{3,5})", re.I)
_MODEL_NUM = re.compile(r"0*(\d{3,5})")
_QTY = re.compile(r"(\d+)\s*шт")


def _norm_id(x):
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s if _ID.match(str(x).strip()) else None


def _sheet_maps(cost_file: str):
    wb = openpyxl.load_workbook(cost_file, read_only=True, data_only=True)
    by_id = {}          # sku_id -> (cost_set, sheet, name)
    by_token = {}       # (model, qty) -> (cost_set, sheet, name)
    order = {n: i for i, n in enumerate(SHEET_PRIORITY)}
    sheets = sorted(wb.worksheets, key=lambda w: order.get(w.title, 99))
    for ws in sheets:
        rows = list(ws.iter_rows(values_only=True))
        hr = None
        for i, r in enumerate(rows[:15]):
            cells = [str(c) if c is not None else "" for c in r]
            if any(c == "Артикул" for c in cells) and any("себестоимость за комплект" in c for c in cells):
                hr = i; header = cells; break
        if hr is None:
            continue
        c_name = [j for j, c in enumerate(header) if c == "Артикул"][0]
        c_set = [j for j, c in enumerate(header) if "себестоимость за комплект" in c][0]
        c_qty = [j for j, c in enumerate(header) if c == "комплект"]
        c_qty = c_qty[0] if c_qty else None
        for r in rows[hr + 1:]:
            if c_name >= len(r) or not isinstance(r[c_name], str):
                continue
            name = r[c_name]
            cset = r[c_set] if c_set < len(r) else None
            if not isinstance(cset, (int, float)) or cset <= 0:
                continue
            cset = float(cset)
            sid = next((_norm_id(c) for c in r if _norm_id(c)), None)
            if sid and sid not in by_id:
                by_id[sid] = (cset, ws.title, name)
            m = _MODEL.search(name)
            q = r[c_qty] if c_qty is not None and c_qty < len(r) else None
            if m and q:
                key = (m.group(1), int(q))
                by_token.setdefault(key, (cset, ws.title, name))
    return by_id, by_token


def build_cogs(cost_file: str, report_skus: list[dict]) -> dict:
    """report_skus: [{"sku","article","qty_sold"}]. Возвращает матч по каждому."""
    by_id, by_token = _sheet_maps(cost_file)
    out = {}
    for row in report_skus:
        sid = str(row["sku"]).strip()
        if sid.endswith(".0"):
            sid = sid[:-2]
        art = str(row.get("article") or "")
        cost_set = source = matched_name = None
        method = "нет"
        if sid in by_id:
            cost_set, source, matched_name = by_id[sid]
            method = "ID"
        else:
            mnum = _MODEL_NUM.search(art)
            qm = _QTY.search(art)
            if mnum and qm:
                key = (mnum.group(1), int(qm.group(1)))
                if key in by_token:
                    cost_set, source, matched_name = by_token[key]
                    method = f"токен {mnum.group(1)}×{qm.group(1)}шт"
        out[sid] = {
            "cost_set": round(cost_set, 2) if cost_set is not None else None,
            "cogs_total": round(cost_set * row.get("qty_sold", 0), 2) if cost_set is not None else None,
            "method": method, "source_sheet": source, "matched_name": matched_name,
        }
    return out
