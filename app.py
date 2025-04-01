# app.py
import streamlit as st
import os
import tempfile
import logging
from moviepy import VideoFileClip, AudioFileClip 
import re
import yt_dlp

# Import functions from our modules
from audio_utils import calculate_rms_db
from visualization import create_segment_visualization
from video_utils import process_video

# Configure logging for the app (optional, Streamlit handles basic output)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Streamlit Page Configuration ---
st.set_page_config(page_title="Silent Video Editor", layout="wide")
st.title("✂️ Silent Video Segment Remover")
st.markdown("Upload a video file or paste a YouTube URL, adjust the silence detection parameters, and download the edited video with long silences removed.")

# --- Initialize Session State ---
if 'input_path' not in st.session_state:
    st.session_state.input_path = None
    
if 'video_title' not in st.session_state:
    st.session_state.video_title = None

# --- Temp Directory ---
TEMP_DIR = os.path.join(tempfile.gettempdir(), "silent_video_editor")
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)
logging.info(f"Using temporary directory: {TEMP_DIR}")

# YouTube download helper function using yt-dlp
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

# --- Sidebar for Parameters ---
st.sidebar.header("Input Options")

# Create tabs for upload vs URL
input_option = st.sidebar.radio(
    "Select input method:",
    ["Upload Video File", "Video URL (YouTube, etc.)"]
)

