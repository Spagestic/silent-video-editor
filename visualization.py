# visualization.py
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import logging
from audio_utils import calculate_rms_db # Import from our local module

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def create_segment_visualization(audio_array, fps, silence_threshold_db=-40, min_silence_len_sec=1, figsize=(12, 6)):
    """
    Generates a Matplotlib figure visualizing audio segments.
    Returns the figure object.
    """
    logging.info(f"Starting visualization generation: threshold={silence_threshold_db}dB, min_len={min_silence_len_sec}s")
    # Convert to mono if stereo
    if len(audio_array.shape) > 1 and audio_array.shape[1] > 1:
        audio_array_mono = np.mean(audio_array, axis=1)
    elif len(audio_array.shape) > 1 and audio_array.shape[1] == 1:
        audio_array_mono = audio_array.flatten()
    else:
         audio_array_mono = audio_array

    if audio_array_mono.size == 0 or fps <= 0:
        logging.error("Cannot visualize: Empty audio array or invalid FPS.")
        # Return an empty figure or raise an error
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "Error: No audio data to visualize", ha='center', va='center')
        return fig

    frame_size = int(fps * min_silence_len_sec)
    if frame_size <= 0:
        logging.error(f"Calculated frame size is zero or negative ({frame_size}). Check FPS ({fps}) and min_silence_len_sec ({min_silence_len_sec}).")
        frame_size = int(fps) # Fallback to 1 second if calculation failed
        if frame_size <= 0:
             frame_size = 1024 # Absolute fallback
        logging.warning(f"Using fallback frame size: {frame_size}")


    frame_duration_sec = frame_size / fps
    num_audio_samples = len(audio_array_mono)
    total_duration_sec = num_audio_samples / fps

    logging.debug(f"Audio samples: {num_audio_samples}, FPS: {fps}, Total duration: {total_duration_sec:.2f}s")
    logging.debug(f"Frame size: {frame_size} samples, Frame duration: {frame_duration_sec:.3f}s")

    rms_db = calculate_rms_db(audio_array_mono, frame_size)
    num_rms_frames = len(rms_db)

    if num_rms_frames == 0:
        logging.warning("RMS calculation resulted in zero frames.")
        fig, ax = plt.subplots(figsize=figsize)
        ax.text(0.5, 0.5, "Could not calculate RMS energy", ha='center', va='center')
        return fig

    frame_times = np.arange(num_rms_frames) * frame_duration_sec

    # Ensure frame_times doesn't exceed total duration due to rounding/framing
    if len(frame_times) > 0 and frame_times[-1] + frame_duration_sec > total_duration_sec:
         frame_times = frame_times[frame_times < total_duration_sec - frame_duration_sec] # Adjust if needed
         rms_db = rms_db[:len(frame_times)] # Match rms_db length
         num_rms_frames = len(frame_times)
         logging.debug(f"Adjusted frame times to fit within total duration. New frame count: {num_rms_frames}")


    silent_frame_indices = np.where(rms_db <= silence_threshold_db)[0]
    non_silent_frame_indices = np.where(rms_db > silence_threshold_db)[0]

    time_waveform = np.arange(num_audio_samples) / fps

    fig, axs = plt.subplots(3, 1, figsize=figsize, sharex=True) # Share x-axis

    # --- Plot 1: Audio Waveform ---
    axs[0].plot(time_waveform, audio_array_mono, color='blue', alpha=0.6)
    axs[0].set_title('Audio Waveform (Mono)')
    axs[0].set_ylabel('Amplitude')
    axs[0].grid(True, linestyle=':', alpha=0.5)
    axs[0].set_xlim(0, total_duration_sec)

    # --- Plot 2: RMS Energy ---
    if num_rms_frames > 0:
        axs[1].plot(frame_times, rms_db, color='green', marker='.', linestyle='-', markersize=3)
        axs[1].axhline(y=silence_threshold_db, color='red', linestyle='--', label=f'Threshold ({silence_threshold_db} dB)')
        axs[1].set_title('RMS Energy per Segment')
        axs[1].set_ylabel('dBFS')
        axs[1].legend(loc='upper right')
        axs[1].grid(True, linestyle=':', alpha=0.5)
    else:
        axs[1].text(0.5, 0.5, "No RMS data", ha='center', va='center')


        # --- Plot 3: Silent/Non-Silent Segments ---
    ax_segments = axs[2]

    def add_segments(frame_indices, color, alpha):
        for idx in frame_indices:
            if idx >= len(frame_times): # Safety check
                continue
            start_time = frame_times[idx]
            # Ensure width doesn't make rectangle go beyond plot limits
            width = min(frame_duration_sec, total_duration_sec - start_time)
            if width > 0:
                rect = Rectangle((start_time, 0), width, 1, color=color, alpha=alpha, edgecolor=None)
                ax_segments.add_patch(rect)

    if num_rms_frames > 0:
        # Add non-silent first (green background) then silent (red overlay)
        # Create a default green background representing "non-silent unless marked"
        bg_rect = Rectangle((0,0), total_duration_sec, 1, color='green', alpha=0.3, edgecolor=None)
        ax_segments.add_patch(bg_rect)
        # Overlay silent segments in red
        add_segments(silent_frame_indices, 'red', 0.6) # Make red more prominent

    ax_segments.set_title('Detected Segments (Red=Silent, Green=Keep)')
    ax_segments.set_xlabel('Time (seconds)')
    ax_segments.set_ylim(0, 1)
    ax_segments.set_yticks([])
    ax_segments.grid(False) # No grid needed here

    plt.tight_layout() # Adjust layout

    # --- Log segment info ---
    silent_segments_times = [(frame_times[idx], frame_times[idx] + frame_duration_sec) for idx in silent_frame_indices if idx < len(frame_times)]
    non_silent_segments_times = [(frame_times[idx], frame_times[idx] + frame_duration_sec) for idx in non_silent_frame_indices if idx < len(frame_times)]

    silent_duration_calc = sum(e - s for s, e in silent_segments_times)
    non_silent_duration_calc = sum(e - s for s, e in non_silent_segments_times)

    logging.info(f"Visualization: Found {len(silent_segments_times)} silent segments (Total: {silent_duration_calc:.2f}s)")
    logging.info(f"Visualization: Found {len(non_silent_segments_times)} non-silent segments (Total: {non_silent_duration_calc:.2f}s)")
    if total_duration_sec > 0:
         logging.info(f"Total duration: {total_duration_sec:.2f}s, Detected Silent: {silent_duration_calc/total_duration_sec*100:.1f}%")

    return fig