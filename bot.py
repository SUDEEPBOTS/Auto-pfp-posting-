import os
import asyncio
import requests
from google import genai
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from motor.motor_asyncio import AsyncIOMotorClient
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from threading import Thread

# --- CONFIG ---
API_ID = int(os.getenv("API_ID", "12345"))
API_HASH = os.getenv("API_HASH", "your_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_token")
MONGO_URL = os.getenv("MONGO_URL")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = "b74e609faafda42e8"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OWNER_ID = 8228478790
CHANNEL_ID = -1003593852129
CHANNEL_LINK = "@Aesthetic_Channel"

# Latest Gemini Client
client_gemini = genai.Client(api_key=GEMINI_API_KEY)

app_bot = Client("aesthetic_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["aesthetic_db"]["posted_images"]

async def check_with_gemini(image_url, category):
    try:
        # Image fetch karke byte data nikalna
        response = requests.get(image_url, timeout=10)
        if response.status_code != 200: return False
        
        prompt = f"Is this a high-quality aesthetic anime or real-life pfp for {category}? Answer only 'Yes' or 'No'."
        
        # Latest Gemini 2.0 API call
        result = client_gemini.models.generate_content(
            model="gemini-2.5-flash",
            contents=[prompt, response.content]
        )
        return "Yes" in result.text
    except Exception as e:
        print(f"DEBUG: Gemini AI Error -> {e}")
        return False

# ... baki fetch_images aur post_pack function same rahenge ...

async def post_pack(category):
    print(f"DEBUG: Starting search for {category}...")
    url = "https://www.googleapis.com/customsearch/v1"
    params = {'q': f"{category} aesthetic pfp anime 4k", 'cx': GOOGLE_CSE_ID, 'key': GOOGLE_API_KEY, 'searchType': 'image', 'num': 20}
    
    try:
        res = requests.get(url, params=params).json()
        links = [item['link'] for item in res.get('items', [])]
    except: links = []

    final_list = []
    for link in links:
        if not await db.find_one({"url": link}):
            if await check_with_gemini(link, category):
                final_list.append(link)
                await db.insert_one({"url": link, "category": category})
        if len(final_list) == 5: break

    if len(final_list) == 5:
        try:
            # Blockquote caption logic
            caption = f"> ✨ **NEW {category.upper()} AESTHETIC PACK**\n\n**Category:** #{category}\n**Quality:** 4K AI Verified\n**Join:** {CHANNEL_LINK}"
            media = [InputMediaPhoto(final_list[0], caption=caption)]
            for img in final_list[1:]: media.append(InputMediaPhoto(img))
            
            await app_bot.send_media_group(CHANNEL_ID, media)
            print(f"SUCCESS: Posted to {CHANNEL_ID}")
            return True
        except Exception as e:
            print(f"ERROR: Telegram failed -> {e}")
    return False

# --- WEB & SCHEDULER START ---
web_app = Flask(__name__)
@web_app.route('/')
def home(): return "Active"

def run_flask(): web_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

if __name__ == "__main__":
    Thread(target=run_flask).start()
    app_bot.run()
    
