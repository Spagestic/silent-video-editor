import streamlit as st
import os
from components.youtube_downloader import download_youtube_video
from components.video_recorder import record_video

def create_sidebar():
    """
    Creates the sidebar with input options and processing parameters.
    Returns:
        A tuple containing the selected input option and parameter values.
    """
    st.sidebar.header("Input Options")

    # Input method selection
    input_option = st.sidebar.radio(
        "Select input method:",
        ["Upload Video File", "Video URL (YouTube, etc.)", "Record Video"]
    )

    # Input handling based on selection
    if input_option == "Upload Video File":
        uploaded_file = st.sidebar.file_uploader("Choose a video file...", type=["mp4", "mov", "avi", "mkv"])
        if uploaded_file is not None:
            # Save uploaded file temporarily
            input_path = os.path.join(os.path.join(os.path.expanduser("~"), "AppData", "Local", "Temp", "silent_video_editor"), uploaded_file.name)
            with open(input_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            # Store in session state
            st.session_state.input_path = input_path
            st.session_state.video_title = uploaded_file.name

    elif input_option == "Video URL (YouTube, etc.)":
        video_url = st.sidebar.text_input("Paste video URL:", placeholder="https://www.youtube.com/watch?v=...")
        if video_url:
            download_placeholder = st.sidebar.empty()
            if st.sidebar.button("Download & Prepare Video"):
                success, downloaded_path, title = download_youtube_video(video_url, download_placeholder)
                if success:
                    st.session_state.input_path = downloaded_path
                    st.session_state.video_title = title

    elif input_option == "Record Video":
        record_video()

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

    # --- Advanced Processing Options ---
    st.sidebar.markdown("---")
    st.sidebar.header("Advanced Processing")

    # Noise Reduction
    enable_noise_reduction = st.sidebar.checkbox(
        "Enable Noise Reduction",
        value=False,
        help="Reduce background noise from the audio"
    )

    if enable_noise_reduction:
        noise_reduction_strength = st.sidebar.slider(
            "Noise Reduction Strength",
            min_value=0.0,
            max_value=1.0,
            value=0.5,
            step=0.05,
            help="Higher values remove more noise but may affect voice quality"
        )
        
    else:
        noise_reduction_strength = 0.5 # Default value when disabled

    # Filler Word Removal
    enable_filler_removal = st.sidebar.checkbox(
        "Remove Filler Words (Experimental)",
        value=False,
        help="Attempt to detect and remove 'ums', 'uhs', and other filler words"
    )

    if enable_filler_removal:
        filler_sensitivity = st.sidebar.slider(
            "Filler Detection Sensitivity",
            min_value=0.0,
            max_value=1.0,
            value=0.7,
            step=0.1,
            help="Higher values detect more potential fillers but may remove actual words"
        )
    else:
        filler_sensitivity = 0.7 # Default value when disabled

    return (
        input_option,
        silence_threshold,
        min_silence_duration,
        merge_gap,
        start_padding,
        end_padding,
        enable_noise_reduction,
        noise_reduction_strength,
        enable_filler_removal,
        filler_sensitivity
    )