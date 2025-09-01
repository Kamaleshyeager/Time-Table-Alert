# timetable_bot.py
"""
Telegram Timetable Reminder Bot — updated to offer ALL slot labels per time-position
- Each user selects slot label for each time-position (Tue-Sat)
- Users type only the variable fields (course code/name/faculty/venue)
- Saves per-user to users/<chat_id>.json
- Schedules reminders 5 minutes before times (IST)
Requires:
  python-telegram-bot==13.15 apscheduler pytz
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from telegram import (
    Bot,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ParseMode,
)
from telegram.ext import (
    Updater,
    CallbackContext,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    Filters,
)

# ---------------------------
# CONFIG - Edit your token
# ---------------------------
BOT_TOKEN = "INSERT YOUR BOT_TOKEN HERE"
IST = pytz.timezone("Asia/Kolkata")
DATA_DIR = "users"
os.makedirs(DATA_DIR, exist_ok=True)

# ---------------------------
# All possible slot labels from your grid (collected from the timetable image)
# (If you want to remove/add any, edit here)
# ---------------------------
SLOT_LABELS = [
    "A1","A2","B1","B2","C1","C2","D1","D2","E1","E2","F1","F2",
    "TA1","TA2","TB1","TB2","TC1","TC2",
    "TBB1","TBB2","TAA1","TAA2","TF1","TF2",
    "TFF1","TFF2","TGG1","TGG2","TCC1","TCC2","TDD1","TDD2",
    "SC1","SC2","SD1","SD2","SE1","SE2",
    "G1","G2","ECS","CLUB"
]

# ---------------------------
# Time positions (every main hourly start). We'll iterate these for Tue-Sat.
# You can adjust times if your institute uses slightly different start times.
# ---------------------------
TIME_POSITIONS = [
    {"time_24": "08:00", "time_12": "08:00 AM"},
    {"time_24": "09:00", "time_12": "09:00 AM"},
    {"time_24": "10:00", "time_12": "10:00 AM"},
    {"time_24": "11:00", "time_12": "11:00 AM"},
    {"time_24": "12:00", "time_12": "12:00 PM"},
    {"time_24": "13:00", "time_12": "01:00 PM"},
    {"time_24": "14:00", "time_12": "02:00 PM"},
    {"time_24": "15:00", "time_12": "03:00 PM"},
    {"time_24": "16:00", "time_12": "04:00 PM"},
    {"time_24": "17:00", "time_12": "05:00 PM"},
    {"time_24": "18:00", "time_12": "06:00 PM"},
    {"time_24": "19:00", "time_12": "07:00 PM"},
]

DAY_ORDER = ["Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

DAY_TO_CRON = {
    "Monday": "mon", "Tuesday": "tue", "Wednesday": "wed",
    "Thursday": "thu", "Friday": "fri", "Saturday": "sat", "Sunday": "sun"
}

# ---------------------------
# Logging & scheduler
# ---------------------------
logging.basicConfig(format="%(asctime)s %(levelname)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("timetable-bot")
scheduler = BackgroundScheduler(timezone=IST)
scheduler.start()

bot = Bot(token=BOT_TOKEN)

# ---------------------------
# Storage helpers
# ---------------------------
def user_file(chat_id: int) -> str:
    return os.path.join(DATA_DIR, f"{chat_id}.json")

def load_user(chat_id: int) -> Dict[str, Any]:
    path = user_file(chat_id)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"semester": "", "classes": []}

def save_user(chat_id: int, data: Dict[str, Any]) -> None:
    with open(user_file(chat_id), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def clear_user_jobs(chat_id: int):
    for job in list(scheduler.get_jobs()):
        if job.id.startswith(f"user-{chat_id}-"):
            scheduler.remove_job(job.id)

# ---------------------------
# Scheduling helpers
# ---------------------------
def minus_minutes(hh: int, mm: int, mins: int = 5):
    total = hh * 60 + mm - mins
    total %= (24 * 60)
    return divmod(total, 60)  # (hour, minute)

def schedule_user_reminders(chat_id: int, classes: List[Dict[str, Any]]):
    clear_user_jobs(chat_id)
    for c in classes:
        day = c["day"]
        cron_day = DAY_TO_CRON.get(day, None)
        if not cron_day:
            continue
        h24, m24 = [int(x) for x in c["time_24"].split(":")]
        rem_h, rem_m = minus_minutes(h24, m24, 5)
        job_id = f"user-{chat_id}-{day}-{c['slot']}-{c['time_24']}"
        scheduler.add_job(
            func=send_reminder_job,
            trigger="cron",
            id=job_id,
            day_of_week=cron_day,
            hour=int(rem_h),
            minute=int(rem_m),
            args=[chat_id, c],
            replace_existing=True,
            misfire_grace_time=60,
        )
    logger.info(f"Scheduled {len(classes)} reminders for user {chat_id}")

def send_reminder_job(chat_id: int, c: Dict[str, Any]):
    now = datetime.now(IST)
    date_str = now.strftime("%d-%b-%Y (%A)")
    user = load_user(chat_id)
    text = (
        f"📅 *{date_str}*\n"
        f"⏰ *{c['time_12']}* (in ~5 min)\n"
        f"🪑 *Slot:* {c['slot']}  •  *Day:* {c['day']}\n"
        f"📖 *{c.get('course_code','')}* — {c.get('course_name','')}\n"
        f"👨‍🏫 *Faculty:* {c.get('faculty','')}\n"
        f"🏛 *Venue:* {c.get('venue','')}\n"
        f"🎓 *Semester:* {user.get('semester','')}"
    )
    try:
        bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.warning(f"Failed to send reminder to {chat_id}: {e}")

# ---------------------------
# UI helpers
# ---------------------------
def chunked_buttons(items, per_row=3):
    rows = []
    for i in range(0, len(items), per_row):
        rows.append([InlineKeyboardButton(x, callback_data=f"slot_select:{x}") for x in items[i:i+per_row]])
    return rows

# ---------------------------
# Bot handlers (menu & setup)
# ---------------------------
def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    kb = [
        [InlineKeyboardButton("🧩 Set up / Edit my timetable", callback_data="setup")],
        [InlineKeyboardButton("👀 Show my timetable", callback_data="show")],
        [InlineKeyboardButton("🗑 Clear my timetable", callback_data="clear")],
        [InlineKeyboardButton("🔁 Reschedule reminders", callback_data="resched")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ]
    context.bot.send_message(
        chat_id=chat_id,
        text=(
            "Hi — I’ll remind you *5 minutes before* each class (Tue→Sat grid).\n\n"
            "Tap *Set up* to map your courses to the shared slot/time grid.\n\n"
            "I save your data so you only do this once. Share the bot with friends — everyone keeps their own data."
        ),
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(kb),
    )

def handle_menu_callback(update: Update, context: CallbackContext):
    data = update.callback_query.data
    chat_id = update.effective_chat.id
    update.callback_query.answer()
    if data == "setup":
        start_setup(update, context)
    elif data == "show":
        show_timetable_cb(update, context)
    elif data == "clear":
        save_user(chat_id, {"semester": "", "classes": []})
        clear_user_jobs(chat_id)
        update.callback_query.edit_message_text("✅ Cleared your timetable and reminders.")
    elif data == "resched":
        user = load_user(chat_id)
        schedule_user_reminders(chat_id, user.get("classes", []))
        update.callback_query.edit_message_text("🔁 Reminders rescheduled.")
    elif data == "help":
        update.callback_query.edit_message_text(
            "Commands:\n/start /setup /show /clear /reschedule\n\n"
            "During setup you'll choose the slot label for each time-position (poll-like). "
            "If you choose a slot, you'll type course code, name, faculty, venue. "
            "Finish early with *Finish setup* button."
        )

# ---------------------------
# SETUP WIZARD
# ---------------------------
# We'll iterate over a flattened list of positions: (day, time_index)
POSITIONS = []
for d in DAY_ORDER:
    for t in TIME_POSITIONS:
        POSITIONS.append({"day": d, "time_24": t["time_24"], "time_12": t["time_12"]})

def start_setup(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    context.user_data["setup"] = {
        "pos_index": 0,
        "semester": "",
        "draft_classes": [],
        "await": "semester",
        "collecting": {},  # holds data while collecting fields for a chosen slot
    }
    # ask semester
    if update.callback_query:
        update.callback_query.edit_message_text("🎓 Type your *Semester* name/number (e.g., `Fall Sem (2025-2026)`):", parse_mode=ParseMode.MARKDOWN)
    else:
        context.bot.send_message(chat_id, "🎓 Type your *Semester* name/number (e.g., `Fall Sem (2025-2026)`):", parse_mode=ParseMode.MARKDOWN)

def ask_next_position(update: Update, context: CallbackContext):
    s = context.user_data.get("setup")
    if not s:
        return
    idx = s["pos_index"]
    if idx >= len(POSITIONS):
        finalize_setup(update, context)
        return
    pos = POSITIONS[idx]
    day, t12 = pos["day"], pos["time_12"]
    text = f"Do you have a class on *{day}* at *{t12}* ?\nSelect the slot label (or No class / Other / Finish setup)"
    # build keyboard: chunk slot labels, plus No class, Other, Finish
    kb = chunked_buttons(SLOT_LABELS, per_row=4)
    kb.append([
        InlineKeyboardButton("❌ No class", callback_data="slot_select:__NO__"),
        InlineKeyboardButton("✏️ Other (type slot)", callback_data="slot_select:__OTHER__"),
        InlineKeyboardButton("✅ Finish setup", callback_data="slot_select:__FINISH__"),
    ])
    # send as a new message (or edit)
    update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))

def slot_select_cb(update: Update, context: CallbackContext):
    """Called when user picks a slot label (or No/Other/Finish)"""
    query = update.callback_query
    chat_id = update.effective_chat.id
    data = query.data  # like "slot_select:A2" or "slot_select:__NO__"
    query.answer()
    if "setup" not in context.user_data:
        query.edit_message_text("Please use /setup to begin.")
        return
    s = context.user_data["setup"]
    idx = s["pos_index"]
    # finish early?
    if data.endswith("__FINISH__"):
        query.edit_message_text("Finishing setup early as requested...")
        finalize_setup(update, context)
        return
    # No class -> skip this position
    if data.endswith("__NO__"):
        s["pos_index"] += 1
        query.edit_message_text(f"Skipped. Moving on.")
        ask_next_position(update, context)
        return
    # Other -> ask to type the slot label
    if data.endswith("__OTHER__"):
        s["await"] = "slot_custom"
        query.edit_message_text("Type the *slot label* (e.g., A1 or TBB2) for this time:", parse_mode=ParseMode.MARKDOWN)
        return

    # Otherwise a real slot label was chosen
    chosen = data.split(":",1)[1]
    # start collecting course fields
    s["collecting"] = {
        "slot": chosen,
        "day": POSITIONS[idx]["day"],
        "time_24": POSITIONS[idx]["time_24"],
        "time_12": POSITIONS[idx]["time_12"],
    }
    s["await"] = "course_code"
    query.edit_message_text(f"You chose *{chosen}* for {POSITIONS[idx]['day']} {POSITIONS[idx]['time_12']}.\nNow: Enter *Course Code* (e.g., LAW2113):", parse_mode=ParseMode.MARKDOWN)

def setup_text(update: Update, context: CallbackContext):
    """Handles typed text during setup (semester, custom slot name, course fields)"""
    if "setup" not in context.user_data:
        return
    s = context.user_data["setup"]
    text = (update.message.text or "").strip()
    if not text:
        return

    # semester first
    if s.get("await") == "semester":
        s["semester"] = text
        s["await"] = None
        update.message.reply_text("Semester saved. Now I'll go through each time-position (Tue→Sat). For each you can choose a slot or skip.")
        ask_next_position(update, context)
        return

    # custom slot label
    if s.get("await") == "slot_custom":
        s["collecting"] = {
            "slot": text,
            "day": POSITIONS[s["pos_index"]]["day"],
            "time_24": POSITIONS[s["pos_index"]]["time_24"],
            "time_12": POSITIONS[s["pos_index"]]["time_12"],
        }
        s["await"] = "course_code"
        update.message.reply_text(f"Slot label set to *{text}*.\nNow enter *Course Code* (e.g., LAW2113):", parse_mode=ParseMode.MARKDOWN)
        return

    # collecting fields for a chosen slot
    if s.get("await") in ("course_code","course_name","faculty","venue"):
        field = s["await"]
        if field == "course_code":
            s["collecting"]["course_code"] = text
            s["await"] = "course_name"
            update.message.reply_text("Enter *Course Name* (e.g., Law and Economics):", parse_mode=ParseMode.MARKDOWN)
            return
        elif field == "course_name":
            s["collecting"]["course_name"] = text
            s["await"] = "faculty"
            update.message.reply_text("Enter *Faculty Name*:", parse_mode=ParseMode.MARKDOWN)
            return
        elif field == "faculty":
            s["collecting"]["faculty"] = text
            s["await"] = "venue"
            update.message.reply_text("Enter *Venue* (e.g., AB-2 410):", parse_mode=ParseMode.MARKDOWN)
            return
        elif field == "venue":
            s["collecting"]["venue"] = text
            # finalize this class entry
            entry = {
                "day": s["collecting"]["day"],
                "slot": s["collecting"]["slot"],
                "time_24": s["collecting"]["time_24"],
                "time_12": s["collecting"]["time_12"],
                "course_code": s["collecting"].get("course_code",""),
                "course_name": s["collecting"].get("course_name",""),
                "faculty": s["collecting"].get("faculty",""),
                "venue": s["collecting"].get("venue",""),
            }
            s["draft_classes"].append(entry)
            s["collecting"] = {}
            s["await"] = None
            s["pos_index"] += 1
            update.message.reply_text("✅ Saved this class. Moving on...")
            ask_next_position(update, context)
            return

def finalize_setup(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    s = context.user_data.get("setup", {})
    user_data = {"semester": s.get("semester",""), "classes": s.get("draft_classes", [])}
    save_user(chat_id, user_data)
    schedule_user_reminders(chat_id, user_data["classes"])

    # summary
    if not user_data["classes"]:
        context.bot.send_message(chat_id, "You didn't add any classes. Use /setup anytime to add them.")
        return

    lines = [f"🎓 Semester: *{user_data['semester']}*", ""]
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for c in user_data["classes"]:
        by_day.setdefault(c["day"], []).append(c)
    for d in DAY_ORDER:
        if d in by_day:
            lines.append(f"📅 *{d}*")
            for c in sorted(by_day[d], key=lambda x: x["time_24"]):
                lines.append(f"  • {c['time_12']}  {c['slot']}  {c.get('course_code','')} – {c.get('course_name','')}  ({c.get('faculty','')}; {c.get('venue','')})")
            lines.append("")
    context.bot.send_message(chat_id, "\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    context.bot.send_message(chat_id, "✅ All set! I will ping you 5 minutes before each class. Use /show to view or /reschedule to re-create reminders.")
    # clean up setup state
    context.user_data.pop("setup", None)

# ---------------------------
# Small command handlers
# ---------------------------
def show_timetable_cb(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user = load_user(chat_id)
    if not user["classes"]:
        update.callback_query.edit_message_text("You don't have any classes saved. Use /setup to add.")
        return
    lines = [f"🎓 Semester: *{user.get('semester','—')}*", ""]
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for c in user["classes"]:
        by_day.setdefault(c["day"], []).append(c)
    for d in DAY_ORDER:
        if d in by_day:
            lines.append(f"📅 *{d}*")
            for c in sorted(by_day[d], key=lambda x: x["time_24"]):
                lines.append(f"  • {c['time_12']}  {c['slot']}  {c.get('course_code','')} – {c.get('course_name','')}  ({c.get('faculty','')}; {c.get('venue','')})")
            lines.append("")
    update.callback_query.edit_message_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

def cmd_setup(update: Update, context: CallbackContext):
    start_setup(update, context)

def cmd_show(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user = load_user(chat_id)
    if not user["classes"]:
        update.message.reply_text("You don't have any classes saved. Use /setup to add.")
        return
    lines = [f"🎓 Semester: *{user.get('semester','—')}*", ""]
    by_day: Dict[str, List[Dict[str, Any]]] = {}
    for c in user["classes"]:
        by_day.setdefault(c["day"], []).append(c)
    for d in DAY_ORDER:
        if d in by_day:
            lines.append(f"📅 *{d}*")
            for c in sorted(by_day[d], key=lambda x: x["time_24"]):
                lines.append(f"  • {c['time_12']}  {c['slot']}  {c.get('course_code','')} – {c.get('course_name','')}  ({c.get('faculty','')}; {c.get('venue','')})")
            lines.append("")
    update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

def cmd_clear(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    save_user(chat_id, {"semester": "", "classes": []})
    clear_user_jobs(chat_id)
    update.message.reply_text("✅ Cleared your timetable and reminders.")

def cmd_reschedule(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user = load_user(chat_id)
    schedule_user_reminders(chat_id, user.get("classes", []))
    update.message.reply_text("🔁 Reminders rescheduled.")

# ---------------------------
# Main
# ---------------------------
def main():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # menu buttons
    dp.add_handler(CallbackQueryHandler(handle_menu_callback, pattern="^(setup|show|clear|resched|help)$"))

    # slot selection (many slot labels + special codes)
    dp.add_handler(CallbackQueryHandler(slot_select_cb, pattern="^slot_select:"))

    # text handler (semester, custom slot label, course fields)
    dp.add_handler(MessageHandler(Filters.text & (~Filters.command), setup_text))

    # commands
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("setup", cmd_setup))
    dp.add_handler(CommandHandler("show", cmd_show))
    dp.add_handler(CommandHandler("clear", cmd_clear))
    dp.add_handler(CommandHandler("reschedule", cmd_reschedule))

    # on start: schedule reminders for existing users
    for fname in os.listdir(DATA_DIR):
        if fname.endswith(".json"):
            try:
                chat_id = int(fname.replace(".json",""))
                user = load_user(chat_id)
                schedule_user_reminders(chat_id, user.get("classes",[]))
            except Exception as e:
                logger.warning(f"Skipping {fname}: {e}")

    logger.info("Bot started. Listening…")
    updater.start_polling(drop_pending_updates=True)
    updater.idle()

if __name__ == "__main__":
    main()
