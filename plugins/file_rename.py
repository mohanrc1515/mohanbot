from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from hachoir.metadata import extractMetadata
from helper.ffmpeg import fix_thumb, take_screen_shot, add_metadata
from hachoir.parser import createParser
from helper.utils import progress_for_pyrogram, convert, humanbytes, add_prefix_suffix
from helper.database import jishubotz
from asyncio import sleep, get_event_loop
from threading import Thread
import os, time, random, asyncio, math, glob

# Dictionary to store user sessions
user_sessions = {}

# Constants
MAX_FILE_SIZE = 2000 * 1024 * 1024  # 2GB (Telegram's limit per file)
CHUNK_SIZE = 2000 * 1024 * 1024  # Exactly 2GB chunks for splitting

async def split_large_file(file_path, chunk_size=CHUNK_SIZE):
    """Split large file into exactly 2GB chunks"""
    chunk_paths = []
    file_size = os.path.getsize(file_path)
    total_chunks = math.ceil(file_size / chunk_size)
    
    with open(file_path, 'rb') as f:
        for i in range(total_chunks):
            chunk_path = f"{file_path}.part{i+1:03d}"
            with open(chunk_path, 'wb') as chunk_file:
                remaining = min(chunk_size, file_size - (i * chunk_size))
                chunk_file.write(f.read(remaining))
            chunk_paths.append(chunk_path)
    
    return chunk_paths

async def download_threaded(file_path, message, bot, ms):
    try:
        await bot.download_media(
            message=message,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("🚀 Downloading...", ms, time.time())
        )
    except Exception as e:
        await ms.edit(f"Download error: {e}")
        raise

def run_async(coro):
    loop = get_event_loop()
    return loop.run_until_complete(coro)

async def convert_to_video(input_path, output_path):
    """Convert any file to video format using FFmpeg"""
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "28",
        "-c:a", "aac",
        "-strict", "experimental",
        "-f", "mp4",
        output_path
    ]
    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()
    return output_path if os.path.exists(output_path) else None

async def upload_as_video(bot, user_id, file_path, caption, thumb_path, ms, chunk_info=None):
    """Upload any file as video"""
    try:
        # Convert to video first
        video_path = f"{file_path}.mp4"
        await ms.edit("🔄 Converting to video format...")
        converted_path = await convert_to_video(file_path, video_path)
        
        if not converted_path:
            return await ms.edit("❌ Failed to convert file to video format")
        
        # Get duration for the video
        duration = 0
        try:
            parser = createParser(video_path)
            metadata = extractMetadata(parser)
            if metadata and metadata.has("duration"):
                duration = metadata.get('duration').seconds
            if parser:
                parser.close()
        except Exception as e:
            print(f"Error getting duration: {e}")
        
        # Prepare caption with chunk info if available
        final_caption = caption
        if chunk_info:
            final_caption = f"{caption}\n\nPart {chunk_info[0]}/{chunk_info[1]}"
        
        await bot.send_video(
            chat_id=user_id,
            video=video_path,
            caption=final_caption,
            thumb=thumb_path,
            duration=duration,
            progress=progress_for_pyrogram,
            progress_args=(f"📤 Uploading video {chunk_info[0]}/{chunk_info[1]}..." if chunk_info else "📤 Uploading video...", ms, time.time())
        )
        
        return True
    except Exception as e:
        await ms.edit(f"Video upload error: {str(e)}")
        return False
    finally:
        # Clean up converted video file
        if 'video_path' in locals() and os.path.exists(video_path):
            try:
                os.remove(video_path)
            except:
                pass

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_file_upload(client, message):
    user_id = message.from_user.id
    
    # Clear previous session if exists
    if user_id in user_sessions:
        del user_sessions[user_id]
    
    file = getattr(message, message.media.value)
    filename = file.file_name  
    
    # Create new session
    user_sessions[user_id] = {
        'original_message': message,
        'filename': filename,
        'state': 'awaiting_thumbnail',
        'is_large_file': file.file_size > MAX_FILE_SIZE
    }

    await message.reply(
        text="Please send me a thumbnail photo for this file (send as photo).\n\n"
             "If you don't want a thumbnail, just click /skip",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Skip Thumbnail", callback_data="skip_thumbnail")]
        ])
    )

@Client.on_message(filters.private & filters.photo)
async def receive_thumbnail(bot, message):
    user_id = message.from_user.id
    
    if user_id not in user_sessions or user_sessions[user_id]['state'] != 'awaiting_thumbnail':
        return await message.reply("Please send a file first, then send the thumbnail")
    
    user_sessions[user_id]['thumbnail'] = message
    user_sessions[user_id]['state'] = 'processing'
    
    original_message = user_sessions[user_id]['original_message']
    await process_and_upload(bot, user_id, original_message, thumbnail_message=message)

@Client.on_callback_query(filters.regex("skip_thumbnail"))
async def skip_thumbnail(bot, update):
    user_id = update.from_user.id
    
    if user_id not in user_sessions or user_sessions[user_id]['state'] != 'awaiting_thumbnail':
        return await update.answer("No file found to upload")
    
    user_sessions[user_id]['state'] = 'processing'
    original_message = user_sessions[user_id]['original_message']
    await process_and_upload(bot, user_id, original_message, thumbnail_message=None)
    await update.message.delete()

