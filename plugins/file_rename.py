from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply, CallbackQuery
from hachoir.metadata import extractMetadata
from helper.ffmpeg import fix_thumb, take_screen_shot, add_metadata, add_default_subtitle
from hachoir.parser import createParser
from helper.utils import progress_for_pyrogram, convert, humanbytes, add_prefix_suffix
from helper.database import jishubotz
from asyncio import sleep
from PIL import Image
import os, time, re, random, asyncio

# Dictionary to store user choices
user_choices = {}

@Client.on_callback_query(filters.regex(r'^subtitle_'))
async def subtitle_callback(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id
    
    if data == "subtitle_default":
        user_choices[user_id] = {"subtitle": "default"}
        await callback_query.message.edit_text(
            "✅ Default subtitle (MOHAN for 3 seconds) will be added.",
            reply_markup=None
        )
    elif data == "subtitle_custom":
        user_choices[user_id] = {"subtitle": "custom"}
        await callback_query.message.edit_text(
            "📁 Please send your subtitle file (.srt or .ass format):",
            reply_markup=ForceReply(True)
        )
    elif data == "subtitle_none":
        user_choices[user_id] = {"subtitle": "none"}
        await callback_query.message.edit_text(
            "✅ No subtitle will be added to your file.",
            reply_markup=None
        )
    await callback_query.answer()

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_media(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name
    user_id = message.from_user.id

    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("❌ File size exceeds 2GB limit.")

    # Ask for custom thumbnail
    thumb_msg = await message.reply_text(
        "**🖼️ Please send a custom thumbnail (image) for this file.**\n\n"
        "⚠️ Send as a photo (not as a document).\n"
        "⏳ Waiting for 60 seconds...",
        reply_markup=ForceReply(True)
    )
    
    try:
        # Wait for thumbnail (60 seconds timeout)
        thumbnail_msg = await client.listen(
            chat_id=message.chat.id,
            filters=filters.photo & filters.reply,
            timeout=60
        )
        thumb_path = await client.download_media(thumbnail_msg.photo)
        width, height, thumb_path = await fix_thumb(thumb_path)
        await thumb_msg.delete()
    except asyncio.TimeoutError:
        thumb_path = None
        await thumb_msg.edit_text("⏰ No thumbnail received. Proceeding without one.")

    # Ask for subtitle preference
    subtitle_keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Default Subtitle", callback_data="subtitle_default"),
            InlineKeyboardButton("Custom Subtitle", callback_data="subtitle_custom"),
        ],
        [
            InlineKeyboardButton("No Subtitle", callback_data="subtitle_none")
        ]
    ])
    
    sub_msg = await message.reply_text(
        "**📝 Choose subtitle option:**\n\n"
        "• Default: Adds 'MOHAN' for first 3 seconds\n"
        "• Custom: You provide subtitle file (.srt/.ass)\n"
        "• None: Original file without subtitles",
        reply_markup=subtitle_keyboard
    )
    
    # Initialize variables
    subtitle_path = None
    choice = None
    
    try:
        # Wait for user response (60 seconds timeout)
        wait_msg = await client.listen(
            chat_id=message.chat.id,
            timeout=60,
            filters=(filters.callback_query | 
                   (filters.document & filters.reply & 
                   (filters.regex(r'\.srt$') | filters.regex(r'\.ass$')))
        
        if isinstance(wait_msg, CallbackQuery):
            # User selected an option from the keyboard
            choice = user_choices.get(user_id, {}).get("subtitle")
            
            # If custom subtitle selected, wait for the file
            if choice == "custom":
                custom_sub_msg = await message.reply_text(
                    "📁 Please send your subtitle file (.srt or .ass format):",
                    reply_markup=ForceReply(True)
                )
                try:
                    subtitle_msg = await client.listen(
                        chat_id=message.chat.id,
                        filters=filters.document & filters.reply & 
                               (filters.regex(r'\.srt$') | filters.regex(r'\.ass$')),
                        timeout=60
                    )
                    subtitle_path = await client.download_media(subtitle_msg.document)
                    await custom_sub_msg.delete()
                except asyncio.TimeoutError:
                    await custom_sub_msg.edit_text("⏰ No subtitle received. Using default instead.")
                    choice = "default"
                    
        else:
            # User sent a subtitle file directly
            choice = "custom"
            subtitle_path = await client.download_media(wait_msg.document)
            
    except asyncio.TimeoutError:
        choice = "default"
        await message.reply_text("⏰ Timeout. Adding default subtitle.")
    finally:
        await sub_msg.delete()

    # Start processing
    ms = await message.reply_text("🚀 Downloading file...")
    file_path = f"downloads/{message.chat.id}/{filename}"
    
    try:
        path = await client.download_media(
            message=message,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("📥 Downloading...", ms, time.time()))
    except Exception as e:
        return await ms.edit(f"❌ Download failed: {e}")

    # Handle subtitle based on user choice
    if choice == "default":
        try:
            output_path = f"downloads/{message.chat.id}/subbed_{filename}"
            await add_default_subtitle(path, output_path, "MOHAN", duration=3)
            path = output_path
            await ms.edit("✅ Added default subtitle for first 3 seconds")
        except Exception as e:
            await ms.edit(f"⚠️ Couldn't add default subtitle: {e}")
    elif choice == "custom" and subtitle_path:
        try:
            # For custom subtitles, we'll handle during upload
            pass
        except Exception as e:
            await ms.edit(f"⚠️ Error processing custom subtitle: {e}")

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
                duration=convert(duration))
        except Exception as e:
            caption = f"**{filename}**"
    else:
        caption = f"**{filename}**"

    # Upload as video (default)
    await ms.edit("🎥 Uploading as video...")
    try:
        if choice == "custom" and subtitle_path:
            # If custom subtitle exists, send with subtitle
            await client.send_video(
                chat_id=message.chat.id,
                video=metadata_path if _bool_metadata else path,
                caption=caption,
                thumb=thumb_path,
                duration=duration,
                progress=progress_for_pyrogram,
                progress_args=("⬆️ Uploading with subtitles...", ms, time.time()),
                subtitles=subtitle_path)
        else:
            # Without custom subtitle (may have default subtitle)
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
        if subtitle_path and os.path.exists(subtitle_path):
            os.remove(subtitle_path)
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(path) and path != file_path:
            os.remove(path)
        if user_id in user_choices:
            del user_choices[user_id]
        await ms.delete()
