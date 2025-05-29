import os
import re
import sys
import json
import time
import asyncio
import signal
import requests
from aiohttp import ClientSession
from pyromod import listen
from subprocess import getstatusoutput
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import m3u8
from Cryptodome.Cipher import AES
import base64
from vars import API_ID, API_HASH, BOT_TOKEN
from utils import progress_bar, humanbytes, TimeFormatter
import helper

# Configuration
ADMIN_ID = 1012164907  # Your admin user ID
MAX_CONCURRENT_DOWNLOADS = 3  # Limit simultaneous downloads
DOWNLOAD_TIMEOUT = 3600  # 1 hour timeout per download

# Global flags and trackers
is_shutting_down = False
current_downloads = {}
active_tasks = set()

bot = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

class DownloadStatus:
    def __init__(self, total, completed=0, failed=0, current="", user_id=None):
        self.total = total
        self.completed = completed
        self.failed = failed
        self.current = current
        self.user_id = user_id
        self.start_time = time.time()
        self.last_update = time.time()

async def notify_admin(message):
    """Send notification to admin"""
    try:
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"⚠️ Admin Notification:\n\n{message}"
        )
    except Exception as e:
        print(f"Failed to notify admin: {str(e)}")

async def is_admin(user_id):
    """Check if user is admin"""
    return user_id == ADMIN_ID

async def download_m3u8(url, output_file, key_url=None):
    """Enhanced m3u8 downloader with key handling"""
    try:
        # Download m3u8 playlist
        playlist = m3u8.load(url)
        
        if playlist.keys and playlist.keys[0]:
            # Handle encrypted streams
            key_response = requests.get(key_url or playlist.keys[0].uri)
            key = key_response.content
            iv = playlist.keys[0].iv or b'\0' * 16
            
            cipher = AES.new(key, AES.MODE_CBC, iv)
        
        segments = []
        for segment in playlist.segments:
            segment_url = segment.uri
            if not segment_url.startswith('http'):
                segment_url = os.path.dirname(url) + '/' + segment_url
            
            segment_response = requests.get(segment_url)
            segment_data = segment_response.content
            
            if playlist.keys and playlist.keys[0]:
                # Decrypt segment if encrypted
                segment_data = cipher.decrypt(segment_data)
            
            segments.append(segment_data)
        
        # Combine segments and save
        with open(output_file, 'wb') as f:
            for segment in segments:
                f.write(segment)
        
        return True
    except Exception as e:
        print(f"M3U8 download error: {str(e)}")
        return False

