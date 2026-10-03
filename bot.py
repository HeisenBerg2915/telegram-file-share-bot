import os
import asyncio
import secrets
import html
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from pymongo import MongoClient

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatJoinRequest,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_ID = os.getenv("ADMIN_ID")

# Request-to-Join channel
REQUEST_CHANNEL_ID = -1004366581317
REQUEST_CHANNEL_LINK = "https://t.me/+TBEZZOyLdPdjODg1"

# /connect അനുവദിച്ച Group ID
CONNECTED_GROUP_ID = -1002670818803

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing")

mongo = MongoClient(MONGO_URI)
db = mongo["file_share_bot"]
batches = db["batches"]
connected_groups = db["connected_groups"]
filters_collection = db["filters"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

active_batches = {}

# User -> batch code waiting for channel request
pending_access = {}

FILES_PER_PAGE = 8


async def delete_file_later(chat_id, message_id):
    await asyncio.sleep(300)

    try:
        await bot.delete_message(
            chat_id=chat_id,
            message_id=message_id,
        )
        print(f"Auto-deleted message: {message_id}")
    except Exception as e:
        print(f"Auto-delete error for {message_id}: {e}")

# ============================================================
# FILTER SYSTEM
# ============================================================

async def filter_admin_only(message: Message):
    admin_id = os.getenv("ADMIN_ID")

    if not admin_id or str(message.from_user.id) != str(admin_id):
        await message.answer(
            "🚫 <b>Access Denied</b>\n\n"
            "This command is available for admins only.",
            parse_mode="HTML",
        )
        return False

    return True


def parse_filter_buttons(text):
    """
    Example:
    [Leo 2023](buttonurl:https://example.com)
    """

    import re

    pattern = r"\[([^\]]+)\]\(buttonurl:([^)]+)\)"

    matches = re.findall(pattern, text or "")

    return [
        {
            "name": name.strip(),
            "url": url.strip(),
        }
        for name, url in matches
    ]

# ============================================================
# /filter
# ============================================================

@router.message(Command("filter"))
async def filter_handler(message: Message):

    if not await filter_admin_only(message):
        return

    # /filter keyword
    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "❌ <b>Usage:</b>\n\n"
            "<code>/filter leo</code>\n\n"
            "Reply to a photo/message containing:\n"
            "<code>[Leo 2023](buttonurl:https://example.com)</code>",
            parse_mode="HTML",
        )
        return

    keyword = parts[1].strip().lower()

    # /filter must be a reply
    if not message.reply_to_message:
        await message.answer(
            "❌ Please reply to the message you want to use for the filter."
        )
        return

    source_message = message.reply_to_message

    # Caption / text
    source_text = (
        source_message.caption
        or source_message.text
        or ""
    )

    # Find buttons
    buttons = parse_filter_buttons(source_text)

    # Remove button syntax from displayed caption
    import re

    clean_caption = re.sub(
        r"\[([^\]]+)\]\(buttonurl:([^)]+)\)",
        "",
        source_text
    ).strip()

    # --------------------------------------------------------
    # PHOTO FILTER
    # --------------------------------------------------------

    photo_file_id = None

    if source_message.photo:
        # Highest quality photo
        photo_file_id = source_message.photo[-1].file_id

    # --------------------------------------------------------
    # Must have either photo or text
    # --------------------------------------------------------

    if not photo_file_id and not clean_caption:
        await message.answer(
            "❌ The replied message has no photo or text."
        )
        return

    # --------------------------------------------------------
    # Save filter
    # --------------------------------------------------------

    filter_data = {
        "keyword": keyword,
        "buttons": buttons,
        "caption": clean_caption,
        "photo_file_id": photo_file_id,
        "created_at": datetime.now(timezone.utc),
        "created_by": message.from_user.id,
    }

    filters_collection.update_one(
        {"keyword": keyword},
        {
            "$set": filter_data
        },
        upsert=True,
    )

    await message.answer(
        "✅ <b>Filter Created</b>\n\n"
        f"🔎 Keyword: <code>{keyword}</code>\n"
        f"🖼️ Poster: {'Yes' if photo_file_id else 'No'}\n"
        f"🔘 Results: <b>{len(buttons)}</b>",
        parse_mode="HTML",
    )


# ============================================================
# /filters
# ============================================================

