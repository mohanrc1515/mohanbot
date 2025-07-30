import os
import time
import json
import uuid
import asyncio
from PIL import Image
from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser

# Bot setup
app = Client("my_bot")

# Dictionary to store user sessions
user_sessions = {}

async def probe_file(file_path):
    """Get media file information using ffprobe"""
    command = [
        'ffprobe', '-v', 'quiet',
        '-print_format', 'json',
        '-show_format', '-show_streams',
        file_path
    ]
    
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    try:
        return json.loads(stdout.decode())
    except:
        return {'streams': []}

async def fix_thumb(thumb):
    width = 0
    height = 0
    try:
        if thumb is not None:
            parser = createParser(thumb)
            metadata = extractMetadata(parser)
            if metadata.has("width"):
                width = metadata.get("width")
            if metadata.has("height"):
                height = metadata.get("height")
                
            with Image.open(thumb) as img:
                img.convert("RGB").save(thumb)
                if width > 320 or height > 320:
                    ratio = min(320/width, 320/height)
                    width = int(width * ratio)
                    height = int(height * ratio)
                    img = img.resize((width, height))
                img.save(thumb, "JPEG")
            parser.close()
    except Exception as e:
        print(e)
        thumb = None 
    return width, height, thumb
    
async def take_screen_shot(video_file, output_directory, ttl):
    out_put_file_name = f"{output_directory}/{time.time()}.jpg"
    file_genertor_command = [
        "ffmpeg",
        "-ss",
        str(ttl),
        "-i",
        video_file,
        "-vframes",
        "1",
        "-q:v",
        "2",
        out_put_file_name
    ]
    process = await asyncio.create_subprocess_exec(
        *file_genertor_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if os.path.lexists(out_put_file_name):
        return out_put_file_name
    return None

async def remove_subtitles(input_path, output_path, sub_indices):
    """Remove specified subtitle tracks from video"""
    try:
        probe = await probe_file(input_path)
        if not probe:
            return None
            
        stream_mapping = []
        for i, stream in enumerate(probe.get('streams', [])):
            if stream.get('codec_type') == 'subtitle' and i in sub_indices:
                continue
            stream_mapping.extend(['-map', f'0:{i}'])
        
        command = [
            'ffmpeg', '-y', '-i', input_path,
            *stream_mapping,
            '-c', 'copy',
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        return output_path if os.path.exists(output_path) else None
    except Exception as e:
        print(f"Error removing subtitles: {str(e)}")
        return None

async def add_subtitle(video_path, subtitle_path, output_path):
    """Add subtitle to video file"""
    try:
        command = [
            'ffmpeg', '-y', '-i', video_path, '-i', subtitle_path,
            '-map', '0', '-map', '1',
            '-c:v', 'copy', '-c:a', 'copy',
            '-c:s', 'mov_text',
            '-metadata:s:s:0', 'language=eng',
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        return output_path if os.path.exists(output_path) else None
    except Exception as e:
        print(f"Error adding subtitle: {str(e)}")
        return None

async def burn_subtitles(
    input_path: str,
    output_path: str,
    subtitle_path: str,
    font_size: int = 24,
    font_color: str = "white",
    bg_color: str = "black@0.5",
    position: str = "bottom"
):
    """
    Burn subtitles permanently into video
    Returns output path if successful, None otherwise
    """
    try:
        if not os.path.exists(subtitle_path):
            return None

        # Position mapping
        position_map = {
            "top": "(h-text_h)/10",
            "middle": "(h-text_h)/2",
            "bottom": "h-text_h-10"
        }
        pos_y = position_map.get(position.lower(), "h-text_h-10")

        # FFmpeg filter for subtitles with styling
        subtitle_filter = (
            f"subtitles='{subtitle_path.replace(':', '\\:')}':"
            f"force_style='Fontsize={font_size},"
            f"PrimaryColour={font_color},"
            f"BackColour={bg_color},"
            f"Alignment=2,MarginV=20,"
            f"Outline=1,Shadow=0'"
        )

        command = [
            'ffmpeg', '-y', '-i', input_path,
            '-vf', subtitle_filter,
            '-c:a', 'copy',
            '-c:v', 'libx264',
            '-crf', '18',
            '-preset', 'fast',
            output_path
        ]

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()

        return output_path if os.path.exists(output_path) else None

    except Exception as e:
        print(f"Error burning subtitles: {str(e)}")
        return None

@app.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_file_upload(client, message: Message):
    file = getattr(message, message.media.value)
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("File too large (max 2GB)")

    session_id = str(uuid.uuid4())
    temp_path = f"temp_{session_id}_{file.file_name}"
    await message.download(temp_path)
    
    existing_subs = []
    probe = await probe_file(temp_path)
    for i, stream in enumerate(probe.get('streams', [])):
        if stream.get('codec_type') == 'subtitle':
            existing_subs.append(i)
    os.remove(temp_path)
    
    user_sessions[message.from_user.id] = {
        'session_id': session_id,
        'message_id': message.id,
        'filename': file.file_name,
        'original_message': message,
        'subtitles': [],  # For soft subtitles
        'burn_subtitles': [],  # For hardcoded subtitles
        'existing_subs': existing_subs,
        'subs_to_remove': [],
        'burn_settings': {
            'font_size': 24,
            'font_color': "white",
            'bg_color': "black@0.5",
            'position': "bottom"
        }
    }

    await show_subtitle_options(message.from_user.id, session_id)

async def show_subtitle_options(user_id, session_id):
    session_data = user_sessions[user_id]
    buttons = []
    
    if session_data['existing_subs']:
        buttons.append([InlineKeyboardButton("📜 Existing Subtitles", callback_data="ignore")])
        for sub_idx in session_data['existing_subs']:
            buttons.append([
                InlineKeyboardButton(
                    f"✅ Remove Track {sub_idx}" if sub_idx in session_data['subs_to_remove'] else f"❌ Remove Track {sub_idx}",
                    callback_data=f"toggle_sub_{session_id}_{sub_idx}"
                )
            ])
    
    buttons.extend([
        [InlineKeyboardButton("➕ Add Soft Subtitle", callback_data=f"add_sub_{session_id}")],
        [InlineKeyboardButton("🔥 Add Burned Subtitle", callback_data=f"burn_sub_{session_id}")],
        [InlineKeyboardButton("⚙️ Burn Settings", callback_data=f"burn_settings_{session_id}")],
        [InlineKeyboardButton("⏩ Continue", callback_data=f"cont_{session_id}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{session_id}")]
    ])
    
    text = "🔠 <b>Subtitle Management</b>\n\n"
    if session_data['existing_subs']:
        text += f"Found {len(session_data['existing_subs'])} subtitle tracks\n"
    if session_data['subtitles']:
        text += f"{len(session_data['subtitles'])} soft subtitles to add\n"
    if session_data['burn_subtitles']:
        text += f"{len(session_data['burn_subtitles'])} subtitles to burn\n"
    text += "Select options below:"
    
    await session_data['original_message'].reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex("^burn_sub_"))
async def handle_burn_subtitle(bot, update):
    user_id = update.from_user.id
    session_id = update.data.split('_')[-1]
    
    if user_id not in user_sessions or user_sessions[user_id]['session_id'] != session_id:
        return await update.answer("Session expired")
    
    session_data = user_sessions[user_id]
    await update.message.edit_text(
        "📌 <b>Send me the subtitle file to burn (.srt, .ass, etc.)</b>\n\n"
        "Note: Burned subtitles will be permanently embedded in the video.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("↩️ Back", callback_data=f"back_{session_id}")]
        ])
    )
    
    session_data['awaiting_subtitle'] = 'burn'

