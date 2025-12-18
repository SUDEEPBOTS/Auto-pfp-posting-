import os
import asyncio
import requests
import tempfile
from threading import Thread

from flask import Flask
from pyrogram import Client, filters
from pyrogram.types import InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton

from motor.motor_asyncio import AsyncIOMotorClient

import google.generativeai as genai
from google.generativeai.types import content_types


# ================= CONFIG =================

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")

MONGO_URL = os.getenv("MONGO_URL")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = "b74e609faafda42e8"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

OWNER_ID = 8228478790
CHANNEL_ID = -1003593852129
CHANNEL_LINK = "@Aesthetic_Channel"

# =========================================

genai.configure(api_key=GEMINI_API_KEY)
gemini = genai.GenerativeModel("gemini-2.5-flash")

bot = Client(
    "aesthetic_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

mongo = AsyncIOMotorClient(MONGO_URL)
db = mongo["aesthetic_db"]["images"]

web = Flask(__name__)


# ================= UTILS =================

def caption(category, pfp_type):
    emoji = "👦" if category == "boys" else "👧"
    return (
        f"> ✨ **NEW {category.upper()} AESTHETIC PFP PACK** {emoji}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 **Category:** #{category.capitalize()}\n"
        f"🎭 **Type:** {pfp_type}\n"
        f"📸 **Quality:** HD PFP\n"
        f"🤖 **Verified:** Gemini AI\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🚀 **Join:** {CHANNEL_LINK}"
    )


async def google_images(query):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "q": query,
        "cx": GOOGLE_CSE_ID,
        "key": GOOGLE_API_KEY,
        "searchType": "image",
        "num": 20
    }
    r = requests.get(url, params=params).json()
    return [i["link"] for i in r.get("items", [])]


async def download_image(url):
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            return None
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        tmp.write(r.content)
        tmp.close()
        return tmp.name, r.content
    except:
        return None


async def gemini_check(image_bytes):
    """
    Gemini image dekh kar batayega:
    - boy / girl
    - anime / real
    - pfp suitable hai ya nahi
    """
    blob = content_types.Blob(
        mime_type="image/jpeg",
        data=image_bytes
    )

    prompt = (
        "Analyze this image and answer strictly in this format:\n"
        "Gender: Boy or Girl\n"
        "Style: Anime or Real\n"
        "PFP: Yes or No\n"
    )

    res = gemini.generate_content([prompt, blob])
    text = res.text.lower()

    if "pfp: yes" not in text:
        return None

    gender = "boys" if "boy" in text else "girls"
    style = "Anime" if "anime" in text else "Real"

    return gender, style


# ================= CORE =================

async def post_pack(expected_category):
    print(f"[INFO] Searching {expected_category} images")

    links = await google_images(f"{expected_category} aesthetic pfp anime 4k")

    media = []
    pfp_style = "Unknown"

    for link in links:
        if await db.find_one({"url": link}):
            continue

        downloaded = await download_image(link)
        if not downloaded:
            continue

        file_path, img_bytes = downloaded

        gemini_result = await gemini_check(img_bytes)
        if not gemini_result:
            continue

        detected_category, style = gemini_result

        if detected_category != expected_category:
            continue

        pfp_style = style

        await db.insert_one({
            "url": link,
            "category": detected_category,
            "style": style
        })

        if not media:
            media.append(
                InputMediaPhoto(
                    file_path,
                    caption=caption(detected_category, style)
                )
            )
        else:
            media.append(InputMediaPhoto(file_path))

        print(f"[OK] Image approved: {style}")

        if len(media) == 5:
            break

    if len(media) < 5:
        print("[FAIL] Enough images not found")
        return False

    await bot.send_media_group(CHANNEL_ID, media)
    print("[SUCCESS] Posted to channel")
    return True


# ================= BOT =================

@bot.on_message(filters.command("start") & filters.user(OWNER_ID))
async def start(_, msg):
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Post Boys 👦", callback_data="boys"),
            InlineKeyboardButton("Post Girls 👧", callback_data="girls")
        ]
    ])
    await msg.reply(
        "✨ **Aesthetic PFP Bot Active**\n"
        "🤖 Gemini 2.5 Flash\n"
        "📦 MongoDB Enabled",
        reply_markup=kb
    )


@bot.on_callback_query(filters.user(OWNER_ID))
async def cb(_, q):
    await q.answer("AI working...")
    ok = await post_pack(q.data)
    if ok:
        await q.message.edit_text("✅ Posted Successfully")
    else:
        await q.message.edit_text("❌ Failed (Check logs)")


# ================= WEB =================

@web.route("/")
def home():
    return "Bot Online"


if __name__ == "__main__":
    Thread(
        target=lambda: web.run(
            host="0.0.0.0",
            port=int(os.getenv("PORT", 8080))
        )
    ).start()

    bot.run()
