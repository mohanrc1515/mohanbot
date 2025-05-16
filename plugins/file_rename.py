from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from hachoir.metadata import extractMetadata
from helper.ffmpeg import fix_thumb, take_screen_shot, add_metadata, add_default_subtitle
from hachoir.parser import createParser
from helper.utils import progress_for_pyrogram, convert, humanbytes
from helper.database import jishubotz
from asyncio import sleep
from PIL import Image
import os
import time
import random
import asyncio

# Dictionary to store user thumbnail choices
user_thumbnails = {}

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_media(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name
    
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("Sorry, this bot doesn't support uploading files bigger than 2GB")

    # Ask if user wants thumbnail
    thumb_keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("With Thumbnail", callback_data="with_thumb")],
        [InlineKeyboardButton("Without Thumbnail", callback_data="without_thumb")]
    ])
    
    thumb_msg = await message.reply_text(
        "**Do you want to add a thumbnail?**",
        reply_markup=thumb_keyboard
    )

    try:
        # Wait for user's thumbnail choice
        thumb_response = await client.listen(
            chat_id=message.chat.id,
            filters=filters.callback_query,
            timeout=30
        )
        await thumb_msg.delete()
        
        if thumb_response.data == "with_thumb":
            # Ask for custom thumbnail
            thumb_ask = await message.reply_text(
                "**Please send a custom thumbnail (as photo, not document):**",
                reply_markup=ForceReply(True)
            )
            
            try:
                thumb_msg = await client.listen(
                    chat_id=message.chat.id,
                    filters=filters.photo & filters.reply,
                    timeout=30
                )
                thumb_path = await client.download_media(thumb_msg.photo)
                width, height, thumb_path = await fix_thumb(thumb_path)
                user_thumbnails[message.chat.id] = thumb_path
                await thumb_ask.delete()
            except asyncio.TimeoutError:
                await thumb_ask.edit_text("⏰ No thumbnail received. Proceeding without one.")
                user_thumbnails[message.chat.id] = None
        else:
            user_thumbnails[message.chat.id] = None
            
    except asyncio.TimeoutError:
        await thumb_msg.edit_text("⏰ Timeout. Proceeding without thumbnail.")
        user_thumbnails[message.chat.id] = None

    # Start processing with original filename
    ms = await message.reply_text("🚀 Downloading file...")
    file_path = f"downloads/{message.chat.id}/{filename}"
    
    try:
        path = await client.download_media(
            message=message,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("📥 Downloading...", ms, time.time())
        )
    except Exception as e:
        return await ms.edit(f"❌ Download failed: {e}")

    # Add default "MOHAN" subtitle for first 3 seconds
    try:
        output_path = f"downloads/{message.chat.id}/subbed_{filename}"
        await add_default_subtitle(path, output_path, "MOHAN", duration=3)
        path = output_path
        await ms.edit("✅ Added default subtitle for first 3 seconds")
    except Exception as e:
        await ms.edit(f"⚠️ Couldn't add default subtitle: {e}")

    # Get metadata (if enabled)
    _bool_metadata = await jishubotz.get_metadata(message.chat.id)
    if _bool_metadata:
        metadata = await jishubotz.get_metadata_code(message.chat.id)
        metadata_path = f"Metadata/{filename}"
        await add_metadata(path, metadata_path, metadata, ms)
    else:
        await ms.edit("⏳ Preparing to upload...")

    # Extract duration (for videos/audio)
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
    c_caption = await jishubotz.get_caption(message.chat.id)
    if c_caption:
        try:
            caption = c_caption.format(
                filename=filename,
                filesize=humanbytes(file.file_size),
                duration=convert(duration)
            )
        except Exception as e:
            caption = f"**{filename}**"
    else:
        caption = f"**{filename}**"

    # Get thumbnail
    thumb_path = user_thumbnails.get(message.chat.id)
    if not thumb_path:
        # Try to get thumbnail from database
        c_thumb = await jishubotz.get_thumbnail(message.chat.id)
        if c_thumb:
            thumb_path = await client.download_media(c_thumb)
            width, height, thumb_path = await fix_thumb(thumb_path)
        else:
            # Try to generate thumbnail from video
            if file.media == MessageMediaType.VIDEO and duration > 0:
                try:
                    thumb_path_ = await take_screen_shot(path, os.path.dirname(path), random.randint(0, duration - 1))
                    width, height, thumb_path = await fix_thumb(thumb_path_)
                except:
                    thumb_path = None

    # Upload as video (for all file types)
    await ms.edit("🎥 Uploading as video...")
    try:
        await client.send_video(
            chat_id=message.chat.id,
            video=metadata_path if _bool_metadata else path,
            caption=caption,
            thumb=thumb_path,
            duration=duration,
            progress=progress_for_pyrogram,
            progress_args=("⬆️ Uploading...", ms, time.time()))
    except Exception as e:
        await ms.edit(f"❌ Upload failed: {e}")
    finally:
        # Cleanup
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(path) and path != file_path:
            os.remove(path)
        if message.chat.id in user_thumbnails:
            del user_thumbnails[message.chat.id]
        await ms.delete()
