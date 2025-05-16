from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from hachoir.metadata import extractMetadata
from helper.ffmpeg import fix_thumb, add_metadata  # Removed take_screen_shot
from hachoir.parser import createParser
from helper.utils import progress_for_pyrogram, convert, humanbytes, add_prefix_suffix
from helper.database import jishubotz
from asyncio import sleep
import os, time, random
from pathlib import Path

# Dictionary to store temporary data
temp_data = {}

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_file_upload(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name  
    
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("Sorry, this bot doesn't support uploading files bigger than 2GB")

    # Store the message reference for later use
    temp_data[message.from_user.id] = {
        'message_id': message.id,
        'filename': filename
    }

    # Only ask for custom thumbnail
    await message.reply(
        text=f"**File Received:** `{filename}`\n\n"
             "Please send a custom thumbnail photo for this file\n\n"
             "The file will not be processed without a thumbnail",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Cancel Upload", callback_data="cancel_upload")]
        ])
    )

@Client.on_message(filters.private & filters.photo)
async def receive_thumbnail(bot, message):
    user_id = message.from_user.id
    
    if user_id not in temp_data:
        return await message.reply("Please send a file first, then send the thumbnail")
    
    # Store the thumbnail message ID
    temp_data[user_id]['thumbnail_id'] = message.id
    
    # Proceed to upload
    filename = temp_data[user_id]['filename']
    original_message_id = temp_data[user_id]['message_id']
    
    await message.reply(
        text=f"✅ Thumbnail received!\n\nFile ready for upload:\n`{filename}`",
        reply_to_message_id=original_message_id,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Start Upload", callback_data="upload_video")],
            [InlineKeyboardButton("Cancel", callback_data="cancel_upload")]
        ])
    )

@Client.on_callback_query(filters.regex("cancel_upload"))
async def cancel_upload(bot, update):
    user_id = update.from_user.id
    if user_id in temp_data:
        del temp_data[user_id]
    await update.message.edit_text("❌ Upload cancelled")
    await sleep(5)
    await update.message.delete()

@Client.on_callback_query(filters.regex("^upload_video"))
async def upload_file(bot, update):
    user_id = update.from_user.id
    
    if user_id not in temp_data:
        return await update.answer("No file found to upload", show_alert=True)
    
    file_data = temp_data[user_id]
    
    # Verify thumbnail exists
    if 'thumbnail_id' not in file_data:
        return await update.answer("Please send a thumbnail first", show_alert=True)
    
    # Get the original message
    try:
        original_message = await bot.get_messages(user_id, file_data['message_id'])
    except:
        return await update.answer("Original message not found", show_alert=True)
    
    file = original_message
    media = getattr(file, file.media.value)
    
    # Prepare paths and variables
    prefix = await jishubotz.get_prefix(user_id)
    suffix = await jishubotz.get_suffix(user_id)
    
    try:
        new_filename = add_prefix_suffix(file_data['filename'], prefix, suffix)
    except Exception as e:
        return await update.message.edit(f"Error setting prefix/suffix: {e}")
    
    file_path = f"downloads/{user_id}/{new_filename}"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    ms = await update.message.edit("🚀 Downloading file...")
    
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
    if file.media == MessageMediaType.VIDEO:
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
                duration=convert(duration) if duration else ""
            )
        except Exception as e:
            caption = f"**{new_filename}**"
    else:
        caption = f"**{new_filename}**"
    
    # Handle thumbnail (only custom)
    try:
        thumb_msg = await bot.get_messages(user_id, file_data['thumbnail_id'])
        ph_path = await bot.download_media(thumb_msg)
        width, height, ph_path = await fix_thumb(ph_path)
    except Exception as e:
        return await ms.edit(f"❌ Thumbnail processing failed: {e}")
    
    # Start uploading as video
    await ms.edit("📤 Uploading file as video...")
    
    try:
        await bot.send_video(
            chat_id=user_id,
            video=metadata_path if _bool_metadata else file_path,
            caption=caption,
            thumb=ph_path,
            duration=duration if duration else None,
            progress=progress_for_pyrogram,
            progress_args=("📤 Uploading...", ms, time.time())
        )
    except Exception as e:
        await ms.edit(f"Upload failed: {e}")
    finally:
        # Clean up
        if 'ph_path' in locals() and ph_path and os.path.exists(ph_path):
            os.remove(ph_path)
        if 'file_path' in locals() and file_path and os.path.exists(file_path):
            os.remove(file_path)
        if '_bool_metadata' in locals() and _bool_metadata and 'metadata_path' in locals() and os.path.exists(metadata_path):
            os.remove(metadata_path)
        
        # Remove temporary data
        if user_id in temp_data:
            del temp_data[user_id]
        
        await sleep(5)
        await ms.delete()
