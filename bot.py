import os
import asyncio
import secrets
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from pymongo import MongoClient

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message, Update


load_dotenv()


BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")


if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing")

# MongoDB
mongo = MongoClient(MONGO_URI)
db = mongo["file_share_bot"]
batches = db["batches"]


# Telegram
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
router = Router()

dp.include_router(router)


# Temporary active batches
active_batches = {}


# /start
@router.message(Command("start"))
async def start_handler(message: Message):
    parts = message.text.split(maxsplit=1)

    if len(parts) == 1:
        await message.answer(
            "👋 Welcome!\n\n"
            "Use /batch to create a file batch."
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

    await message.answer(
        f"📦 Sending {len(files)} files..."
    )

    for file in files:
        try:
            await bot.send_document(
                chat_id=message.chat.id,
                document=file["file_id"]
            )
        except Exception as e:
            print("File send error:", e)

    await message.answer("✅ All files sent.")


# /batch
@router.message(Command("batch"))
async def batch_handler(message: Message):
    user_id = message.from_user.id

    if str(user_id) != os.getenv("ADMIN_ID"):
        await message.answer("❌ You are not authorized to use /batch.")
        return

    active_batches[user_id] = []

    await message.answer(
        "📤 Send your files one by one.\n\n"
        "Send multiple files and when finished use /finish."
    )


# /finish
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
        "created_at": datetime.now(timezone.utc)
    }

    batches.insert_one(batch_data)

    del active_batches[user_id]

    me = await bot.get_me()

    share_link = f"https://t.me/{me.username}?start={code}"

    await message.answer(
        "✅ Batch created successfully!\n\n"
        f"📦 Files: {len(files)}\n\n"
        f"🔗 Share Link:\n{share_link}"
    )


# Receive files
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
        "mime_type": document.mime_type
    }

    active_batches[user_id].append(file_data)

    count = len(active_batches[user_id])

    await message.answer(
        f"✅ File added\n\n"
        f"📄 {document.file_name}\n"
        f"📦 Files in batch: {count}\n\n"
        f"Send another file or /finish"
    )


# FastAPI
app = FastAPI()


@app.get("/")
async def health():
    return {
        "status": "running",
        "service": "Telegram File Share Bot"
    }

@app.on_event("startup")
async def startup():
    await bot.delete_webhook(drop_pending_updates=True)

    asyncio.create_task(dp.start_polling(bot))

    print("🤖 Bot polling started")


@app.on_event("shutdown")
async def shutdown():
    await bot.session.close()
