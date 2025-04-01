# app.py
import streamlit as st
import os
import tempfile
import logging
from moviepy import VideoFileClip, AudioFileClip # Added AudioFileClip just in case, though clip.audio should work

# Import functions from our modules
from audio_utils import calculate_rms_db
from visualization import create_segment_visualization
from video_utils import process_video

# Configure logging for the app (optional, Streamlit handles basic output)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Streamlit Page Configuration ---
st.set_page_config(page_title="Silent Video Editor", layout="wide")
st.title("✂️ Silent Video Segment Remover")
st.markdown("Upload a video file, adjust the silence detection parameters, and download the edited video with long silences removed.")

# --- Temp Directory ---
TEMP_DIR = os.path.join(tempfile.gettempdir(), "silent_video_editor")
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)
logging.info(f"Using temporary directory: {TEMP_DIR}")

# --- Sidebar for Parameters ---

st.sidebar.header("Input Video")
uploaded_file = st.sidebar.file_uploader("Choose a video file...", type=["mp4", "mov", "avi", "mkv"])

st.sidebar.markdown("---")

st.sidebar.header("Detection Parameters")
silence_threshold = st.sidebar.slider(
    "Silence Threshold (dBFS)",
    min_value=-70.0,
    max_value=0.0,
    value=-40.0, # Default threshold
    step=1.0,
    help="Audio segments below this level (in decibels relative to full scale) are considered potentially silent. Lower values detect quieter sounds as non-silent."
)

min_silence_duration = st.sidebar.slider(
    "Minimum Silence Duration (seconds)",
    min_value=0.1,
    max_value=10.0,
    value=1.0, # Default minimum silence length to cut
    step=0.1,
    help="Only silent segments longer than this duration will be removed."
)

merge_gap = st.sidebar.slider(
    "Merge Gap (seconds)",
    min_value=0.0,
    max_value=2.0,
    value=0.2, # Default gap to merge
    step=0.05,
    help="Keep short silences (e.g., pauses in speech) shorter than this duration by merging the surrounding non-silent segments."
)

st.sidebar.subheader("Refinement Padding")
start_padding = st.sidebar.slider(
    "Start Padding (seconds)",
    min_value=0.0,
    max_value=0.5, # Keep max relatively small
    value=0.10, # Default start padding
    step=0.01,
    help="Keep this much extra time *before* detected sound starts. Helps prevent cutting off initial faint sounds."
)

end_padding = st.sidebar.slider(
    "End Padding (seconds)",
    min_value=0.0,
    max_value=0.5, # Keep max relatively small
    value=0.10, # Default end padding
    step=0.01,
    help="Keep this much extra time *after* detected sound ends. Helps prevent cutting off trailing faint sounds or echoes."
)

# --- Main Area ---
if uploaded_file is not None:
    st.subheader("Uploaded Video Preview")
    # Save uploaded file temporarily to read with moviepy
    input_path = os.path.join(TEMP_DIR, uploaded_file.name)
    with open(input_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    st.success(f"Uploaded '{uploaded_file.name}'")

    # Display basic video info and preview (optional)
    video_clip_for_info = None # Define outside try block for potential cleanup
    try:
        video_clip_for_info = VideoFileClip(input_path)
        st.write(f"**Duration:** {video_clip_for_info.duration:.2f} seconds")
        st.video(input_path) # Display the whole video player
    except Exception as e:
        st.error(f"Could not read video file info: {e}")
        input_path = None # Mark as invalid
    finally:
        if video_clip_for_info:
            video_clip_for_info.close() # Close the clip used only for info

    if input_path and os.path.exists(input_path): # Check if path is still valid
        # --- Visualization Section ---
        st.subheader("Audio Analysis & Segment Visualization")
        vis_placeholder = st.empty()
        vis_placeholder.info("Generating audio visualization... (this might take a moment)")

        audio_clip_for_vis = None # Define outside try block for cleanup
        vis_clip = None
        try:
            # Re-open the clip specifically for processing/visualization if needed
            vis_clip = VideoFileClip(input_path)
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
        process_button_disabled = not (input_path and os.path.exists(input_path))
        process_button = st.button("🚀 Remove Silent Segments", key="process", disabled=process_button_disabled)

        if process_button_disabled:
             st.warning("Cannot process - input video file is missing or invalid.")


        if process_button and not process_button_disabled:
            output_filename = f"{os.path.splitext(uploaded_file.name)[0]}_edited.mp4"
            output_path = os.path.join(TEMP_DIR, output_filename)

            st_progress_bar = st.progress(0.0)
            st_status_text = st.empty()

            def progress_callback(progress_value, message):
                st_progress_bar.progress(min(1.0, progress_value)) # Ensure progress doesn't exceed 1.0
                st_status_text.info(message)

            try:
                success, result_message = process_video(
                    video_path=input_path,
                    output_path=output_path,
                    silence_threshold_db=silence_threshold,
                    min_silence_len_sec=min_silence_duration,
                    merge_gap_sec=merge_gap,
                    start_padding_sec=start_padding,
                    end_padding_sec=end_padding,
                    progress_callback=progress_callback
                )

                if success:
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

            # No finally block for input_path cleanup here, as it might be needed
            # if the user wants to retry processing with different parameters without re-uploading.
            # Streamlit's temp file handling or session state might manage this.
            # If explicit cleanup is desired, it needs careful state management.

else:
    st.info("Please upload a video file using the sidebar to begin.")

# Add footer or instructions
st.markdown("---")
st.markdown("Developed with Streamlit and MoviePy.")