async def extract_utkarsh_content(url):
    """Extract content from Utkarsh Classes app links"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://www.utkarsh.com/'
        }
        
        # Handle different Utkarsh URL formats
        if 'utkarshnew.android' in url:
            # Extract video ID from URL
            video_id = re.search(r'id=([^&]+)', url)
            if video_id:
                video_id = video_id.group(1)
                api_url = f"https://api.utkarshclasses.com/v1/videos/{video_id}"
                
                response = requests.get(api_url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    if 'video_url' in data:
                        return data['video_url']
                    elif 'm3u8_url' in data:
                        return data['m3u8_url']
        
        # Try direct extraction if API fails
        response = requests.get(url, headers=headers, allow_redirects=True)
        final_url = response.url
        
        # Check for m3u8 in final URL
        if '.m3u8' in final_url:
            return final_url
        
        # Try to find m3u8 in page content
        content = response.text
        m3u8_match = re.search(r'(https?://[^\s]+\.m3u8[^\s"]*)', content)
        if m3u8_match:
            return m3u8_match.group(1)
        
        return None
    except Exception as e:
        print(f"Utkarsh extraction error: {str(e)}")
        return None

@bot.on_message(filters.command(["start"]))
async def start_command(client, message):
    user_id = message.from_user.id
    if await is_admin(user_id):
        admin_text = "\n\n👑 You are logged in as ADMIN"
    else:
        admin_text = ""
    
    await message.reply_text(
        f"🚀 **Advanced Video Downloader Bot**{admin_text}\n\n"
        "I can download videos from multiple platforms including:\n"
        "- YouTube\n"
        "- Google Drive\n"
        "- M3U8 streams\n"
        "- Classplus\n"
        "- VisionIAS\n"
        "- Utkarsh Classes\n\n"
        "**Features:**\n"
        "• V2 Download System (faster)\n"
        "• Batch processing\n"
        "• Quality selection\n"
        "• Auto thumbnail\n"
        "• Progress tracking\n\n"
        "Use /help for usage instructions"
    )

@bot.on_message(filters.command(["help"]))
async def help_command(client, message):
    user_id = message.from_user.id
    admin_commands = ""
    if await is_admin(user_id):
        admin_commands = (
            "\n\n🔐 **Admin Commands:**\n"
            "/broadcast - Send message to all users\n"
            "/stats - Get bot statistics\n"
            "/logs - Get recent logs"
        )
    
    await message.reply_text(
        "📚 **How to use:**\n\n"
        "1. Create a text file with video links (one per line)\n"
        "2. Send the text file to me\n"
        "3. Use /upload or /v2 command\n"
        "4. Follow the prompts to set options\n\n"
        "⚙️ **Commands:**\n"
        "/start - Check bot status\n"
        "/upload - Standard download\n"
        "/v2 - Faster download system\n"
        "/stop - Cancel ongoing downloads\n"
        "/status - Check current downloads"
        f"{admin_commands}"
    )

@bot.on_message(filters.command(["v2"]))
async def v2_download_command(client, message):
    """V2 Download System - Faster and more reliable"""
    user_id = message.from_user.id
    try:
        # Check if user has active downloads
        if user_id in current_downloads:
            await message.reply_text("⚠️ You already have an active download. Please wait or /stop it first.")
            return

        editable = await message.reply_text('🚀 **V2 Download System Activated**\n\n📤 Please send me the text file with links')
        input_message = await bot.listen(message.chat.id, timeout=300)
        
        if input_message.document:
            x = await input_message.download()
        else:
            await message.reply_text("❌ Please send a text file")
            return
            
        await input_message.delete(True)

        path = f"./downloads/{message.chat.id}"
        os.makedirs(path, exist_ok=True)
        
        try:
            with open(x, "r") as f:
                content = f.read()
            content = content.split("\n")
            links = []
            for i in content:
                i = i.strip()
                if i and not i.startswith("#"):  # Skip empty lines and comments
                    if "://" not in i:
                        i = "https://" + i
                    links.append(i)
            os.remove(x)
            if not links:
                raise Exception("No valid links found in file")
        except Exception as e:
            await message.reply_text(f"❌ **Invalid file input:** {str(e)}")
            if os.path.exists(x):
                os.remove(x)
            return

        await editable.edit(f"🔗 **Total links found:** {len(links)}\n\n📝 Send starting index (default is 1)")
        try:
            input0 = await bot.listen(message.chat.id, timeout=60)
            raw_text = input0.text
            await input0.delete(True)
            start_index = int(raw_text) if raw_text.isdigit() else 1
            if start_index < 1 or start_index > len(links):
                raise ValueError("Invalid starting index")
        except Exception as e:
            await editable.edit(f"⚠️ Using default starting index 1\nError: {str(e)}")
            start_index = 1
            await asyncio.sleep(2)

        await editable.edit("📛 **Enter batch name:**")
        input1 = await bot.listen(message.chat.id, timeout=60)
        batch_name = input1.text
        await input1.delete(True)

        await editable.edit("🖼 **Select quality (144,240,360,480,720,1080):**")
        input2 = await bot.listen(message.chat.id, timeout=60)
        quality = input2.text
        await input2.delete(True)
        
        resolution_map = {
            "144": "256x144",
            "240": "426x240",
            "360": "640x360",
            "480": "854x480",
            "720": "1280x720",
            "1080": "1920x1080"
        }
        res = resolution_map.get(quality, "UN")

        await editable.edit("📝 **Enter caption (or send 'no' for none):**")
        input3 = await bot.listen(message.chat.id, timeout=60)
        caption = input3.text if input3.text.lower() != 'no' else ""
        await input3.delete(True)

        await editable.edit("🖼 **Send thumbnail URL (or 'no' for none):**")
        input6 = await bot.listen(message.chat.id, timeout=60)
        thumb_url = input6.text
        await input6.delete(True)
        await editable.delete()

        # Download thumbnail if provided
        thumb_path = None
        if thumb_url.lower() != 'no' and (thumb_url.startswith("http://") or thumb_url.startswith("https://")):
            try:
                thumb_path = f"thumb_{message.chat.id}.jpg"
                os.system(f"wget '{thumb_url}' -O '{thumb_path}'")
            except Exception as e:
                await message.reply_text(f"⚠️ Failed to download thumbnail: {str(e)}")
                thumb_path = None

        # Initialize download status
        status = DownloadStatus(total=len(links), user_id=user_id)
        current_downloads[user_id] = status

        status_msg = await message.reply_text(
            f"⏳ **V2 Download Started**\n\n"
            f"• 📦 Total Files: {status.total}\n"
            f"• ✅ Completed: {status.completed}\n"
            f"• ❌ Failed: {status.failed}\n"
            f"• 🎬 Quality: {quality}p\n"
            f"• 📛 Batch: {batch_name}\n\n"
            f"🔄 **Status:** Preparing..."
        )

        # Create task and add to active tasks
        task = asyncio.create_task(
            process_v2_downloads(
                message, links, start_index, quality, batch_name,
                caption, thumb_path, status, status_msg, path
            )
        )
        active_tasks.add(task)
        task.add_done_callback(active_tasks.discard)

    except Exception as e:
        await message.reply_text(f"❌ **V2 Download Error:** {str(e)}")
        if user_id in current_downloads:
            del current_downloads[user_id]

async def process_v2_downloads(message, links, start_index, quality, batch_name, 
                             caption, thumb_path, status, status_msg, path):
    """Process downloads for V2 command"""
    try:
        for i in range(start_index - 1, len(links)):
            if is_shutting_down:
                await status_msg.edit_text("🛑 Download process stopped due to bot shutdown")
                break

            try:
                url = links[i]
                status.current = f"Processing {i+1}/{len(links)}"
                current_downloads[status.user_id] = status

                # Update status
                await status_msg.edit_text(
                    f"⏳ **V2 Download Progress**\n\n"
                    f"• 📦 Total Files: {status.total}\n"
                    f"• ✅ Completed: {status.completed}\n"
                    f"• ❌ Failed: {status.failed}\n"
                    f"• 🎬 Quality: {quality}p\n"
                    f"• 📛 Batch: {batch_name}\n\n"
                    f"🔗 **Current:** {url[:50]}...\n\n"
                    f"🔄 **Status:** Downloading..."
                )

                # Handle Utkarsh Classes links
                if 'utkarshnew.android' in url:
                    extracted_url = await extract_utkarsh_content(url)
                    if extracted_url:
                        url = extracted_url
                    else:
                        await message.reply_text(f"❌ Failed to extract Utkarsh content from: {url}")
                        status.failed += 1
                        continue
                
                # Process URL
                if "drive.google.com" in url:
                    url = url.replace("file/d/", "uc?export=download&id=").replace("/view?usp=sharing", "")
                
                # Platform-specific handling
                if "visionias" in url:
                    async with ClientSession() as session:
                        async with session.get(url, headers={
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                        }) as resp:
                            text = await resp.text()
                            url_match = re.search(r"(https://.*?playlist.m3u8.*?)\"", text)
                            if url_match:
                                url = url_match.group(1)
                
                elif 'videos.classplusapp' in url:
                    try:
                        api_url = f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}'
                        headers = {
                            'x-access-token': 'eyJhbGciOiJIUzM4NCIsInR5cCI6IkpXVCJ9.eyJpZCI6MzgzNjkyMTIsIm9yZ0lkIjoyNjA1LCJ0eXBlIjoxLCJtb2JpbGUiOiI5MTcwODI3NzQyODkiLCJuYW1lIjoiQWNlIiwiZW1haWwiOm51bGwsImlzRmlyc3RMb2dpbiI6dHJ1ZSwiZGVmYXVsdExhbmd1YWdlIjpudWxsLCJjb3VudHJ5Q29kZSI6IklOIiwiaXNJbnRlcm5hdGlvbmFsIjowLCJpYXQiOjE2NDMyODE4NzcsImV4cCI6MTY0Mzg4NjY3N30.hM33P2ai6ivdzxPPfm01LAd4JWv-vnrSxGXqvCirCSpUfhhofpeqyeHPxtstXwe0'
                        }
                        url = requests.get(api_url, headers=headers).json()['url']
                    except Exception as e:
                        await message.reply_text(f"❌ Failed to process Classplus URL: {str(e)}")
                        status.failed += 1
                        continue
                
                elif '/master.mpd' in url:
                    id = url.split("/")[-2]
                    url = f"https://d26g5bnklkwsh4.cloudfront.net/{id}/master.m3u8"

                # Generate filename
                name = re.sub(r'[^\w\-_\. ]', '', url.split('/')[-1].split('?')[0][:60])
                name = f'{str(i+1).zfill(3)}) {name}'
                output_file = os.path.join(path, f"{name}.mp4")

                # V2 Download Command
                if "youtu" in url:
                    cmd = f'yt-dlp -f "bestvideo[height<={quality}]+bestaudio/best[height<={quality}]" --merge-output-format mkv --no-part --hls-use-mpegts "{url}" -o "{output_file}"'
                elif "m3u8" in url or "mpd" in url:
                    cmd = f'yt-dlp -f "best[height<={quality}]" --hls-use-mpegts --no-part "{url}" -o "{output_file}"'
                else:
                    cmd = f'yt-dlp -f "best[height<={quality}]" --no-part "{url}" -o "{output_file}"'

                # Execute download
                start_time = time.time()
                return_code = os.system(cmd)
                
                if return_code == 0 and os.path.exists(output_file):
                    # File downloaded successfully
                    file_caption = (
                        f"📛 **Batch:** {batch_name}\n"
                        f"📂 **File {i+1}/{len(links)}:** {name}\n"
                        f"🖼 **Quality:** {quality}p\n\n"
                        f"{caption if caption else ''}"
                    )
                    
                    try:
                        if output_file.endswith('.mkv') or output_file.endswith('.mp4'):
                            await helper.send_vid(bot, message, file_caption, output_file, thumb_path, name, status_msg)
                        else:
                            await message.reply_document(
                                document=output_file,
                                caption=file_caption,
                                thumb=thumb_path
                            )
                        status.completed += 1
                    except FloodWait as e:
                        await message.reply_text(f"⏳ Flood wait: {e.x} seconds")
                        time.sleep(e.x)
                        continue
                    except Exception as e:
                        await message.reply_text(f"❌ Failed to send file: {str(e)}")
                        status.failed += 1
                    
                    # Clean up
                    os.remove(output_file)
                else:
                    status.failed += 1
                    await message.reply_text(f"❌ Download failed for: {name}")

                # Update status
                current_downloads[status.user_id] = status
                time_elapsed = TimeFormatter(time.time() - start_time)
                
                await status_msg.edit_text(
                    f"⏳ **V2 Download Progress**\n\n"
                    f"• 📦 Total Files: {status.total}\n"
                    f"• ✅ Completed: {status.completed}\n"
                    f"• ❌ Failed: {status.failed}\n"
                    f"• 🎬 Quality: {quality}p\n"
                    f"• 📛 Batch: {batch_name}\n"
                    f"• ⏱ Last File Time: {time_elapsed}\n\n"
                    f"🔄 **Status:** {'Downloading...' if i < len(links)-1 else 'Completed'}"
                )

            except Exception as e:
                status.failed += 1
                await message.reply_text(f"❌ Error processing {links[i]}: {str(e)}")
                continue

        # Final status
        if status.user_id in current_downloads:
            del current_downloads[status.user_id]
        await status_msg.edit_text(
            f"🎉 **V2 Download Completed**\n\n"
            f"• 📦 Total Files: {status.total}\n"
            f"• ✅ Success: {status.completed}\n"
            f"• ❌ Failed: {status.failed}\n"
            f"• 🎬 Quality: {quality}p\n"
            f"• 📛 Batch: {batch_name}\n\n"
            f"⏱ Total Time: {TimeFormatter(time.time() - status.start_time)}"
        )
        
        # Clean up thumbnail
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)

    except Exception as e:
        await message.reply_text(f"❌ **Download Process Error:** {str(e)}")
        if status.user_id in current_downloads:
            del current_downloads[status.user_id]

@bot.on_message(filters.command(["stop"]))
async def stop_process(client, message):
    user_id = message.from_user.id
    try:
        await cleanup(user_id)
        await message.reply_text("✅ **Your downloads have been stopped!**")
    except Exception as e:
        await message.reply_text(f"❌ Error stopping processes: {str(e)}")

@bot.on_message(filters.command(["status"]))
async def status_command(client, message):
    """Check current download status"""
    user_id = message.from_user.id
    status_text = "📊 **Bot Status**\n\n"
    status_text += f"• 🏃‍♂️ Shutdown Status: {'🛑 Stopping' if is_shutting_down else '✅ Running'}\n"
    
    if user_id in current_downloads:
        status = current_downloads[user_id]
        status_text += f"\n📦 **Your Current Download**\n"
        status_text += f"• Total: {status.total}\n"
        status_text += f"• Completed: {status.completed}\n"
        status_text += f"• Failed: {status.failed}\n"
        status_text += f"• Current: {status.current}\n"
        status_text += f"• Elapsed: {TimeFormatter(time.time() - status.start_time)}"
    else:
        status_text += "\nℹ️ You don't have any active downloads\n"
    
    if await is_admin(user_id):
        status_text += f"\n👑 **Admin Stats**\n"
        status_text += f"• Active Users: {len(current_downloads)}\n"
        status_text += f"• Active Tasks: {len(active_tasks)}\n"
    
    status_text += f"\n💻 System Load: {os.getloadavg()[0]:.2f}"
    await message.reply_text(status_text)

@bot.on_message(filters.command(["broadcast"]) & filters.user(ADMIN_ID))
async def broadcast_command(client, message):
    """Admin-only broadcast message"""
    try:
        if not message.reply_to_message:
            await message.reply_text("❌ Please reply to a message to broadcast")
            return
            
        # Get all user IDs who have interacted with the bot
        # Note: In a real implementation, you'd need to track users in a database
        await message.reply_text("⚠️ Broadcast functionality requires user tracking implementation")
        
    except Exception as e:
        await message.reply_text(f"❌ Broadcast error: {str(e)}")

@bot.on_message(filters.command(["stats"]) & filters.user(ADMIN_ID))
async def stats_command(client, message):
    """Admin-only statistics"""
    try:
        stats_text = "📈 **Bot Statistics**\n\n"
        stats_text += f"• Active Downloads: {len(current_downloads)}\n"
        stats_text += f"• Active Tasks: {len(active_tasks)}\n"
        stats_text += f"• System Load: {os.getloadavg()[0]:.2f}\n"
        stats_text += f"• Uptime: {TimeFormatter(time.time() - bot.start_time)}"
        
        await message.reply_text(stats_text)
    except Exception as e:
        await message.reply_text(f"❌ Stats error: {str(e)}")

async def cleanup(user_id=None):
    """Cleanup function to kill any running processes"""
    try:
        if user_id:
            # Cleanup specific user's downloads
            if user_id in current_downloads:
                del current_downloads[user_id]
            os.system(f"pkill -u {user_id} yt-dlp")
        else:
            # Full cleanup
            current_downloads.clear()
            os.system("pkill -9 yt-dlp")
            os.system("pkill -9 aria2c")
            os.system("pkill -9 ffmpeg")
    except Exception as e:
        print(f"Cleanup error: {str(e)}")

async def shutdown(signal, loop):
    """Cleanup and shutdown coroutines"""
    global is_shutting_down
    is_shutting_down = True
    
    print(f"Received exit signal {signal.name}...")
    await notify_admin(f"Bot received {signal.name} signal. Shutting down...")
    
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    
    await cleanup()
    
    [task.cancel() for task in tasks]
    print(f"Cancelling {len(tasks)} outstanding tasks")
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

def handle_exception(loop, context):
    """Global exception handler"""
    msg = context.get("exception", context["message"])
    print(f"Caught exception: {msg}")
    asyncio.create_task(notify_admin(f"Bot Exception:\n\n{msg}"))

async def main():
    # Your bot initialization code
    bot = YourBotClass()
    try:
        await bot.start()  # Assuming start() is an async function
    except KeyboardInterrupt:
        pass
    finally:
        if hasattr(bot, 'stop') and asyncio.iscoroutinefunction(bot.stop):
            await bot.stop()
        elif hasattr(bot, 'stop'):
            bot.stop()  # For synchronous stop methods

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
