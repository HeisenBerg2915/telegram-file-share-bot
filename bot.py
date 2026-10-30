import os
import asyncio
import secrets
import html
from datetime import datetime, timezone
from aiogram.types import BufferedInputFile
from pdf_generator import create_filters_pdf

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
REQUEST_CHANNEL_LINK = "https://t.me/+P1NVvQus-ugyNGE9"

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


# Caption tags to remove (case-insensitive)
TAGS = [
    "dvdwap.com", "Dvdworld", "DVDWORLD", "@ALBCINEMAS©", "@FC_HEVC", "[CF]", "DVDWO", "KC", "KC_", "MF", "themoviesboss", "MLM", "MZone", "MoviezzClub", "HDMVCOUNTER", "YMovieZNew",
    "A2MOVIES", "HDTCPREDVDFILES", "Tamil_Full_Movie",
    "@ADrama_Lovers", "@AVA", "@BuLLMovieee", "@BM_Links", "@BestMovie", "@T4TSA", "@CC", "@CC_All", "@CC_ALL_MOVIES2", "@CC_NEW", "@CC_X265",
    "@CCineClub", "@CCM", "@CMVLA", "@CE_Links", "@CMEHD", "@Clipmate_Movie_Team", "@CR_Rockers", "@cinecom88", " @Cinematic_world", "@Cinema Company", " @cinema_company", "@Cinema_Company", "@CINEMA_BUDDIES", "@Country_Fellows",
    "@Cinema_Kottaka", "@cinema library", "@CKMovies", "@CK_HEVC", "@CK_Moviez", "CT™️", "@CelluloidCineClub", " @colorkannadi_movies", "@C_V", "@CVM", "@DailyMovieZhunt", "@desimovies", "@DK_Drama", "@DM_LinkZzzz",
    "@DMovies", "@DramaOST", "@Dubbedmovies", " @DVDWOALL", "@DvdWap", "@E4E", "@E4E_Rockers", "Filmy4wap_xyz", "@FBM_x265", "@FBM_HW", "@FBM_New", "@FILIMHOUSE",
    "@FilmCage", "@Film_Kottaka", "@FrediesChannel", "@HEVC_Cinemaz", "@IM",
    "@HEVC_Moviesz", "@HOREK_ROKOM", "@HEVCHubX", "@Hk", "@IndianMoviez", "@KBO", "@KD_Deck", "@KGRockers",
    "@KW", "@KR", "@KannadaWarriors", "@KeralaBoxOffice", "@KL_ROCKERZ", "@lonelylinkss", "@Links2U", "@Linkz_MM", "@ᒪᕈT",
    "@M_Zone", "@mobile_mm", "Malayalam_Full_Movie", "@Mallu_Movies", "@malayalam movies", "@MAASFILE", "@MC", "@MC_4U", "@MinaKaze", "@MJ_Linkz", "@MJ_Moviez", "@MM", "@MM_Movies", "@MM_Linkz",
    "@MM_NEW", "@MM_ALL", "@MM_TvSeries", "@MOVIEHUNT", "@MOVIEZMOB", "@MPC", "@MalluRockers",
    "@Mallu_Rockers", "@mfmixsouth", "@Mc_South", "@MPC", "@MovieWorld2000", "@Movie_Hub", " @MM_Linkz", "@N3SSSS", "@bheeshmat",
    "@desimovies Telegram", "@favio", "@film_down_load", "@iMediaShare",
    "@infotainmentmedia", "@kickass_torrents", "@msp", "@moviescollection17",
    "@moviesdeveloper", "@MoviesTop10", "@MoviesWar", "@myflixx", "@NithinMovies", "@NRDramaa", "@nanacinemas", "@OB", "PDisk", "@PIT", "@PM",
    "@PM_Old", "@Qualitymovies", "@Rarefilms.", "@R_A_R_B_G", "@RickyChannel", "@RatedRMovies", "@Sky_MoviesHD", " @sherlibrary", "@SY_MS", "@telugu_moviez", "@TG UPDATES1",
    "@TN60_LinkzZ", "@TEAMxKL", "@TV 30NAMA1", "@TamilPrime_LinkZz", "@TamilDubbs", "@TamilMV", "@TGmovie9", "@TamilMV_Live", "@TamilRockers", "@Tamilmoviez",
    "@Tamil_HD_Movies_Requests", "@Tamil_Linkz", "Tamil_LinkZz", "@Tamil_LinkzZ", "@Tamil_Seriesz", "@TeamHDT", "@Team_HDT",
    "@Team_Hevc", "@Theprofffesorr", "@TR_Moviez", "@TR_Updates", "@Tv2Us",
    "@TvSeriesBay", "@UCDump", "@VR", "www_Movcr_cc", "@WMR", "@WorldCinemaToday", "@X265 E4E", "@YTSLT",
    "@cinemaheist", "@trolldcompany", "@yamandanmovies", "@Zee_Keralam_HD", "F&T",
    "www.",
    "www_DVDWap_Com_",
    "www_TamilMV_pw",
    "www_1TamilMV",
    "www_1TamilMV_fun",
    "www_1TamilMV_rodeo",
    "www_1TamilMV_fans",
    "www_1TamilMV_nl",
    "www_1TamilMV_art",
    "www_1TamilMV_org",
    "www_1TamilMV_eu",
    "www_1TamilMV_men",
    "www_1TamilMV_wtf",
    "www_1TamilMV_city",
    "www_1TamilMV_cafe",
    "www_1TamilMV_help",
    "www_1TamilMV_im",
    "www_1TamilMV_phd",
    "www_1TamilMV_one",
    "www_1TamilMV_guru",
    "www_1TamilMV_us",
    "www_1TamilMV_live",
    "www_1TamilMV_pw",
    "www_1TamilMV_life",
    "www_1TamilMV_me",
    "www_1TamilMV_vin",
    "www_1TamilMV_sbs",
    "www_1TamilMV_mx",
    "www_1TamilMV_team",
    "www_1TamilMV_cyou",
    "www_1TamilMV_pics",
    "www_1TamilMV_click",
    "www_1TamilMV_pro",
    "www_1TamilMV_lease",
    "www_1TamilMV_rocks",
    "www_1TamilMV_meme",
    "www_1TamilMV_ing",
    "www_1TamilMV_pizza",
    "www_1TamilMV_li",
    "www_1TamilMV_top",
    "www_1TamilMV_promo",
    "www_1TamilMV_gs",
    "www_1TamilMV_bio",
    "www_1TamilMV_xyz",
    "www.1TamilBlasters.dad",
    "www.1TamilMV.ac",
    "www.1TamilMV.cafe",
    "www.1TamilMV.eu",
    "www.1TamilMV.fans",
    "www.1TamilMV.fun",
    "www.1TamilMV.gold",
    "www.1TamilMV.gs",
    "www.1TamilMV.help",
    "www.1TamilMV.im",
    "www.1TamilMV.ing",
    "www.1TamilMV.lease",
    "www.1TamilMV.li",
    "www.1TamilMV.life",
    "www.1TamilMV.me",
    "www.1TamilMV.men",
    "www.1TamilMV.meme",
    "www.1TamilMV.mx",
    "www.1TamilMV.nl",
    "www.1TamilMV.one",
    "www.1TamilMV.org",
    "www.1TamilMV.phd",
    "www.1TamilMV.pics",
    "www.1TamilMV.pizza",
    "www.1TamilMV.pro",
    "www.1TamilMV.prof",
    "www.1TamilMV.promo",
    "www.1TamilMV.pw",
    "www.1TamilMV.rodeo",
    "www.1TamilMV.rocks",
    "www.1TamilMV.sbs",
    "www.1TamilMV.team",
    "www.1TamilMV.top",
    "www.1TamilMV.us",
    "www.1TamilMV.vin",
    "www.1TamilMV.wf",
    "www.1TamilMV.wtf",
    "www.1TamilMV.xyz",
    "www.1TamilMV.bio",
    "@mfmixsouth",
]


