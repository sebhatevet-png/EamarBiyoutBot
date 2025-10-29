# bot.py — Eamar Biyout Store Bot (aiogram v3, Python 3.12)
# تشغيل محلي + إشعار للمدير عند بدء التشغيل

import os
import asyncio
import urllib.parse
from datetime import datetime
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.types import (
    Message,
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.client.default import DefaultBotProperties
from dotenv import load_dotenv

# ========= تحميل متغيرات البيئة =========
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN مفقود في ملف .env")

# ========= بيانات المتجر =========
STORE_NAME = "إعمار البيوت للسيراميك والمواد الصحية — سبها"
WHATSAPP_INTL = "218915190151"
WHATSAPP_LINK = f"https://wa.me/{WHATSAPP_INTL}"
GOOGLE_MAPS_LINK = "https://maps.app.goo.gl/44BRQdCMW3S7VcPu8"
FACEBOOK_PAGE = ""
CATALOG_LINK = ""
WORKING_HOURS = (
    "السبت–الخميس:\n"
    "صباحًا 09:00–13:00\n"
    "مساءً 16:00–20:00\n"
    "الجمعة: إجازة"
)
OFFERS = [
    "خصم على باقات الحمّام المتكاملة — استفسر الآن.",
    "أسعار مميزة على بلاط 60×60 (لامع/مطفأ).",
    "خصومات على لواصق البلاط (كولا) للطلبات بالجملة."
]
ORDERS = {
    "EB-2510-001": {"status": "قيد التجهيز", "eta": "خلال 48 ساعة", "note": "بانتظار تأكيد القياسات."},
    "EB-2510-002": {"status": "تم التسليم", "eta": "-", "note": "سُلّم يوم 24/10/2025."},
}

# ========= تهيئة البوت والـ Dispatcher =========
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# استيراد الراوترات
from handlers.tile_calculator import router as tile_calc_router, start_calc as tile_start_calc
dp.include_router(tile_calc_router)
from handlers.offers_60 import router as offers60_router
dp.include_router(offers60_router)
router = Router()
dp.include_router(router)

# ========= لوحات الأزرار =========
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧮 حاسبة السيراميك"), KeyboardButton(text="📰 أحدث العروض")],
        [KeyboardButton(text="📰 أحدث العروض 60×60")],
        [KeyboardButton(text="🧾 طلب عرض سعر"), KeyboardButton(text="📦 تتبّع الطلب")],
        [KeyboardButton(text="📍 الموقع"), KeyboardButton(text="🕘 أوقات العمل")],
        [KeyboardButton(text="📞 واتساب مباشر"), KeyboardButton(text="ℹ️ معلومات")],
    ],
    resize_keyboard=True
)

def inline_links():
    kb = InlineKeyboardBuilder()
    kb.button(text="راسلنا واتساب", url=WHATSAPP_LINK)
    if GOOGLE_MAPS_LINK:
        kb.button(text="الموقع على الخريطة", url=GOOGLE_MAPS_LINK)
    if CATALOG_LINK:
        kb.button(text="قائمة المنتجات", url=CATALOG_LINK)
    if FACEBOOK_PAGE:
        kb.button(text="صفحتنا على فيسبوك", url=FACEBOOK_PAGE)
    kb.adjust(1)
    return kb.as_markup()

WELCOME_TEXT = (
    f"مرحبًا بك في <b>{STORE_NAME}</b> 👋\n"
    "اختر من الأزرار بالأسفل لحاسبة السيراميك، طلب عرض سعر، العروض، التتبّع، أو تواصل فوري عبر واتساب."
)
INFO_TEXT = (
    f"<b>{STORE_NAME}</b>\n"
    "متخصصون في السيراميك والبورسلين والمواد الصحية ولواصق البلاط.\n"
    "نوفر الاستشارة والقياس والتوصيل داخل سبها. لسرعة الرد اضغط «واتساب مباشر»."
)

# ========= نموذج طلب عرض سعر (FSM) =========
class QuoteForm(StatesGroup):
    product = State()
    area = State()
    quantity = State()
    specs = State()
    customer = State()
    phone = State()
    address = State()
    notes = State()

