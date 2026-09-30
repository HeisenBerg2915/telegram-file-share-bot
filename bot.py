import os
import asyncio
import secrets
import re
import json
from datetime import datetime, timezone
from urllib.parse import quote
from urllib.request import Request, urlopen

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
TMDB_TOKEN = os.getenv("TMDB_TOKEN")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

if not MONGO_URI:
    raise RuntimeError("MONGO_URI is missing")

if not TMDB_TOKEN:
    raise RuntimeError("TMDB_TOKEN is missing")


# =========================
# MONGODB
# =========================

mongo = MongoClient(MONGO_URI)

db = mongo["file_share_bot"]
batches = db["batches"]


# =========================
# TELEGRAM
# =========================

bot = Bot(token=BOT_TOKEN)

dp = Dispatcher()

router = Router()

dp.include_router(router)


# =========================
# ACTIVE BATCHES
# =========================

active_batches = {}

FILES_PER_PAGE = 4


# =========================
# AUTO DELETE
# =========================

async def delete_file_later(chat_id, message_id):
    await asyncio.sleep(300)

    try:
        await bot.delete_message(
            chat_id=chat_id,
            message_id=message_id,
        )

        print(
            f"Auto-deleted message: {message_id}"
        )

    except Exception as e:
        print(
            f"Auto-delete error for {message_id}: {e}"
        )


# =========================
# CLEAN FILE NAME
# =========================

def clean_movie_name(file_name):
    if not file_name:
        return ""

    name = os.path.splitext(file_name)[0]

    # Replace separators
    name = name.replace(".", " ")
    name = name.replace("_", " ")

    # Remove common quality/release tags
    patterns = [
        r"\b\d{3,4}p\b",
        r"\b4k\b",

        r"\bWEB[- ]?DL\b",
        r"\bWEB[- ]?Rip\b",
        r"\bWEBRip\b",
        r"\bBluRay\b",
        r"\bBRRip\b",
        r"\bHDRip\b",
        r"\bHDTV\b",
        r"\bDVDRip\b",

        r"\bx264\b",
        r"\bx265\b",
        r"\bHEVC\b",

        r"\bAAC\b",
        r"\bDDP?\b",
        r"\b5\.1\b",

        r"\b10bit\b",
        r"\b8bit\b",

        r"\bESub\b",
        r"\bESubs\b",

        r"\bMulti\b",
        r"\bDual Audio\b",

        r"\bMalayalam\b",
        r"\bTamil\b",
        r"\bTelugu\b",
        r"\bHindi\b",
        r"\bEnglish\b",

        r"\bS\d{1,2}E\d{1,2}\b",
        r"\bS\d{1,2}\b",

        r"\bSeason\s+\d+\b",
        r"\bEpisode\s+\d+\b",
    ]

    for pattern in patterns:
        name = re.sub(
            pattern,
            " ",
            name,
            flags=re.IGNORECASE,
        )

    # Remove brackets
    name = re.sub(
        r"[\[\]\(\)\{\}]",
        " ",
        name,
    )

    # Remove repeated spaces
    name = re.sub(
        r"\s+",
        " ",
        name,
    ).strip()

    return name


# =========================
# TMDB REQUEST
# =========================

def tmdb_request(endpoint):

    url = (
        "https://api.themoviedb.org/3/"
        + endpoint
    )

    request = Request(
        url,
        headers={
            "Authorization": (
                f"Bearer {TMDB_TOKEN}"
            ),
            "accept": "application/json",
        },
    )

    with urlopen(
        request,
        timeout=10,
    ) as response:

        return json.loads(
            response.read().decode(
                "utf-8"
            )
        )


# =========================
# SEARCH TMDB
# =========================

