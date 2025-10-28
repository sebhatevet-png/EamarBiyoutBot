# bot.py — Eamar Biyout Store Bot (aiogram v3, Python 3.12)
# يدعم العربية: طلب عرض سعر، أحدث العروض، تتبّع الطلب، واتساب مباشر، الموقع، أوقات العمل، معلومات + زر حاسبة السيراميك

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

if not BOT_TOKEN or "PASTE_YOUR_BOTFATHER_TOKEN_HERE" in BOT_TOKEN:
    raise RuntimeError("الرجاء وضع BOT_TOKEN الصحيح داخل ملف .env")

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

# ========= تهيئة البوت/الـDP =========
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# ⬇️ راوتر الحاسبة أوّلًا + سنستورد دالة الفتح لاستخدامها مع زر الواجهة
from handlers.tile_calculator import router as tile_calc_router, start_calc as tile_start_calc
dp.include_router(tile_calc_router)   # ⬅️ أولاً

# 🔗 راوتر عروض 60×60 (الجديد)
from handlers.offers_60 import router as offers60_router
dp.include_router(offers60_router)    # ⬅️ ثانيًا

# راوترك العام لباقي وظائف المتجر
router = Router()
dp.include_router(router)             # ⬅️ ثالثًا

# ========= لوحات الأزرار =========
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧮 حاسبة السيراميك"), KeyboardButton(text="📰 أحدث العروض")],
        [KeyboardButton(text="📰 أحدث العروض 60×60")],  # زر جديد لعرض الصور المؤرشفة
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

# ========= الأوامر والرسائل =========
@router.message(CommandStart())
async def start_cmd(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer(WELCOME_TEXT, reply_markup=main_kb)

# 🔘 زر الواجهة لفتح الحاسبة مباشرة
@router.message(F.text == "🧮 حاسبة السيراميك")
async def open_calculator_from_home(msg: Message, state: FSMContext):
    await tile_start_calc(msg, state)

@router.message(Command("help"))
async def help_cmd(msg: Message):
    await msg.answer(
        "✨ ماذا أفعل؟\n"
        "• 🧮 حاسبة السيراميك: من زر الواجهة أو الأمر /tile\n"
        "• 🧾 طلب عرض سعر: نموذج سريع.\n"
        "• 📰 أحدث العروض: آخر الخصومات.\n"
        "• 📦 تتبّع الطلب: أدخل رقم الطلب.\n"
        "• 📍 الموقع، 🕘 أوقات العمل، 📞 واتساب مباشر.",
        reply_markup=inline_links()
    )

@router.message(F.text == "ℹ️ معلومات")
@router.message(Command("info"))
async def info_cmd(msg: Message):
    await msg.answer(INFO_TEXT, reply_markup=inline_links())

@router.message(F.text == "🕘 أوقات العمل")
@router.message(Command("hours"))
async def hours_cmd(msg: Message):
    await msg.answer(WORKING_HOURS)

@router.message(F.text == "📍 الموقع")
@router.message(Command("location"))
async def location_cmd(msg: Message):
    await msg.answer(f"الموقع على الخريطة:\n{GOOGLE_MAPS_LINK}", reply_markup=inline_links())

@router.message(F.text == "📞 واتساب مباشر")
@router.message(Command("contact"))
async def contact_cmd(msg: Message):
    await msg.answer(f"تواصل عبر واتساب:\n{WHATSAPP_LINK}", reply_markup=inline_links())

@router.message(F.text == "📰 أحدث العروض")
async def latest_offers(msg: Message):
    body = "📰 <b>أحدث عروضنا:</b>\n• " + "\n• ".join(OFFERS) if OFFERS else "لا توجد عروض حالية."
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

# ========= طلب عرض سعر (حوار تفاعلي) =========
@router.message(F.text == "🧾 طلب عرض سعر")
async def quote_start(msg: Message, state: FSMContext):
    await state.set_state(QuoteForm.product)
    await msg.answer("ما المنتج/المجموعة المطلوبة؟ (مثال: بورسلين 60×60، خلاط مغسلة، كولا بلاط...)")

@router.message(QuoteForm.product)
async def step_product(msg: Message, state: FSMContext):
    await state.update_data(product=msg.text.strip())
    await state.set_state(QuoteForm.area)
    await msg.answer("اذكر المساحة/المكان (مثال: مطبخ 12م²، حمّام 2×2م، صالة 4×5م)...")

@router.message(QuoteForm.area)
async def step_area(msg: Message, state: FSMContext):
    await state.update_data(area=msg.text.strip())
    await state.set_state(QuoteForm.quantity)
    await msg.answer("الكمية التقريبية (متر²/قطعة/طقم)...")

@router.message(QuoteForm.quantity)
async def step_quantity(msg: Message, state: FSMContext):
    await state.update_data(quantity=msg.text.strip())
    await state.set_state(QuoteForm.specs)
    await msg.answer("المواصفات (قياس/لون/ماركة/ملمس)...")

@router.message(QuoteForm.specs)
async def step_specs(msg: Message, state: FSMContext):
    await state.update_data(specs=msg.text.strip())
    await state.set_state(QuoteForm.customer)
    await msg.answer("الاسم الكامل:")

@router.message(QuoteForm.customer)
async def step_customer(msg: Message, state: FSMContext):
    await state.update_data(customer=msg.text.strip())
    await state.set_state(QuoteForm.phone)
    await msg.answer("رقم الهاتف:")

@router.message(QuoteForm.phone)
async def step_phone(msg: Message, state: FSMContext):
    await state.update_data(phone=msg.text.strip())
    await state.set_state(QuoteForm.address)
    await msg.answer("العنوان داخل سبها:")

@router.message(QuoteForm.address)
async def step_address(msg: Message, state: FSMContext):
    await state.update_data(address=msg.text.strip())
    await state.set_state(QuoteForm.notes)
    await msg.answer("ملاحظات إضافية؟ (أرسل '-' إن لم يوجد)")

@router.message(QuoteForm.notes)
async def step_notes(msg: Message, state: FSMContext):
    await state.update_data(notes=msg.text.strip())
    data = await state.get_data()
    await state.clear()

    summary = (
        "✅ <b>تم استلام طلب عرض السعر</b>\n"
        f"• المنتج: {data['product']}\n"
        f"• المساحة/المكان: {data['area']}\n"
        f"• الكمية: {data['quantity']}\n"
        f"• المواصفات: {data['specs']}\n"
        f"• الاسم: {data['customer']}\n"
        f"• الهاتف: {data['phone']}\n"
        f"• العنوان: {data['address']}\n"
        f"• ملاحظات: {data['notes']}\n"
    )
    wa_prefill = make_whatsapp_prefill(data)
    ikb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="إرسال الطلب عبر واتساب", url=wa_prefill)],
        [InlineKeyboardButton(text="واتساب مباشر", url=WHATSAPP_LINK)]
    ])
    await msg.answer(summary, reply_markup=ikb)

    if ADMIN_CHAT_ID and ADMIN_CHAT_ID != "0":
        try:
            await bot.send_message(int(ADMIN_CHAT_ID), f"📥 طلب جديد من @{msg.from_user.username or msg.from_user.id}\n\n{summary}")
        except Exception:
            pass

# ========= fallback يعمل فقط بلا حالة FSM =========
@router.message(StateFilter(None))
async def fallback(msg: Message):
    await msg.answer(
        "مرحبًا! اختر من الأزرار بالأسفل — ولحساب السيراميك اضغط «🧮 حاسبة السيراميك».",
        reply_markup=main_kb
    )

# ========= التشغيل =========
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
