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
import os, time, random, uuid

# Dictionary to store temporary thumbnails with unique session IDs
user_sessions = {}

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_file_upload(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name  
    
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("Sorry, this bot doesn't support uploading files bigger than 2GB")

    # Create a unique session ID for this upload
    session_id = str(uuid.uuid4())
    
    # Store the message reference with unique session ID
    user_sessions[message.from_user.id] = {
        'session_id': session_id,
        'message_id': message.id,
        'filename': filename,
        'original_message': message
    }

    await message.reply(
        text="Please send me a thumbnail photo for this file (send as photo).\n\n"
             "If you don't want a thumbnail, just click /skip",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Skip Thumbnail", callback_data=f"skip_thumbnail_{session_id}")]
        ])
    )

@Client.on_message(filters.private & filters.photo)
async def receive_thumbnail(bot, message):
    user_id = message.from_user.id
    
    if user_id not in user_sessions:
        return await message.reply("Please send a file first, then send the thumbnail")
    
    session_data = user_sessions[user_id]
    
    # Store the thumbnail with the session ID
    session_data['thumbnail'] = message
    user_sessions[user_id] = session_data
    
    await process_and_upload(bot, user_id, session_data['original_message'], thumbnail_message=message)

@Client.on_callback_query(filters.regex("^skip_thumbnail_"))
async def skip_thumbnail(bot, update):
    user_id = update.from_user.id
    session_id = update.data.split("_")[2]
    
    if user_id not in user_sessions or user_sessions[user_id]['session_id'] != session_id:
        return await update.answer("Session expired or invalid")
    
    session_data = user_sessions[user_id]
    await process_and_upload(bot, user_id, session_data['original_message'], thumbnail_message=None)
    await update.message.delete()

async def process_and_upload(bot, user_id, original_message, thumbnail_message=None):
    if user_id not in user_sessions:
        return
    
    session_data = user_sessions[user_id]
    filename = session_data['filename']
    
    # Verify this is still the active session
    file = original_message
    if not hasattr(file, file.media.value):
        return
    
    media = getattr(file, file.media.value)
    
    # Prepare paths with session ID to avoid conflicts
    prefix = await jishubotz.get_prefix(user_id)
    suffix = await jishubotz.get_suffix(user_id)
    
    try:
        new_filename = add_prefix_suffix(filename, prefix, suffix)
    except Exception as e:
        return await original_message.reply(f"Error setting prefix/suffix: {e}")
    
    # Create unique download path with session ID
    unique_path_id = session_data['session_id'][:8]
    file_path = f"downloads/{user_id}_{unique_path_id}/{new_filename}"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    ms = await original_message.reply("🚀 Downloading file...")
    
    try:
        path = await bot.download_media(
            message=file,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("🚀 Downloading...", ms, time.time())
        )
    except Exception as e:
        await ms.edit(f"Download failed: {e}")
        # Clean up session
        if user_id in user_sessions:
            del user_sessions[user_id]
        return
    
    # Handle metadata if enabled
    _bool_metadata = await jishubotz.get_metadata(user_id)
    metadata_path = None
    if _bool_metadata:
        metadata = await jishubotz.get_metadata_code(user_id)
        metadata_path = f"Metadata/{unique_path_id}_{new_filename}"
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
    if thumbnail_message:
        try:
            ph_path = await bot.download_media(thumbnail_message)
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
            video=metadata_path if _bool_metadata and metadata_path else file_path,
            caption=caption,
            thumb=ph_path,
            duration=duration,
            progress=progress_for_pyrogram,
            progress_args=("📤 Uploading...", ms, time.time())
        )
    except Exception as e:
        await ms.edit(f"Upload failed: {e}")
    finally:
        # Clean up files
        for file_to_remove in [ph_path, file_path, metadata_path]:
            if file_to_remove and os.path.exists(file_to_remove):
                try:
                    os.remove(file_to_remove)
                except:
                    pass
        
        # Clean up directory
        download_dir = os.path.dirname(file_path)
        if os.path.exists(download_dir):
            try:
                os.rmdir(download_dir)
            except:
                pass
        
        # Remove session data
        if user_id in user_sessions and user_sessions[user_id]['session_id'] == session_data['session_id']:
            del user_sessions[user_id]
        
        await ms.delete()
