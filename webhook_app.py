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
import os
from fastapi import FastAPI
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "super-secret")
DOMAIN = os.getenv("WEBHOOK_DOMAIN") or os.getenv("RAILWAY_PUBLIC_DOMAIN")

if not DOMAIN:
    raise RuntimeError("لم يتم تحديد WEBHOOK_DOMAIN أو RAILWAY_PUBLIC_DOMAIN")

# إزالة البروتوكول الزائد والمنفذ (في حال وجودهما)
DOMAIN = DOMAIN.strip().replace("http://", "").replace("https://", "")
DOMAIN = DOMAIN.split(":")[0]  # إزالة أي منفذ مثل :10000
BASE_URL = f"https://{DOMAIN}"

WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = f"{BASE_URL}{WEBHOOK_PATH}"

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

app = FastAPI()


@app.on_event("startup")
async def on_startup():
    await bot.delete_webhook(drop_pending_updates=True)
    await bot.set_webhook(url=WEBHOOK_URL)
    print(f"✅ Webhook set: {WEBHOOK_URL}")

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
