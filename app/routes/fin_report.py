"""Финансовый отчёт (P&L) по маркетплейсу."""
from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Any
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db, SessionLocal
from app.deps import get_workspace_for_user
from app.models import (
    Workspace, MarketplaceAccount, Sku,
    FinReport, FinReportPeriod,
)
from app.services.ya_market_reports import (
    YaMarketReportsClient, YaMarketReportError,
    parse_key_indicators_xlsx, parse_realization_xlsx,
    week_ranges,
)

router = APIRouter(prefix="/api/workspaces/{workspace_id}/fin-report", tags=["fin_report"])


class GenerateReq(BaseModel):
    date_from: date
    date_to: date
    source: str = Field(default="key_indicators", pattern="^(key_indicators|realization|mixed)$")


class PeriodResponse(BaseModel):
    id: int
    period_type: str
    period_from: date
    period_to: date
    revenue_gross: float = 0
    revenue_return: float = 0
    revenue_correction: float = 0
    revenue_total: float = 0
    revenue_without_spp: float = 0
    commission: float = 0
    delivery_logistics: float = 0
    logistics_correction: float = 0
    logistics_total: float = 0
    storage: float = 0
    processing: float = 0
    penalties: float = 0
    advertising: float = 0
    acquiring: float = 0
    other: float = 0
    payout: float = 0
    cost_of_sales: float = 0
    profit: float = 0
    margin_pct: float = 0
    units_sold: int = 0

    class Config:
        from_attributes = True


class ReportResponse(BaseModel):
    id: int
    marketplace: str
    period_from: date
    period_to: date
    source: str
    status: str
    error: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    periods: list[PeriodResponse] = []

    class Config:
        from_attributes = True


def _get_account(db: Session, workspace_id: int) -> MarketplaceAccount:
    acc = db.query(MarketplaceAccount).filter_by(
        workspace_id=workspace_id, marketplace="ya_market"
    ).first()
    if not acc:
        raise HTTPException(400, "Нет подключённого Ya.Market аккаунта")
    if not acc.business_id:
        raise HTTPException(400, "У аккаунта не указан business_id")
    return acc


def _sku_cost_map(db: Session, workspace_id: int) -> dict[str, float]:
    skus = db.query(Sku).filter_by(workspace_id=workspace_id).all()
    return {s.sku: float(s.cost_rub or 0) for s in skus}


