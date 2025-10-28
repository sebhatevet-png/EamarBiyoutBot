# handlers/offers_60.py
# عروض صور 60×60 — أرشفة (رفع مرة واحدة) + عرض مع أزرار تنقّل
import os, json, asyncio
from typing import Dict, List, Tuple

from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    FSInputFile, InputMediaPhoto
)

router = Router(name="offers_60_router")

# ===== إعدادات عامة =====
IMAGES_DIR = "images/60x60"
OFFERS_JSON = "offers_60x60.json"
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")  # تأكد من ضبطه في .env

# ===== دوال مساعدة =====
def save_map(d: Dict[str, str]) -> None:
    """حفظ قائمة الصور المؤرشفة (رقم العرض → file_id)."""
    with open(OFFERS_JSON, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

def load_items() -> List[Tuple[str, str]]:
    """تحميل قائمة الصور المؤرشفة من ملف JSON."""
    if os.path.exists(OFFERS_JSON):
        with open(OFFERS_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
            return sorted(data.items(), key=lambda kv: kv[0])
    return []

def nav_kb(idx: int, total: int) -> InlineKeyboardMarkup:
    """إنشاء أزرار التنقل (التالي / السابق / رجوع)."""
    prev_btn = InlineKeyboardButton(text="⬅️ السابق", callback_data=f"offer60:{max(0, idx-1)}")
    next_btn = InlineKeyboardButton(text="التالي ➡️", callback_data=f"offer60:{min(total-1, idx+1)}")
    back_btn = InlineKeyboardButton(text="🔙 رجوع", callback_data="offer60:back")
    return InlineKeyboardMarkup(inline_keyboard=[[prev_btn, next_btn], [back_btn]])

# ===== (1) أمر الأرشفة: /index_60 =====
@router.message(Command("index_60"))
async def index_60(msg: Message, bot: Bot):
    """رفع الصور من المجلد واستخراج file_id لكل منها."""
    if not ADMIN_CHAT_ID or ADMIN_CHAT_ID == "0" or str(msg.chat.id) != str(ADMIN_CHAT_ID):
        return await msg.answer(
            "❌ هذا الأمر مخصص للمدير فقط.\n"
            "ضبط ADMIN_CHAT_ID الصحيح داخل ملف .env ثم أعد التشغيل."
        )

    if not os.path.isdir(IMAGES_DIR):
        return await msg.answer(f"❌ المجلد غير موجود: <code>{IMAGES_DIR}</code>")

    files = [f for f in os.listdir(IMAGES_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    if not files:
        return await msg.answer("📁 لا توجد صور داخل المجلد.")

    files.sort()
    await msg.answer(f"⏳ بدء الأرشفة… عدد الصور: {len(files)}")

    result_map: Dict[str, str] = {}
    ok = 0

    for fname in files:
        code = os.path.splitext(fname)[0]  # مثل: 6600001
        path = os.path.join(IMAGES_DIR, fname)
        try:
            sent = await bot.send_photo(
                chat_id=msg.chat.id,
                photo=FSInputFile(path),
                caption=f"📦 أرشفة عرض {code} — 60×60"
            )
            file_id = sent.photo[-1].file_id
            result_map[code] = file_id
            ok += 1
            await asyncio.sleep(0.6)  # لتجنب FloodWait
        except Exception as e:
            await msg.answer(f"⚠️ فشل في {fname}: {e}")

    if result_map:
        save_map(result_map)
        await msg.answer(
            f"✅ اكتملت الأرشفة.\n"
            f"عدد العروض: {ok}\n"
            f"تم إنشاء الملف: <code>{OFFERS_JSON}</code>"
        )
    else:
        await msg.answer("⚠️ لم يتم أرشفة أي صورة.")

# ===== (2) عرض العروض للمستخدم =====
@router.message(F.text == "📰 أحدث العروض 60×60")
async def show_offers_60(msg: Message):
    """عرض أول صورة من العروض المؤرشفة."""
    items = load_items()
    if not items:
        return await msg.answer("📂 لا توجد عروض مؤرشفة بعد. شغّل الأمر /index_60 أولًا.")

    idx = 0
    code, file_id = items[idx]
    caption = (
        f"🧱 عرض <b>{code}</b> — 60×60\n"
        f"({idx+1} من {len(items)})\n"
        f"💬 اطلبه بذكر رقم العرض."
    )
    await msg.answer_photo(photo=file_id, caption=caption, reply_markup=nav_kb(idx, len(items)))

# ===== (3) التنقل بين الصور =====
@router.callback_query(F.data.startswith("offer60:"))
async def paginate_offers_60(cb: CallbackQuery):
    """التنقل بين الصور (التالي / السابق / رجوع)."""
    items = load_items()
    if not items:
        return await cb.answer("لا توجد بيانات.", show_alert=True)

    action = cb.data.split(":")[1]
    if action == "back":
        await cb.message.edit_caption(caption="🔙 رجوع للقائمة.", reply_markup=None)
        return await cb.answer()

    try:
        idx = int(action)
    except:
        return await cb.answer("⚠️ خطأ في الفهرس.")

    if idx < 0 or idx >= len(items):
        return await cb.answer("🚫 وصلت للنهاية.")

    code, file_id = items[idx]
    caption = (
        f"🧱 عرض <b>{code}</b> — 60×60\n"
        f"({idx+1} من {len(items)})\n"
        f"💬 اطلبه بذكر رقم العرض."
    )
    try:
        await cb.message.edit_media(
            InputMediaPhoto(media=file_id, caption=caption, parse_mode="HTML"),
            reply_markup=nav_kb(idx, len(items))
        )
    except:
        # أحيانًا لا يمكن تعديل الرسالة، نرسل واحدة جديدة
        await cb.message.answer_photo(photo=file_id, caption=caption, reply_markup=nav_kb(idx, len(items)))
    await cb.answer()
# ===== (أوامر مساعدة) فحص وإكمال المفقود =====
def _dir_codes() -> List[str]:
    """الأكواد المستخرجة من أسماء ملفات المجلد (بدون الامتداد)."""
    if not os.path.isdir(IMAGES_DIR):
        return []
    files = [f for f in os.listdir(IMAGES_DIR) if f.lower().endswith((".jpg", ".jpeg", ".png", ".webp"))]
    return sorted([os.path.splitext(f)[0] for f in files])

def _json_codes() -> List[str]:
    """الأكواد الموجودة داخل JSON (المؤرشفة)."""
    return [k for k, _ in load_items()]

@router.message(Command("check_60"))
async def check_60(msg: Message):
    """تقرير الفروقات بين المجلد وملف JSON."""
    codes_dir = _dir_codes()
    codes_json = _json_codes()

    missing = [c for c in codes_dir if c not in codes_json]
    extra = [c for c in codes_json if c not in codes_dir]  # حالات قديمة لو حُذفت صورة من المجلد

    report = [
        f"📁 في المجلد: {len(codes_dir)} صورة",
        f"🗂️ في JSON المؤرشف: {len(codes_json)} عنصر",
        f"❗ المفقود (يحتاج أرشفة): {len(missing)}",
    ]
    if missing:
        # نعرض أول 20 فقط لو القائمة طويلة
        preview = ", ".join(missing[:20])
        more = f" … (+{len(missing)-20})" if len(missing) > 20 else ""
        report.append(f"القائمة: {preview}{more}")

    if extra:
        preview_e = ", ".join(extra[:20])
        more_e = f" … (+{len(extra)-20})" if len(extra) > 20 else ""
        report.append(f"ℹ️ عناصر موجودة في JSON ولكن ليست في المجلد: {len(extra)}\n{preview_e}{more_e}")

    await msg.answer("\n".join(report))

@router.message(Command("index_60_missing"))
async def index_60_missing(msg: Message, bot: Bot):
    """أرشفة المفقود فقط (حسب مقارنة المجلد مع JSON)."""
    if not ADMIN_CHAT_ID or ADMIN_CHAT_ID == "0" or str(msg.chat.id) != str(ADMIN_CHAT_ID):
        return await msg.answer("❌ هذا الأمر للمدير فقط. اضبط ADMIN_CHAT_ID في .env.")

    codes_dir = _dir_codes()
    if not codes_dir:
        return await msg.answer(f"❌ لا توجد صور في المجلد: <code>{IMAGES_DIR}</code>")

    codes_json = _json_codes()
    missing = [c for c in codes_dir if c not in codes_json]

    if not missing:
        return await msg.answer("✅ لا توجد عناصر مفقودة. كل شيء مؤرشف.")

    await msg.answer(f"⏳ البدء في أرشفة المفقود… ({len(missing)} عنصر)")

    # حمّل الخريطة الحالية (إن وُجدت) لنضيف عليها
    current_map = {}
    if os.path.exists(OFFERS_JSON):
        try:
            with open(OFFERS_JSON, "r", encoding="utf-8") as f:
                current_map = json.load(f)
        except Exception:
            current_map = {}

    ok, fails = 0, []
    for code in missing:
        path_jpg = os.path.join(IMAGES_DIR, f"{code}.jpg")
        path_jpeg = os.path.join(IMAGES_DIR, f"{code}.jpeg")
        path_png = os.path.join(IMAGES_DIR, f"{code}.png")
        path_webp = os.path.join(IMAGES_DIR, f"{code}.webp")

        # اختر أول امتداد موجود فعليًا
        path = None
        for p in (path_jpg, path_jpeg, path_png, path_webp):
            if os.path.exists(p):
                path = p
                break

        if not path:
            fails.append((code, "الملف غير موجود بامتداد معروف"))
            continue

        try:
            sent = await bot.send_photo(
                chat_id=msg.chat.id,
                photo=FSInputFile(path),
                caption=f"📦 أرشفة مفقود {code} — 60×60"
            )
            file_id = sent.photo[-1].file_id
            current_map[code] = file_id
            ok += 1
            await asyncio.sleep(0.6)
        except Exception as e:
            fails.append((code, str(e)))

    # حفظ التحديث
    save_map(current_map)

    # ملخص
    lines = [
        f"✅ تمت أرشفة: {ok}",
        f"⚠️ فشل: {len(fails)}"
    ]
    if fails:
        # نعرض أول 10 أخطاء لتقليل الازدحام
        preview_fails = "\n".join([f"- {c}: {err}" for c, err in fails[:10]])
        more_f = f"\n… (+{len(fails)-10} حالات أخرى)" if len(fails) > 10 else ""
        lines.append(preview_fails + more_f)

    await msg.answer("\n".join(lines))
