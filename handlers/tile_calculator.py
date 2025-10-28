# handlers/tile_calculator.py
"""
Tile Calculator + Arabic PDF + Logo (Aiogram v3)
- Main menu: Kitchen/Bath/Floors/Flat
- Dual input modes (dimensions OR direct areas)
- Fixed prices: wall=29, floor=29 (per m²), decor=20, strip=10 (per unit)
- Arabic-shaped PDF with Amiri font + optional logo
"""

from __future__ import annotations
import os
import io
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from aiogram import Router, F
from aiogram.types import (
    Message, CallbackQuery,
    ReplyKeyboardRemove, BufferedInputFile,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

# ---- PDF / Arabic shaping ----
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Optional Arabic shaping
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    _ARABIC_OK = True
except Exception:
    _ARABIC_OK = False

router = Router(name="tile_calculator_pdf")

# ---------- Pricing Constants ----------
PRICE_WALL_PER_M2 = 29.0
PRICE_FLOOR_PER_M2 = 29.0
PRICE_DECOR_PER_UNIT = 20.0
PRICE_STRIP_PER_UNIT = 10.0

DEFAULT_HEIGHT_M = 3.2  # for kitchen/bath when using dimensions or area (default)

# ---------- Helpers ----------
def ceildiv(a: float, b: float) -> int:
    return math.ceil(a / b)

def safe_float(text: str) -> Optional[float]:
    try:
        return float(str(text).replace(",", ".").strip())
    except Exception:
        return None

def ar(s: str) -> str:
    if not isinstance(s, str):
        s = str(s)
    if _ARABIC_OK:
        try:
            reshaped = arabic_reshaper.reshape(s)
            return get_display(reshaped)
        except Exception:
            return s
    return s

# ---------- Data Models ----------
@dataclass
class Line:
    label: str
    unit: str
    qty: float
    price: float
    @property
    def total(self) -> float:
        return round(self.qty * self.price, 2)

@dataclass
class SpaceInvoice:
    name: str
    category: str  # kitchen|bath|floor|flat
    perimeter_m: float = 0.0
    height_m: float = DEFAULT_HEIGHT_M
    wall_area_m2: float = 0.0
    floor_area_m2: float = 0.0
    lines: List[Line] = field(default_factory=list)
    def compute_totals(self) -> float:
        return round(sum(l.total for l in self.lines), 2)

# ---------- FSM ----------
class TileFlow(StatesGroup):
    choosing_category = State()
    choosing_mode = State()

    # Kitchen/Bath (dimensions)
    kb_length = State()
    kb_width = State()
    kb_height_edit = State()

    # Kitchen/Bath (direct areas)
    kb_wall_area = State()
    kb_floor_area = State()
    kb_height_edit_area = State()

    # Floors/Flat (dual modes)
    ff_mode = State()
    ff_length = State()
    ff_width = State()
    ff_area = State()

    after_space_summary = State()

# ---------- Keyboards ----------
def main_menu_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="🛁 حمام", callback_data="cat:bath")
    kb.button(text="🍳 مطبخ", callback_data="cat:kitchen")
    kb.button(text="🏠 أرضيات فقط", callback_data="cat:floor")
    kb.button(text="🧱 مساحات مسطّحة", callback_data="cat:flat")
    kb.adjust(2, 2)
    return kb

def input_mode_kb(kb_kind: str) -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="📏 إدخال الأبعاد (ط × ع)", callback_data=f"mode:{kb_kind}:dim")
    kb.button(text="🔢 إدخال المساحة مباشرة", callback_data=f"mode:{kb_kind}:area")
    kb.adjust(1, 1)
    return kb

def after_space_actions_kb(kind: str) -> InlineKeyboardBuilder:
    # يظهر بعد كل حساب مساحة: إضافة/نوع آخر/طباعة PDF/القائمة الرئيسية
    label_map = {"kitchen": "مطبخ", "bath": "حمّام", "floor": "أرضية", "flat": "مساحة مسطّحة"}
    kb = InlineKeyboardBuilder()
    kb.button(text=f"➕ إضافة {label_map.get(kind, 'مساحة')} أخرى", callback_data=f"add_more:{kind}")
    kb.button(text="➕ إضافة نوع آخر", callback_data="add_other")
    kb.button(text="🧾 عرض / حفظ PDF إجمالي", callback_data="export_pdf")
    kb.button(text="🏠 القائمة الرئيسية", callback_data="go_main")
    kb.adjust(1, 1, 1, 1)
    return kb