def make_whatsapp_prefill(data: dict) -> str:
    lines = [
        f"طلب عرض سعر — {STORE_NAME}",
        f"• المنتج/المجموعة: {data.get('product','-')}",
        f"• المساحة/المكان: {data.get('area','-')}",
        f"• الكمية التقريبية: {data.get('quantity','-')}",
        f"• المواصفات (قياس/لون/ماركة): {data.get('specs','-')}",
        f"• الاسم: {data.get('customer','-')}",
        f"• الهاتف: {data.get('phone','-')}",
        f"• العنوان (داخل سبها): {data.get('address','-')}",
        f"• ملاحظات: {data.get('notes','-')}",
        f"• التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    ]
    return f"https://wa.me/{WHATSAPP_INTL}?text=" + urllib.parse.quote("\n".join(lines))

# ========= أوامر و ردود =========
@router.message(CommandStart())
async def start_cmd(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(WELCOME_TEXT, reply_markup=main_kb)

@router.message(F.text == "🧮 حاسبة السيراميك")
async def open_calculator_from_home(msg: Message, state: FSMContext):
    await tile_start_calc(msg, state)

@router.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer(
        "✨ ماذا أفعل؟\n"
        "• 🧮 حاسبة السيراميك: من زر الواجهة أو /tile\n"
        "• 🧾 طلب عرض سعر: نموذج سريع.\n"
        "• 📰 أحدث العروض: آخر الخصومات.\n"
        "• 📦 تتبّع الطلب: أدخل رقم الطلب.\n"
        "• 📍 الموقع، 🕘 أوقات العمل، 📞 واتساب مباشر.",
        reply_markup=inline_links()
    )

@router.message(F.text == "ℹ️ معلومات")
async def info_cmd(msg: Message):
    await msg.answer(INFO_TEXT, reply_markup=inline_links())

@router.message(F.text == "🕘 أوقات العمل")
async def hours_cmd(msg: Message):
    await msg.answer(WORKING_HOURS)

@router.message(F.text == "📍 الموقع")
async def location_cmd(msg: Message):
    await msg.answer(f"الموقع على الخريطة:\n{GOOGLE_MAPS_LINK}", reply_markup=inline_links())

@router.message(F.text == "📞 واتساب مباشر")
async def contact_cmd(msg: Message):
    await msg.answer(f"تواصل عبر واتساب:\n{WHATSAPP_LINK}", reply_markup=inline_links())

@router.message(F.text == "📰 أحدث العروض")
async def latest_offers(msg: Message):
    body = "📰 <b>أحدث عروضنا:</b>\n• " + "\n• ".join(OFFERS)
    await msg.answer(body, reply_markup=inline_links())

# ========= تتبّع الطلب =========
class TrackForm(StatesGroup):
    code = State()

@router.message(F.text == "📦 تتبّع الطلب")
async def ask_order_code(msg: Message, state: FSMContext):
    await state.set_state(TrackForm.code)
    await msg.answer("أرسل رقم الطلب بصيغة: <code>EB-YYMM-###</code>\nمثال: <code>EB-2510-001</code>")

@router.message(TrackForm.code)
async def track_order(msg: Message, state: FSMContext):
    code = msg.text.strip()
    order = ORDERS.get(code)
    if order:
        reply = (
            f"نتيجة التتبع <b>{code}</b>:\n"
            f"• الحالة: {order['status']}\n"
            f"• الزمن المتوقع: {order['eta']}\n"
            f"• ملاحظة: {order['note']}"
        )
    else:
        reply = "عذرًا، لم نعثر على هذا الرقم.\nتواصل عبر واتساب مع ذكر الاسم ورقم الطلب:\n" + WHATSAPP_LINK
    await state.clear()
    await msg.answer(reply, reply_markup=inline_links())

# ========= إشعار المدير عند بدء التشغيل =========
async def notify_admin():
    try:
        msg = f"✅ تم تشغيل بوت إعمار البيوت بنجاح 💻\n📅 في: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        await bot.send_message(ADMIN_CHAT_ID, msg)
        print("📨 تم إرسال إشعار البدء إلى المدير.")
    except Exception as e:
        print(f"⚠️ فشل إرسال الإشعار: {e}")

# ========= التشغيل =========
async def main():
    print("✅ البوت بدأ التشغيل... الرجاء الانتظار")
    await notify_admin()
    await dp.start_polling(bot)
    print("✅ Bot started and ready!")

if __name__ == "__main__":
    asyncio.run(main())
