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
        if thumb != None:
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
            
                # Resize the image
                resized_img = img.resize((width, height))
                
                # Save the resized image in JPEG format
                resized_img.save(thumb, "JPEG")
            parser.close()
    except Exception as e:
        print(e)
        thumb = None 
       
    return width, height, thumb
    
async def take_screen_shot(video_file, output_directory, ttl):
    """Capture a frame from video at specific time (in seconds)"""
    out_put_file_name = f"{output_directory}/{time.time()}.jpg"
    
    # Ensure the timestamp doesn't exceed video duration
    try:
        parser = createParser(video_file)
        metadata = extractMetadata(parser)
        if metadata.has("duration"):
            duration = metadata.get('duration').seconds
            ttl = min(ttl, duration-1)  # Don't exceed video length
        parser.close()
    except:
        pass
    
    file_genertor_command = [
        "ffmpeg",
        "-ss",
        str(ttl),  # Seek to specified time
        "-i",
        video_file,
        "-vframes", "1",  # Capture just 1 frame
        "-q:v", "2",  # Quality level (2 is very high quality)
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

async def get_video_duration(video_file):
    """Helper function to get video duration"""
    try:
        parser = createParser(video_file)
        metadata = extractMetadata(parser)
        if metadata.has("duration"):
            return metadata.get('duration').seconds
        return 0
    except Exception as e:
        print(f"Error getting video duration: {e}")
        return 0
    finally:
        if 'parser' in locals():
            parser.close()

async def add_metadata(input_path, output_path, metadata, ms):
    try:
        await ms.edit("<i>I Found Metadata, Adding Into Your File ⚡</i>")
        command = [
            'ffmpeg', '-y', '-i', input_path, '-map', '0', '-c:s', 'copy', '-c:a', 'copy', '-c:v', 'copy',
            '-metadata', f'title={metadata}',  # Set Title Metadata
            '-metadata', f'author={metadata}',  # Set Author Metadata
            '-metadata:s:s', f'title={metadata}',  # Set Subtitle Metadata
            '-metadata:s:a', f'title={metadata}',  # Set Audio Metadata
            '-metadata:s:v', f'title={metadata}',  # Set Video Metadata
            '-metadata', f'artist={metadata}',  # Set Artist Metadata
            output_path
        ]
        
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        e_response = stderr.decode().strip()
        t_response = stdout.decode().strip()
        print(e_response)
        print(t_response)

        if os.path.exists(output_path):
            await ms.edit("<i>Metadata Has Been Successfully Added To Your File ✅</i>")
            return output_path
        else:
            await ms.edit("<i>Failed To Add Metadata To Your File ❌</i>")
            return None
    except Exception as e:
        print(f"Error occurred while adding metadata: {str(e)}")
        await ms.edit("<i>An Error Occurred While Adding Metadata To Your File ❌</i>")
        return None