def _run_generation(report_id: int, workspace_id: int, mp_account_id: int,
                    dt_from: date, dt_to: date, source: str) -> None:
    db = SessionLocal()
    try:
        rep = db.query(FinReport).get(report_id)
        if not rep:
            return
        rep.status = "processing"
        db.commit()

        acc = db.query(MarketplaceAccount).get(mp_account_id)
        if not acc:
            rep.status = "failed"; rep.error = "MarketplaceAccount not found"; db.commit(); return

        weeks_list = week_ranges(dt_from, dt_to)

        try:
            with YaMarketReportsClient(acc.api_token, acc.business_id) as cli:
                totals = {
                    "revenue": 0.0, "commission": 0.0, "logistics": 0.0,
                    "storage": 0.0, "ads": 0.0, "penalties": 0.0,
                    "acquiring": 0.0, "units": 0,
                }
                per_week: dict[tuple[date, date], dict[str, float]] = {
                    w: dict(totals) for w in weeks_list
                }

                if source in ("key_indicators", "mixed"):
                    ki_report_id = cli.generate_key_indicators(dt_from, dt_to)
                    rep.ya_report_id = ki_report_id
                    db.commit()
                    ki_info = cli.wait_for_report(ki_report_id)
                    file_url = ki_info.get("file")
                    if file_url:
                        xlsx = cli.download_report(file_url)
                        parsed = parse_key_indicators_xlsx(xlsx)
                        rep.raw_data = {"key_indicators": parsed}
                        totals.update(parsed.get("totals") or {})
                        rows = parsed.get("_rows") or {}
                        for metric, vals in rows.items():
                            data = vals[1:] if len(vals) > 1 else vals
                            for i, w in enumerate(weeks_list):
                                if i < len(data):
                                    per_week[w][metric] = data[i]

                items_by_sku: dict[str, dict] = {}
                if source in ("realization", "mixed"):
                    rl_report_id = cli.generate_realization(dt_from, dt_to, acc.campaign_id)
                    rep.ya_report_id = rl_report_id
                    db.commit()
                    rl_info = cli.wait_for_report(rl_report_id)
                    file_url = rl_info.get("file")
                    if file_url:
                        xlsx = cli.download_report(file_url)
                        items = parse_realization_xlsx(xlsx)
                        raw = rep.raw_data or {}
                        raw["realization_rows"] = len(items)
                        rep.raw_data = raw
                        for it in items:
                            sku = it["sku"]
                            agg = items_by_sku.setdefault(sku, {
                                "qty": 0, "price_sum": 0.0, "commission": 0.0,
                                "delivery": 0.0, "acquiring": 0.0,
                            })
                            agg["qty"] += int(it.get("qty") or 0)
                            agg["price_sum"] += float(it.get("price") or 0)
                            agg["commission"] += float(it.get("commission") or 0)
                            agg["delivery"] += float(it.get("delivery") or 0)
                            agg["acquiring"] += float(it.get("acquiring") or 0)

        except YaMarketReportError as e:
            rep.status = "failed"; rep.error = str(e); db.commit()
            return
        except Exception as e:
            rep.status = "failed"; rep.error = f"Unexpected: {e}"; db.commit()
            return

        cost_map = _sku_cost_map(db, workspace_id)
        if items_by_sku:
            total_cost = 0.0
            total_units = 0
            for sku, agg in items_by_sku.items():
                q = int(agg.get("qty") or 0)
                total_units += q
                total_cost += q * cost_map.get(sku, 0.0)
            totals["cost_of_sales"] = total_cost
            totals["units"] = total_units
        else:
            if totals.get("units") and cost_map:
                avg_cost = sum(cost_map.values()) / max(1, len(cost_map))
                totals["cost_of_sales"] = avg_cost * totals["units"]

        _upsert_period(db, rep.id, "total", dt_from, dt_to, totals, cost_map, items_by_sku)
        for w in weeks_list:
            wk_totals = per_week.get(w) or {}
            if not any(wk_totals.values()) and weeks_list:
                dw = (w[1] - w[0]).days + 1
                dt_total = (dt_to - dt_from).days + 1
                share = dw / max(1, dt_total)
                wk_totals = {k: (v * share if isinstance(v, (int, float)) else v)
                             for k, v in totals.items()}
            _upsert_period(db, rep.id, "week", w[0], w[1], wk_totals, cost_map, {})

        rep.status = "done"
        rep.completed_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def _upsert_period(db: Session, report_id: int, ptype: str,
                   dt_from: date, dt_to: date,
                   totals: dict, cost_map: dict, items_by_sku: dict) -> None:
    revenue = float(totals.get("revenue") or 0)
    commission = float(totals.get("commission") or 0)
    logistics = float(totals.get("logistics") or 0)
    storage = float(totals.get("storage") or 0)
    ads = float(totals.get("ads") or 0)
    penalties = float(totals.get("penalties") or 0)
    acquiring = float(totals.get("acquiring") or 0)
    units = int(totals.get("units") or 0)
    cost_of_sales = float(totals.get("cost_of_sales") or 0)

    payout = revenue - (commission + logistics + storage + ads + penalties + acquiring)
    profit = payout - cost_of_sales
    margin = (profit / revenue * 100) if revenue > 0 else 0

    p = FinReportPeriod(
        report_id=report_id,
        period_type=ptype,
        period_from=dt_from, period_to=dt_to,
        revenue_gross=revenue, revenue_total=revenue,
        commission=commission,
        delivery_logistics=logistics, logistics_total=logistics,
        storage=storage,
        advertising=ads,
        penalties=penalties,
        acquiring=acquiring,
        payout=payout,
        cost_of_sales=cost_of_sales,
        profit=profit,
        margin_pct=round(margin, 2),
        units_sold=units,
    )
    db.add(p)


@router.post("/generate")
def generate(
    req: GenerateReq,
    bg: BackgroundTasks,
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    if req.date_from > req.date_to:
        raise HTTPException(400, "date_from > date_to")
    acc = _get_account(db, ws.id)

    rep = FinReport(
        workspace_id=ws.id,
        mp_account_id=acc.id,
        marketplace="ya_market",
        period_from=req.date_from,
        period_to=req.date_to,
        source=req.source,
        status="pending",
    )
    db.add(rep); db.commit(); db.refresh(rep)

    bg.add_task(_run_generation, rep.id, ws.id, acc.id,
                req.date_from, req.date_to, req.source)
    return {"report_id": rep.id, "status": rep.status}


@router.get("", response_model=list[ReportResponse])
def list_reports(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
    limit: int = 20,
):
    reps = (
        db.query(FinReport)
        .filter_by(workspace_id=ws.id)
        .order_by(desc(FinReport.created_at))
        .limit(limit)
        .all()
    )
    return reps


@router.get("/latest", response_model=ReportResponse | None)
def latest(
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    rep = (
        db.query(FinReport)
        .filter_by(workspace_id=ws.id, status="done")
        .order_by(desc(FinReport.completed_at))
        .first()
    )
    return rep


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: int,
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    rep = db.query(FinReport).filter_by(workspace_id=ws.id, id=report_id).first()
    if not rep:
        raise HTTPException(404, "Report not found")
    return rep


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(
    report_id: int,
    ws: Workspace = Depends(get_workspace_for_user),
    db: Session = Depends(get_db),
):
    rep = db.query(FinReport).filter_by(workspace_id=ws.id, id=report_id).first()
    if not rep:
        raise HTTPException(404, "Report not found")
    db.delete(rep); db.commit()

