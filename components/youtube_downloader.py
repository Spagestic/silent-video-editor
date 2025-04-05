import re
import os
import yt_dlp
import logging
import tempfile

TEMP_DIR = os.path.join(tempfile.gettempdir(), "silent_video_editor")

def download_youtube_video(url, download_placeholder):
    """
    Downloads a YouTube video using yt-dlp.
    Returns (success, file_path, video_title)
    """
    # Extract video ID for potential reference
    youtube_id_match = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/)([^&\n?]+)', url)
    if not youtube_id_match:
        download_placeholder.error("Invalid YouTube URL format")
        return False, None, None
    
    video_id = youtube_id_match.group(1)
    
    try:
        download_placeholder.info("Downloading video using yt-dlp... Please wait.")
        
        # Configure yt-dlp options - fixed for the current yt-dlp version
        ydl_opts = {
            'format': 'best[ext=mp4]/best',  # Prefer MP4 format
            'outtmpl': {
                'default': os.path.join(TEMP_DIR, f'%(title)s.%(ext)s'),
            },
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
        }
        
        # Create a yt-dlp object and extract info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            video_title = info.get('title', f'YouTube Video {video_id}')
            
            # Create a safe filename
            safe_title = "".join([c if c.isalnum() or c in [' ', '.', '_', '-'] else '_' for c in video_title])
            
            # Update output template with safe filename - correctly formatted for newer yt-dlp
            ydl_opts['outtmpl'] = {
                'default': os.path.join(TEMP_DIR, f'{safe_title}.%(ext)s'),
            }
            
            download_placeholder.info(f"Downloading: {video_title}")
            
            # Actually download the video
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Determine the actual output file (could be .mp4, .mkv, etc.)
            for ext in ['mp4', 'mkv', 'webm']:
                possible_file = os.path.join(TEMP_DIR, f'{safe_title}.{ext}')
                if os.path.exists(possible_file):
                    output_path = possible_file
                    break
            else:
                # If we didn't find an expected file, search the directory for any recent file
                files = [os.path.join(TEMP_DIR, f) for f in os.listdir(TEMP_DIR) 
                         if os.path.isfile(os.path.join(TEMP_DIR, f))]
                if files:
                    files.sort(key=os.path.getmtime, reverse=True)
                    output_path = files[0]  # Most recently modified file
                else:
                    raise Exception("Failed to locate downloaded file")
            
            download_placeholder.success(f"Downloaded successfully: {video_title}")
            return True, output_path, video_title
    
    except Exception as e:
        download_placeholder.error(f"""
        Error downloading the YouTube video: {str(e)}
        
        Please try:
        1. Using a different YouTube URL
        2. Downloading the video manually and uploading it instead
        3. Checking if the video has country or age restrictions
        """)
        logging.error(f"YouTube download error: {str(e)}", exc_info=True)
        return False, None, None