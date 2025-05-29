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

# Global flag for graceful shutdown
is_shutting_down = False

bot = Client(
    "bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

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

@bot.on_message(filters.command(["start"]))
async def start_command(client, message):
    await message.reply_text(
        "Hello! I'm a video downloader bot specialized for Utkarsh Classes Jodhpur. "
        "Send me a text file with links and use /upload to start downloading."
    )

@bot.on_message(filters.command(["help"]))
async def help_command(client, message):
    await message.reply_text(
        "**How to use:**\n\n"
        "1. Create a text file with video links (one per line)\n"
        "2. Send the text file to me\n"
        "3. Use /upload command\n"
        "4. Follow the prompts to set quality and other options\n\n"
        "**Special Features for Utkarsh Classes:**\n"
        "- Automatically extracts video content from Utkarsh portal\n"
        "- Handles encrypted streams\n"
        "- Preserves original course structure\n\n"
        "**Commands:**\n"
        "/start - Check if bot is alive\n"
        "/upload - Start downloading videos\n"
        "/stop - Stop ongoing downloads"
    )

async def extract_utkarsh_content(url):
    """Specialized function to extract content from Utkarsh Classes portal"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Referer': 'https://utkarsh.com/',
            'Origin': 'https://utkarsh.com'
        }
        
        # First get the main page to get cookies
        session = requests.Session()
        session.get(url, headers=headers)
        
        # Extract the video ID from URL
        video_id = re.search(r'video/(\d+)', url)
        if not video_id:
            return None
            
        # API endpoint for video data
        api_url = f"https://utkarsh.com/api/video/{video_id.group(1)}"
        
        response = session.get(api_url, headers=headers)
        if response.status_code != 200:
            return None
            
        data = response.json()
        
        # Extract the m3u8 URL
        if 'playlist' in data and 'url' in data['playlist']:
            m3u8_url = data['playlist']['url']
            
            # Get encryption key if exists
            key_url = None
            if 'encryption_key' in data['playlist']:
                key_url = data['playlist']['encryption_key']
                
            return {
                'm3u8_url': m3u8_url,
                'key_url': key_url,
                'title': data.get('title', 'Utkarsh Video'),
                'description': data.get('description', '')
            }
            
        return None
    except Exception as e:
        print(f"Error extracting Utkarsh content: {str(e)}")
        return None

@bot.on_message(filters.command(["upload"]))
async def upload(bot: Client, m: Message):
    try:
        editable = await m.reply_text('𝕤ᴇɴᴅ ᴛxᴛ ғɪʟᴇ ⚡️')
        input_message = await bot.listen(editable.chat.id)
        x = await input_message.download()
        await input_message.delete(True)

        path = f"./downloads/{m.chat.id}"
        
        try:
            with open(x, "r") as f:
                content = f.read()
            content = content.split("\n")
            links = []
            for i in content:
                if i.strip():  # Skip empty lines
                    links.append(i.split("://", 1))
            os.remove(x)
            if not links:
                raise Exception("No valid links found in file")
        except Exception as e:
            await m.reply_text(f"**Invalid file input: {str(e)}**")
            if os.path.exists(x):
                os.remove(x)
            return

        await editable.edit(f"**𝕋ᴏᴛᴀʟ ʟɪɴᴋ𝕤 ғᴏᴜɴᴅ ᴀʀᴇ🔗🔗** **{len(links)}**\n\n**𝕊ᴇɴᴅ 𝔽ʀᴏᴍ ᴡʜᴇʀᴇ ʏᴏᴜ ᴡᴀɴᴛ ᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴɪᴛɪᴀʟ ɪ𝕤** **1**")
        try:
            input0: Message = await bot.listen(editable.chat.id)
            raw_text = input0.text
            await input0.delete(True)
            if not raw_text.isdigit():
                raise Exception("Please send a valid number")
        except Exception as e:
            await editable.edit(f"Failed to get starting number: {str(e)}")
            return

        await editable.edit("**Now Please Send Me Your Batch Name**")
        input1: Message = await bot.listen(editable.chat.id)
        raw_text0 = input1.text
        await input1.delete(True)

        await editable.edit("**𝔼ɴᴛᴇʀ ʀᴇ𝕤ᴏʟᴜᴛɪᴏɴ📸**\n144,240,360,480,720,1080 please choose quality")
        input2: Message = await bot.listen(editable.chat.id)
        raw_text2 = input2.text
        await input2.delete(True)
        
        try:
            if raw_text2 == "144":
                res = "256x144"
            elif raw_text2 == "240":
                res = "426x240"
            elif raw_text2 == "360":
                res = "640x360"
            elif raw_text2 == "480":
                res = "854x480"
            elif raw_text2 == "720":
                res = "1280x720"
            elif raw_text2 == "1080":
                res = "1920x1080" 
            else: 
                res = "UN"
        except Exception:
            res = "UN"

        await editable.edit("Now Enter A Caption to add caption on your uploaded file")
        input3: Message = await bot.listen(editable.chat.id)
        raw_text3 = input3.text
        await input3.delete(True)
        highlighter = f"️ ⁪⁬⁮⁮⁮"
        MR = highlighter if raw_text3 == 'Robin' else raw_text3

        await editable.edit("Now send the Thumb url\nEg » https://graph.org/file/ce1723991756e48c35aa1.jpg \n Or if don't want thumbnail send = no")
        input6 = message = await bot.listen(editable.chat.id)
        raw_text6 = input6.text
        await input6.delete(True)
        await editable.delete()

        thumb = input6.text
        if thumb.startswith("http://") or thumb.startswith("https://"):
            getstatusoutput(f"wget '{thumb}' -O 'thumb.jpg'")
            thumb = "thumb.jpg"
        else:
            thumb = "no"

        count = 1 if len(links) == 1 else int(raw_text)

        try:
            for i in range(count - 1, len(links)):
                if is_shutting_down:
                    await m.reply_text("Download process stopped due to bot shutdown")
                    break
                    
                # Process URL
                V = links[i][1].replace("file/d/","uc?export=download&id=").replace("www.youtube-nocookie.com/embed", "youtu.be").replace("?modestbranding=1", "").replace("/view?usp=sharing","")
                url = "https://" + V

                # Handle Utkarsh Classes URLs
                if "utkarsh" in url.lower():
                    utkarsh_data = await extract_utkarsh_content(url)
                    if utkarsh_data:
                        url = utkarsh_data['m3u8_url']
                        name1 = utkarsh_data['title']
                        key_url = utkarsh_data.get('key_url')
                    else:
                        await m.reply_text(f"Failed to extract Utkarsh content from {url}")
                        continue
                elif "visionias" in url:
                    async with ClientSession() as session:
                        async with session.get(url, headers={'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'Accept-Language': 'en-US,en;q=0.9', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'Pragma': 'no-cache', 'Referer': 'http://www.visionias.in/', 'Sec-Fetch-Dest': 'iframe', 'Sec-Fetch-Mode': 'navigate', 'Sec-Fetch-Site': 'cross-site', 'Upgrade-Insecure-Requests': '1', 'User-Agent': 'Mozilla/5.0 (Linux; Android 12; RMX2121) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Mobile Safari/537.36', 'sec-ch-ua': '"Chromium";v="107", "Not=A?Brand";v="24"', 'sec-ch-ua-mobile': '?1', 'sec-ch-ua-platform': '"Android"',}) as resp:
                            text = await resp.text()
                            url = re.search(r"(https://.*?playlist.m3u8.*?)\"", text).group(1)
                
                elif 'videos.classplusapp' in url:
                    url = requests.get(f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}', headers={'x-access-token': 'eyJhbGciOiJIUzM4NCIsInR5cCI6IkpXVCJ9.eyJpZCI6MzgzNjkyMTIsIm9yZ0lkIjoyNjA1LCJ0eXBlIjoxLCJtb2JpbGUiOiI5MTcwODI3NzQyODkiLCJuYW1lIjoiQWNlIiwiZW1haWwiOm51bGwsImlzRmlyc3RMb2dpbiI6dHJ1ZSwiZGVmYXVsdExhbmd1YWdlIjpudWxsLCJjb3VudHJ5Q29kZSI6IklOIiwiaXNJbnRlcm5hdGlvbmFsIjowLCJpYXQiOjE2NDMyODE4NzcsImV4cCI6MTY0Mzg4NjY3N30.hM33P2ai6ivdzxPPfm01LAd4JWv-vnrSxGXqvCirCSpUfhhofpeqyeHPxtstXwe0'}).json()['url']
                
                elif '/master.mpd' in url:
                    id = url.split("/")[-2]
                    url = f"https://d26g5bnklkwsh4.cloudfront.net/{id}/master.m3u8"

                # Process filename
                if "utkarsh" not in url.lower():
                    name1 = links[i][0].replace("\t", "").replace(":", "").replace("/", "").replace("+", "").replace("#", "").replace("|", "").replace("@", "").replace("*", "").replace(".", "").replace("https", "").replace("http", "").strip()
                
                name = f'{str(count).zfill(3)}) {name1[:60]}'

                # Set format based on URL type
                ytf = f"b[height<={raw_text2}][ext=mp4]/bv[height<={raw_text2}][ext=mp4]+ba[ext=m4a]/b[ext=mp4]" if "youtu" in url else f"b[height<={raw_text2}]/bv[height<={raw_text2}]+ba/b/bv+ba"

                # Set download command
                if "utkarsh" in url.lower() and url.endswith('.m3u8'):
                    # Special handling for Utkarsh m3u8 streams
                    output_file = f"{name}.mp4"
                    success = await download_m3u8(url, output_file, key_url)
                    if success:
                        cc = f'**[📽️] Vid_ID:** {str(count).zfill(3)}. {name1}{MR}.mp4\n**𝔹ᴀᴛᴄʜ** » **{raw_text0}**'
                        await helper.send_vid(bot, m, cc, output_file, thumb, name, None)
                        count += 1
                        os.remove(output_file)
                        continue
                    else:
                        await m.reply_text(f"Failed to download Utkarsh video: {name1}")
                        continue
                else:
                    cmd = f'yt-dlp -o "{name}.mp4" "{url}"' if "jw-prod" in url else f'yt-dlp -f "{ytf}" "{url}" -o "{name}.mp4"'

                try:
                    cc = f'**[📽️] Vid_ID:** {str(count).zfill(3)}. {name1}{MR}.mkv\n**𝔹ᴀᴛᴄʜ** » **{raw_text0}**'
                    cc1 = f'**[📁] Pdf_ID:** {str(count).zfill(3)}. {name1}{MR}.pdf \n**𝔹ᴀᴛᴄʜ** » **{raw_text0}**'

                    if "drive" in url:
                        try:
                            ka = await helper.download(url, name)
                            copy = await bot.send_document(chat_id=m.chat.id,document=ka, caption=cc1)
                            count+=1
                            os.remove(ka)
                            time.sleep(1)
                        except FloodWait as e:
                            await m.reply_text(str(e))
                            time.sleep(e.x)
                            continue
                    
                    elif ".pdf" in url:
                        try:
                            cmd = f'yt-dlp -o "{name}.pdf" "{url}"'
                            download_cmd = f"{cmd} -R 25 --fragment-retries 25"
                            os.system(download_cmd)
                            copy = await bot.send_document(chat_id=m.chat.id, document=f'{name}.pdf', caption=cc1)
                            count += 1
                            os.remove(f'{name}.pdf')
                        except FloodWait as e:
                            await m.reply_text(str(e))
                            time.sleep(e.x)
                            continue
                    else:
                        Show = f"**⥥ 🄳🄾🅆🄽🄻🄾🄰🄳🄸🄽🄶⬇️⬇️... »**\n\n**📝Name »** `{name}\n❄Quality » {raw_text2}`\n\n**🔗URL »** `{url}`"
                        prog = await m.reply_text(Show)
                        res_file = await helper.download_video(url, cmd, name)
                        filename = res_file
                        await prog.delete(True)
                        await helper.send_vid(bot, m, cc, filename, thumb, name, prog)
                        count += 1
                        time.sleep(1)

                except Exception as e:
                    await m.reply_text(f"**downloading Interrupted**\n{str(e)}\n**Name** » {name}\n**Link** » `{url}`")
                    continue

        except Exception as e:
            await m.reply_text(str(e))
            return
        await m.reply_text("**𝔻ᴏɴᴇ 𝔹ᴏ𝕤𝕤😎**")
    except Exception as e:
        await m.reply_text(f"An error occurred: {str(e)}")

@bot.on_message(filters.command("stop"))
async def stop_process(client, message):
    try:
        await cleanup()
        await message.reply_text("**✅ All processes stopped!**")
    except Exception as e:
        await message.reply_text(f"❌ Error stopping processes: {str(e)}")

async def cleanup():
    """Cleanup function to kill any running processes"""
    try:
        os.system("pkill -9 yt-dlp")
        os.system("pkill -9 aria2c")
        os.system("pkill -9 ffmpeg")
    except:
        pass

async def shutdown(signal, loop):
    """Cleanup and shutdown coroutines"""
    global is_shutting_down
    is_shutting_down = True
    
    print(f"Received exit signal {signal.name}...")
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

def main():
    loop = asyncio.get_event_loop()
    
    # Set up signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGQUIT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(shutdown(s, loop))
    
    # Set up exception handler
    loop.set_exception_handler(handle_exception)
    
    try:
        loop.run_until_complete(bot.run())
    finally:
        loop.close()

if __name__ == "__main__":
    main()
