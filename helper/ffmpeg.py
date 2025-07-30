import time
import os
import asyncio
from PIL import Image
from hachoir.metadata import extractMetadata
from hachoir.parser import createParser
from pyrogram.types import Message

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
                
            # Open the image file
            with Image.open(thumb) as img:
                # Convert the image to RGB format and save it back to the same file
                img.convert("RGB").save(thumb)
                
                # Resize the image if needed
                if width > 320 or height > 320:  # Telegram's recommended thumbnail size
                    ratio = min(320/width, 320/height)
                    width = int(width * ratio)
                    height = int(height * ratio)
                    img = img.resize((width, height))
                
                # Save the resized image in JPEG format
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
        "2",  # Quality setting (2 = high quality)
        out_put_file_name
    ]
    process = await asyncio.create_subprocess_exec(
        *file_genertor_command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    e_response = stderr.decode().strip()
    t_response = stdout.decode().strip()
    if os.path.lexists(out_put_file_name):
        return out_put_file_name
    return None
    
async def add_metadata(input_path, output_path, metadata, ms):
    try:
        await ms.edit("<i>I Found Metadata, Adding Into Your File ⚡</i>")
        command = [
            'ffmpeg', '-y', '-i', input_path, '-map', '0', '-c', 'copy',
            '-metadata', f'title={metadata}',  # Set Title Metadata
            '-metadata', f'author={metadata}',  # Set Author Metadata
            '-metadata', f'artist={metadata}',  # Set Artist Metadata
            '-metadata', f'comment={metadata}',  # Set Comment Metadata
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        
        if os.path.exists(output_path):
            await ms.edit("<i>Metadata Added Successfully ✅</i>")
            return output_path
        else:
            await ms.edit("<i>Failed To Add Metadata ❌</i>")
            return None
    except Exception as e:
        print(f"Error adding metadata: {str(e)}")
        await ms.edit("<i>Error Adding Metadata ❌</i>")
        return None

async def add_subtitle(video_path, subtitle_path, output_path):
    """Add subtitle to video file"""
    try:
        command = [
            'ffmpeg', '-y', '-i', video_path, '-i', subtitle_path,
            '-map', '0', '-map', '1',
            '-c:v', 'copy', '-c:a', 'copy',
            '-c:s', 'mov_text',  # For MP4 files
            '-metadata:s:s:0', 'language=eng',  # Set subtitle language
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        
        if os.path.exists(output_path):
            return output_path
        return None
    except Exception as e:
        print(f"Error adding subtitle: {str(e)}")
        return None

async def remove_subtitles(input_path, output_path, sub_indices):
    """Remove specified subtitle tracks from video"""
    try:
        # Build stream mapping excluding specified subtitle indices
        stream_mapping = []
        probe = await probe_file(input_path)
        
        for i, stream in enumerate(probe.get('streams', [])):
            if stream.get('codec_type') == 'subtitle' and i in sub_indices:
                continue  # Skip these subtitles
            stream_mapping.extend(['-map', f'0:{i}'])
        
        command = [
            'ffmpeg', '-y', '-i', input_path,
            *stream_mapping,
            '-c', 'copy',  # Copy all streams without re-encoding
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        
        if os.path.exists(output_path):
            return output_path
        return None
    except Exception as e:
        print(f"Error removing subtitles: {str(e)}")
        return None

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

async def extract_subtitles(input_path, output_dir):
    """Extract all subtitles from video file"""
    try:
        probe = await probe_file(input_path)
        subs = []
        
        for i, stream in enumerate(probe.get('streams', [])):
            if stream.get('codec_type') == 'subtitle':
                ext = {
                    'subrip': '.srt',
                    'ass': '.ass',
                    'webvtt': '.vtt'
                }.get(stream.get('codec_name'), '.srt')
                
                output_path = f"{output_dir}/sub_{i}{ext}"
                command = [
                    'ffmpeg', '-y', '-i', input_path,
                    '-map', f'0:{i}', '-c:s', 'copy',
                    output_path
                ]
                
                process = await asyncio.create_subprocess_exec(
                    *command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await process.communicate()
                
                if os.path.exists(output_path):
                    subs.append({
                        'index': i,
                        'language': stream.get('tags', {}).get('language', 'und'),
                        'path': output_path
                    })
        
        return subs
    except Exception as e:
        print(f"Error extracting subtitles: {str(e)}")
        return []
