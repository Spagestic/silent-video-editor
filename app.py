import streamlit as st
import os
import tempfile
import logging
from moviepy import VideoFileClip

# Import component files
from components.sidebar import create_sidebar
from utils.visualization import create_segment_visualization
from utils.video_utils import process_video

# Configure logging
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

if 'output_path' not in st.session_state:
    st.session_state.output_path = None

# --- Temp Directory ---
TEMP_DIR = os.path.join(tempfile.gettempdir(), "silent_video_editor")
if not os.path.exists(TEMP_DIR):
    os.makedirs(TEMP_DIR)
logging.info(f"Using temporary directory: {TEMP_DIR}")

# --- Sidebar ---
input_option, silence_threshold, min_silence_duration, merge_gap, start_padding, end_padding, enable_noise_reduction, noise_reduction_strength, enable_filler_removal, filler_sensitivity = create_sidebar()

# --- Main Area ---
if st.session_state.input_path and os.path.exists(st.session_state.input_path):
    st.subheader("Video Preview")
    st.success(f"Ready to process: {st.session_state.video_title}")

    # Display basic video info and preview
    video_clip_for_info = None
    try:
        video_clip_for_info = VideoFileClip(st.session_state.input_path)
        st.write(f"**Duration:** {video_clip_for_info.duration:.2f} seconds")
        st.video(st.session_state.input_path)
    except Exception as e:
        st.error(f"Could not read video file info: {e}")
        st.session_state.input_path = None
    finally:
        if video_clip_for_info:
            video_clip_for_info.close()

    if st.session_state.input_path and os.path.exists(st.session_state.input_path):
        # --- Visualization Section ---
        st.subheader("Audio Analysis & Segment Visualization")
        vis_placeholder = st.empty()
        vis_placeholder.info("Generating audio visualization... (this might take a moment)")

        audio_clip_for_vis = None
        vis_clip = None
        try:
            vis_clip = VideoFileClip(st.session_state.input_path)
            audio_clip_for_vis = vis_clip.audio
            if audio_clip_for_vis:
                target_fps = audio_clip_for_vis.fps if audio_clip_for_vis.fps and audio_clip_for_vis.fps > 0 else 44100
                max_vis_duration_sec = 300
                vis_duration_sec = min(audio_clip_for_vis.duration, max_vis_duration_sec)
                logging.info(f"Preparing audio for visualization (up to {vis_duration_sec:.2f}s)")

                audio_subclip_for_vis = audio_clip_for_vis.subclipped(0, vis_duration_sec)

                audio_array = audio_subclip_for_vis.to_soundarray(
                    fps=target_fps,
                    nbytes=2,
                    quantize=False
                )

                logging.info(f"Generating visualization plot...")
                fig = create_segment_visualization(
                    audio_array,
                    target_fps,
                    silence_threshold_db=silence_threshold,
                    min_silence_len_sec=min_silence_duration
                )
                vis_placeholder.pyplot(fig)
                del audio_array
                audio_subclip_for_vis.close()

            else:
                vis_placeholder.warning("Video has no audio track. Cannot visualize or process silence.")
        except Exception as e:
            vis_placeholder.error(f"Error generating visualization: {e}")
            logging.error("Visualization failed", exc_info=True)
        finally:
            if audio_clip_for_vis:
                audio_clip_for_vis.close()
            if vis_clip:
                vis_clip.close()

        # --- Processing Section ---
        st.subheader("Process and Download")
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
                st_progress_bar.progress(min(1.0, progress_value))
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
                    st_progress_bar.progress(1.0)

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
    st.info("Please upload a video file or paste a YouTube URL to begin.")

# Add footer or instructions
st.markdown("---")
st.markdown("Developed with Streamlit and MoviePy. Supports YouTube videos and local files.")