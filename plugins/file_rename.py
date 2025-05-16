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
async def rename_start(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name  
    if file.file_size > 2000 * 1024 * 1024:
         return await message.reply_text("Sorry Bro This Bot Doesn't Support Uploading Files Bigger Than 2GB")

    try:
        await message.reply_text(
            text=f"**Please Enter New Filename...**\n\n**Old File Name** :- `{filename}`",
	    reply_to_message_id=message.id,  
	    reply_markup=ForceReply(True)
        )       
        await sleep(30)
    except FloodWait as e:
        await sleep(e.value)
        await message.reply_text(
            text=f"**Please Enter New Filename**\n\n**Old File Name** :- `{filename}`",
	    reply_to_message_id=message.id,  
	    reply_markup=ForceReply(True)
        )
    except:
        pass


@Client.on_message(filters.private & filters.reply)
async def refunc(client, message):
    reply_message = message.reply_to_message
    if (reply_message.reply_markup) and isinstance(reply_message.reply_markup, ForceReply):
        new_name = message.text 
        await message.delete() 
        msg = await client.get_messages(message.chat.id, reply_message.id)
        file = msg.reply_to_message
        media = getattr(file, file.media.value)
        if not "." in new_name:
            if "." in media.file_name:
                extn = media.file_name.rsplit('.', 1)[-1]
            else:
                extn = "mkv"
            new_name = new_name + "." + extn
        await reply_message.delete()

        # Ask for thumbnail
        await message.reply_text(
            text="**Please send a thumbnail image for this file** (send as photo)\n\n"
                 "Send /skip if you don't want to add a thumbnail",
            reply_to_message_id=file.id
        )
        
        # Store the filename in user data to use after thumbnail is received
        client.user_data[message.from_user.id] = {
            "new_name": new_name,
            "file_message_id": file.id
        }


@Client.on_message(filters.private & filters.photo)
async def receive_thumbnail(client, message):
    user_id = message.from_user.id
    if user_id not in client.user_data:
        return
    
    data = client.user_data[user_id]
    new_name = data["new_name"]
    file_message_id = data["file_message_id"]
    
    # Download the thumbnail
    thumb_path = f"downloads/{user_id}_thumb.jpg"
    await message.download(file_name=thumb_path)
    
    # Get the file message
    file = await client.get_messages(message.chat.id, file_message_id)
    
    # Show upload options
    button = [[InlineKeyboardButton("📁 Document", callback_data="upload_document")]]
    if file.media in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
        button.append([InlineKeyboardButton("🎥 Video", callback_data="upload_video")])
    elif file.media == MessageMediaType.AUDIO:
        button.append([InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")])
    
    await message.reply(
        text=f"**Select The Output File Type**\n\n**File Name :-** `{new_name}`\n\n"
             "✅ Thumbnail received",
        reply_to_message_id=file.id,
        reply_markup=InlineKeyboardMarkup(button)
    )
    
    # Store thumbnail path in user data
    client.user_data[user_id]["thumb_path"] = thumb_path
    client.user_data[user_id]["thumb_message_id"] = message.id


@Client.on_message(filters.private & filters.command("skip"))
async def skip_thumbnail(client, message):
    user_id = message.from_user.id
    if user_id not in client.user_data:
        return
    
    data = client.user_data[user_id]
    new_name = data["new_name"]
    file_message_id = data["file_message_id"]
    
    # Get the file message
    file = await client.get_messages(message.chat.id, file_message_id)
    
    # Show upload options
    button = [[InlineKeyboardButton("📁 Document", callback_data="upload_document")]]
    if file.media in [MessageMediaType.VIDEO, MessageMediaType.DOCUMENT]:
        button.append([InlineKeyboardButton("🎥 Video", callback_data="upload_video")])
    elif file.media == MessageMediaType.AUDIO:
        button.append([InlineKeyboardButton("🎵 Audio", callback_data="upload_audio")])
    
    await message.reply(
        text=f"**Select The Output File Type**\n\n**File Name :-** `{new_name}`\n\n"
             "⏩ Thumbnail skipped",
        reply_to_message_id=file.id,
        reply_markup=InlineKeyboardMarkup(button)
    )
    
    # Mark that no thumbnail was provided
    client.user_data[user_id]["thumb_path"] = None


@Client.on_callback_query(filters.regex("upload"))
async def doc(bot, update):    
    # Creating Directory for Metadata
    if not os.path.isdir("Metadata"):
        os.mkdir("Metadata")
        
    # Extracting necessary information    
    user_id = update.from_user.id
    if user_id not in bot.user_data:
        return await update.message.edit("Session expired. Please start over.")
    
    data = bot.user_data[user_id]
    new_name = data["new_name"]
    file_message_id = data["file_message_id"]
    thumb_path = data.get("thumb_path")
    
    prefix = await jishubotz.get_prefix(update.message.chat.id)
    suffix = await jishubotz.get_suffix(update.message.chat.id)
    new_filename_ = new_name.split(":-")[1]

    try:
        new_filename = add_prefix_suffix(new_filename_, prefix, suffix)
    except Exception as e:
        return await update.message.edit(f"Something Went Wrong Can't Able To Set Prefix Or Suffix 🥺 \n\n**Contact My Creator :** @CallAdminRobot\n\n**Error :** `{e}`")
    
    file_path = f"downloads/{update.from_user.id}/{new_filename}"
    file = await bot.get_messages(update.message.chat.id, file_message_id)

    ms = await update.message.edit("🚀 Try To Download...  ⚡")    
    try:
        path = await bot.download_media(message=file, file_name=file_path, progress=progress_for_pyrogram, progress_args=("🚀 Try To Downloading...  ⚡", ms, time.time()))                    
    except Exception as e:
        return await ms.edit(e)
    
    # Metadata Adding Code
    _bool_metadata = await jishubotz.get_metadata(update.message.chat.id) 
    
    if _bool_metadata:
        metadata = await jishubotz.get_metadata_code(update.message.chat.id)
        metadata_path = f"Metadata/{new_filename}"
        await add_metadata(path, metadata_path, metadata, ms)
    else:
        await ms.edit("⏳ Mode Changing...  ⚡")

    duration = 0
    try:
        parser = createParser(file_path)
        metadata = extractMetadata(parser)
        if metadata.has("duration"):
            duration = metadata.get('duration').seconds
        parser.close()   
    except:
        pass
        
    media = getattr(file, file.media.value)
    c_caption = await jishubotz.get_caption(update.message.chat.id)

    if c_caption:
        try:
            caption = c_caption.format(filename=new_filename, filesize=humanbytes(media.file_size), duration=convert(duration))
        except Exception as e:
            return await ms.edit(text=f"Your Caption Error Except Keyword Argument: ({e})")             
    else:
        caption = f"**{new_filename}**"
 
    # Process thumbnail
    ph_path = None
    if thumb_path:
        try:
            width, height, ph_path = await fix_thumb(thumb_path)
        except Exception as e:
            print(f"Error processing thumbnail: {e}")
            ph_path = None
    else:
        # If no thumbnail was provided, try to generate one for videos
        if file.media == MessageMediaType.VIDEO:
            try:
                ph_path_ = await take_screen_shot(file_path, os.path.dirname(os.path.abspath(file_path)), random.randint(0, duration - 1))
                width, height, ph_path = await fix_thumb(ph_path_)
            except Exception as e:
                ph_path = None
                print(f"Error generating thumbnail: {e}")

    await ms.edit("💠 Try To Upload...  ⚡")
    type = update.data.split("_")[1]
    try:
        if type == "document":
            await bot.send_document(
                update.message.chat.id,
                document=metadata_path if _bool_metadata else file_path,
                thumb=ph_path, 
                caption=caption, 
                progress=progress_for_pyrogram,
                progress_args=("💠 Try To Uploading...  ⚡", ms, time.time()))

        elif type == "video": 
            await bot.send_video(
                update.message.chat.id,
                video=metadata_path if _bool_metadata else file_path,
                caption=caption,
                thumb=ph_path,
                duration=duration,
                progress=progress_for_pyrogram,
                progress_args=("💠 Try To Uploading...  ⚡", ms, time.time()))

        elif type == "audio": 
            await bot.send_audio(
                update.message.chat.id,
                audio=metadata_path if _bool_metadata else file_path,
                caption=caption,
                thumb=ph_path,
                duration=duration,
                progress=progress_for_pyrogram,
                progress_args=("💠 Try To Uploading...  ⚡", ms, time.time()))

    except Exception as e:          
        os.remove(file_path)
        if ph_path:
            os.remove(ph_path)
        return await ms.edit(f"**Error :** `{e}`")    
    
    # Cleanup
    await ms.delete() 
    if ph_path:
        os.remove(ph_path)
    if file_path:
        os.remove(file_path)
    if user_id in bot.user_data:
        del bot.user_data[user_id]
