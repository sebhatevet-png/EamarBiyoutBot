# webhook_app.py — FastAPI + Aiogram v3 webhook for Railway
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram.types import Update
from bot import bot, dp  # يستورد bot و dp (لا يشغّل polling)

DOMAIN = os.getenv("WEBHOOK_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN")
if not DOMAIN:
    raise RuntimeError("حدد WEBHOOK_DOMAIN أو اترك Railway يملأ RAILWAY_PUBLIC_DOMAIN تلقائيًا.")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "super-secret")
BASE_URL = f"https://{DOMAIN}".rstrip("/")
WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH

@asynccontextmanager
async def lifespan(app: FastAPI):
    # يضبط عنوان الويب هوك عند تشغيل السيرفر
    await bot.set_webhook(WEBHOOK_URL, drop_pending_updates=True)
    yield
    # عند الإطفاء يلغي الويب هوك (اختياري)
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass

app = FastAPI(title="EamarBiyoutBot Webhook", lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "ok", "webhook": WEBHOOK_URL}

@app.post(WEBHOOK_PATH)
async def telegram_update(request: Request):
    data = await request.json()
    update = Update.model_validate(data)  # Aiogram v3 + Pydantic v2
    await dp.feed_update(bot, update)
    return {"ok": True}
