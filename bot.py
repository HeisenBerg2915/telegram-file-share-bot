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
    InlineKeyboardButton
)


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing")


# =========================
# MongoDB
# =========================

mongo = MongoClient(MONGO_URI)

db = mongo["file_share_bot"]
batches = db["batches"]


# =========================
# Telegram
# =========================

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

router = Router()

dp.include_router(router)


# =========================
# Temporary active batches
# =========================

active_batches = {}


# =========================
# Pagination Settings
# =========================

FILES_PER_PAGE = 4


# =========================
# Delete Single File
# =========================

async def delete_file_later(chat_id, message_id):

    # 5 minutes
    await asyncio.sleep(300)

    try:

        await bot.delete_message(
            chat_id=chat_id,
            message_id=message_id
        )

        print(
            f"Auto-deleted file message: "
            f"{message_id}"
        )

    except Exception as e:

        print(
            f"Auto-delete error for "
            f"{message_id}: {e}"
        )


# =========================
# Create File List Keyboard
# =========================

def create_file_keyboard(
    code,
    files,
    page=0
):

    total_files = len(files)

    total_pages = (
        (total_files + FILES_PER_PAGE - 1)
        // FILES_PER_PAGE
    )

    start = page * FILES_PER_PAGE

    end = start + FILES_PER_PAGE

    page_files = files[start:end]


    keyboard = []


    # =========================
    # File Buttons
    # =========================

    for index, file in enumerate(
        page_files,
        start=start
    ):

        file_name = file.get(
            "file_name",
            "Unnamed file"
        )


        # Telegram button text
        # should not become too long
        if len(file_name) > 45:

            file_name = (
                file_name[:42] + "..."
            )


        keyboard.append([

            InlineKeyboardButton(

                text=f"📄 {file_name}",

                callback_data=(
                    f"file:{code}:{index}"
                )
            )

        ])


    # =========================
    # Page Navigation
    # =========================

    navigation = []


    # Back button
    if page > 0:

        navigation.append(

            InlineKeyboardButton(

                text="⬅️ BACK",

                callback_data=(
                    f"page:{code}:{page - 1}"
                )
            )

        )


    # Next button
    if page < total_pages - 1:

        navigation.append(

            InlineKeyboardButton(

                text="NEXT ➡️",

                callback_data=(
                    f"page:{code}:{page + 1}"
                )
            )

        )


    if navigation:

        keyboard.append(
            navigation
        )


    # =========================
    # Page Indicator
    # =========================

    keyboard.append([

        InlineKeyboardButton(

            text=f"{page + 1}/{total_pages}",

            callback_data="page_info"

        )

    ])


    return InlineKeyboardMarkup(
        inline_keyboard=keyboard
    )


# =========================
# /start
# =========================

@router.message(Command("start"))
async def start_handler(message: Message):
    parts = message.text.split(maxsplit=1)

    if len(parts) == 1:
        keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(
                text="👥 Jᴏɪɴ ᴏʀᴜ Gʀᴏᴜᴘ 👥",
                url="https://t.me/+Ik14BdOewjQzYjI1"
            )
        ],
        [
            InlineKeyboardButton(
                text="📌 Jᴏɪɴ Uᴘᴅᴀᴛᴇ Cʜᴀɴɴᴇʟ 📌",
                url="https://t.me/Clmainchannel"
            )
        ]
    ]
        )

        await message.answer(
            "👋 <b>Welcome!</b>\n\n"
            "🤖 <b>ഞാൻ ഒരു Fɪʟᴇ Sʜᴀʀɪɴɢ Bᴏᴛ ആണ്.</b>\n"
            "🎬 <b>ചിത്രലോകം ഗ്രൂപ്പിന് വേണ്ടി മാത്രം എന്നെ നിർമ്മിച്ചിരിക്കുന്നു. ❤️</b>",
            parse_mode="HTML",
            reply_markup=keyboard
        )
        return

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
        page=0
    )

    sent_message = await message.answer(
    "📦 <b>Available Files</b>\n\n"
    "📄 Select a file below to download it.",
    parse_mode="HTML",
    reply_markup=keyboard
)

