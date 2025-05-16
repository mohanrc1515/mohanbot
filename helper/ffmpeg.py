import time
import os
import asyncio
import random
from PIL import Image, ImageDraw, ImageFont
import textwrap
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
    out_put_file_name = f"{output_directory}/{time.time()}.jpg"
    file_genertor_command = [
        "ffmpeg",
        "-ss",
        str(ttl),
        "-i",
        video_file,
        "-vframes",
        "1",
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

async def generate_text_thumbnail(text, output_directory="downloads/thumbnails"):
    """Generate a thumbnail image with text centered on a colored background"""
    try:
        os.makedirs(output_directory, exist_ok=True)
        thumb_path = f"{output_directory}/thumb_{time.time()}.jpg"
        
        # Image dimensions (YouTube thumbnail standard)
        width, height = 1280, 720
        
        # Generate random but pleasant background color
        r = random.randint(0, 150)
        g = random.randint(0, 150)
        b = random.randint(0, 150)
        
        # Create image with background
        image = Image.new("RGB", (width, height), (r, g, b))
        draw = ImageDraw.Draw(image)
        
        # Try to use a nice font (fallback to default if not available)
        try:
            font = ImageFont.truetype("arial.ttf", 80)
        except:
            try:
                font = ImageFont.truetype("arialbd.ttf", 80)
            except:
                font = ImageFont.load_default()
        
        # Calculate text size and position
        text_width, text_height = draw.textsize(text, font=font)
        while text_width > width - 40 and font.size > 20:
            font = ImageFont.truetype(font.path, font.size - 5)
            text_width, text_height = draw.textsize(text, font=font)
        
        # Wrap text if needed
        wrapped_text = textwrap.wrap(text, width=15)
        y_text = (height - (text_height * len(wrapped_text))) // 2
        
        # Draw each line of text
        for line in wrapped_text:
            text_width, text_height = draw.textsize(line, font=font)
            draw.text(
                ((width - text_width) // 2, y_text),
                line,
                font=font,
                fill=(255, 255, 255)  # White text
            )
            y_text += text_height
        
        # Save the thumbnail
        image.save(thumb_path, "JPEG", quality=95)
        return thumb_path
        
    except Exception as e:
        print(f"Error generating text thumbnail: {e}")
        return None
    
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
