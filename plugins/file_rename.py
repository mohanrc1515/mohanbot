from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from hachoir.metadata import extractMetadata
from helper.ffmpeg import fix_thumb, take_screen_shot, add_metadata
from hachoir.parser import createParser
from helper.utils import progress_for_pyrogram, convert, humanbytes, add_prefix_suffix
from helper.database import jishubotz
from asyncio import sleep
import os, time, random

# Dictionary to store temporary data
user_data = {}

@Client.on_message(filters.private & filters.command("start"))
async def start_command(client, message):
    # Clear any existing data when user starts fresh
    user_id = message.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    
    await message.reply(
        text="📁 **File Upload Bot**\n\n"
             "Please send me a thumbnail photo first (send as photo).\n\n"
             "If you don't want a thumbnail, click /skip",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Skip Thumbnail", callback_data="skip_thumbnail")]
        ])
    )

@Client.on_message(filters.private & filters.photo)
async def receive_thumbnail(bot, message):
    user_id = message.from_user.id
    
    # Initialize user data if not exists
    if user_id not in user_data:
        user_data[user_id] = {}
    
    # Store the thumbnail message ID
    user_data[user_id]['thumbnail_id'] = message.id
    
    await message.reply(
        text="✅ Thumbnail received!\n\n"
             "Now please send me the file you want to upload (video/document/audio)."
    )

@Client.on_callback_query(filters.regex("skip_thumbnail"))
async def skip_thumbnail(bot, update):
    user_id = update.from_user.id
    
    # Initialize user data if not exists
    if user_id not in user_data:
        user_data[user_id] = {}
    
    await update.message.edit_text(
        text="⏩ Thumbnail skipped!\n\n"
             "Now please send me the file you want to upload (video/document/audio)."
    )

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_file_upload(client, message):
    user_id = message.from_user.id
    
    # Check if user has started the process
    if user_id not in user_data:
        return await message.reply("Please send /start first to begin the upload process")
    
    file = getattr(message, message.media.value)
    filename = file.file_name  
    
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("Sorry, this bot doesn't support uploading files bigger than 2GB")

    # Store the file message reference
    user_data[user_id]['file_message_id'] = message.id
    user_data[user_id]['filename'] = filename
    
    # Start processing immediately
    await process_and_upload(client, user_id, message)

async def process_and_upload(bot, user_id, message):
    if user_id not in user_data:
        return
    
    file_data = user_data[user_id]
    
    # Check if file was sent
    if 'file_message_id' not in file_data:
        return await message.reply("Please send a file to upload")
    
    original_message_id = file_data['file_message_id']
    filename = file_data['filename']
    
    # Get the original message
    try:
        original_message = await bot.get_messages(user_id, original_message_id)
    except:
        return await message.edit("Original message not found")
    
    file = original_message
    media = getattr(file, file.media.value)
    
    # Prepare paths and variables
    prefix = await jishubotz.get_prefix(user_id)
    suffix = await jishubotz.get_suffix(user_id)
    
    try:
        new_filename = add_prefix_suffix(filename, prefix, suffix)
    except Exception as e:
        return await message.edit(f"Error setting prefix/suffix: {e}")
    
    file_path = f"downloads/{user_id}/{new_filename}"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    ms = await message.edit("🚀 Downloading file...")
    
    try:
        path = await bot.download_media(
            message=file,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("🚀 Downloading...", ms, time.time())
        )
    except Exception as e:
        return await ms.edit(f"Download failed: {e}")
    
    # Handle metadata if enabled
    _bool_metadata = await jishubotz.get_metadata(user_id)
    if _bool_metadata:
        metadata = await jishubotz.get_metadata_code(user_id)
        metadata_path = f"Metadata/{new_filename}"
        await add_metadata(path, metadata_path, metadata, ms)
    
    # Get duration for media files
    duration = 0
    try:
        parser = createParser(file_path)
        metadata = extractMetadata(parser)
        if metadata.has("duration"):
            duration = metadata.get('duration').seconds
        parser.close()
    except:
        pass
    
    # Prepare caption
    c_caption = await jishubotz.get_caption(user_id)
    if c_caption:
        try:
            caption = c_caption.format(
                filename=new_filename,
                filesize=humanbytes(media.file_size),
                duration=convert(duration)
            )
        except Exception as e:
            caption = f"**{new_filename}**"
    else:
        caption = f"**{new_filename}**"
    
    # Handle thumbnail
    ph_path = None
    if 'thumbnail_id' in file_data:
        try:
            thumb_msg = await bot.get_messages(user_id, file_data['thumbnail_id'])
            ph_path = await bot.download_media(thumb_msg)
            width, height, ph_path = await fix_thumb(ph_path)
        except Exception as e:
            print(f"Error processing thumbnail: {e}")
    
    # If no thumbnail was provided, try to generate one for videos
    if not ph_path and file.media == MessageMediaType.VIDEO:
        try:
            ph_path = await take_screen_shot(
                file_path,
                os.path.dirname(os.path.abspath(file_path)),
                random.randint(0, duration - 1) if duration > 0 else 0
            )
            width, height, ph_path = await fix_thumb(ph_path)
        except Exception as e:
            print(f"Error generating thumbnail: {e}")
    
    # Start uploading as video
    await ms.edit("📤 Uploading as video...")
    
    try:
        await bot.send_video(
            chat_id=user_id,
            video=metadata_path if _bool_metadata else file_path,
            caption=caption,
            thumb=ph_path,
            duration=duration,
            progress=progress_for_pyrogram,
            progress_args=("📤 Uploading...", ms, time.time())
        )
    except Exception as e:
        await ms.edit(f"Upload failed: {e}")
    finally:
        # Clean up
        if ph_path and os.path.exists(ph_path):
            os.remove(ph_path)
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
        if _bool_metadata and metadata_path and os.path.exists(metadata_path):
            os.remove(metadata_path)
        
        # Remove temporary data
        if user_id in user_data:
            del user_data[user_id]
        
        await ms.delete()
