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
            # First get dimensions
            parser = createParser(thumb)
            metadata = extractMetadata(parser)
            if metadata.has("width"):
                width = metadata.get("width")
            if metadata.has("height"):
                height = metadata.get("height")
            parser.close()

            # Then process image
            with Image.open(thumb) as img:
                # Convert to RGB if needed
                if img.mode != 'RGB':
                    img = img.convert("RGB")
                
                # Resize maintaining aspect ratio if needed
                if width > 320 or height > 320:  # Telegram's recommended thumbnail size
                    img.thumbnail((320, 320))
                
                # Save as JPEG
                img.save(thumb, "JPEG", quality=95)
                
                # Get final dimensions
                width, height = img.size
                
    except Exception as e:
        print(f"Error fixing thumbnail: {e}")
        thumb = None 
       
    return width, height, thumb


async def take_screen_shot(video_file, output_directory, ttl):
    out_put_file_name = f"{output_directory}/{time.time()}.jpg"
    try:
        file_genertor_command = [
            "ffmpeg",
            "-ss",
            str(ttl),
            "-i",
            video_file,
            "-vframes",
            "1",
            "-q:v",
            "2",  # Quality level (2-31, lower is better)
            out_put_file_name
        ]
        process = await asyncio.create_subprocess_exec(
            *file_genertor_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        
        if os.path.lexists(out_put_file_name):
            return out_put_file_name
        return None
    except Exception as e:
        print(f"Error taking screenshot: {e}")
        return None
    
    
async def add_metadata(input_path, output_path, metadata, ms):
    try:
        await ms.edit("<i>I Found Metadata, Adding Into Your File ⚡</i>")
        command = [
            'ffmpeg', '-y', '-i', input_path,
            '-map', '0',
            '-c', 'copy',  # Copy all streams without re-encoding
            '-metadata', f'title={metadata}',
            '-metadata', f'author={metadata}',
            '-metadata', f'artist={metadata}',
            '-metadata', f'comment={metadata}',
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        
        if os.path.exists(output_path):
            await ms.edit("<i>Metadata Added Successfully ✅</i>")
            return output_path
        else:
            await ms.edit("<i>Failed To Add Metadata ❌</i>")
            return None
    except Exception as e:
        print(f"Error adding metadata: {e}")
        await ms.edit("<i>Metadata Addition Failed ❌</i>")
        return None


async def add_default_subtitle(input_path, output_path, text="MOHAN", duration=3):
    try:
        command = [
            'ffmpeg', '-y', '-i', input_path,
            '-vf', f"drawtext=text='{text}':fontsize=24:fontcolor=white:"
                   f"box=1:boxcolor=black@0.5:boxborderw=5:"
                   f"x=(w-text_w)/2:y=h-text_h-10:"
                   f"enable='between(t,0,{duration})'",
            '-c:a', 'copy',  # Copy audio without re-encoding
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await process.communicate()
        
        if os.path.exists(output_path):
            return output_path
        return None
    except Exception as e:
        print(f"Error adding default subtitle: {e}")
        return None