asyncio.create_task(
    delete_file_later(
        message.chat.id,
        sent_message.message_id
    )
)
    
    # =========================
    # Normal /start
    # =========================

    if len(parts) == 1:

        await message.answer(

            "👋 Welcome!\n\n"

            "Use /batch to create "
            "a file batch."
        )

        return


    # =========================
    # Share Code
    # =========================

    code = parts[1]


    batch = batches.find_one({

        "code": code

    })


    if not batch:

        await message.answer(

            "❌ Batch not found."
        )

        return


    files = batch.get(
        "files",
        []
    )


    if not files:

        await message.answer(

            "❌ No files found."
        )

        return


    # =========================
    # File List
    # =========================

    keyboard = create_file_keyboard(

        code=code,

        files=files,

        page=0

    )


    await message.answer(

        "📦 <b>Available Files</b>\n\n"

        "📄 Select a file below "
        "to download it.",

        parse_mode="HTML",

        reply_markup=keyboard

    )


# =========================
# Pagination Callback
# =========================

@router.callback_query(
    lambda query:
        query.data.startswith("page:")
)
async def pagination_handler(
    query: CallbackQuery
):

    try:

        _, code, page_str = (
            query.data.split(":")
        )

        page = int(page_str)

    except Exception:

        await query.answer(
            "❌ Invalid page.",
            show_alert=True
        )

        return


    # =========================
    # Find Batch
    # =========================

    batch = batches.find_one({

        "code": code

    })


    if not batch:

        await query.answer(

            "❌ Batch not found.",

            show_alert=True

        )

        return


    files = batch.get(
        "files",
        []
    )


    if not files:

        await query.answer(

            "❌ No files found.",

            show_alert=True

        )

        return


    # =========================
    # Validate Page
    # =========================

    total_pages = (

        (len(files) + FILES_PER_PAGE - 1)
        // FILES_PER_PAGE

    )


    if page < 0 or page >= total_pages:

        await query.answer(

            "❌ Invalid page.",

            show_alert=True

        )

        return


    # =========================
    # Update Keyboard
    # =========================

    keyboard = create_file_keyboard(

        code=code,

        files=files,

        page=page

    )


    try:

        await query.message.edit_reply_markup(

            reply_markup=keyboard

        )

    except Exception as e:

        print(
            "Pagination error:",
            e
        )


    await query.answer()


# =========================
# Page Info Button
# =========================

@router.callback_query(
    lambda query:
        query.data == "page_info"
)
async def page_info_handler(
    query: CallbackQuery
):

    await query.answer(
        "📄 Select a file to download it.",
        show_alert=False
    )


# =========================
# File Button Callback
# =========================

@router.callback_query(
    lambda query:
        query.data.startswith("file:")
)
async def file_callback_handler(
    query: CallbackQuery
):

    try:

        _, code, index_str = (
            query.data.split(":")
        )

        index = int(index_str)

    except Exception:

        await query.answer(

            "❌ Invalid file.",

            show_alert=True

        )

        return


    # =========================
    # Find Batch
    # =========================

    batch = batches.find_one({

        "code": code

    })


    if not batch:

        await query.answer(

            "❌ Batch not found.",

            show_alert=True

        )

        return


    files = batch.get(
        "files",
        []
    )


    # =========================
    # Validate File Index
    # =========================

    if index < 0 or index >= len(files):

        await query.answer(

            "❌ File not found.",

            show_alert=True

        )

        return


    file = files[index]


    file_id = file.get(
        "file_id"
    )


    file_name = file.get(

        "file_name",

        "Unnamed file"

    )


    if not file_id:

        await query.answer(

            "❌ File ID missing.",

            show_alert=True

        )

        return


    # Stop Telegram loading animation
    await query.answer()


    # =========================
    # Send Selected File
    # =========================

    try:

        sent_message = await bot.send_document(

            chat_id=query.message.chat.id,

            document=file_id,

            caption=(

                f"📄 {file_name}\n\n"

                "⏳ This file will be "
                "automatically deleted "
                "after 5 minutes.\n"

                "📥 Please download/save "
                "it before deletion."

            )

        )


        # =========================
        # Schedule Auto Delete
        # =========================

        asyncio.create_task(

            delete_file_later(

                query.message.chat.id,

                sent_message.message_id

            )

        )


    except Exception as e:

        print(

            "File send error:",

            e

        )

        await bot.send_message(

            chat_id=query.message.chat.id,

            text=(

                "❌ Failed to send the file.\n\n"

                "Please try again."

            )

        )


