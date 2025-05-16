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

# Dictionary to store temporary thumbnails (in-memory, you might want to use a database instead)
temp_thumbnails = {}

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_file_upload(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name  
    
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("Sorry, this bot doesn't support uploading files bigger than 2GB")

    # Store the message reference for later use
    temp_thumbnails[message.from_user.id] = {
        'message_id': message.id,
        'filename': filename
    }

    # Always ask for thumbnail first
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
    
    if user_id not in temp_thumbnails:
        return await message.reply("Please send a file first, then send the thumbnail")
    
    # Store the thumbnail message ID temporarily
    temp_thumbnails[user_id]['thumbnail_id'] = message.id
    
    # Show upload options
    filename = temp_thumbnails[user_id]['filename']
    original_message_id = temp_thumbnails[user_id]['message_id']
    
    buttons = [
        [InlineKeyboardButton("📁 Document", callback_data="upload_document")],
        [InlineKeyboardButton("🎥 Video", callback_data="upload_video")],
        [InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")]
    ]
    
    await message.reply(
        text=f"Thumbnail received!\n\nNow select the output file type for:\n`{filename}`",
        reply_to_message_id=original_message_id,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex("skip_thumbnail"))
async def skip_thumbnail(bot, update):
    user_id = update.from_user.id
    
    if user_id not in temp_thumbnails:
        return await update.answer("No file found to upload")
    
    # Show upload options without thumbnail
    filename = temp_thumbnails[user_id]['filename']
    original_message_id = temp_thumbnails[user_id]['message_id']
    
    buttons = [
        [InlineKeyboardButton("📁 Document", callback_data="upload_document")],
        [InlineKeyboardButton("🎥 Video", callback_data="upload_video")],
        [InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")]
    ]
    
    await update.message.edit_text(
        text=f"Thumbnail skipped!\n\nSelect the output file type for:\n`{filename}`",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex("^upload"))
async def upload_file(bot, update):
    user_id = update.from_user.id
    
    if user_id not in temp_thumbnails:
        return await update.answer("No file found to upload", show_alert=True)
    
    file_data = temp_thumbnails[user_id]
    original_message_id = file_data['message_id']
    filename = file_data['filename']
    
    # Get the original message
    try:
        original_message = await bot.get_messages(user_id, original_message_id)
    except:
        return await update.answer("Original message not found", show_alert=True)
    
    file = original_message
    media = getattr(file, file.media.value)
    
    # Prepare paths and variables
    prefix = await jishubotz.get_prefix(user_id)
    suffix = await jishubotz.get_suffix(user_id)
    
    try:
        new_filename = add_prefix_suffix(filename, prefix, suffix)
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
    
    # Start uploading
    await ms.edit("📤 Uploading file...")
    upload_type = update.data.split("_")[1]
    
    try:
        if upload_type == "document":
            await bot.send_document(
                chat_id=user_id,
                document=metadata_path if _bool_metadata else file_path,
                thumb=ph_path,
                caption=caption,
                progress=progress_for_pyrogram,
                progress_args=("📤 Uploading...", ms, time.time())
            )
        elif upload_type == "video":
            await bot.send_video(
                chat_id=user_id,
                video=metadata_path if _bool_metadata else file_path,
                caption=caption,
                thumb=ph_path,
                duration=duration,
                progress=progress_for_pyrogram,
                progress_args=("📤 Uploading...", ms, time.time())
            )
        elif upload_type == "audio":
            await bot.send_audio(
                chat_id=user_id,
                audio=metadata_path if _bool_metadata else file_path,
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
        if user_id in temp_thumbnails:
            del temp_thumbnails[user_id]
        
        await ms.delete()
