# webhook_app.py — FastAPI + Aiogram v3 for Render
# ✅ يعيد استخدام bot و dp (مع كل الأوامر والراوترات) من bot.py

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram.types import Update

# ⚠️ مهم: bot.py يجب ألا يبدأ polling عند مجرد الاستيراد.
# (عندك مضبوط داخل if __name__ == "__main__": asyncio.run(main()))
from bot import bot, dp  # يعيد استخدام جميع الهاندلرز/الراوترات المضافة في bot.py

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "super-secret")

# على Render نقرأ WEBHOOK_DOMAIN (اسم الدومين العام للتطبيق)
DOMAIN = os.getenv("WEBHOOK_DOMAIN")
if not DOMAIN:
    raise RuntimeError("WEBHOOK_DOMAIN غير مضبوط في بيئة Render")

# تنظيف الدومين: إزالة بروتوكول ومنفذ، ثم بناء https://<domain>
DOMAIN = DOMAIN.strip().replace("http://", "").replace("https://", "")
DOMAIN = DOMAIN.split(":")[0]  # منع :10000
BASE_URL = f"https://{DOMAIN}".rstrip("/")

WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ربط الويبهوك (مع حذف القديم)
    try:
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"⚠️ delete_webhook: {e}")
    await bot.set_webhook(WEBHOOK_URL)
    print(f"✅ Webhook set to: {WEBHOOK_URL}")
    yield
    try:
        await bot.delete_webhook(drop_pending_updates=False)
    except Exception:
        pass

app = FastAPI(title="EamarBiyoutBot Webhook", lifespan=lifespan)

@app.get("/")
async def root():
    return {"status": "ok", "webhook": WEBHOOK_URL}

# ✅ هذا هو مسار استقبال التحديثات وتمريرها لنفس dp الخاص بكامل أوامرك
@app.post(WEBHOOK_PATH)
async def telegram_update(request: Request):
    data = await request.json()
    update = Update.model_validate(data)  # Aiogram v3 (Pydantic v2)
    await dp.feed_update(bot, update)
    return {"ok": True}