@router.message(Command("filters"))
async def filters_handler(message: Message):

    if not await filter_admin_only(message):
        return

    filters = list(
        filters_collection.find(
            {},
            {
                "_id": 0,
                "keyword": 1,
                "buttons": 1,
            }
        ).sort("keyword", 1)
    )

    if not filters:
        await message.answer(
            "📂 <b>No filters found.</b>",
            parse_mode="HTML",
        )
        return

    text = "📋 <b>Available Filters</b>\n\n"

    for item in filters:
        keyword = item.get("keyword", "")
        count = len(item.get("buttons", []))

        text += (
            f"🔎 <code>{keyword}</code> "
            f"— {count} result(s)\n"
        )

    await message.answer(
        text,
        parse_mode="HTML",
    )


# ============================================================
# /deletefilter
# ============================================================

@router.message(Command("deletefilter"))
async def delete_filter_handler(message: Message):

    if not await filter_admin_only(message):
        return

    parts = message.text.split(maxsplit=1)

    if len(parts) < 2:
        await message.answer(
            "❌ <b>Usage:</b>\n\n"
            "<code>/deletefilter leo</code>",
            parse_mode="HTML",
        )
        return

    keyword = parts[1].strip().lower()

    result = filters_collection.delete_one(
        {"keyword": keyword}
    )

    if result.deleted_count == 0:
        await message.answer(
            f"❌ Filter <code>{keyword}</code> not found.",
            parse_mode="HTML",
        )
        return

    await message.answer(
        f"✅ Filter <code>{keyword}</code> deleted.",
        parse_mode="HTML",
    )


# ============================================================
# /alldeletefilters
# ============================================================

