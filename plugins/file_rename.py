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

    # Ask for thumbnail for every file type
    await message.reply_text(
        text="**Please send a thumbnail photo for this file**",
        reply_to_message_id=message.id,
        reply_markup=ForceReply(True)
    )


async def process_upload(client, message, filename, thumb=None):
    # Creating Directory for Metadata
    if not os.path.isdir("Metadata"):
        os.mkdir("Metadata")
        
    # Extracting necessary information    
    prefix = await jishubotz.get_prefix(message.chat.id)
    suffix = await jishubotz.get_suffix(message.chat.id)

    try:
        new_filename = add_prefix_suffix(filename, prefix, suffix)
    except Exception as e:
        return await message.reply_text(f"Something Went Wrong Can't Able To Set Prefix Or Suffix 🥺 \n\n**Contact My Creator :** @CallAdminRobot\n\n**Error :** `{e}`")
    
    file_path = f"downloads/{message.chat.id}/{new_filename}"
    file = message

    ms = await message.reply_text("🚀 Try To Download...  ⚡")    
    try:
        path = await client.download_media(message=file, file_name=file_path, progress=progress_for_pyrogram, progress_args=("🚀 Try To Downloading...  ⚡", ms, time.time()))                    
    except Exception as e:
        return await ms.edit(e)
    

    # Metadata Adding Code
    _bool_metadata = await jishubotz.get_metadata(message.chat.id) 
    
    if _bool_metadata:
        metadata = await jishubotz.get_metadata_code(message.chat.id)
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
        
    ph_path = thumb
    user_id = int(message.chat.id) 
    media = getattr(file, file.media.value)
    c_caption = await jishubotz.get_caption(message.chat.id)
    c_thumb = await jishubotz.get_thumbnail(message.chat.id)

    if c_caption:
         try:
             caption = c_caption.format(filename=new_filename, filesize=humanbytes(media.file_size), duration=convert(duration))
         except Exception as e:
             return await ms.edit(text=f"Your Caption Error Except Keyword Argument: ({e})")             
    else:
         caption = f"**{new_filename}**"
 
    if (media.thumbs or c_thumb or thumb):
         if c_thumb:
             ph_path = await client.download_media(c_thumb)
             width, height, ph_path = await fix_thumb(ph_path)
         elif thumb:
             ph_path = await client.download_media(thumb)
             width, height, ph_path = await fix_thumb(ph_path)
         else:
             try:
                 ph_path_ = await take_screen_shot(file_path, os.path.dirname(os.path.abspath(file_path)), random.randint(0, duration - 1))
                 width, height, ph_path = await fix_thumb(ph_path_)
             except Exception as e:
                 ph_path = None
                 print(e)  


    await ms.edit("💠 Try To Upload...  ⚡")
    try:
        # Upload all files as videos
        await client.send_video(
            message.chat.id,
            video=metadata_path if _bool_metadata else file_path,
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
 
    await ms.delete() 
    if ph_path:
        os.remove(ph_path)
    if file_path:
        os.remove(file_path)


@Client.on_message(filters.private & filters.reply)
async def refunc(client, message):
    reply_message = message.reply_to_message
    if (reply_message.reply_markup) and isinstance(reply_message.reply_markup, ForceReply):
        # This is a reply to thumbnail request
        if reply_message.text and "thumbnail" in reply_message.text.lower():
            if not message.photo:
                return await message.reply_text("Please send a valid photo for thumbnail")
            
            original_message = await client.get_messages(
                message.chat.id,
                reply_message.reply_to_message.id
            )
            file = getattr(original_message, original_message.media.value)
            await process_upload(client, original_message, file.file_name, thumb=message)
            await message.delete()
            await reply_message.delete()