def edit_height_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔧 تعديل الارتفاع", callback_data="edit_height")
    kb.button(text="متابعة", callback_data="skip_height")
    kb.adjust(2)
    return kb

def restart_kb() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔁 بدء جديد (حاسبة)", callback_data="restart_calc")
    kb.button(text="🏠 القائمة الرئيسية", callback_data="go_main")
    kb.button(text="➕ إضافة نوع آخر", callback_data="add_other")
    kb.adjust(1, 1, 1)
    return kb

def main_reply_kb() -> ReplyKeyboardMarkup:
    # لوحة القائمة الرئيسية (مستقلة عن bot.py)
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🧾 طلب عرض سعر"), KeyboardButton(text="📰 أحدث العروض")],
            [KeyboardButton(text="📦 تتبّع الطلب"), KeyboardButton(text="📍 الموقع")],
            [KeyboardButton(text="🕘 أوقات العمل"), KeyboardButton(text="📞 واتساب مباشر")],
            [KeyboardButton(text="ℹ️ معلومات"), KeyboardButton(text="🧮 حاسبة السيراميك")]
        ],
        resize_keyboard=True
    )

# ---------- Session ----------
SESSION_KEY = "tile_session"

@dataclass
class SessionData:
    counters: Dict[str, int] = field(default_factory=lambda: {"kitchen":0, "bath":0, "floor":0, "flat":0})
    spaces: List[SpaceInvoice] = field(default_factory=list)

async def get_session(state: FSMContext) -> SessionData:
    data = await state.get_data()
    s: SessionData = data.get(SESSION_KEY)
    if not s:
        s = SessionData()
        await state.update_data(**{SESSION_KEY: s})
    return s

async def push_space(state: FSMContext, space: SpaceInvoice):
    s = await get_session(state)
    s.spaces.append(space)
    await state.update_data(**{SESSION_KEY: s})

# ---------- Entry ----------
@router.message(Command("tile"))
async def start_calc(m: Message, state: FSMContext):
    await state.set_state(TileFlow.choosing_category)
    await m.answer("📊 حاسبة السيراميك — اختر النوع:", reply_markup=ReplyKeyboardRemove())
    await m.answer("اختر من القائمة:", reply_markup=main_menu_kb().as_markup())

# ---------- Category selection ----------
@router.callback_query(F.data.startswith("cat:"))
async def on_category(cq: CallbackQuery, state: FSMContext):
    kind = cq.data.split(":", 1)[1]
    await state.update_data(current_kind=kind)
    await cq.message.answer("اختر طريقة الإدخال:", reply_markup=input_mode_kb(kind).as_markup())
    await cq.answer()

# ---------- Mode selection ----------
@router.callback_query(F.data.startswith("mode:"))
async def on_mode(cq: CallbackQuery, state: FSMContext):
    _, kind, mode = cq.data.split(":")
    await state.update_data(current_kind=kind, current_mode=mode)

    if kind in {"kitchen", "bath"}:
        if mode == "dim":
            await state.set_state(TileFlow.kb_length)
            await cq.message.answer("أدخل الطول بالمتر:")
        else:
            await state.set_state(TileFlow.kb_wall_area)
            await cq.message.answer("أدخل مساحة الحائط (م²):")
    else:
        if mode == "dim":
            await state.set_state(TileFlow.ff_length)
            await cq.message.answer("أدخل الطول بالمتر:")
        else:
            await state.set_state(TileFlow.ff_area)
            await cq.message.answer("أدخل المساحة الإجمالية (م²):")
    await cq.answer()

# ---------- Kitchen/Bath (dimensions) ----------
@router.message(TileFlow.kb_length)
async def kb_length(m: Message, state: FSMContext):
    val = safe_float(m.text)
    if not val or val <= 0:
        return await m.answer("أدخل رقمًا صحيحًا بالمتر.")
    await state.update_data(kb_length=val)
    await state.set_state(TileFlow.kb_width)
    await m.answer("أدخل العرض بالمتر:")