async def process_and_upload(bot, user_id, original_message, thumbnail_message=None):
    if user_id not in user_sessions:
        return
    
    try:
        file_data = user_sessions[user_id]
        filename = file_data['filename']
        is_large_file = file_data['is_large_file']
        
        file = original_message
        media = getattr(file, file.media.value)
        
        # Get user settings
        prefix = await jishubotz.get_prefix(user_id)
        suffix = await jishubotz.get_suffix(user_id)
        
        try:
            new_filename = add_prefix_suffix(filename, prefix, suffix)
        except Exception as e:
            return await original_message.reply(f"Error setting prefix/suffix: {e}")
        
        # Create unique download directory
        timestamp = int(time.time())
        download_dir = f"downloads/{user_id}/{timestamp}/"
        os.makedirs(download_dir, exist_ok=True)
        file_path = os.path.join(download_dir, new_filename)
        
        ms = await original_message.reply("🚀 Downloading file...")
        
        # Start threaded download
        download_thread = Thread(
            target=lambda: run_async(
                download_threaded(file_path, file, bot, ms)
            )
        )
        download_thread.start()
        download_thread.join()
        
        if not os.path.exists(file_path):
            return await ms.edit("Download failed - file not found")
        
        # Handle metadata (only for non-split files)
        _bool_metadata = await jishubotz.get_metadata(user_id) if not is_large_file else False
        metadata_path = None
        if _bool_metadata:
            metadata = await jishubotz.get_metadata_code(user_id)
            metadata_dir = f"Metadata/{user_id}/{timestamp}/"
            os.makedirs(metadata_dir, exist_ok=True)
            metadata_path = os.path.join(metadata_dir, new_filename)
            await add_metadata(file_path, metadata_path, metadata, ms)
        
        # Prepare caption
        c_caption = await jishubotz.get_caption(user_id)
        if c_caption:
            try:
                caption = c_caption.format(
                    filename=new_filename,
                    filesize=humanbytes(media.file_size),
                    duration="0:00"  # Placeholder, actual duration will be detected after conversion
                )
            except Exception as e:
                print(f"Error formatting caption: {e}")
                caption = f"**{new_filename}**"
        else:
            caption = f"**{new_filename}**"
        
        # Handle thumbnail
        ph_path = None
        if thumbnail_message:
            try:
                thumb_dir = f"thumbnails/{user_id}/"
                os.makedirs(thumb_dir, exist_ok=True)
                ph_path = await bot.download_media(
                    thumbnail_message, 
                    file_name=os.path.join(thumb_dir, f"thumb_{timestamp}.jpg")
                )
                width, height, ph_path = await fix_thumb(ph_path)
            except Exception as e:
                print(f"Error processing thumbnail: {e}")
        
        # Generate thumbnail for videos if needed
        if not ph_path:
            try:
                thumb_dir = f"thumbnails/{user_id}/"
                os.makedirs(thumb_dir, exist_ok=True)
                ph_path = await take_screen_shot(
                    file_path,
                    thumb_dir,
                    0  # Take first frame for thumbnail
                )
                width, height, ph_path = await fix_thumb(ph_path)
            except Exception as e:
                print(f"Error generating thumbnail: {e}")
        
        # Handle file upload
        await ms.edit("📤 Preparing upload...")
        
        # Split large files into chunks
        upload_paths = []
        if is_large_file:
            await ms.edit("✂️ Splitting large file into 2GB chunks...")
            upload_paths = await split_large_file(metadata_path if _bool_metadata else file_path)
        else:
            upload_paths = [metadata_path if _bool_metadata else file_path]
        
        # Upload all files as videos
        total_chunks = len(upload_paths)
        for i, path in enumerate(upload_paths):
            chunk_num = i + 1
            await upload_as_video(
                bot, 
                user_id, 
                path, 
                caption, 
                ph_path, 
                ms,
                chunk_info=(chunk_num, total_chunks) if is_large_file else None
            )
        
        await ms.edit("✅ All video uploads completed successfully!")
        await sleep(2)
        
    except Exception as e:
        await original_message.reply(f"An error occurred: {str(e)}")
    finally:
        # Cleanup
        def safe_remove(path):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except:
                pass
        
        def safe_rmdir(dirpath):
            try:
                if dirpath and os.path.exists(dirpath) and not os.listdir(dirpath):
                    os.rmdir(dirpath)
            except:
                pass
        
        # Clean up all chunks and original files
        if 'upload_paths' in locals():
            for path in upload_paths:
                safe_remove(path)
                if is_large_file:
                    for part_file in glob.glob(f"{path}.part*"):
                        safe_remove(part_file)
        
        safe_remove(ph_path)
        safe_remove(file_path)
        safe_remove(metadata_path)
        
        safe_rmdir(os.path.dirname(file_path))
        if metadata_path:
            safe_rmdir(os.path.dirname(metadata_path))
        
        # Clear session
        if user_id in user_sessions:
            del user_sessions[user_id]
        
        if 'ms' in locals():
            await ms.delete()
