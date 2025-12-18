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

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID", "12345"))
API_HASH = os.getenv("API_HASH", "your_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_token")
MONGO_URL = os.getenv("MONGO_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = "b74e609faafda42e8"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OWNER_ID = 8228478790
CHANNEL_ID = -1003593852129
CHANNEL_LINK = "@Aesthetic_Channel" # Apna channel link yahan badlein

# Gemini Stable Setup
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.5-flash')

app_bot = Client("aesthetic_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["aesthetic_db"]["posted_images"]

def get_caption(category):
    emoji = "👦" if category == "boys" else "👧"
    # Blockquote (>) with proper spacing for Telegram
    cap = (
        f"> ✨ **NEW {category.upper()} AESTHETIC PACK** {emoji}\n\n"
        f"**━━━━━━━━━━━━━━━━━━━━**\n"
        f"👤 **Type:** #{category.capitalize()} #Anime #PFP\n"
        f"📸 **Quantity:** 05 High Definition Pix\n"
        f"🎨 **Verified by Gemini AI**\n"
        f"**━━━━━━━━━━━━━━━━━━━━**\n"
        f"🚀 **Join:** {CHANNEL_LINK}"
    )
    return cap

async def fetch_images(query):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {'q': query, 'cx': GOOGLE_CSE_ID, 'key': GOOGLE_API_KEY, 'searchType': 'image', 'num': 25}
    try:
        res = requests.get(url, params=params).json()
        items = res.get('items', [])
        print(f"DEBUG: Found {len(items)} images on Google.")
        return [item['link'] for item in items]
    except Exception as e:
        print(f"ERROR: Google Search failed -> {e}")
        return []

async def check_with_gemini(image_url, category):
    try:
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200: return False
        img_data = response.content
        prompt = f"Is this a high-quality aesthetic anime or real-life pfp for {category}? Answer only 'Yes' or 'No'."
        result = gemini_model.generate_content([prompt, {'mime_type': 'image/jpeg', 'data': img_data}])
        return "Yes" in result.text
    except Exception as e:
        print(f"DEBUG: Gemini skipping image due to error: {e}")
        return False

async def post_pack(category):
    print(f"DEBUG: Process started for {category}...")
    links = await fetch_images(f"{category} aesthetic pfp anime 4k")
    
    final_list = []
    for link in links:
        if not await db.find_one({"url": link}):
            if await check_with_gemini(link, category):
                final_list.append(link)
                await db.insert_one({"url": link, "category": category})
                print(f"DEBUG: Image {len(final_list)} approved by AI.")
        if len(final_list) == 5: break

    if len(final_list) == 5:
        try:
            caption = get_caption(category)
            media = [InputMediaPhoto(final_list[0], caption=caption)]
            for img in final_list[1:]:
                media.append(InputMediaPhoto(img))
            
            # Send to Telegram
            await app_bot.send_media_group(CHANNEL_ID, media)
            print(f"SUCCESS: Pack posted to {CHANNEL_ID}")
            return True
        except Exception as e:
            print(f"CRITICAL ERROR: Telegram failed to send -> {e}")
            return False
    else:
        print(f"DEBUG: Could not find 5 unique AI-approved images. Found: {len(final_list)}")
        return False

# --- FLASK & SCHEDULER ---
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Bot is Online!"

def auto_job():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(post_pack("boys"))
    loop.run_until_complete(post_pack("girls"))

scheduler = BackgroundScheduler()
scheduler.add_job(auto_job, 'cron', hour='0,6,12,18')
scheduler.start()

@app_bot.on_message(filters.command("start") & filters.user(OWNER_ID))
async def start_msg(client, message):
    btns = InlineKeyboardMarkup([[
        InlineKeyboardButton("Manual Post Boys 👦", callback_data="do_boys"),
        InlineKeyboardButton("Manual Post Girls 👧", callback_data="do_girls")
    ]])
    await message.reply_text("✨ **Aesthetic PFP Bot**\nStatus: Active\nModel: Gemini 2.5 Flash", reply_markup=btns)

@app_bot.on_callback_query(filters.user(OWNER_ID))
async def btn_callback(client, cb):
    cat = "boys" if cb.data == "do_boys" else "girls"
    await cb.answer(f"AI is searching {cat} pics...")
    status = await post_pack(cat)
    
    if status:
        await cb.message.edit_text(f"✅ Successful! Posted to channel.")
    else:
        await cb.message.edit_text(f"❌ Failed! Check Render Logs for the exact error.")

if __name__ == "__main__":
    Thread(target=lambda: web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))).start()
    app_bot.run()
    