@router.message(TileFlow.kb_width)
async def kb_width(m: Message, state: FSMContext):
    val = safe_float(m.text)
    if not val or val <= 0:
        return await m.answer("أدخل رقمًا صحيحًا بالمتر.")
    await state.update_data(kb_width=val, kb_height=DEFAULT_HEIGHT_M)

    await m.answer(f"سيتم الحساب بارتفاع قياسي: {DEFAULT_HEIGHT_M} م")
    await state.set_state(TileFlow.kb_height_edit)
    await m.answer("هل تريد تعديل الارتفاع أم المتابعة؟", reply_markup=edit_height_kb().as_markup())

@router.callback_query(F.data == "edit_height")
async def cb_edit_height(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kind = data.get("current_kind")
    mode = data.get("current_mode")
    if kind in {"kitchen", "bath"} and mode == "area" and "kb_wall_area_val" in data:
        await state.set_state(TileFlow.kb_height_edit_area)
        await cq.message.answer("أدخل الارتفاع المطلوب بالمتر (مثال 2.8):")
    else:
        await cq.message.answer("أدخل الارتفاع المطلوب بالمتر (مثال 2.8):")
    await cq.answer()

@router.callback_query(F.data == "skip_height")
async def cb_skip_height(cq: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    kind = data.get("current_kind")
    mode = data.get("current_mode")
    if kind in {"kitchen", "bath"} and mode == "area" and "kb_wall_area_val" in data:
        wall_area = float(data.get("kb_wall_area_val", 0.0))
        floor_area = float(data.get("kb_floor_area_val", 0.0))
        H = float(data.get("kb_height", DEFAULT_HEIGHT_M))
        await finalize_kb_area(cq.message, state, wall_area, floor_area, H)
    else:
        L = float(data.get("kb_length"))
        W = float(data.get("kb_width"))
        H = float(data.get("kb_height", DEFAULT_HEIGHT_M))
        await finalize_kb_dim(cq.message, state, L, W, H)
    await cq.answer()

@router.message(TileFlow.kb_height_edit)
async def kb_height_value_dims(m: Message, state: FSMContext):
    val = safe_float(m.text)
    data = await state.get_data()
    if val and val > 0:
        await state.update_data(kb_height=val)
        await m.answer(f"تم ضبط الارتفاع على {val} م.")
    L = float(data.get("kb_length"))
    W = float(data.get("kb_width"))
    H = float(data.get("kb_height", DEFAULT_HEIGHT_M))
    await finalize_kb_dim(m, state, L, W, H)

# ---------- Kitchen/Bath (direct areas) ----------
@router.message(TileFlow.kb_wall_area)
async def kb_wall_area(m: Message, state: FSMContext):
    val = safe_float(m.text)
    if val is None or val <= 0:
        return await m.answer("أدخل مساحة صحيحة (م²).")
    await state.update_data(kb_wall_area_val=val)
    await state.set_state(TileFlow.kb_floor_area)
    await m.answer("أدخل مساحة الأرضية (م²):")

@router.message(TileFlow.kb_floor_area)
async def kb_floor_area(m: Message, state: FSMContext):
    val = safe_float(m.text)
    if val is None or val < 0:
        return await m.answer("أدخل مساحة صحيحة (م²).")
    await state.update_data(kb_floor_area_val=val, kb_height=DEFAULT_HEIGHT_M)
    data = await state.get_data()
    wall_area = float(data.get("kb_wall_area_val", 0.0))
    H = float(data.get("kb_height", DEFAULT_HEIGHT_M))
    perimeter_std = round((wall_area / H) if H > 0 else 0.0, 2)

    await m.answer(
        f"سيتم حساب المحيط تلقائيًا من مساحة الحائط ÷ الارتفاع القياسي {H}م.\n"
        f"المحيط المبدئي = {perimeter_std} متر.\n"
        "هل تريد المتابعة أم تعديل الارتفاع؟",
        reply_markup=edit_height_kb().as_markup()
    )
    await state.set_state(TileFlow.kb_height_edit_area)

@router.message(TileFlow.kb_height_edit_area)
async def kb_height_value_area(m: Message, state: FSMContext):
    val = safe_float(m.text)
    data = await state.get_data()
    wall_area = float(data.get("kb_wall_area_val", 0.0))
    floor_area = float(data.get("kb_floor_area_val", 0.0))
    H = float(data.get("kb_height", DEFAULT_HEIGHT_M))

    if val and val > 0:
        H = val
        await state.update_data(kb_height=H)
        await m.answer(f"تم ضبط الارتفاع على {H} م.")

    await finalize_kb_area(m, state, wall_area, floor_area, H)

async def finalize_kb_dim(m: Message, state: FSMContext, L: float, W: float, H: float):
    perimeter = 2 * (L + W)
    wall_area = perimeter * H
    floor_area = L * W

    data = await state.get_data()
    s = await get_session(state)
    kind = data.get("current_kind")
    s.counters[kind] += 1
    idx = s.counters[kind]
    name = ("مطبخ " if kind == "kitchen" else "حمّام ") + str(idx)

    decor_units = ceildiv(perimeter, 0.6)
    strip_units = decor_units * 2

    space = SpaceInvoice(
        name=name, category=kind,
        perimeter_m=round(perimeter, 2), height_m=H,
        wall_area_m2=round(wall_area, 2), floor_area_m2=round(floor_area, 2)
    )
    space.lines.extend([
        Line("حائط", "م²", qty=round(wall_area, 2), price=PRICE_WALL_PER_M2),
        Line("أرضية", "م²", qty=round(floor_area, 2), price=PRICE_FLOOR_PER_M2),
        Line("ديكورات", "قطعة", qty=float(decor_units), price=PRICE_DECOR_PER_UNIT),
        Line("استريشات", "قطعة", qty=float(strip_units), price=PRICE_STRIP_PER_UNIT),
    ])

    await push_space(state, space)
    await show_space_summary(m, state, space)
    await state.set_state(TileFlow.after_space_summary)

async def finalize_kb_area(m: Message, state: FSMContext, wall_area: float, floor_area: float, H: float):
    perimeter = (wall_area / H) if H and H > 0 else 0.0

    data = await state.get_data()
    s = await get_session(state)
    kind = data.get("current_kind")
    s.counters[kind] += 1
    idx = s.counters[kind]
    name = ("مطبخ " if kind == "kitchen" else "حمّام ") + str(idx)

    decor_units = ceildiv(perimeter, 0.6)
    strip_units = decor_units * 2

    space = SpaceInvoice(
        name=name, category=kind,
        perimeter_m=round(perimeter, 2), height_m=H,
        wall_area_m2=round(wall_area, 2), floor_area_m2=round(floor_area, 2)
    )
    space.lines.extend([
        Line("حائط", "م²", qty=round(wall_area, 2), price=PRICE_WALL_PER_M2),
        Line("أرضية", "م²", qty=round(floor_area, 2), price=PRICE_FLOOR_PER_M2),
        Line("ديكورات", "قطعة", qty=float(decor_units), price=PRICE_DECOR_PER_UNIT),
        Line("استريشات", "قطعة", qty=float(strip_units), price=PRICE_STRIP_PER_UNIT),
    ])

    await push_space(state, space)
    await show_space_summary(m, state, space)
    await state.set_state(TileFlow.after_space_summary)

# ---------- Floors / Flat ----------
@router.message(TileFlow.ff_length)
async def ff_length(m: Message, state: FSMContext):
    val = safe_float(m.text)
    if not val or val <= 0:
        return await m.answer("أدخل رقمًا صحيحًا بالمتر.")
    await state.update_data(ff_length=val)
    await state.set_state(TileFlow.ff_width)
    await m.answer("أدخل العرض بالمتر:")

@router.message(TileFlow.ff_width)
async def ff_width(m: Message, state: FSMContext):
    val = safe_float(m.text)
    if not val or val <= 0:
        return await m.answer("أدخل رقمًا صحيحًا بالمتر.")
    data = await state.get_data()
    L = float(data.get("ff_length"))
    area = L * float(val)
    await finalize_ff_space(m, state, area)

@router.message(TileFlow.ff_area)
async def ff_area(m: Message, state: FSMContext):
    val = safe_float(m.text)
    if val is None or val < 0:
        return await m.answer("أدخل مساحة صحيحة (م²).")
    await finalize_ff_space(m, state, val)

async def finalize_ff_space(m: Message, state: FSMContext, area: float):
    data = await state.get_data()
    kind = data.get("current_kind")

    s = await get_session(state)
    s.counters[kind] += 1
    idx = s.counters[kind]
    base = "أرضية " if kind == "floor" else "مساحة مسطّحة "
    name = base + str(idx)

    space = SpaceInvoice(name=name, category=kind, wall_area_m2=0.0, floor_area_m2=round(area, 2))
    space.lines.append(Line("صنف 1", "م²", qty=round(area, 2), price=PRICE_FLOOR_PER_M2))

    await push_space(state, space)
    await show_space_summary(m, state, space)
    await state.set_state(TileFlow.after_space_summary)

# ---------- After-space summary & actions ----------
async def show_space_summary(m: Message, state: FSMContext, space: SpaceInvoice):
    lines = [f"{space.name}"]
    if space.category in {"kitchen", "bath"}:
        lines.append(f"• المحيط: {space.perimeter_m} م | الارتفاع: {space.height_m} م")
        lines.append(f"• الحائط: {space.wall_area_m2} م² | الأرضية: {space.floor_area_m2} م²")
    total = space.compute_totals()
    lines.append("")
    for ln in space.lines:
        lines.append(f"- {ln.label}: {ln.qty} {ln.unit} × {ln.price} = {ln.total}")
    lines.append("—" * 20)
    lines.append(f"إجمالي {space.name}: {total} د.ل")

    data = await state.get_data()
    kind = data.get("current_kind")
    # هنا الأزرار صار فيها زر القائمة الرئيسية أيضًا
    await m.answer("\n".join(lines), reply_markup=after_space_actions_kb(kind).as_markup())

@router.callback_query(F.data.startswith("add_more:"))
async def add_more_same_kind(cq: CallbackQuery, state: FSMContext):
    kind = cq.data.split(":", 1)[1]
    await state.update_data(current_kind=kind)
    await cq.message.answer("اختر طريقة الإدخال:", reply_markup=input_mode_kb(kind).as_markup())
    await cq.answer()

@router.callback_query(F.data == "add_other")
async def add_other_kind(cq: CallbackQuery, state: FSMContext):
    await state.set_state(TileFlow.choosing_category)
    await cq.message.answer("اختر نوعًا جديدًا:", reply_markup=main_menu_kb().as_markup())
    await cq.answer()

# ---------- Export PDF ----------
@router.callback_query(F.data == "export_pdf")
async def export_pdf(cq: CallbackQuery, state: FSMContext):
    s = await get_session(state)
    if not s.spaces:
        await cq.message.answer("لا توجد بيانات بعد.")
        return await cq.answer()

    pdf_bytes = build_pdf(s.spaces)
    file_name = "فاتورة_السيراميك.pdf"
    doc = BufferedInputFile(pdf_bytes, filename=file_name)
    await cq.message.answer_document(doc)

    # اخرج من الحالة
    await state.clear()

    # أزرار مختصرة بعد الطباعة
    await cq.message.answer(
        "تم إنشاء الفاتورة ✅\nهل ترغب بالبدء من جديد أو العودة للقائمة الرئيسية؟",
        reply_markup=restart_kb().as_markup()
    )
    await cq.answer()

@router.callback_query(F.data == "restart_calc")
async def restart_calc(cq: CallbackQuery, state: FSMContext):
    await state.update_data(**{SESSION_KEY: SessionData()})
    await state.set_state(TileFlow.choosing_category)
    await cq.message.answer("📊 حاسبة السيراميك — اختر النوع:", reply_markup=ReplyKeyboardRemove())
    await cq.message.answer("اختر من القائمة:", reply_markup=main_menu_kb().as_markup())
    await cq.answer()

@router.callback_query(F.data == "go_main")
async def go_main(cq: CallbackQuery, state: FSMContext):
    await state.clear()
    await cq.message.answer("تمت العودة إلى القائمة الرئيسية ✅", reply_markup=main_reply_kb())
    await cq.answer()

# ---------- PDF Builder ----------
def register_arabic_font() -> str:
    font_path = os.path.join("fonts", "Amiri-Regular.ttf")
    if os.path.exists(font_path):
        try:
            pdfmetrics.registerFont(TTFont("Amiri", font_path))
            return "Amiri"
        except Exception:
            pass
    return "Helvetica"

def draw_logo(c: canvas.Canvas, W: float, H: float, margin: float):
    logo_path = os.path.join("assets", "logo.png")
    if os.path.exists(logo_path):
        try:
            c.drawImage(logo_path, margin, H - margin - 1.5*cm, width=3.0*cm, height=1.5*cm,
                        preserveAspectRatio=True, mask='auto')
        except Exception:
            pass

def build_pdf(spaces: List[SpaceInvoice]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    W, H = A4

    font_name = register_arabic_font()
    margin = 1.5 * cm
    y = H - margin

    c.setTitle("فاتورة السيراميك")

    def header():
        nonlocal y
        c.setFont(font_name, 16)
        c.setFillColor(colors.black)
        c.drawRightString(W - margin, y, ar("فاتورة السيراميك — إعمار البيوت"))
        draw_logo(c, W, H, margin)
        y -= 0.8 * cm
        c.setLineWidth(1)
        c.line(margin, y, W - margin, y)
        y -= 0.5 * cm

    def draw_space(space: SpaceInvoice):
        nonlocal y
        if y < 5 * cm:
            c.showPage()
            y = H - margin
            header()
        c.setFont(font_name, 13)
        c.drawRightString(W - margin, y, ar(space.name))
        y -= 0.5 * cm
        c.setFont(font_name, 10)
        if space.category in {"kitchen", "bath"}:
            c.drawRightString(W - margin, y, ar(f"المحيط: {space.perimeter_m} م | الارتفاع: {space.height_m} م"))
            y -= 0.4 * cm
            c.drawRightString(W - margin, y, ar(f"الحائط: {space.wall_area_m2} م² | الأرضية: {space.floor_area_m2} م²"))
            y -= 0.5 * cm

        # table header
        c.setFont(font_name, 10)
        c.drawRightString(W - margin, y, ar("الإجمالي"))
        c.drawRightString(W - margin - 3.0*cm, y, ar("السعر"))
        c.drawRightString(W - margin - 5.5*cm, y, ar("الكمية"))
        c.drawRightString(W - margin - 8.5*cm, y, ar("الوحدة"))
        c.drawRightString(W - margin - 10.5*cm, y, ar("البند"))
        y -= 0.35 * cm
        c.setLineWidth(0.5)
        c.line(margin, y, W - margin, y)
        y -= 0.3 * cm

        for ln in space.lines:
            if y < 3 * cm:
                c.showPage()
                y = H - margin
                header()
                c.setFont(font_name, 10)
                c.drawRightString(W - margin, y, ar("الإجمالي"))
                c.drawRightString(W - margin - 3.0*cm, y, ar("السعر"))
                c.drawRightString(W - margin - 5.5*cm, y, ar("الكمية"))
                c.drawRightString(W - margin - 8.5*cm, y, ar("الوحدة"))
                c.drawRightString(W - margin - 10.5*cm, y, ar("البند"))
                y -= 0.35 * cm
                c.setLineWidth(0.5)
                c.line(margin, y, W - margin, y)
                y -= 0.3 * cm

            c.setFont(font_name, 10)
            c.drawRightString(W - margin, y, f"{ln.total:.2f}")
            c.drawRightString(W - margin - 3.0*cm, y, f"{ln.price:.2f}")
            c.drawRightString(W - margin - 5.5*cm, y, f"{ln.qty}")
            c.drawRightString(W - margin - 8.5*cm, y, ar(ln.unit))
            c.drawRightString(W - margin - 10.5*cm, y, ar(ln.label))
            y -= 0.32 * cm

        c.setLineWidth(0.5)
        c.line(margin, y, W - margin, y)
        y -= 0.3 * cm
        c.setFont(font_name, 11)
        c.drawRightString(W - margin, y, ar(f"إجمالي {space.name}: {space.compute_totals():.2f} د.ل"))
        y -= 0.6 * cm

    def footer(grand_total: float):
        nonlocal y
        if y < 3.0 * cm:
            c.showPage()
            y = H - margin
            header()
        c.setLineWidth(1)
        c.line(margin, y, W - margin, y)
        y -= 0.5 * cm
        c.setFont(font_name, 14)
        c.setFillColor(colors.darkblue)
        c.drawRightString(W - margin, y, ar(f"الإجمالي الكلي: {grand_total:.2f} د.ل"))
        c.setFillColor(colors.black)
        y -= 0.8 * cm
        c.setFont(font_name, 9)
        c.drawRightString(W - margin, y, ar("شكراً لاختياركم إعمار البيوت للسيراميك والمواد الصحية — سبها"))
        y -= 0.3 * cm
        c.drawRightString(W - margin, y, ar("واتساب: +218928220151"))

    header()
    grand = 0.0
    for sp in spaces:
        draw_space(sp)
        grand += sp.compute_totals()
    footer(grand)

    c.save()
    buf.seek(0)
    return buf.read()
