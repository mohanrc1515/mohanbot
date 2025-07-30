async def burn_subtitles(
    input_path: str,
    output_path: str,
    subtitle_path: str,
    ms: Message = None,
    font_size: int = 24,
    font_color: str = "white",
    bg_color: str = "black@0.5",
    position: str = "bottom"
):
    """
    Burn subtitles permanently into video
    
    Parameters:
    - input_path: Path to input video file
    - output_path: Path to output video with burned subtitles
    - subtitle_path: Path to subtitle file (.srt, .ass, etc.)
    - ms: Pyrogram Message object for status updates
    - font_size: Font size in pixels
    - font_color: Font color (name or hex)
    - bg_color: Background color with opacity (e.g., "black@0.5")
    - position: "top", "middle", or "bottom"
    
    Returns:
    - Path to output file if successful, None otherwise
    """
    try:
        if ms:
            await ms.edit("<i>Starting subtitle burn process...</i>")
        
        if not os.path.exists(subtitle_path):
            if ms:
                await ms.edit("<i>Subtitle file not found!</i>")
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
            '-c:v', 'libx264',  # Re-encode video
            '-crf', '18',       # Good quality
            '-preset', 'fast',
            output_path
        ]

        if ms:
            await ms.edit("<i>Burning subtitles into video...</i>")

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if os.path.exists(output_path):
            if ms:
                await ms.edit("<i>Subtitles burned successfully! ✅</i>")
            return output_path
        else:
            error_msg = stderr.decode().strip()
            print(f"Error burning subtitles: {error_msg}")
            if ms:
                await ms.edit("<i>Failed to burn subtitles! ❌</i>")
            return None

    except Exception as e:
        error_msg = f"Error in subtitle burning: {str(e)}"
        print(error_msg)
        if ms:
            await ms.edit(f"<i>Error: {str(e)}</i>")
        return None
