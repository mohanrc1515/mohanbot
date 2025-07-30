from pyrogram import Client, filters
from pyrogram.enums import MessageMediaType
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import os, uuid, ffmpeg

# ... (keep your existing imports and setup)

@Client.on_message(filters.private & (filters.document | filters.audio | filters.video))
async def handle_file_upload(client, message):
    file = getattr(message, message.media.value)
    filename = file.file_name  
    
    if file.file_size > 2000 * 1024 * 1024:
        return await message.reply_text("Sorry, this bot doesn't support uploading files bigger than 2GB")

    session_id = str(uuid.uuid4())
    
    # First download the file to check for existing subtitles
    temp_path = f"temp_{session_id}_{filename}"
    await message.download(temp_path)
    
    # Detect existing subtitles
    existing_subs = await detect_subtitles(temp_path)
    os.remove(temp_path)  # Clean up temp file
    
    user_sessions[message.from_user.id] = {
        'session_id': session_id,
        'message_id': message.id,
        'filename': filename,
        'original_message': message,
        'subtitles': [],  # For new subtitles to add
        'existing_subs': existing_subs,  # For existing subtitles
        'subs_to_remove': []  # For subtitles to remove
    }

    await show_subtitle_options(message.from_user.id, session_id)

async def detect_subtitles(file_path):
    try:
        probe = ffmpeg.probe(file_path)
        streams = probe.get('streams', [])
        return [i for i, stream in enumerate(streams) if stream.get('codec_type') == 'subtitle']
    except:
        return []

async def show_subtitle_options(user_id, session_id):
    session_data = user_sessions[user_id]
    buttons = []
    
    # Add buttons for existing subtitles to remove
    if session_data['existing_subs']:
        buttons.append([InlineKeyboardButton("📜 Existing Subtitles", callback_data="ignore")])
        for sub_idx in session_data['existing_subs']:
            buttons.append([
                InlineKeyboardButton(f"❌ Remove Subtitle Track {sub_idx}", 
                                   callback_data=f"remove_existing_{session_id}_{sub_idx}")
            ])
    
    # Add buttons for new subtitle operations
    buttons.extend([
        [InlineKeyboardButton("➕ Add New Subtitle", callback_data=f"add_subtitle_{session_id}")],
        [InlineKeyboardButton("⏩ Continue Without Changes", callback_data=f"continue_{session_id}")],
        [InlineKeyboardButton("🔄 Refresh Subtitle List", callback_data=f"refresh_{session_id}")]
    ])
    
    text = "🔠 <b>Subtitle Management</b>\n\n"
    if session_data['existing_subs']:
        text += f"Found {len(session_data['existing_subs'])} existing subtitle tracks.\n"
    text += "You can remove existing subtitles or add new ones."
    
    await user_sessions[user_id]['original_message'].reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@Client.on_callback_query(filters.regex("^remove_existing_"))
async def remove_existing_subtitle(bot, update):
    user_id = update.from_user.id
    parts = update.data.split('_')
    session_id = parts[3]
    sub_idx = int(parts[4])
    
    if user_id not in user_sessions or user_sessions[user_id]['session_id'] != session_id:
        return await update.answer("Session expired")
    
    session_data = user_sessions[user_id]
    if sub_idx in session_data['existing_subs']:
        if sub_idx not in session_data['subs_to_remove']:
            session_data['subs_to_remove'].append(sub_idx)
            await update.answer(f"Will remove subtitle track {sub_idx}")
        else:
            session_data['subs_to_remove'].remove(sub_idx)
            await update.answer(f"Won't remove subtitle track {sub_idx}")
    
    await update.message.edit_reply_markup(
        await generate_subtitle_markup(user_id, session_id)
    )

@Client.on_callback_query(filters.regex("^add_subtitle_"))
async def add_subtitle_callback(bot, update):
    user_id = update.from_user.id
    session_id = update.data.split("_")[2]
    
    if user_id not in user_sessions or user_sessions[user_id]['session_id'] != session_id:
        return await update.answer("Session expired")
    
    await update.answer("Please send me the subtitle file (supported: .srt, .ass, .vtt)")
    await update.message.edit_text("Waiting for subtitle file...")

@Client.on_callback_query(filters.regex("^continue_"))
async def continue_processing(bot, update):
    user_id = update.from_user.id
    session_id = update.data.split("_")[1]
    
    if user_id not in user_sessions or user_sessions[user_id]['session_id'] != session_id:
        return await update.answer("Session expired")
    
    await update.message.delete()
    await process_and_upload(bot, user_id, user_sessions[user_id]['original_message'])

@Client.on_callback_query(filters.regex("^refresh_"))
async def refresh_subtitle_list(bot, update):
    user_id = update.from_user.id
    session_id = update.data.split("_")[1]
    
    if user_id not in user_sessions or user_sessions[user_id]['session_id'] != session_id:
        return await update.answer("Session expired")
    
    await show_subtitle_options(user_id, session_id)
    await update.answer("Subtitle list refreshed")

async def generate_subtitle_markup(user_id, session_id):
    session_data = user_sessions[user_id]
    buttons = []
    
    # Existing subtitles with removal toggle
    if session_data['existing_subs']:
        buttons.append([InlineKeyboardButton("📜 Existing Subtitles", callback_data="ignore")])
        for sub_idx in session_data['existing_subs']:
            if sub_idx in session_data['subs_to_remove']:
                buttons.append([
                    InlineKeyboardButton(f"✅ Will Remove Track {sub_idx}", 
                                      callback_data=f"remove_existing_{session_id}_{sub_idx}")
                ])
            else:
                buttons.append([
                    InlineKeyboardButton(f"❌ Remove Track {sub_idx}", 
                                      callback_data=f"remove_existing_{session_id}_{sub_idx}")
                ])
    
    # Standard operations
    buttons.extend([
        [InlineKeyboardButton("➕ Add New Subtitle", callback_data=f"add_subtitle_{session_id}")],
        [InlineKeyboardButton("⏩ Continue", callback_data=f"continue_{session_id}")],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"refresh_{session_id}")]
    ])
    
    return InlineKeyboardMarkup(buttons)

async def process_and_upload(bot, user_id, original_message):
    if user_id not in user_sessions:
        return
    
    session_data = user_sessions[user_id]
    filename = session_data['filename']
    
    # ... (keep your existing file download code)
    
    # Process subtitle removal if any
    output_path = file_path
    if session_data['subs_to_remove']:
        output_path = f"{file_path}_no_subs.mp4"
        await remove_subtitles(file_path, output_path, session_data['subs_to_remove'])
        file_path = output_path
    
    # Process new subtitles if any
    for sub in session_data['subtitles']:
        new_output_path = f"{file_path}_with_sub.mp4"
        await add_subtitle(file_path, sub, new_output_path)
        file_path = new_output_path
    
    # ... (continue with your existing upload code)

async def remove_subtitles(input_path, output_path, sub_indices):
    """Remove specified subtitle tracks from video"""
    input_stream = ffmpeg.input(input_path)
    
    # Build complex filter to exclude specified subtitle streams
    streams = ffmpeg.probe(input_path)['streams']
    stream_mapping = []
    stream_index = 0
    
    for i, stream in enumerate(streams):
        if stream['codec_type'] == 'subtitle' and i in sub_indices:
            continue  # Skip these subtitles
        stream_mapping.extend(['-map', f'0:{i}'])
    
    (
        ffmpeg
        .input(input_path)
        .output(output_path, **{'c': 'copy'}, *stream_mapping)
        .overwrite_output()
        .run()
)