def search_tmdb(movie_name):

    if not movie_name:
        return None

    encoded_name = quote(
        movie_name
    )

    # -------------------------
    # MOVIE SEARCH
    # -------------------------

    try:

        movie_data = tmdb_request(
            "search/movie"
            f"?query={encoded_name}"
            "&include_adult=false"
            "&language=en-US"
            "&page=1"
        )

        movie_results = (
            movie_data.get(
                "results",
                []
            )
        )

        for result in movie_results:

            if result.get(
                "poster_path"
            ):

                return result

    except Exception as e:

        print(
            "TMDB movie search error:",
            e
        )


    # -------------------------
    # TV SEARCH
    # -------------------------

    try:

        tv_data = tmdb_request(
            "search/tv"
            f"?query={encoded_name}"
            "&include_adult=false"
            "&language=en-US"
            "&page=1"
        )

        tv_results = (
            tv_data.get(
                "results",
                []
            )
        )

        for result in tv_results:

            if result.get(
                "poster_path"
            ):

                return result

    except Exception as e:

        print(
            "TMDB TV search error:",
            e
        )

    return None


# =========================
# GET POSTER
# =========================

async def get_movie_poster(
    file_name
):

    movie_name = clean_movie_name(
        file_name
    )

    if not movie_name:
        return None, ""

    print(
        "Searching TMDB for:",
        movie_name
    )

    try:

        result = await asyncio.to_thread(
            search_tmdb,
            movie_name,
        )

        if not result:

            print(
                "No TMDB result found:",
                movie_name
            )

            return None, movie_name

        poster_path = result.get(
            "poster_path"
        )

        if not poster_path:

            return None, movie_name

        poster_url = (
            "https://image.tmdb.org/t/p/w500"
            + poster_path
        )

        print(
            "Poster found:",
            poster_url
        )

        return poster_url, movie_name

    except Exception as e:

        print(
            "Poster search error:",
            e
        )

        return None, movie_name


# =========================
# FILE KEYBOARD
# =========================

def create_file_keyboard(
    code,
    files,
    page=0,
):

    total_files = len(files)

    total_pages = (
        total_files
        + FILES_PER_PAGE
        - 1
    ) // FILES_PER_PAGE

    start = (
        page
        * FILES_PER_PAGE
    )

    end = (
        start
        + FILES_PER_PAGE
    )

    page_files = files[
        start:end
    ]

    keyboard = []


    # -------------------------
    # FILE BUTTONS
    # -------------------------

    for index, file in enumerate(
        page_files,
        start=start,
    ):

        file_name = (
            file.get(
                "file_name"
            )
            or "Unnamed file"
        )

        if len(file_name) > 45:

            file_name = (
                file_name[:42]
                + "..."
            )

        keyboard.append([
            InlineKeyboardButton(
                text=(
                    f"📄 {file_name}"
                ),
                callback_data=(
                    f"file:{code}:{index}"
                ),
            )
        ])


    # -------------------------
    # NAVIGATION
    # -------------------------

    navigation = []


    if page > 0:

        navigation.append(
            InlineKeyboardButton(
                text="⬅️ BACK",
                callback_data=(
                    f"page:{code}:"
                    f"{page - 1}"
                ),
            )
        )


    if page < total_pages - 1:

        navigation.append(
            InlineKeyboardButton(
                text="NEXT ➡️",
                callback_data=(
                    f"page:{code}:"
                    f"{page + 1}"
                ),
            )
        )


    if navigation:

        keyboard.append(
            navigation
        )


    # -------------------------
    # PAGE NUMBER
    # -------------------------

    keyboard.append([
        InlineKeyboardButton(
            text=(
                f"{page + 1}/"
                f"{total_pages}"
            ),
            callback_data="page_info",
        )
    ])


    return InlineKeyboardMarkup(
        inline_keyboard=keyboard
    )


# =========================
# START
# =========================