@router.message(Command("alldeletefilters"))
async def delete_all_filters_handler(message: Message):

    if not await filter_admin_only(message):
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ YES, DELETE ALL",
                    callback_data="delete_all_filters:yes",
                ),
                InlineKeyboardButton(
                    text="❌ CANCEL",
                    callback_data="delete_all_filters:no",
                ),
            ]
        ]
    )

    await message.answer(
        "⚠️ <b>Delete All Filters?</b>\n\n"
        "This will permanently delete all filters.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# ============================================================
# DELETE ALL FILTERS CONFIRMATION
# ============================================================

@router.callback_query(
    lambda query: (
        query.data
        and query.data.startswith("delete_all_filters:")
    )
)
async def delete_all_filters_callback(query: CallbackQuery):

    admin_id = os.getenv("ADMIN_ID")

    if not admin_id or str(query.from_user.id) != str(admin_id):
        await query.answer(
            "🚫 Admin only.",
            show_alert=True,
        )
        return

    action = query.data.split(":", 1)[1]

    if action == "no":
        await query.message.delete()
        await query.answer("Cancelled.")
        return

    result = filters_collection.delete_many({})

    await query.message.edit_text(
        "✅ <b>All filters deleted.</b>\n\n"
        f"🗑️ Deleted: {result.deleted_count}",
        parse_mode="HTML",
    )

    await query.answer("Done.")

def format_file_size(size):
    if not size:
        return "0 B"

    size = float(size)

    if size >= 1024 ** 3:
        return f"{size / (1024 ** 3):.2f} GB"

    if size >= 1024 ** 2:
        return f"{size / (1024 ** 2):.2f} MB"

    if size >= 1024:
        return f"{size / 1024:.2f} KB"

    return f"{int(size)} B"


def create_file_keyboard(code, files, page=0):
    total_files = len(files)
    total_pages = (total_files + FILES_PER_PAGE - 1) // FILES_PER_PAGE

    start = page * FILES_PER_PAGE
    end = start + FILES_PER_PAGE
    page_files = files[start:end]

    keyboard = []

    for index, file in enumerate(page_files, start=start):
        file_name = file.get("file_name") or "Unnamed file"
        file_size = format_file_size(file.get("file_size"))

        # Filename അധികം നീളുന്നത് ഒഴിവാക്കാൻ
        max_name_length = 40

        if len(file_name) > max_name_length:
            file_name = file_name[:max_name_length - 3] + "..."

        keyboard.append([
            InlineKeyboardButton(
                text=f"[{file_size}] ▷ {file_name}",
                callback_data=f"file:{code}:{index}",
            )
        ])

    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ ʙᴀᴄᴋ",
                callback_data=f"page:{code}:{page - 1}",
            )
        )

    if page < total_pages - 1:
        navigation.append(
            InlineKeyboardButton(
                text="ɴᴇxᴛ ➡️",
                callback_data=f"page:{code}:{page + 1}",
            )
        )

    if navigation:
        keyboard.append(navigation)

    keyboard.append([
        InlineKeyboardButton(
            text=f"{page + 1}/{total_pages}",
            callback_data="page_info",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


# ============================================================
# SEND FILE RESULT
# ============================================================

async def send_batch_result(chat_id, code):
    batch = batches.find_one({"code": code})

    if not batch:
        await bot.send_message(
            chat_id=chat_id,
            text="❌ Batch not found.",
        )
        return False

    files = batch.get("files", [])

    if not files:
        await bot.send_message(
            chat_id=chat_id,
            text="❌ No files found.",
        )
        return False

    import re

    first_file_name = files[0].get("file_name", "Unknown")

    year_match = re.search(
        r"\b(19\d{2}|20\d{2})\b",
        first_file_name
    )

    year = year_match.group(1) if year_match else "N/A"

    movie_name = re.sub(
        r"\.(mp4|mkv|avi|mov|webm)$",
        "",
        first_file_name,
        flags=re.IGNORECASE
    )

    if year_match:
        movie_name = movie_name.replace(year, "").strip()

    movie_name = re.sub(r"[_\.]+", " ", movie_name).strip()

    keyboard = create_file_keyboard(
        code=code,
        files=files,
        page=0,
    )

    sent_message = await bot.send_message(
    chat_id=chat_id,
    text=(
        f"<blockquote>{movie_name} ({year})</blockquote>\n\n"
        "<b>🎬 Your requested files are ready!</b>\n\n"
        "<b>📄 താഴെ നൽകിയിരിക്കുന്ന button-ൽ നിന്ന് "
        "നിങ്ങൾക്ക് ആവശ്യമുള്ള file തിരഞ്ഞെടുക്കാം.</b>\n\n"
        "🔗 <a href='https://t.me/Clmainchannel'>"
        "<b>Team ചിത്രലോകം™️</b></a>"
    ),
    parse_mode="HTML",
    reply_markup=keyboard
    )

    asyncio.create_task(
        delete_file_later(
            chat_id,
            sent_message.message_id,
        )
    )

    return True


# ============================================================
# START
# ============================================================

@router.message(Command("start"))
async def start_handler(message: Message):
    parts = message.text.split(maxsplit=1)

    # Normal /start
    if len(parts) == 1:
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="👥 Jᴏɪɴ ᴏʀᴜ Gʀᴏᴜᴘ 👥",
                        url="https://t.me/+Ik14BdOewjQzYjI1",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="📌 Jᴏɪɴ Uᴘᴅᴀᴛᴇ Cʜᴀɴɴᴇʟ 📌",
                        url="https://t.me/Clmainchannel",
                    )
                ],
            ]
        )

        await message.answer(
            "<b>Wᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ Dʀᴏᴘ Zᴏɴᴇ ⚡</b>\n\n"
            "🤖 <b>ഞാൻ ഒരു Fɪʟᴇ Sʜᴀʀɪɴɢ Bᴏᴛ ആണ്.</b>\n"
            "🎬 <b>ചിത്രലോകം ഗ്രൂപ്പിന് വേണ്ടി മാത്രം എന്നെ നിർമ്മിച്ചിരിക്കുന്നു. ❤️</b>",
            parse_mode="HTML",
            reply_markup=keyboard,
        )
        return

    # Share link /start CODE
    code = parts[1]

    batch = batches.find_one({"code": code})

    if not batch:
        await message.answer("❌ Batch not found.")
        return

    files = batch.get("files", [])

    if not files:
        await message.answer("❌ No files found.")
        return

    user_id = message.from_user.id

    # Check if user is already a member of the request channel
    try:
        member = await bot.get_chat_member(
            chat_id=REQUEST_CHANNEL_ID,
            user_id=user_id,
        )

        status = member.status

        # Already joined -> show files directly
        if status in ("member", "administrator", "creator"):
            await send_batch_result(
                chat_id=user_id,
                code=code,
            )
            return

    except Exception as e:
        print(f"Membership check error: {e}")

    # User is not a member -> show Join + Try Again
    pending_access[user_id] = code

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Jᴏɪɴ Tᴏ Cʜᴀɴɴᴇʟ",
                    url="https://t.me/+TBEZZOyLdPdjODg1",
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Tʀʏ Aɢᴀɪɴ",
                    callback_data=f"check_join:{code}",
                )
            ],
        ]
    )

    await message.answer(
        "<b>🔒 Cʜᴀɴɴᴇʟ Jᴏɪɴ Rᴇǫᴜɪʀᴇᴅ</b>\n\n"
        "<b>📢 ആദ്യം താഴെയുള്ള channel-ൽ Join Request അയക്കുക.</b>\n\n"
        "<b>✅ Request അയച്ച ശേഷം TRY AGAIN അമർത്തുക.</b>",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

# ============================================================
# CONNECT GROUP
# ============================================================

@router.message(Command("connect"))
async def connect_handler(message: Message):

    # Group / Supergroup മാത്രം
    if message.chat.type not in ("group", "supergroup"):
        await message.answer(
            "❌ ഈ command group-ൽ മാത്രം ഉപയോഗിക്കാം."
        )
        return

    # Admin അനുവദിച്ച Group ID ആണോ?
    if message.chat.id != CONNECTED_GROUP_ID:
        await message.answer(
            "❌ ഈ group-ൽ bot connect ചെയ്യാൻ അനുവദിച്ചിട്ടില്ല."
        )
        return

    # Connected group save ചെയ്യുക
    connected_groups.update_one(
        {"chat_id": message.chat.id},
        {
            "$set": {
                "chat_id": message.chat.id,
                "group_name": message.chat.title,
                "connected_at": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )

    await message.answer(
        "✅ <b>Gʀᴏᴜᴘ Cᴏɴɴᴇᴄᴛᴇᴅ</b>",
        parse_mode="HTML",
    )
    
# ============================================================
# JOIN REQUEST HANDLER
# ============================================================

@router.chat_join_request()
async def join_request_handler(request: ChatJoinRequest):
    user_id = request.from_user.id
    chat_id = request.chat.id

    print(
        f"Join request received: "
        f"user={user_id}, channel={chat_id}"
    )

    # Only our request channel
    if chat_id != REQUEST_CHANNEL_ID:
        return

    # User must have opened a batch link first
    if user_id not in pending_access:
        return

    try:
        # Auto approve the join request
        await bot.approve_chat_join_request(
            chat_id=chat_id,
            user_id=user_id,
        )

        print(
            f"Join request approved for user {user_id}"
        )

    except Exception as e:
        print(
            f"Join request approval error: {e}"
        )


# ============================================================
# TRY AGAIN
# ============================================================

@router.callback_query(
    lambda query: (
        query.data
        and query.data.startswith("check_join:")
    )
)
async def check_join_handler(query: CallbackQuery):
    user_id = query.from_user.id

    try:
        _, code = query.data.split(":", 1)
    except Exception:
        await query.answer(
            "❌ Invalid request.",
            show_alert=True,
        )
        return

    # Make sure this user is checking their own pending code
    if pending_access.get(user_id) != code:
        pending_access[user_id] = code

    try:
        member = await bot.get_chat_member(
            chat_id=REQUEST_CHANNEL_ID,
            user_id=user_id,
        )

        status = member.status

        # Valid subscribed/member statuses
        if status in ("member", "administrator", "creator"):
            pending_access.pop(user_id, None)

            await query.answer(
                "✅ Verified!",
                show_alert=False,
            )

            try:
                await query.message.delete()
            except Exception:
                pass

            await send_batch_result(
                chat_id=user_id,
                code=code,
            )

            return

        # Still pending
        if status == "restricted":
            await query.answer(
                "⏳ Your request is still pending.",
                show_alert=True,
            )
            return

        await query.answer(
            "❌ Please Join the channel first.",
            show_alert=True,
        )

    except Exception as e:
        print(
            f"Join verification error: {e}"
        )

        await query.answer(
            "❌ Please send a Join Request first.",
            show_alert=True,
        )


# ============================================================
# PAGINATION
# ============================================================

@router.callback_query(
    lambda query: query.data and query.data.startswith("page:")
)
async def pagination_handler(query: CallbackQuery):
    try:
        _, code, page_str = query.data.split(":")
        page = int(page_str)
    except Exception:
        await query.answer(
            "❌ Invalid page.",
            show_alert=True,
        )
        return

    batch = batches.find_one({"code": code})

    if not batch:
        await query.answer(
            "❌ Batch not found.",
            show_alert=True,
        )
        return

    files = batch.get("files", [])

    if not files:
        await query.answer(
            "❌ No files found.",
            show_alert=True,
        )
        return

    total_pages = (
        len(files) + FILES_PER_PAGE - 1
    ) // FILES_PER_PAGE

    if page < 0 or page >= total_pages:
        await query.answer(
            "❌ Invalid page.",
            show_alert=True,
        )
        return

    keyboard = create_file_keyboard(
        code=code,
        files=files,
        page=page,
    )

    try:
        await query.message.edit_reply_markup(
            reply_markup=keyboard
        )
    except Exception as e:
        print("Pagination error:", e)

    await query.answer()


# ============================================================
# PAGE INFO
# ============================================================

@router.callback_query(
    lambda query: query.data == "page_info"
)
async def page_info_handler(query: CallbackQuery):
    await query.answer(
        "📄 Select a file to download it.",
        show_alert=False,
    )


# ============================================================
# FILE DOWNLOAD
# ============================================================

@router.callback_query(
    lambda query: query.data and query.data.startswith("file:")
)
async def file_callback_handler(query: CallbackQuery):
    try:
        _, code, index_str = query.data.split(":")
        index = int(index_str)
    except Exception:
        await query.answer(
            "❌ Invalid file.",
            show_alert=True,
        )
        return

    batch = batches.find_one({"code": code})

    if not batch:
        await query.answer(
            "❌ Batch not found.",
            show_alert=True,
        )
        return

    files = batch.get("files", [])

    if index < 0 or index >= len(files):
        await query.answer(
            "❌ File not found.",
            show_alert=True,
        )
        return

    file = files[index]

    file_id = file.get("file_id")
    file_name = file.get("file_name") or "Unnamed file"

    if not file_id:
        await query.answer(
            "❌ File ID missing.",
            show_alert=True,
        )
        return

    await query.answer()

    try:
        sent_message = await bot.send_document(
            chat_id=query.message.chat.id,
            document=file_id,
            caption=(
                f"📄 {file_name}\n\n"
                "⏳ This file will be automatically deleted "
                "after 5 minutes.\n"
                "📥 Please download/save it before deletion."
            ),
        )

        asyncio.create_task(
            delete_file_later(
                query.message.chat.id,
                sent_message.message_id,
            )
        )

    except Exception as e:
        print("File send error:", e)

        await bot.send_message(
            chat_id=query.message.chat.id,
            text=(
                "❌ Failed to send the file.\n\n"
                "Please try again."
            ),
        )


# ============================================================
# BATCH
# ============================================================

@router.message(Command("batch"))
async def batch_handler(message: Message):
    user_id = message.from_user.id

    if str(user_id) != os.getenv("ADMIN_ID"):
        await message.answer(
            "❌ You are not authorized to use /batch."
        )
        return

    active_batches[user_id] = []

    await message.answer(
        "📤 Send your files one by one.\n\n"
        "Send multiple files and when finished use /finish."
    )


# ============================================================
# FINISH
# ============================================================

@router.message(Command("finish"))
async def finish_handler(message: Message):
    user_id = message.from_user.id

    if user_id not in active_batches:
        await message.answer(
            "❌ No active batch.\n\n"
            "Use /batch first."
        )
        return

    files = active_batches[user_id]

    if not files:
        await message.answer(
            "❌ No files received.\n\n"
            "Send at least one file."
        )
        return

    code = secrets.token_urlsafe(8)

    batch_data = {
        "code": code,
        "user_id": user_id,
        "files": files,
        "created_at": datetime.now(timezone.utc),
    }

    batches.insert_one(batch_data)

    del active_batches[user_id]

    me = await bot.get_me()

    share_link = (
        f"https://t.me/{me.username}?start={code}"
    )

    await message.answer(
        "✅ Batch created successfully!\n\n"
        f"📦 Files: {len(files)}\n\n"
        f"🔗 Share Link:\n{share_link}"
    )


# ============================================================
# STATS
# ============================================================

@router.message(Command("stats"))
async def stats_handler(message: Message):
    user_id = message.from_user.id

    if str(user_id) != os.getenv("ADMIN_ID"):
        await message.answer(
            "❌ You are not authorized to use /stats."
        )
        return

    total_batches = batches.count_documents({})

    pipeline = [
        {"$unwind": "$files"},
        {"$count": "total"},
    ]

    result = list(
        batches.aggregate(pipeline)
    )

    total_files = (
        result[0]["total"]
        if result
        else 0
    )

    unique_users = len(
        batches.distinct("user_id")
    )

    await message.answer(
        "📊 <b>Bot Statistics</b>\n\n"
        f"👥 Users: {unique_users}\n"
        f"📦 Total Batches: {total_batches}\n"
        f"📁 Total Files: {total_files}",
        parse_mode="HTML",
    )

# ============================================================
# FILTER SEARCH
# ============================================================

@router.message(lambda message: message.text is not None)
async def filter_search_handler(message: Message):

    # Commands ignore ചെയ്യുക
    if message.text.startswith("/"):
        return

    # Group / Supergroup മാത്രം
    if message.chat.type not in ("group", "supergroup"):
        return

    keyword = message.text.strip().lower()

    if not keyword:
        return

    filter_data = filters_collection.find_one(
        {"keyword": keyword}
    )

    if not filter_data:
        return

    buttons = filter_data.get("buttons", [])
    caption = filter_data.get("caption", "")
    photo_file_id = filter_data.get("photo_file_id")

    # --------------------------------------------------------
    # CREATE BUTTONS
    # --------------------------------------------------------

    keyboard = []

    for item in buttons:
        name = item.get("name")
        url = item.get("url")

        if not name or not url:
            continue

        keyboard.append([
            InlineKeyboardButton(
                text=f"{name}",
                url=url,
            )
        ])

    reply_markup = None

    if keyboard:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=keyboard
        )

    # --------------------------------------------------------
    # PHOTO RESULT
    # --------------------------------------------------------

    if photo_file_id:

        # Keep the poster caption inside Telegram's blockquote
        # style, matching the poster/result format.
        display_caption = caption or f"🔎 Search Results For: {keyword}"
        display_caption = f"<blockquote><b>{html.escape(display_caption)}</b></blockquote>"

        result_message = await bot.send_photo(
            chat_id=message.chat.id,
            photo=photo_file_id,
            caption=display_caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
            reply_to_message_id=message.message_id,
        )

    # --------------------------------------------------------
    # TEXT RESULT
    # Existing text-only filter support
    # --------------------------------------------------------

    else:

        result_message = await message.answer(
            f"🔎 <b>Search Results For: {keyword}</b>\n\n"
            f"{caption}\n\n"
            f"📁 Results: <b>{len(keyboard)}</b>",
            parse_mode="HTML",
            reply_markup=reply_markup,
            reply_to_message_id=message.message_id,
        )

    # --------------------------------------------------------
    # DELETE SEARCH RESULT AFTER 5 MINUTES
    # --------------------------------------------------------

    asyncio.create_task(
        delete_file_later(
            message.chat.id,
            result_message.message_id
        )
    )
    
# ============================================================
# FILE HANDLER
# ============================================================

@router.message()
async def file_handler(message: Message):
    user_id = message.from_user.id

    if user_id not in active_batches:
        return

    media = message.document or message.video

    if not media:
        await message.answer(
            "⚠️ Please send a document or video."
        )
        return

    
    file_data = {
        "file_id": media.file_id,
        "file_name": (
            getattr(media, "file_name", None)
            or (
                message.caption.strip()
                if message.caption
                else f"video_{len(active_batches[user_id]) + 1}.mp4"
            )
        ),
        "file_size": media.file_size,
        "mime_type": media.mime_type,
    }

    active_batches[user_id].append(file_data)

    count = len(active_batches[user_id])

    await message.answer(
        f"✅ File added\n\n"
        f"📄 {file_data['file_name']}\n"
        f"📦 Files in batch: {count}\n\n"
        f"Send another file or /finish"
    )
# ============================================================
# FASTAPI
# ============================================================

app = FastAPI()


@app.get("/")
@app.head("/")
async def health():
    return {
        "status": "running",
        "service": "Telegram File Share Bot",
    }


@app.on_event("startup")
async def startup():
    await bot.delete_webhook(
        drop_pending_updates=True
    )

    asyncio.create_task(
        dp.start_polling(bot)
    )

    print("🤖 Bot polling started")


@app.on_event("shutdown")
async def shutdown():
    await bot.session.close()
