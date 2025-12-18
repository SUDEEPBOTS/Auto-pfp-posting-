import os
import asyncio
import requests
import google.generativeai as genai
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from threading import Thread

# --- CONFIGURATION (Render Variables se uthayega) ---
API_ID = int(os.getenv("API_ID", "12345"))
API_HASH = os.getenv("API_HASH", "your_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_token")
MONGO_URL = os.getenv("MONGO_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = "b74e609faafda42e8"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OWNER_ID = 8228478790
CHANNEL_ID = -1003593852129
CHANNEL_LINK = "@Aesthetic_Channel" # Apna channel username yahan badlein

# Gemini 2.0 Flash Setup
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.0-flash-exp')

app_bot = Client("aesthetic_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["aesthetic_db"]["posted_images"]

# --- DECORATION (Blockquote & Stylish Text) ---
def get_caption(category):
    emoji = "👦" if category == "boys" else "👧"
    cap = (
        f"> ✨ **NEW {category.upper()} AESTHETIC PACK** {emoji}\n\n"
        f"**━━━━━━━━━━━━━━━━━━━━**\n"
        f"👤 **Type:** #{category.capitalize()} #Anime #PFP\n"
        f"📸 **Quantity:** 05 High Definition Pix\n"
        f"🎨 **Quality Control:** Gemini 2.0 AI\n"
        f"**━━━━━━━━━━━━━━━━━━━━**\n"
        f"🚀 **Join:** {CHANNEL_LINK}"
    )
    return cap

# --- CORE LOGIC ---
async def fetch_images(query):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {'q': query, 'cx': GOOGLE_CSE_ID, 'key': GOOGLE_API_KEY, 'searchType': 'image', 'num': 20}
    try:
        res = requests.get(url, params=params).json()
        return [item['link'] for item in res.get('items', [])]
    except: return []

async def check_with_gemini(image_url, category):
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200: return False
        img_data = response.content
        prompt = f"Analyze this image. Is it a high-quality aesthetic anime or real-life {category} pfp? Answer only 'Yes' or 'No'."
        result = gemini_model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': img_data}])
        return "Yes" in result.text
    except: return False

async def post_pack(category):
    query = f"{category} aesthetic pfp anime 4k"
    links = await fetch_images(query)
    
    final_list = []
    for link in links:
        if not await db.find_one({"url": link}): # Duplicate check
            if await check_with_gemini(link, category): # Gemini filter
                final_list.append(link)
                await db.insert_one({"url": link, "category": category})
        if len(final_list) == 5: break

    if len(final_list) == 5:
        caption = get_caption(category)
        media = [InputMediaPhoto(final_list[0], caption=caption)]
        for img in final_list[1:]:
            media.append(InputMediaPhoto(img))
        await app_bot.send_media_group(CHANNEL_ID, media)

# --- KEEP ALIVE SERVER ---
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Bot is Alive!"

def run_flask():
    web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- SCHEDULER (4 times a day) ---
def auto_job():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(post_pack("boys"))
    loop.run_until_complete(post_pack("girls"))

scheduler = BackgroundScheduler()
scheduler.add_job(auto_job, 'cron', hour='0,6,12,18')
scheduler.start()

# --- OWNER HANDLERS ---
@app_bot.on_message(filters.command("start") & filters.user(OWNER_ID))
async def start_msg(client, message):
    btns = InlineKeyboardMarkup([[
        InlineKeyboardButton("Manual Post Boys 👦", callback_data="do_boys"),
        InlineKeyboardButton("Manual Post Girls 👧", callback_data="do_girls")
    ]])
    await message.reply_text("✨ **Aesthetic PFP Bot**\nStatus: 24/7 Active\nAI: Gemini 2.0 Flash", reply_markup=btns)

@app_bot.on_callback_query(filters.user(OWNER_ID))
async def btn_callback(client, cb):
    cat = "boys" if cb.data == "do_boys" else "girls"
    await cb.answer(f"AI is picking best {cat} pics...")
    await post_pack(cat)
    await cb.message.edit_text(f"✅ Successful! 5 {cat.capitalize()} pics posted to channel.")

if __name__ == "__main__":
    Thread(target=run_flask).start()
    app_bot.run()
  
