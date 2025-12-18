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
import logging

# Setup logging for debugging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID", "12345"))
API_HASH = os.getenv("API_HASH", "your_hash")
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_token")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID", "b74e609faafda42e8")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OWNER_ID = 8228478790
CHANNEL_ID = -1003593852129  # Ensure this is correct
CHANNEL_LINK = "@Aesthetic_Channel"  # Your channel link

# Gemini Setup
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-2.0-flash')  # Use 2.0-flash for stability

# Initialize bot
app_bot = Client(
    "aesthetic_bot", 
    api_id=API_ID, 
    api_hash=API_HASH, 
    bot_token=BOT_TOKEN,
    in_memory=True
)

# Database setup
db_client = AsyncIOMotorClient(MONGO_URL)
db = db_client["aesthetic_db"]["posted_images"]

def get_caption(category):
    emoji = "👦" if category == "boys" else "👧"
    cap = (
        f"✨ NEW {category.upper()} AESTHETIC PACK {emoji}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 Type: #{category.capitalize()} #Anime #PFP\n"
        f"📸 Quantity: 05 High Definition Pix\n"
        f"🎨 Verified by Gemini AI\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🚀 Join: {CHANNEL_LINK}"
    )
    return cap

async def fetch_images(query):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'q': query,
        'cx': GOOGLE_CSE_ID,
        'key': GOOGLE_API_KEY,
        'searchType': 'image',
        'num': 10,  # Reduced for faster testing
        'imgSize': 'large'
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        res = response.json()
        items = res.get('items', [])
        logger.info(f"Found {len(items)} images for query: {query}")
        return [item['link'] for item in items]
    except Exception as e:
        logger.error(f"Google Search failed: {e}")
        return []

async def check_with_gemini(image_url, category):
    try:
        # Download image
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(image_url, timeout=15, headers=headers)
        if response.status_code != 200:
            logger.warning(f"Failed to download image: {response.status_code}")
            return False
        
        # Check image size
        if len(response.content) < 10240:  # Less than 10KB
            logger.warning("Image too small, skipping")
            return False
        
        # Gemini check
        prompt = f"""
        Analyze this image as a potential profile picture (PFP):
        1. Is this a high-quality image? (good resolution, clear)
        2. Is this aesthetic/artistic?
        3. Is this suitable for {category}?
        4. Is this appropriate/SFW?
        
        Answer ONLY with 'APPROVED' if all conditions are met, otherwise 'REJECTED'.
        """
        
        try:
            result = gemini_model.generate_content([
                prompt,
                {"mime_type": "image/jpeg", "data": response.content}
            ])
            
            if hasattr(result, 'text'):
                verdict = result.text.strip().upper()
                logger.info(f"Gemini verdict: {verdict} for {image_url[:50]}...")
                return "APPROVED" in verdict
            else:
                logger.warning("No text in Gemini response")
                return False
                
        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return False
            
    except Exception as e:
        logger.error(f"Error checking image: {e}")
        return False