def clean_caption_tags(caption):
    """Remove configured source/channel tags from captions and tidy spacing."""
    import re

    cleaned = caption or ""
    # Remove longer tags first so partial entries do not interfere with full ones.
    for tag in sorted({str(t).strip() for t in TAGS if str(t).strip()}, key=len, reverse=True):
        if tag == "www.":
            # Remove a www-prefixed domain as a whole, rather than leaving the domain behind.
            cleaned = re.sub(r"(?i)\bwww\.[a-z0-9_-]+(?:\.[a-z0-9_-]+)*", "", cleaned)
        elif "*" in tag:
            pattern = re.escape(tag).replace(r"\*", r".*?")
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        else:
            cleaned = re.sub(re.escape(tag), "", cleaned, flags=re.IGNORECASE)

    # Tidy leftover separators and repeated whitespace after tag removal.
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"[ \t]*([|•·])(?:[ \t]*[|•·])+[ \t]*", " ", cleaned)
    cleaned = re.sub(r"[ \t]*[-_]{2,}[ \t]*", " ", cleaned)
    cleaned = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", cleaned)
    return cleaned.strip(" \t\n|•·-_")



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
    """Parse existing URL buttons plus alert buttons, preserving their order.

    Existing buttonurl and :same behavior is kept unchanged. New syntax:
    [Season 3](buttonalert:Message shown in popup)
    """
    import re

    pattern = r"\[([^\]]+)\]\((buttonurl|buttonalert):(.*?)\)"
    buttons = []

    for match in re.finditer(pattern, text or ""):
        name, button_type, raw_value = match.groups()
        name = name.strip()
        raw_value = raw_value.strip()

        if button_type == "buttonalert":
            buttons.append({
                "name": name,
                "type": "alert",
                "alert_text": raw_value,
                "same": False,
            })
            continue

        same = raw_value.endswith(":same")
        url = raw_value[:-5].strip() if same else raw_value
        buttons.append({
            "name": name,
            "url": url,
            "type": "url",
            "same": same,
        })

    return buttons

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
        r"\[([^\]]+)\]\(button(?:url|alert):[^)]*\)",
        "",
        source_text
    ).strip()
    clean_caption = clean_caption_tags(clean_caption)

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
            },
        ).sort("keyword", 1)
    )

    pdf_data = create_filters_pdf(filters)

    pdf_file = BufferedInputFile(
        pdf_data,
        filename="filters_report.pdf",
    )

    await message.answer_document(
        document=pdf_file,
        caption=(
            "📋 <b>Available Filters</b>\n\n"
            f"🔢 Total Filters: <b>{len(filters)}</b>"
        ),
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

def natural_sort_key(value):
    """Sort filenames in human/numeric order (Episode 2 before Episode 10)."""
    import re

    return [
        int(part) if part.isdigit() else part.casefold()
        for part in re.split(r"(\\d+)", str(value or ""))
    ]


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
        file_name = clean_caption_tags(file.get("file_name") or "Unnamed file")
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

    first_file_name = clean_caption_tags(files[0].get("file_name", "Unknown"))

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
        "<b>🎬 Your Requested Files Are Ready!</b>\n\n"
        "<b>📄 താഴെ നൽകിയിരിക്കുന്ന Button-ൽ നിന്ന് "
        "നിങ്ങൾക്ക് ആവശ്യമുള്ള File തിരഞ്ഞെടുക്കാം.</b>\n\n"
        "🔗 <a href='https://t.me/Flim_maxx'>"
        "<b>⟬ ᴛᴇᴀᴍ ғʟɪᴍ ᴍᴀxx ⟭</b></a>"
    ),
    parse_mode="HTML",
    reply_markup=keyboard
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
        bot_info = await bot.get_me()

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ",
                        url=f"https://t.me/{bot_info.username}?startgroup=true",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="ᴊᴏɪɴ ᴛᴏ ɢʀᴏᴜᴘ",
                        url="https://t.me/+Ik14BdOewjQzYjI1",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="ᴊᴏɪɴ ᴛᴏ ᴄʜᴀɴɴᴇʟ",
                        url="https://t.me/Flim_maxx",
                    )
                ],
            ]
        )

        await message.answer_photo(
            photo="https://d.uguu.se/KzaffnRn.jpg",
            caption=(
                "<b>ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ᴅʀᴏᴘ ᴢᴏɴᴇ ⚡</b>\n\n"
                "🤖 <b>ഞാൻ ഒരു Fɪʟᴇ Sʜᴀʀɪɴɢ Bᴏᴛ ആണ്.</b>\n"
                "🎬 <b> നിങ്ങൾക്ക് എന്നെ നിങ്ങളുടെ ഗ്രൂപ്പിലും യൂസ് ചെയ്യാം</b>"
            ),
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

    # Check whether the user already joined the channel
    try:
        member = await bot.get_chat_member(
            chat_id=REQUEST_CHANNEL_ID,
            user_id=user_id,
        )

        if member.status in ("member", "administrator", "creator"):
            await send_batch_result(
                chat_id=user_id,
                code=code,
            )
            return

    except Exception as e:
        print(f"Membership check error: {e}")

    pending_access[user_id] = code

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="ᴊᴏɪɴ ᴛᴏ ᴄʜᴀɴɴᴇʟ",
                    url=REQUEST_CHANNEL_LINK,
                )
            ],
            [
                InlineKeyboardButton(
                    text="ᴛʀʏ ᴀɢᴀɪɴ",
                    callback_data=f"check_join:{code}",
                )
            ],
        ]
    )

    await message.answer(
        "🔒 ഫയലുകൾ ലഭിക്കാൻ ആദ്യം ചാനലിൽ Join Request അയക്കുക.\n\n"
        "നിങ്ങളുടെ Request Approve ചെയ്തശേഷം TRY AGAIN അമർത്തുക.",
        reply_markup=keyboard,
    )
    return

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
            "❌ ഇത് നിങ്ങൾക്ക് ചെയ്യാൻ പറ്റില്ല Sorry..."
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

    if chat_id != REQUEST_CHANNEL_ID:
        return

    code = pending_access.get(user_id)

    if not code:
        return

    try:
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
    file_name = clean_caption_tags(file.get("file_name") or "Unnamed file")

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

    # Store files in natural filename order so the shared link displays
    # Episode 1, Episode 2, ... Episode 10 instead of lexicographic order.
    files.sort(key=lambda item: natural_sort_key(item.get("file_name", "")))

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
# FILTER ALERT BUTTON
# ============================================================