@router.message(
    Command("start")
)
async def start_handler(
    message: Message
):

    parts = message.text.split(
        maxsplit=1
    )


    # =========================
    # NORMAL START
    # =========================

    if len(parts) == 1:

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[

                [
                    InlineKeyboardButton(
                        text=(
                            "👥 Jᴏɪɴ ᴏʀᴜ "
                            "Gʀᴏᴜᴘ 👥"
                        ),
                        url=(
                            "https://t.me/"
                            "+Ik14BdOewjQzYjI1"
                        ),
                    )
                ],

                [
                    InlineKeyboardButton(
                        text=(
                            "📌 Jᴏɪɴ Uᴘᴅᴀᴛᴇ "
                            "Cʜᴀɴɴᴇʟ 📌"
                        ),
                        url=(
                            "https://t.me/"
                            "Clmainchannel"
                        ),
                    )
                ],

            ]
        )


        await message.answer(

            "👋 <b> Wᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ "
            "Dʀᴏᴘ Zᴏɴᴇ ⚡</b>\n\n"

            "🤖 <b>ഞാൻ ഒരു Fɪʟᴇ "
            "Sʜᴀʀɪɴɢ Bᴏᴛ ആണ്.</b>\n"

            "🎬 <b>ചിത്രലോകം ഗ്രൂപ്പിന് വേണ്ടി "
            "മാത്രം എന്നെ നിർമ്മിച്ചിരിക്കുന്നു. ❤️</b>",

            parse_mode="HTML",

            reply_markup=keyboard,
        )

        return


    # =========================
    # SHARE LINK
    # =========================

    code = parts[1]

    batch = batches.find_one(
        {
            "code": code
        }
    )


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


    keyboard = create_file_keyboard(
        code=code,
        files=files,
        page=0,
    )


    # =========================
    # GET POSTER + QUERY
    # =========================

    poster_url = batch.get(
        "poster_url"
    )

    query_name = batch.get(
        "query_name"
    )


    if not poster_url:

        first_file_name = (
            files[0].get(
                "file_name"
            )
        )

        poster_url, query_name = (
            await get_movie_poster(
                first_file_name
            )
        )


        if poster_url:

            batches.update_one(
                {
                    "code": code
                },
                {
                    "$set": {
                        "poster_url":
                            poster_url,
                        "query_name":
                            query_name,
                    }
                },
            )


    if not query_name:

        query_name = clean_movie_name(
            files[0].get(
                "file_name"
            )
        )


    # =========================
    # CAPTION
    # =========================

    caption = (
        "Found Results For Your Query "
        f"{query_name}"
    )


    # =========================
    # SEND POSTER
    # =========================

    if poster_url:

        try:

            sent_message = (
                await message.answer_photo(
                    photo=poster_url,

                    caption=caption,

                    reply_markup=keyboard,
                )
            )

        except Exception as e:

            print(
                "Poster send error:",
                e
            )

            sent_message = (
                await message.answer(
                    caption,
                    reply_markup=keyboard,
                )
            )

    else:

        sent_message = (
            await message.answer(
                caption,
                reply_markup=keyboard,
            )
        )


    # =========================
    # AUTO DELETE
    # =========================

    asyncio.create_task(
        delete_file_later(
            message.chat.id,
            sent_message.message_id,
        )
    )


# =========================
# PAGINATION
# =========================

@router.callback_query(
    lambda query:
        query.data
        and query.data.startswith(
            "page:"
        )
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
            show_alert=True,
        )

        return


    batch = batches.find_one(
        {
            "code": code
        }
    )


    if not batch:

        await query.answer(
            "❌ Batch not found.",
            show_alert=True,
        )

        return


    files = batch.get(
        "files",
        []
    )


    if not files:

        await query.answer(
            "❌ No files found.",
            show_alert=True,
        )

        return


    total_pages = (
        len(files)
        + FILES_PER_PAGE
        - 1
    ) // FILES_PER_PAGE


    if (
        page < 0
        or page >= total_pages
    ):

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

        print(
            "Pagination error:",
            e
        )


    await query.answer()


# =========================
# PAGE INFO
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
        show_alert=False,
    )


# =========================
# FILE DOWNLOAD
# =========================