# File upload option
if input_option == "Upload Video File":
    uploaded_file = st.sidebar.file_uploader("Choose a video file...", type=["mp4", "mov", "avi", "mkv"])
    if uploaded_file is not None:
        # Save uploaded file temporarily to read with moviepy
        input_path = os.path.join(TEMP_DIR, uploaded_file.name)
        with open(input_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        # Store in session state
        st.session_state.input_path = input_path
        st.session_state.video_title = uploaded_file.name
        
# URL input option
else:
    video_url = st.sidebar.text_input("Paste video URL:", placeholder="https://www.youtube.com/watch?v=...")
    
    if video_url:
        download_placeholder = st.sidebar.empty()
        
        if st.sidebar.button("Download & Prepare Video"):
            download_placeholder.info("Analyzing video URL...")
            
            # Check if it's a YouTube URL
            youtube_pattern = r'(?:https?:\/\/)?(?:www\.)?(?:youtube\.com|youtu\.be)\/(?:watch\?v=)?([^\s&]+)'
            match = re.match(youtube_pattern, video_url)
            
            if match:
                # Handle YouTube URL with our helper function
                success, downloaded_path, title = download_youtube_video(video_url, download_placeholder)
                if success:
                    # Store in session state
                    st.session_state.input_path = downloaded_path
                    st.session_state.video_title = title
                
            else:
                # Handle other URLs if needed
                download_placeholder.error("Only YouTube URLs are supported at the moment.")
                st.session_state.input_path = None
                st.session_state.video_title = None

st.sidebar.markdown("---")

# --- Detection Parameters ---
st.sidebar.header("Detection Parameters")

# Use persistent parameters via session state
if 'silence_threshold' not in st.session_state:
    st.session_state.silence_threshold = -40.0

if 'min_silence_duration' not in st.session_state:
    st.session_state.min_silence_duration = 1.0

if 'merge_gap' not in st.session_state:
    st.session_state.merge_gap = 0.2

if 'start_padding' not in st.session_state:
    st.session_state.start_padding = 0.10

if 'end_padding' not in st.session_state:
    st.session_state.end_padding = 0.10

# Parameter input widgets with session state values
silence_threshold = st.sidebar.slider(
    "Silence Threshold (dBFS)",
    min_value=-70.0,
    max_value=0.0,
    value=st.session_state.silence_threshold, 
    step=1.0,
    help="Audio segments below this level (in decibels relative to full scale) are considered potentially silent. Lower values detect quieter sounds as non-silent.",
    key="silence_threshold_slider"
)
st.session_state.silence_threshold = silence_threshold

min_silence_duration = st.sidebar.slider(
    "Minimum Silence Duration (seconds)",
    min_value=0.1,
    max_value=10.0,
    value=st.session_state.min_silence_duration,
    step=0.1,
    help="Only silent segments longer than this duration will be removed.",
    key="min_silence_duration_slider"
)
st.session_state.min_silence_duration = min_silence_duration

merge_gap = st.sidebar.slider(
    "Merge Gap (seconds)",
    min_value=0.0,
    max_value=2.0,
    value=st.session_state.merge_gap,
    step=0.05,
    help="Keep short silences (e.g., pauses in speech) shorter than this duration by merging the surrounding non-silent segments.",
    key="merge_gap_slider"
)
st.session_state.merge_gap = merge_gap

st.sidebar.subheader("Refinement Padding")
start_padding = st.sidebar.slider(
    "Start Padding (seconds)",
    min_value=0.0,
    max_value=0.5, # Keep max relatively small
    value=st.session_state.start_padding,
    step=0.01,
    help="Keep this much extra time *before* detected sound starts. Helps prevent cutting off initial faint sounds.",
    key="start_padding_slider"
)
st.session_state.start_padding = start_padding

end_padding = st.sidebar.slider(
    "End Padding (seconds)",
    min_value=0.0,
    max_value=0.5, # Keep max relatively small
    value=st.session_state.end_padding,
    step=0.01,
    help="Keep this much extra time *after* detected sound ends. Helps prevent cutting off trailing faint sounds or echoes.",
    key="end_padding_slider"
)
st.session_state.end_padding = end_padding

# --- Main Area ---
if st.session_state.input_path and os.path.exists(st.session_state.input_path):
    st.subheader("Video Preview")
    st.success(f"Ready to process: {st.session_state.video_title}")

    # Display basic video info and preview (optional)
    video_clip_for_info = None # Define outside try block for potential cleanup
    try:
        video_clip_for_info = VideoFileClip(st.session_state.input_path)
        st.write(f"**Duration:** {video_clip_for_info.duration:.2f} seconds")
        st.video(st.session_state.input_path) # Display the whole video player
    except Exception as e:
        st.error(f"Could not read video file info: {e}")
        st.session_state.input_path = None # Mark as invalid
    finally:
        if video_clip_for_info:
            video_clip_for_info.close() # Close the clip used only for info

    if st.session_state.input_path and os.path.exists(st.session_state.input_path): # Check if path is still valid
        # --- Visualization Section ---
        st.subheader("Audio Analysis & Segment Visualization")
        vis_placeholder = st.empty()
        vis_placeholder.info("Generating audio visualization... (this might take a moment)")

        audio_clip_for_vis = None # Define outside try block for cleanup
        vis_clip = None
        try:
            # Re-open the clip specifically for processing/visualization if needed
            vis_clip = VideoFileClip(st.session_state.input_path)
            audio_clip_for_vis = vis_clip.audio
            if audio_clip_for_vis:
                target_fps = audio_clip_for_vis.fps if audio_clip_for_vis.fps and audio_clip_for_vis.fps > 0 else 44100
                # Use a reasonable duration limit for visualization if video is very long
                max_vis_duration_sec = 300 # Limit visualization to 5 minutes max to avoid OOM
                vis_duration_sec = min(audio_clip_for_vis.duration, max_vis_duration_sec)
                logging.info(f"Preparing audio for visualization (up to {vis_duration_sec:.2f}s)")

                # --- CORRECTED PART ---
                # Create an audio subclip for the desired visualization duration
                audio_subclip_for_vis = audio_clip_for_vis.subclipped(0, vis_duration_sec)

                # Convert *only the subclip's* audio data to a numpy array
                # Remove the invalid 'duration' argument here
                audio_array = audio_subclip_for_vis.to_soundarray(
                    fps=target_fps,
                    nbytes=2,      # Specify bytes per sample if needed (usually 2 for int16)
                    quantize=False # Usually False for float output, True for integer
                )
                # --- END CORRECTION ---

                logging.info(f"Generating visualization plot...")
                fig = create_segment_visualization(
                    audio_array,
                    target_fps,
                    silence_threshold_db=silence_threshold,
                    min_silence_len_sec=min_silence_duration
                )
                vis_placeholder.pyplot(fig)
                del audio_array # Free memory
                # Close the temporary audio subclip used for visualization
                audio_subclip_for_vis.close()

            else:
                vis_placeholder.warning("Video has no audio track. Cannot visualize or process silence.")
        except Exception as e:
            vis_placeholder.error(f"Error generating visualization: {e}")
            logging.error("Visualization failed", exc_info=True) # Log full traceback
        finally:
             # Ensure clips used for visualization are closed
             if audio_clip_for_vis:
                 audio_clip_for_vis.close()
             if vis_clip:
                 vis_clip.close()


        # --- Processing Section ---
        st.subheader("Process and Download")
        # Add a check to ensure input path still exists before enabling button
        process_button_disabled = not (st.session_state.input_path and os.path.exists(st.session_state.input_path))
        process_button = st.button("🚀 Remove Silent Segments", key="process", disabled=process_button_disabled)

        if process_button_disabled:
             st.warning("Cannot process - input video file is missing or invalid.")


        if process_button and not process_button_disabled:
            # Create a safer filename for the processed output
            if st.session_state.video_title:
                safe_title = "".join([c if c.isalnum() or c in [' ', '.', '_', '-'] else '_' for c in st.session_state.video_title])
                base_name = os.path.splitext(safe_title)[0]
            else:
                base_name = "processed_video"
                
            output_filename = f"{base_name}_edited.mp4"
            output_path = os.path.join(TEMP_DIR, output_filename)

            st_progress_bar = st.progress(0.0)
            st_status_text = st.empty()

            def progress_callback(progress_value, message):
                st_progress_bar.progress(min(1.0, progress_value)) # Ensure progress doesn't exceed 1.0
                st_status_text.info(message)

            try:
                success, result_message = process_video(
                    video_path=st.session_state.input_path,
                    output_path=output_path,
                    silence_threshold_db=silence_threshold,
                    min_silence_len_sec=min_silence_duration,
                    merge_gap_sec=merge_gap,
                    start_padding_sec=start_padding,
                    end_padding_sec=end_padding,
                    progress_callback=progress_callback
                )
                
                # Store the output path in session state
                if success:
                    if 'output_path' not in st.session_state:
                        st.session_state.output_path = output_path
                    else:
                        st.session_state.output_path = output_path
                
                    st_status_text.success(f"Processing complete! Video saved temporarily.")
                    st.balloons()

                    # Provide download button
                    with open(output_path, "rb") as file_bytes:
                        st.download_button(
                            label="⬇️ Download Edited Video",
                            data=file_bytes,
                            file_name=output_filename,
                            mime="video/mp4"
                        )
                    # Optionally display the processed video
                    try:
                        st.video(output_path)
                    except Exception as display_err:
                         st.warning(f"Could not display the processed video preview: {display_err}")


                else:
                    st_status_text.error(f"Processing failed: {result_message}")
                    st_progress_bar.progress(1.0) # Mark as finished even if error

            except Exception as e:
                 st_status_text.error(f"An unexpected error occurred during processing: {e}")
                 logging.error("Processing error in Streamlit app", exc_info=True)
                 st_progress_bar.progress(1.0)

    # Display output video if available (for when parameters change but video was already processed)
    elif 'output_path' in st.session_state and os.path.exists(st.session_state.output_path):
        st.subheader("Previously Processed Video")
        st.info("Your video is still available for download below.")
        
        # Get the filename from the output path
        output_filename = os.path.basename(st.session_state.output_path)
        
        # Provide download button
        with open(st.session_state.output_path, "rb") as file_bytes:
            st.download_button(
                label="⬇️ Download Edited Video",
                data=file_bytes,
                file_name=output_filename,
                mime="video/mp4"
            )
        # Display the processed video
        try:
            st.video(st.session_state.output_path)
        except Exception as display_err:
            st.warning(f"Could not display the processed video preview: {display_err}")

else:
    if input_option == "Upload Video File":
        st.info("Please upload a video file using the sidebar to begin.")
    else:
        st.info("""
        Please paste a YouTube URL and click 'Download & Prepare Video' to begin.
        
        **Note:** Some YouTube videos might be restricted due to copyright or age restrictions. 
        If download fails, try downloading the video manually and uploading it instead.
        """)

# Add footer or instructions
st.markdown("---")
st.markdown("Developed with Streamlit and MoviePy. Supports YouTube videos and local files.")