# =========================
# /batch
# =========================

@router.message(Command("batch"))
async def batch_handler(message: Message):

    user_id = message.from_user.id


    # =========================
    # Admin Only
    # =========================

    if str(user_id) != os.getenv("ADMIN_ID"):

        await message.answer(

            "❌ You are not authorized "
            "to use /batch."

        )

        return


    active_batches[user_id] = []


    await message.answer(

        "📤 Send your files one by one.\n\n"

        "Send multiple files and when "
        "finished use /finish."

    )


# =========================
# /finish
# =========================

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


    # =========================
    # Generate Share Code
    # =========================

    code = secrets.token_urlsafe(8)


    batch_data = {

        "code": code,

        "user_id": user_id,

        "files": files,

        "created_at":
            datetime.now(timezone.utc)

    }


    # =========================
    # Save to MongoDB
    # =========================

    batches.insert_one(
        batch_data
    )


    # =========================
    # Clear Active Batch
    # =========================

    del active_batches[user_id]


    # =========================
    # Get Bot Username
    # =========================

    me = await bot.get_me()


    # =========================
    # Share Link
    # =========================

    share_link = (

        f"https://t.me/"

        f"{me.username}"

        f"?start={code}"

    )


    await message.answer(

        "✅ Batch created successfully!\n\n"

        f"📦 Files: {len(files)}\n\n"

        f"🔗 Share Link:\n"

        f"{share_link}"

    )


# =========================
# /stats
# =========================

@router.message(Command("stats"))
async def stats_handler(message: Message):

    user_id = message.from_user.id


    # =========================
    # Admin Only
    # =========================

    if str(user_id) != os.getenv("ADMIN_ID"):

        await message.answer(

            "❌ You are not authorized "
            "to use /stats."

        )

        return


    # =========================
    # Total Batches
    # =========================

    total_batches = (

        batches.count_documents({})

    )


    # =========================
    # Total Files
    # =========================

    pipeline = [

        {

            "$unwind": "$files"

        },

        {

            "$count": "total"

        }

    ]


    result = list(

        batches.aggregate(

            pipeline

        )

    )


    total_files = (

        result[0]["total"]

        if result

        else 0

    )


    # =========================
    # Unique Users
    # =========================

    unique_users = len(

        batches.distinct(

            "user_id"

        )

    )


    await message.answer(

        "📊 <b>Bot Statistics</b>\n\n"

        f"👥 Users: {unique_users}\n"

        f"📦 Total Batches: "
        f"{total_batches}\n"

        f"📁 Total Files: "
        f"{total_files}",

        parse_mode="HTML"

    )


# =========================
# Receive Files
# =========================

@router.message()
async def file_handler(message: Message):

    user_id = message.from_user.id


    # =========================
    # No Active Batch
    # =========================

    if user_id not in active_batches:

        return


    # =========================
    # Only Documents
    # =========================

    if not message.document:

        await message.answer(

            "⚠️ Please send the file "
            "as a document."

        )

        return


    document = message.document


    file_data = {

        "file_id":
            document.file_id,

        "file_name":
            document.file_name,

        "file_size":
            document.file_size,

        "mime_type":
            document.mime_type

    }


    # =========================
    # Add File
    # =========================

    active_batches[user_id].append(

        file_data

    )


    count = len(

        active_batches[user_id]

    )


    await message.answer(

        f"✅ File added\n\n"

        f"📄 {document.file_name}\n"

        f"📦 Files in batch: {count}\n\n"

        f"Send another file or /finish"

    )


# =========================
# FastAPI
# =========================

app = FastAPI()


# =========================
# Health Check
# =========================

@app.get("/")
async def health():

    return {

        "status": "running",

        "service":
            "Telegram File Share Bot"

    }


# =========================
# Startup
# =========================

@app.on_event("startup")
async def startup():

    # Remove webhook
    await bot.delete_webhook(

        drop_pending_updates=True

    )


    # Start polling
    asyncio.create_task(

        dp.start_polling(bot)

    )


    print(

        "🤖 Bot polling started"

    )


# =========================
# Shutdown
# =========================

@app.on_event("shutdown")
async def shutdown():

    await bot.session.close()