@app.on_message(filters.private & filters.document & filters.regex(r'\.(srt|ass|ssa)$'))
async def handle_subtitle_upload(client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_sessions or 'awaiting_subtitle' not in user_sessions[user_id]:
        return
    
    session_data = user_sessions[user_id]
    sub_path = f"subs_{session_data['session_id']}_{message.document.file_name}"
    await message.download(sub_path)
    
    if session_data['awaiting_subtitle'] == 'burn':
        session_data['burn_subtitles'].append({
            'path': sub_path,
            'settings': session_data['burn_settings']
        })
        await message.reply_text(
            f"✅ Subtitle will be burned into video with current settings:\n"
            f"Font: {session_data['burn_settings']['font_size']}px\n"
            f"Color: {session_data['burn_settings']['font_color']}\n"
            f"Position: {session_data['burn_settings']['position']}"
        )
    else:
        session_data['subtitles'].append(sub_path)
        await message.reply_text("✅ Subtitle will be added as soft subtitle")
    
    del session_data['awaiting_subtitle']
    await show_subtitle_options(user_id, session_data['session_id'])

async def process_and_upload(bot, user_id, original_message):
    if user_id not in user_sessions:
        return
    
    session_data = user_sessions[user_id]
    file_path = f"downloads/{user_id}_{session_data['session_id'][:8]}/{session_data['filename']}"
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    ms = await original_message.reply("Downloading...")
    try:
        await original_message.download(file_path)
    except Exception as e:
        await ms.edit(f"Download failed: {e}")
        return
    
    # Process subtitle removal
    if session_data['subs_to_remove']:
        new_path = f"{file_path}_no_subs.mp4"
        if await remove_subtitles(file_path, new_path, session_data['subs_to_remove']):
            os.remove(file_path)
            file_path = new_path
    
    # Process soft subtitles
    for sub in session_data['subtitles']:
        new_path = f"{file_path}_with_sub.mp4"
        if await add_subtitle(file_path, sub, new_path):
            os.remove(file_path)
            file_path = new_path
    
    # Process burned subtitles
    for sub in session_data['burn_subtitles']:
        new_path = f"{file_path}_burned.mp4"
        if await burn_subtitles(
            file_path,
            new_path,
            sub['path'],
            font_size=sub['settings']['font_size'],
            font_color=sub['settings']['font_color'],
            bg_color=sub['settings']['bg_color'],
            position=sub['settings']['position']
        ):
            os.remove(file_path)
            file_path = new_path
    
    # Upload the final file
    await ms.edit("Uploading...")
    try:
        await bot.send_video(
            chat_id=user_id,
            video=file_path,
            progress=progress_for_pyrogram,
            progress_args=("Uploading...", ms, time.time())
        )
    except Exception as e:
        await ms.edit(f"Upload failed: {e}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)
        await ms.delete()

app.run()
