# webhook_app.py — FastAPI + Aiogram v3 on Render
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher
from aiogram.types import Update
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# --- بيئة التشغيل ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN مفقود")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "super-secret")

# على Render نستخدم WEBHOOK_DOMAIN (أو اسم المجال العام)
DOMAIN = os.getenv("WEBHOOK_DOMAIN")
if not DOMAIN:
    raise RuntimeError("WEBHOOK_DOMAIN غير مضبوط")

# طبيعته قد تكون مع https أو بدون؛ ننظّفها ونمنع المنفذ
DOMAIN = DOMAIN.strip().replace("http://", "").replace("https://", "")
DOMAIN = DOMAIN.split(":")[0]  # منع :10000
BASE_URL = f"https://{DOMAIN}".rstrip("/")

WEBHOOK_PATH = f"/webhook/{WEBHOOK_SECRET}"
WEBHOOK_URL = BASE_URL + WEBHOOK_PATH

# --- كائنات Aiogram المعاد استخدامها من هنا مباشرة ---
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# استورد راوتراتك من bot.py إن رغبت، أو اترك bot.py يديرها محليًا فقط.
# إن كان bot.py يضم الراوترات، يمكنك أيضاً استيرادها هنا:
try:
    from handlers import tile_calculator, offers_60
    dp.include_router(tile_calculator.router)
    dp.include_router(offers_60.router)
except Exception as e:
    print(f"⚠️ لم أضمّن الراوترات من handlers: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # حذف أي ويبهوك قديم ثم تعيين الجديد
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

# نقطة فحص بسيطة
@app.get("/")
async def root():
    return {"status": "ok", "webhook": WEBHOOK_URL}

# ✅ هذا هو المسار الذي كان ناقصًا — يستقبل تحديثات تيليجرام ويمررها للـ Dispatcher
@app.post(WEBHOOK_PATH)
async def telegram_update(request: Request):
    data = await request.json()
    update = Update.model_validate(data)  # Aiogram v3 + Pydantic v2
    await dp.feed_update(bot, update)
    return {"ok": True}
