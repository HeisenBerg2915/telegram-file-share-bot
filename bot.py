import os
import asyncio
import secrets
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
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing")

mongo = MongoClient(MONGO_URI)
db = mongo["file_share_bot"]
batches = db["batches"]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

active_batches = {}

FILES_PER_PAGE = 4


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


def create_file_keyboard(code, files, page=0):
    total_files = len(files)
    total_pages = (total_files + FILES_PER_PAGE - 1) // FILES_PER_PAGE

    start = page * FILES_PER_PAGE
    end = start + FILES_PER_PAGE
    page_files = files[start:end]

    keyboard = []

    for index, file in enumerate(page_files, start=start):
        file_name = file.get("file_name") or "Unnamed file"

        if len(file_name) > 45:
            file_name = file_name[:42] + "..."

        keyboard.append([
            InlineKeyboardButton(
                text=f"📄 {file_name}",
                callback_data=f"file:{code}:{index}",
            )
        ])

    navigation = []

    if page > 0:
        navigation.append(
            InlineKeyboardButton(
                text="⬅️ BACK",
                callback_data=f"page:{code}:{page - 1}",
            )
        )

    if page < total_pages - 1:
        navigation.append(
            InlineKeyboardButton(
                text="NEXT ➡️",
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
            "👋 <b> Wᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ Dʀᴏᴘ Zᴏɴᴇ ⚡</b>\n\n"
            "🤖 <b>ഞാൻ ഒരു Fɪʟᴇ Sʜᴇᴀʀɪɴɢ Bᴏᴛ ആണ്.</b>\n"
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

    keyboard = create_file_keyboard(
        code=code,
        files=files,
        page=0,
    )

    sent_message = await message.answer(
        "📦 <b>Available Files</b>\n\n"
        "📄 Select a file below to download it.",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    # Result message auto-delete after 5 minutes
    asyncio.create_task(
        delete_file_later(
            message.chat.id,
            sent_message.message_id,
        )
    )


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


@router.callback_query(
    lambda query: query.data == "page_info"
)
async def page_info_handler(query: CallbackQuery):
    await query.answer(
        "📄 Select a file to download it.",
        show_alert=False,
    )


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
            text="❌ Failed to send the file.\n\n"
                 "Please try again.",
        )


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


@router.message()
async def file_handler(message: Message):
    user_id = message.from_user.id

    if user_id not in active_batches:
        return

    if not message.document:
        await message.answer(
            "⚠️ Please send the file as a document."
        )
        return

    document = message.document

    file_data = {
        "file_id": document.file_id,
        "file_name": document.file_name,
        "file_size": document.file_size,
        "mime_type": document.mime_type,
    }

    active_batches[user_id].append(file_data)

    count = len(active_batches[user_id])

    await message.answer(
        f"✅ File added\n\n"
        f"📄 {document.file_name}\n"
        f"📦 Files in batch: {count}\n\n"
        f"Send another file or /finish"
    )


app = FastAPI()


@app.get("/")
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