@router.callback_query(lambda query: query.data and query.data.startswith("filter_alert:"))
async def filter_alert_callback(query: CallbackQuery):
    """Show the alert text configured by the admin for a filter button."""
    try:
        _, filter_id, index_text = query.data.split(":", 2)
        from bson import ObjectId
        filter_data = filters_collection.find_one({"_id": ObjectId(filter_id)})
        index = int(index_text)
        button_items = (filter_data or {}).get("buttons", [])
        item = button_items[index]
        alert_text = (item.get("alert_text") or "").strip()
        if item.get("type") != "alert" or not alert_text:
            raise ValueError("Missing alert text")
    except Exception:
        await query.answer("This alert is no longer available.", show_alert=True)
        return

    # Telegram callback alert text is limited; truncate safely to Telegram's limit.
    await query.answer(alert_text[:200], show_alert=True)


# ============================================================
# FILTER SEARCH
# ============================================================

def normalize_filter_keyword(value: str) -> str:
    """Normalize keywords for case- and punctuation-insensitive matching."""
    return "".join(
        char for char in (value or "").casefold()
        if char.isalnum()
    )


def filter_keyword_matches(filter_keyword: str, user_query: str) -> bool:
    """Match a filter title inside a longer user search query."""
    import re

    ignored_words = {"the", "a", "an"}

    def clean_words(value):
        return [
            re.sub(r"[^\w]", "", word, flags=re.UNICODE)
            for word in (value or "").casefold().split()
        ]

    filter_words = [
        word for word in clean_words(filter_keyword) if word
    ]
    query_words = [
        word for word in clean_words(user_query) if word
    ]

    while filter_words and filter_words[0] in ignored_words:
        filter_words.pop(0)

    if not filter_words or not query_words:
        return False

    width = len(filter_words)

    return any(
        query_words[i:i + width] == filter_words
        for i in range(len(query_words) - width + 1)
    )


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

    # Exact matching first
    filter_data = filters_collection.find_one({"keyword": keyword})

    # Exact match ഇല്ലെങ്കിൽ normalized / partial matching
    if not filter_data:
        normalized_query = normalize_filter_keyword(keyword)

        if not normalized_query:
            return

        candidates = list(
            filters_collection.find(
                {},
                {
                    "keyword": 1,
                    "buttons": 1,
                    "caption": 1,
                    "photo_file_id": 1,
                },
            )
        )

        matches = []

        for candidate in candidates:
            candidate_keyword = candidate.get("keyword", "")

            if (
                normalize_filter_keyword(candidate_keyword)
                == normalized_query
                or filter_keyword_matches(candidate_keyword, keyword)
            ):
                matches.append(candidate)

        if matches:
            filter_data = max(
                matches,
                key=lambda item: len(
                    normalize_filter_keyword(item.get("keyword", ""))
                ),
            )

    # Matching filter ഇല്ലെങ്കിൽ നിർത്തുക
    if not filter_data:
        return

    # Filter data
    buttons = filter_data.get("buttons", [])
    caption = filter_data.get("caption", "")
    photo_file_id = filter_data.get("photo_file_id")

    # CREATE BUTTONS
    keyboard = []

    for index, item in enumerate(buttons):
        name = item.get("name")
        button_type = item.get("type", "url")  # old saved filters default to URL
        same = bool(item.get("same", False))

        if not name:
            continue

        if button_type == "alert":
            alert_text = (item.get("alert_text") or "").strip()
            if not alert_text:
                continue
            # Mongo filter _id + button index keeps callback_data short and stable.
            filter_id = str(filter_data.get("_id", ""))
            if not filter_id:
                continue
            button = InlineKeyboardButton(
                text=str(name),
                callback_data=f"filter_alert:{filter_id}:{index}",
            )
            # Alert buttons can be placed in the same row only if explicitly stored so;
            # new buttonalert syntax defaults to its own row.
        else:
            url = (item.get("url") or "").strip()

            # Keep legacy :same support for previously saved filters.
            if url.endswith(":same"):
                url = url[:-5].strip()
                same = True

            if not url:
                continue

            button = InlineKeyboardButton(text=str(name), url=url)

        if same and keyboard:
            keyboard[-1].append(button)
        else:
            keyboard.append([button])

    reply_markup = None

    if keyboard:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=keyboard
        )

    # PHOTO RESULT
    if photo_file_id:
        display_caption = (
            clean_caption_tags(caption)
            or f"🔎 Search Results For: {keyword}"
        )

        display_caption = (
            f"<blockquote><b>"
            f"{html.escape(display_caption)}"
            f"</b></blockquote>"
        )

        result_message = await bot.send_photo(
            chat_id=message.chat.id,
            photo=photo_file_id,
            caption=display_caption,
            parse_mode="HTML",
            reply_markup=reply_markup,
            reply_to_message_id=message.message_id,
        )

    # TEXT RESULT
    else:
        clean_text = clean_caption_tags(caption)

        result_message = await message.answer(
            f"🔎 <b>Search Results For: "
            f"{html.escape(keyword)}</b>\n\n"
            f"{html.escape(clean_text)}\n\n"
            f"📁 Results: <b>{len(keyboard)}</b>",
            parse_mode="HTML",
            reply_markup=reply_markup,
            reply_to_message_id=message.message_id,
        )

    # Search result 5 മിനിറ്റിനു ശേഷം delete ചെയ്യുക
    asyncio.create_task(
        delete_file_later(
            message.chat.id,
            result_message.message_id,
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

    file_name = (
        getattr(media, "file_name", None)
        or (
            message.caption.strip()
            if message.caption
            else f"video_{len(active_batches[user_id]) + 1}.mp4"
        )
    )

    # Remove @spotyseries from filename
    file_name = clean_caption_tags(file_name)
    file_name = file_name.replace("@spotyseries", "").strip()

    file_data = {
        "file_id": media.file_id,
        "file_name": file_name,
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
