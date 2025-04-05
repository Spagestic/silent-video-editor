import streamlit as st
import os
import subprocess
import tempfile

TEMP_DIR = os.path.join(tempfile.gettempdir(), "silent_video_editor")

def record_video():
    """
    Handles video recording using the webcam.
    """
    st.sidebar.info("This feature uses your webcam to record a video.")
    recorded_file = st.sidebar.camera_input("Record a video", key="camera")
    if recorded_file:
        # Save recorded file temporarily
        temp_input_path = os.path.join(TEMP_DIR, "webcam_raw.webm")
        with open(temp_input_path, "wb") as f:
            f.write(recorded_file.getbuffer())
        
        # Convert to proper MP4 using ffmpeg directly
        try:
            input_path = os.path.join(TEMP_DIR, "recorded_video.mp4")
            conversion_status = st.sidebar.empty()
            conversion_status.info("Converting video format...")
            
            # Use ffmpeg directly instead of MoviePy
            ffmpeg_cmd = [
                "ffmpeg", 
                "-y",  # Overwrite output file if it exists
                "-i", temp_input_path,  # Input file
                "-c:v", "libx264",  # Video codec
                "-pix_fmt", "yuv420p",  # Pixel format for compatibility
                "-preset", "fast",  # Encoding speed preset
                "-crf", "23",  # Quality (lower is better)
                input_path  # Output file
            ]
            
            # Run the ffmpeg command
            process = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Check if the conversion was successful
            if process.returncode == 0 and os.path.exists(input_path):
                # Store in session state
                st.session_state.input_path = input_path
                st.session_state.video_title = "recorded_video.mp4"
                conversion_status.success("Video recorded and converted successfully!")
            else:
                raise Exception(f"FFMPEG conversion failed: {process.stderr}")
                
        except Exception as e:
            st.sidebar.error(f"Error converting video: {str(e)}")
            st.sidebar.info("Please try recording again or use file upload instead.")
            if 'input_path' in st.session_state:
                st.session_state.input_path = None