async def post_pack(category):
    logger.info(f"Starting pack posting for {category}...")
    
    links = await fetch_images(f"{category} aesthetic anime pfp 2025")
    
    if not links:
        logger.error("No images found from Google")
        return False
    
    final_list = []
    processed_count = 0
    
    for link in links:
        try:
            # Check if already posted
            existing = await db.find_one({"url": link})
            if existing:
                logger.info(f"Image already posted, skipping: {link[:50]}...")
                continue
            
            processed_count += 1
            logger.info(f"Processing image {processed_count}/{len(links)}")
            
            # Check with Gemini
            if await check_with_gemini(link, category):
                final_list.append(link)
                await db.insert_one({"url": link, "category": category})
                logger.info(f"✅ Image approved: {link[:50]}...")
                
                if len(final_list) == 5:
                    break
            else:
                logger.info(f"❌ Image rejected by AI")
                
        except Exception as e:
            logger.error(f"Error processing image: {e}")
            continue
    
    if len(final_list) >= 3:  # Changed to minimum 3 images
        try:
            caption = get_caption(category)
            
            # Create media group
            media_group = []
            for i, img_url in enumerate(final_list[:5]):  # Max 5 images
                if i == 0:
                    media_group.append(InputMediaPhoto(img_url, caption=caption))
                else:
                    media_group.append(InputMediaPhoto(img_url))
            
            # Send to Telegram
            await app_bot.send_media_group(
                chat_id=CHANNEL_ID,
                media=media_group
            )
            
            logger.info(f"✅ Successfully posted {len(final_list)} images to channel")
            return True
            
        except Exception as e:
            logger.error(f"Telegram posting failed: {e}")
            
            # Try sending images individually
            try:
                caption = get_caption(category)
                await app_bot.send_photo(
                    CHANNEL_ID,
                    final_list[0],
                    caption=caption
                )
                
                for img_url in final_list[1:]:
                    await app_bot.send_photo(CHANNEL_ID, img_url)
                    
                logger.info("Posted images individually")
                return True
            except Exception as e2:
                logger.error(f"Individual posting also failed: {e2}")
                return False
    else:
        logger.error(f"Not enough approved images. Found: {len(final_list)}")
        return False

# --- FLASK & SCHEDULER ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot is Online!"

@web_app.route('/health')
def health():
    return {"status": "healthy", "service": "aesthetic_bot"}

def auto_job():
    """Background job for scheduled posting"""
    logger.info("Running scheduled job...")
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Start bot if not running
        if not app_bot.is_connected:
            loop.run_until_complete(app_bot.start())
        
        # Post packs
        loop.run_until_complete(post_pack("boys"))
        loop.run_until_complete(asyncio.sleep(10))  # Wait 10 seconds
        loop.run_until_complete(post_pack("girls"))
        
    except Exception as e:
        logger.error(f"Scheduled job failed: {e}")
    finally:
        if loop.is_running():
            loop.close()

# Initialize scheduler
scheduler = BackgroundScheduler()
scheduler.add_job(auto_job, 'cron', hour='0,6,12,18')
scheduler.start()

# --- Bot Handlers ---
@app_bot.on_message(filters.command("start") & filters.user(OWNER_ID))
async def start_msg(client, message):
    btns = InlineKeyboardMarkup([[
        InlineKeyboardButton("Manual Post Boys 👦", callback_data="do_boys"),
        InlineKeyboardButton("Manual Post Girls 👧", callback_data="do_girls")
    ]])
    await message.reply_text(
        "✨ Aesthetic PFP Bot\nStatus: Active\nModel: Gemini 2.0 Flash\n\n"
        "Click buttons to post manually:",
        reply_markup=btns
    )

@app_bot.on_callback_query(filters.user(OWNER_ID))
async def btn_callback(client, cb):
    cat = "boys" if cb.data == "do_boys" else "girls"
    await cb.answer(f"AI is searching {cat} pics...")
    
    status = await post_pack(cat)
    
    if status:
        await cb.message.edit_text(f"✅ Successful! {cat.capitalize()} pack posted to channel.")
    else:
        await cb.message.edit_text(f"❌ Failed to post {cat} pack. Check logs.")

@app_bot.on_message(filters.command("status") & filters.user(OWNER_ID))
async def status_check(client, message):
    try:
        count = await db.count_documents({})
        await message.reply_text(f"📊 Database Stats:\nTotal Images: {count}\nBot Status: ✅ Running")
    except Exception as e:
        await message.reply_text(f"❌ Error: {e}")

if __name__ == "__main__":
    # Start Flask web server in thread
    Thread(
        target=lambda: web_app.run(
            host="0.0.0.0",
            port=int(os.environ.get("PORT", 8080)),
            debug=False,
            threaded=True
        )
    ).start()
    
    # Start the bot
    logger.info("Starting Telegram Bot...")
    app_bot.run()
