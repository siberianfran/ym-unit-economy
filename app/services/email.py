"""Отправка email через Resend API."""
from __future__ import annotations
import httpx
from app.config import settings

RESEND_ENDPOINT = "https://api.resend.com/emails"


class EmailError(Exception):
    pass


def _send(to: str, subject: str, html: str) -> None:
    if not settings.resend_api_key:
        raise EmailError("RESEND_API_KEY не настроен")
    with httpx.Client(timeout=15.0) as cli:
        r = cli.post(
            RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {settings.resend_api_key}",
                "Content-Type": "application/json",
            },
            json={"from": settings.email_from, "to": [to], "subject": subject, "html": html},
        )
        if r.status_code >= 400:
            raise EmailError(f"Resend {r.status_code}: {r.text[:300]}")


def send_password_reset(email: str, reset_url: str) -> None:
    subject = "MARJA — восстановление пароля"
    html = (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#0E0B1E">'
        '<div style="text-align:center;margin-bottom:24px">'
        '<div style="display:inline-flex;align-items:center;gap:10px">'
        '<div style="width:40px;height:40px;background:#0E0B1E;color:#fff;border-radius:12px;display:inline-flex;align-items:center;justify-content:center;font-weight:900;font-size:22px">m</div>'
        '<span style="font-size:28px;font-weight:800;letter-spacing:-0.02em">marja</span>'
        '</div></div>'
        '<h1 style="font-size:24px;font-weight:800;margin:0 0 16px">Восстановление пароля</h1>'
        f'<p style="font-size:15px;line-height:1.6;color:#3F3F46;margin:0 0 24px">Кто-то запросил сброс пароля для <b>{email}</b>. Если это был ты — нажми на кнопку ниже. Ссылка действует 60 минут.</p>'
        f'<div style="text-align:center;margin:32px 0"><a href="{reset_url}" style="display:inline-block;background:#8B5CF6;color:#fff;text-decoration:none;padding:14px 28px;border-radius:999px;font-weight:700">Задать новый пароль</a></div>'
        f'<p style="font-size:12px;word-break:break-all;color:#8B5CF6;margin:0 0 16px"><a href="{reset_url}" style="color:#8B5CF6">{reset_url}</a></p>'
        '<hr style="border:none;border-top:1px solid #E4E4E7;margin:20px 0">'
        '<p style="font-size:13px;color:#71717A;margin:0">Если ты не запрашивал восстановление — просто проигнорируй это письмо.</p>'
        '<p style="font-size:12px;color:#A1A1AA;margin:16px 0 0;text-align:center">marja · unit-экономика и финотчёт</p>'
        '</div>'
    )
    _send(email, subject, html)
