from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from hachoir.metadata import extractMetadata
from helper.ffmpeg import fix_thumb, take_screen_shot, add_metadata
from hachoir.parser import createParser
from helper.utils import progress_for_pyrogram, convert, humanbytes, add_prefix_suffix
from helper.database import jishubotz
from asyncio import sleep
from PIL import Image
import os, time, re, random, asyncio

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_media(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name

    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("❌ File size exceeds 2GB limit.")

    # Ask for custom thumbnail
    await message.reply_text(
        "**Please send a custom thumbnail (image) for this file.**\n\n"
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
    except asyncio.TimeoutError:
        thumb_path = None
        await message.reply_text("⏰ No thumbnail received. Proceeding without one.")

    # Start processing (default: upload as video)
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

    # Upload as video (default)
    await ms.edit("🎥 Uploading as video...")
    try:
        await client.send_video(
            chat_id=message.chat.id,
            video=metadata_path if _bool_metadata else file_path,
            caption=caption,
            thumb=thumb_path,
            duration=duration,
            progress=progress_for_pyrogram,
            progress_args=("⬆️ Uploading...", ms, time.time())
        )
    except Exception as e:
        await ms.edit(f"❌ Upload failed: {e}")
    finally:
        # Cleanup
        if thumb_path and os.path.exists(thumb_path):
            os.remove(thumb_path)
        if os.path.exists(file_path):
            os.remove(file_path)
        await ms.delete()