@router.callback_query(
    lambda query:
        query.data
        and query.data.startswith(
            "file:"
        )
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
            show_alert=True,
        )

        return


    batch = batches.find_one(
        {
            "code": code
        }
    )


    if not batch:

        await query.answer(
            "❌ Batch not found.",
            show_alert=True,
        )

        return


    files = batch.get(
        "files",
        []
    )


    if (
        index < 0
        or index >= len(files)
    ):

        await query.answer(
            "❌ File not found.",
            show_alert=True,
        )

        return


    file = files[index]

    file_id = file.get(
        "file_id"
    )

    file_name = (
        file.get(
            "file_name"
        )
        or "Unnamed file"
    )


    if not file_id:

        await query.answer(
            "❌ File ID missing.",
            show_alert=True,
        )

        return


    await query.answer()


    try:

        sent_message = (
            await bot.send_document(

                chat_id=(
                    query.message.chat.id
                ),

                document=file_id,

                caption=(

                    f"📄 {file_name}\n\n"

                    "⏳ This file will be "
                    "automatically deleted "
                    "after 5 minutes.\n"

                    "📥 Please download/save "
                    "it before deletion."
                ),
            )
        )


        asyncio.create_task(
            delete_file_later(
                query.message.chat.id,
                sent_message.message_id,
            )
        )


    except Exception as e:

        print(
            "File send error:",
            e
        )


        await bot.send_message(

            chat_id=(
                query.message.chat.id
            ),

            text=(
                "❌ Failed to send "
                "the file.\n\n"
                "Please try again."
            ),
        )


# =========================
# BATCH
# =========================

@router.message(
    Command("batch")
)
async def batch_handler(
    message: Message
):

    user_id = (
        message.from_user.id
    )


    if str(user_id) != os.getenv(
        "ADMIN_ID"
    ):

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
# FINISH
# =========================

@router.message(
    Command("finish")
)
async def finish_handler(
    message: Message
):

    user_id = (
        message.from_user.id
    )


    if user_id not in active_batches:

        await message.answer(

            "❌ No active batch.\n\n"
            "Use /batch first."
        )

        return


    files = active_batches[
        user_id
    ]


    if not files:

        await message.answer(

            "❌ No files received.\n\n"
            "Send at least one file."
        )

        return


    code = secrets.token_urlsafe(
        8
    )


    # =========================
    # GET POSTER
    # =========================

    first_file_name = (
        files[0].get(
            "file_name"
        )
    )


    poster_url, query_name = (
        await get_movie_poster(
            first_file_name
        )
    )


    # =========================
    # SAVE BATCH
    # =========================

    batch_data = {

        "code": code,

        "user_id": user_id,

        "files": files,

        "poster_url": poster_url,

        "query_name": query_name,

        "created_at": datetime.now(
            timezone.utc
        ),
    }


    batches.insert_one(
        batch_data
    )


    del active_batches[
        user_id
    ]


    me = await bot.get_me()


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
# STATS
# =========================

@router.message(
    Command("stats")
)
async def stats_handler(
    message: Message
):

    user_id = (
        message.from_user.id
    )


    if str(user_id) != os.getenv(
        "ADMIN_ID"
    ):

        await message.answer(
            "❌ You are not authorized "
            "to use /stats."
        )

        return


    total_batches = (
        batches.count_documents({})
    )


    pipeline = [

        {
            "$unwind": "$files"
        },

        {
            "$count": "total"
        },

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

        parse_mode="HTML",
    )


# =========================
# FILE HANDLER
# =========================

@router.message()
async def file_handler(
    message: Message
):

    user_id = (
        message.from_user.id
    )


    if user_id not in active_batches:
        return


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
            document.mime_type,
    }


    active_batches[
        user_id
    ].append(
        file_data
    )


    count = len(
        active_batches[
            user_id
        ]
    )


    await message.answer(

        f"✅ File added\n\n"

        f"📄 {document.file_name}\n"

        f"📦 Files in batch: {count}\n\n"

        f"Send another file or /finish"
    )


# =========================
# FASTAPI
# =========================

app = FastAPI()


@app.get("/")
async def health():

    return {

        "status": "running",

        "service":
            "Telegram File Share Bot",
    }


@app.on_event(
    "startup"
)
async def startup():

    await bot.delete_webhook(
        drop_pending_updates=True
    )


    asyncio.create_task(
        dp.start_polling(bot)
    )


    print(
        "🤖 Bot polling started"
    )


@app.on_event(
    "shutdown"
)
async def shutdown():

    await bot.session.close()
