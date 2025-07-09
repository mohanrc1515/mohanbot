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

# Dictionary to store temporary thumbnails with better structure
user_sessions = {}

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_file_upload(client, message):
    user_id = message.from_user.id
    
    # Clear any previous session for this user
    if user_id in user_sessions:
        del user_sessions[user_id]
    
    file = getattr(message, message.media.value)
    filename = file.file_name  
    
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("Sorry, this bot doesn't support uploading files bigger than 2GB")

    # Create a new session for this user
    user_sessions[user_id] = {
        'original_message': message,
        'filename': filename,
        'state': 'awaiting_thumbnail'
    }

    # Ask for thumbnail
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
    
    # Store the thumbnail and update state
    user_sessions[user_id]['thumbnail'] = message
    user_sessions[user_id]['state'] = 'processing'
    
    # Get the original message
    original_message = user_sessions[user_id]['original_message']
    
    # Start processing
    await process_and_upload(bot, user_id, original_message, thumbnail_message=message)

@Client.on_callback_query(filters.regex("skip_thumbnail"))
async def skip_thumbnail(bot, update):
    user_id = update.from_user.id
    
    if user_id not in user_sessions or user_sessions[user_id]['state'] != 'awaiting_thumbnail':
        return await update.answer("No file found to upload")
    
    # Update state
    user_sessions[user_id]['state'] = 'processing'
    
    # Get the original message
    original_message = user_sessions[user_id]['original_message']
    
    # Start processing without thumbnail
    await process_and_upload(bot, user_id, original_message, thumbnail_message=None)
    await update.message.delete()

async def process_and_upload(bot, user_id, original_message, thumbnail_message=None):
    if user_id not in user_sessions:
        return
    
    try:
        file_data = user_sessions[user_id]
        filename = file_data['filename']
        
        file = original_message
        media = getattr(file, file.media.value)
        
        # Prepare paths and variables
        prefix = await jishubotz.get_prefix(user_id)
        suffix = await jishubotz.get_suffix(user_id)
        
        try:
            new_filename = add_prefix_suffix(filename, prefix, suffix)
        except Exception as e:
            return await original_message.reply(f"Error setting prefix/suffix: {e}")
        
        # Create unique download path to avoid conflicts
        download_dir = f"downloads/{user_id}/{int(time.time())}/"
        os.makedirs(download_dir, exist_ok=True)
        file_path = os.path.join(download_dir, new_filename)
        
        ms = await original_message.reply("🚀 Downloading file...")
        
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
        metadata_path = None
        if _bool_metadata:
            metadata = await jishubotz.get_metadata_code(user_id)
            metadata_dir = f"Metadata/{user_id}/{int(time.time())}/"
            os.makedirs(metadata_dir, exist_ok=True)
            metadata_path = os.path.join(metadata_dir, new_filename)
            await add_metadata(path, metadata_path, metadata, ms)
        
        # Get duration for media files
        duration = 0
        try:
            parser = createParser(file_path)
            metadata = extractMetadata(parser)
            if metadata and metadata.has("duration"):
                duration = metadata.get('duration').seconds
            if parser:
                parser.close()
        except Exception as e:
            print(f"Error getting duration: {e}")
        
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
                    file_name=os.path.join(thumb_dir, f"thumb_{int(time.time())}.jpg")
                )
                width, height, ph_path = await fix_thumb(ph_path)
            except Exception as e:
                print(f"Error processing thumbnail: {e}")
        
        # If no thumbnail was provided, try to generate one for videos
        if not ph_path:
            try:
                thumb_dir = f"thumbnails/{user_id}/"
                os.makedirs(thumb_dir, exist_ok=True)
                ph_path = await take_screen_shot(
                    file_path,
                    thumb_dir,
                    random.randint(0, duration - 1) if duration > 0 else 0
                )
                width, height, ph_path = await fix_thumb(ph_path)
            except Exception as e:
                print(f"Error generating thumbnail: {e}")
        
        # Start uploading (FORCE AS VIDEO)
        await ms.edit("📤 Uploading as video...")
        
        try:
            await bot.send_video(
                chat_id=user_id,
                video=metadata_path if _bool_metadata else file_path,
                caption=caption,
                thumb=ph_path,
                duration=duration if duration else None,  # Set duration if available
                progress=progress_for_pyrogram,
                progress_args=("📤 Uploading...", ms, time.time())
            )
        except FloodWait as e:
            await ms.edit(f"Too many requests! Please wait {e.value} seconds before trying again.")
            await sleep(e.value)
            return await process_and_upload(bot, user_id, original_message, thumbnail_message)
        except Exception as e:
            await ms.edit(f"Upload failed: {str(e)}")
            raise e
        finally:
            # Clean up files
            def safe_remove(filepath):
                try:
                    if filepath and os.path.exists(filepath):
                        os.remove(filepath)
                except Exception as e:
                    print(f"Error removing file {filepath}: {e}")
            
            safe_remove(ph_path)
            safe_remove(file_path)
            safe_remove(metadata_path)
            
            # Clean up empty directories
            def safe_rmdir(dirpath):
                try:
                    if dirpath and os.path.exists(dirpath) and not os.listdir(dirpath):
                        os.rmdir(dirpath)
                except Exception as e:
                    print(f"Error removing directory {dirpath}: {e}")
            
            safe_rmdir(os.path.dirname(file_path))
            if metadata_path:
                safe_rmdir(os.path.dirname(metadata_path))
            
            # Clear the user session
            if user_id in user_sessions:
                del user_sessions[user_id]
            
            await ms.delete()
    
    except Exception as e:
        await original_message.reply(f"An error occurred: {str(e)}")
        if user_id in user_sessions:
            del user_sessions[user_id]
