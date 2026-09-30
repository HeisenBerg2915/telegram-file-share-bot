import os
import asyncio
import secrets
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from pymongo import MongoClient

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message


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
# Auto Delete Function
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
            f"Deleted file message: {message_id}"
        )

    except Exception as e:
        print(
            f"Auto-delete error: {e}"
        )


# =========================
# /start
# =========================

@router.message(Command("start"))
async def start_handler(message: Message):

    parts = message.text.split(maxsplit=1)

    # Normal /start
    if len(parts) == 1:

        await message.answer(
            "👋 Welcome!\n\n"
            "Use /batch to create a file batch."
        )

        return


    # Share code
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


    # Sending message
    await message.answer(
        f"📦 Sending {len(files)} files..."
    )


    # Send files
    for file in files:

        try:

            sent_message = await bot.send_document(

                chat_id=message.chat.id,

                document=file["file_id"],

                # File name as caption
                caption=file.get(
                    "file_name",
                    ""
                )
            )


            # Auto delete after 5 minutes
            asyncio.create_task(

                delete_file_later(

                    message.chat.id,

                    sent_message.message_id
                )
            )


        except Exception as e:

            print(
                "File send error:",
                e
            )


    # Auto delete information
    await message.answer(

        "ℹ️ <b>Auto-Delete Information</b>\n\n"

        "📁 All files sent above will be "
        "<b>automatically deleted after 5 minutes.</b>\n\n"

        "📥 Please download/save the files "
        "before they are deleted.",

        parse_mode="HTML"
    )


    await message.answer(
        "✅ All files sent."
    )


# =========================
# /batch
# =========================

@router.message(Command("batch"))
async def batch_handler(message: Message):

    user_id = message.from_user.id


    # Admin only
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


    # Generate share code
    code = secrets.token_urlsafe(8)


    batch_data = {

        "code": code,

        "user_id": user_id,

        "files": files,

        "created_at":
            datetime.now(timezone.utc)
    }


    # Save to MongoDB
    batches.insert_one(
        batch_data
    )


    # Clear active batch
    del active_batches[user_id]


    # Get bot username
    me = await bot.get_me()


    # Share link
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


    # Admin only
    if str(user_id) != os.getenv("ADMIN_ID"):

        await message.answer(
            "❌ You are not authorized "
            "to use /stats."
        )

        return


    # Total batches
    total_batches = (
        batches.count_documents({})
    )


    # Total files
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


    # Unique users
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


    # No active batch
    if user_id not in active_batches:

        return


    # Only documents
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


    # Add file
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


# Health check
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
