from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from helper.ffmpeg import fix_thumb, take_screen_shot, add_metadata

# Dictionary to store temporary data
temp_thumbnails = {}

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_file_upload(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name  
    
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("Sorry, this bot doesn't support files bigger than 2GB")

    # Store file info
    temp_thumbnails[message.from_user.id] = {
        'message_id': message.id,
        'filename': filename
    }

    # Ask for thumbnail with simplified options
    await message.reply(
        text=f"**File Received:** `{filename}`\n\n"
             "Would you like to add a custom thumbnail?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes, send custom thumbnail", callback_data="want_thumbnail")],
            [InlineKeyboardButton("No, use video frame (190s)", callback_data="use_default_thumbnail")]
        ])
    )

@Client.on_message(filters.private & filters.photo)
async def receive_thumbnail(bot, message):
    user_id = message.from_user.id
    
    if user_id not in temp_thumbnails:
        return await message.reply("Please send a file first")
    
    # Store thumbnail
    temp_thumbnails[user_id]['thumbnail_id'] = message.id
    
    # Proceed to upload
    filename = temp_thumbnails[user_id]['filename']
    await message.reply(
        text=f"✅ Custom thumbnail received!\n\n"
             f"File: `{filename}`\n"
             "Click below to start upload",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Start Upload", callback_data="upload_video")]
        ])
    )

@Client.on_callback_query(filters.regex("want_thumbnail"))
async def want_thumbnail(bot, update):
    await update.message.edit_text(
        "Please send your custom thumbnail as a photo\n\n"
        "Or click below to use default frame",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Use Default Frame", callback_data="use_default_thumbnail")]
        ])
    )

@Client.on_callback_query(filters.regex("use_default_thumbnail"))
async def use_default_thumbnail(bot, update):
    user_id = update.from_user.id
    if user_id not in temp_thumbnails:
        return await update.answer("No file found", show_alert=True)
    
    filename = temp_thumbnails[user_id]['filename']
    await update.message.edit_text(
        text=f"⏩ Will use frame from 190th second!\n\n"
             f"File: `{filename}`\n"
             "Click below to start upload",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Start Upload", callback_data="upload_video")]
        ])
    )

@Client.on_callback_query(filters.regex("^upload_video"))
async def upload_file(bot, update):
    user_id = update.from_user.id
    if user_id not in temp_thumbnails:
        return await update.answer("No file found", show_alert=True)
    
    file_data = temp_thumbnails[user_id]
    original_message = await bot.get_messages(user_id, file_data['message_id'])
    file = getattr(original_message, original_message.media.value)
    
    # Download file
    file_path = f"downloads/{user_id}/{file.file_name}"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    ms = await update.message.edit("🚀 Downloading file...")
    
    try:
        path = await bot.download_media(
            message=original_message,
            file_name=file_path,
            progress=progress_for_pyrogram,
            progress_args=("Downloading...", ms, time.time())
        )
    except Exception as e:
        return await ms.edit(f"Download failed: {e}")
    
    # Handle thumbnail
    ph_path = None
    if 'thumbnail_id' in file_data:  # Custom thumbnail
        try:
            thumb_msg = await bot.get_messages(user_id, file_data['thumbnail_id'])
            ph_path = await bot.download_media(thumb_msg)
            width, height, ph_path = await fix_thumb(ph_path)
        except Exception as e:
            print(f"Thumbnail error: {e}")
    elif original_message.media == MessageMediaType.VIDEO:  # Default frame
        try:
            ph_path = await take_screen_shot(
                file_path,
                os.path.dirname(os.path.abspath(file_path)),
                190  # 190th second frame
            )
            if ph_path:
                width, height, ph_path = await fix_thumb(ph_path)
        except Exception as e:
            print(f"Screenshot error: {e}")
    
    # Upload video
    await ms.edit("📤 Uploading video...")
    try:
        await bot.send_video(
            chat_id=user_id,
            video=file_path,
            thumb=ph_path,
            progress=progress_for_pyrogram,
            progress_args=("Uploading...", ms, time.time())
        )
    except Exception as e:
        await ms.edit(f"Upload failed: {e}")
    finally:
        # Cleanup
        for path in [ph_path, file_path]:
            if path and os.path.exists(path):
                os.remove(path)
        if user_id in temp_thumbnails:
            del temp_thumbnails[user_id]
        await ms.delete()
