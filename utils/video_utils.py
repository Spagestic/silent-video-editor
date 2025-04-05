# video_utils.py
import numpy as np
from moviepy import VideoFileClip, concatenate_videoclips
import logging
from tqdm import tqdm
import os
from utils.audio_utils import calculate_rms_db # Import from our local module

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def detect_non_silent_intervals(audio_array, fps, silence_threshold_db=-40, min_silence_len_sec=1.0, merge_gap_sec=0.2):
    """
    Detects non-silent intervals based on RMS energy.

    Args:
        audio_array (np.ndarray): The audio waveform.
        fps (int): Frames per second of the audio.
        silence_threshold_db (float): Energy threshold in dB below which is considered silent.
        min_silence_len_sec (float): Minimum duration (in seconds) for a silence block to be considered.
                                     Shorter silences within speech might be kept.
        merge_gap_sec (float): Short gaps between non-silent segments to merge (in seconds).

    Returns:
        list of tuples: A list of (start_time, end_time) tuples for non-silent intervals.
    """
    logging.info(f"Detecting non-silent intervals: threshold={silence_threshold_db}dB, min_silence={min_silence_len_sec}s, merge_gap={merge_gap_sec}s")

    # --- Parameter Validation ---
    if fps <= 0:
        logging.error("Invalid FPS provided.")
        return []
    if audio_array is None or audio_array.size == 0:
        logging.warning("Empty audio array provided for detection.")
        return []
    if min_silence_len_sec <= 0:
         logging.warning("min_silence_len_sec must be positive, using 0.1s as fallback.")
         min_silence_len_sec = 0.1
    if merge_gap_sec < 0:
         logging.warning("merge_gap_sec cannot be negative, using 0s.")
         merge_gap_sec = 0


    # --- Frame Calculation ---
    # Use a smaller frame size for detection than for visualization/min_silence_len definition
    # This gives finer granularity for identifying transitions. Let's use ~50ms.
    detection_frame_duration_sec = 0.05
    detection_frame_size = int(fps * detection_frame_duration_sec)
    if detection_frame_size <= 0:
        detection_frame_size = int(fps * 0.1) # Fallback if fps is very low
        if detection_frame_size <= 0:
             detection_frame_size = 256 # Absolute fallback
        detection_frame_duration_sec = detection_frame_size / fps
        logging.warning(f"Using fallback detection frame size: {detection_frame_size} samples ({detection_frame_duration_sec*1000:.1f}ms)")


    # Convert to mono if stereo
    if len(audio_array.shape) > 1 and audio_array.shape[1] > 1:
        audio_array_mono = np.mean(audio_array, axis=1)
    elif len(audio_array.shape) > 1 and audio_array.shape[1] == 1:
        audio_array_mono = audio_array.flatten()
    else:
        audio_array_mono = audio_array

    # --- RMS Calculation ---
    rms_db = calculate_rms_db(audio_array_mono, detection_frame_size)
    if rms_db.size == 0:
        logging.warning("RMS calculation resulted in zero frames for detection.")
        return []

    num_rms_frames = len(rms_db)
    total_duration_sec = len(audio_array_mono) / fps
    logging.debug(f"Detection: Calculated {num_rms_frames} RMS frames using {detection_frame_duration_sec*1000:.1f}ms window.")


    # --- Identify Non-Silent Frames ---
    non_silent_indices = np.where(rms_db > silence_threshold_db)[0]

    if non_silent_indices.size == 0:
        logging.info("No segments detected above the silence threshold.")
        return []


    # --- Group Consecutive Non-Silent Frames ---
    non_silent_groups = []
    if len(non_silent_indices) > 0:
        current_group_start = non_silent_indices[0]
        current_group_end = non_silent_indices[0]
        for i in range(1, len(non_silent_indices)):
            # If the gap between consecutive non-silent frames is small (<= 1 frame index means adjacent)
            if non_silent_indices[i] <= current_group_end + 1 :
                 current_group_end = non_silent_indices[i] # Extend the current group
            else:
                # Gap is too large, end the current group and start a new one
                non_silent_groups.append((current_group_start, current_group_end))
                current_group_start = non_silent_indices[i]
                current_group_end = non_silent_indices[i]
        # Add the last group
        non_silent_groups.append((current_group_start, current_group_end))

    logging.debug(f"Initial grouping found {len(non_silent_groups)} non-silent groups.")

    # --- Convert Frame Indices to Timestamps ---
    intervals_sec = []
    for start_idx, end_idx in non_silent_groups:
         start_time = start_idx * detection_frame_duration_sec
         # End time is the start of the *next* frame after the last detected frame
         end_time = (end_idx + 1) * detection_frame_duration_sec
         # Clamp end_time to total video duration
         end_time = min(end_time, total_duration_sec)
         intervals_sec.append((start_time, end_time))

    if not intervals_sec:
         logging.info("No intervals created after converting indices to time.")
         return []

    # --- Merge Short Gaps Between Intervals ---
    if merge_gap_sec > 0 and len(intervals_sec) > 1:
        merged_intervals = [intervals_sec[0]]
        for i in range(1, len(intervals_sec)):
            prev_start, prev_end = merged_intervals[-1]
            curr_start, curr_end = intervals_sec[i]

            gap_duration = curr_start - prev_end
            if gap_duration <= merge_gap_sec:
                 # Merge: update the end time of the previous interval
                 merged_intervals[-1] = (prev_start, max(prev_end, curr_end))
                 logging.debug(f"Merging gap of {gap_duration:.3f}s between {prev_end:.2f}s and {curr_start:.2f}s")
            else:
                 # No merge, add the current interval as a new one
                 merged_intervals.append((curr_start, curr_end))
        intervals_sec = merged_intervals
        logging.debug(f"After merging gaps (<={merge_gap_sec}s), {len(intervals_sec)} intervals remain.")


    # --- Filter out intervals based on surrounding silence duration ---
    # This uses the `min_silence_len_sec` parameter. We check the silence *before* each non-silent block.
    # If a non-silent block starts immediately after a silence shorter than `min_silence_len_sec`,
    # it might imply that the silence was just a pause within speech, so we might want to keep that silence.
    # This logic is complex to implement perfectly here. A simpler approach is to ensure the *kept* segments
    # are sufficiently long, but the current goal is removing silence *longer* than the threshold.
    # Let's stick to removing based on threshold and minimum length first. The current intervals are *non-silent*.

    # Alternative interpretation: only remove silences *longer* than min_silence_len_sec.
    # This means we need to identify the *silent* intervals first.

    silent_indices = np.where(rms_db <= silence_threshold_db)[0]
    silent_intervals_sec = []
    if len(silent_indices) > 0:
        current_group_start = silent_indices[0]
        current_group_end = silent_indices[0]
        for i in range(1, len(silent_indices)):
            if silent_indices[i] <= current_group_end + 1:
                current_group_end = silent_indices[i]
            else:
                 start_time = current_group_start * detection_frame_duration_sec
                 end_time = (current_group_end + 1) * detection_frame_duration_sec
                 end_time = min(end_time, total_duration_sec)
                 silent_intervals_sec.append((start_time, end_time))
                 current_group_start = silent_indices[i]
                 current_group_end = silent_indices[i]
        # Add the last silent group
        start_time = current_group_start * detection_frame_duration_sec
        end_time = (current_group_end + 1) * detection_frame_duration_sec
        end_time = min(end_time, total_duration_sec)
        silent_intervals_sec.append((start_time, end_time))

    # Filter silent intervals based on min_silence_len_sec
    long_silent_intervals = [(s, e) for s, e in silent_intervals_sec if (e - s) >= min_silence_len_sec]
    logging.debug(f"Identified {len(long_silent_intervals)} silent intervals longer than {min_silence_len_sec}s.")

    # Now, determine the segments to *keep* by inverting the long silent intervals
    kept_intervals = []
    current_time = 0.0
    for silent_start, silent_end in long_silent_intervals:
        if current_time < silent_start:
            # Keep the segment before this long silence
            kept_intervals.append((current_time, silent_start))
        current_time = max(current_time, silent_end) # Move past the silent part

    # Add the final segment after the last long silence
    if current_time < total_duration_sec:
        kept_intervals.append((current_time, total_duration_sec))

    # Optional: Further merge very short kept intervals if desired (might result from tiny kept fragments between long silences)
    # merge_kept_gap = 0.1 # Example: merge kept segments separated by less than 100ms
    # if merge_kept_gap > 0 and len(kept_intervals) > 1:
    #      merged_kept = [kept_intervals[0]]
    #      for i in range(1, len(kept_intervals)):
    #            prev_s, prev_e = merged_kept[-1]
    #            curr_s, curr_e = kept_intervals[i]
    #            if curr_s - prev_e <= merge_kept_gap:
    #                 merged_kept[-1] = (prev_s, max(prev_e, curr_e))
    #            else:
    #                 merged_kept.append((curr_s, curr_e))
    #      kept_intervals = merged_kept


    logging.info(f"Detected {len(kept_intervals)} final intervals to keep.")
    logging.debug(f"Final kept intervals (s): {[(f'{s:.2f}', f'{e:.2f}') for s, e in kept_intervals]}")
    return kept_intervals


def process_video(video_path, output_path, silence_threshold_db=-40,
                  min_silence_len_sec=1.0, merge_gap_sec=0.2,
                  start_padding_sec=0.1, end_padding_sec=0.1, # <-- New Parameters
                  progress_callback=None):
    """
    Removes silent parts from a video based on detected intervals, adding padding.

    Args:
        video_path (str): Path to the input video file.
        output_path (str): Path to save the processed video file.
        silence_threshold_db (float): Silence threshold in dB.
        min_silence_len_sec (float): Minimum duration of silence to remove.
        merge_gap_sec (float): Merge adjacent non-silent segments closer than this.
        start_padding_sec (float): Seconds to keep *before* the start of a detected non-silent segment.
        end_padding_sec (float): Seconds to keep *after* the end of a detected non-silent segment.
        progress_callback (callable, optional): Function to report progress (0.0 to 1.0).

    Returns:
        tuple: (bool, str) indicating success status and a message/path.
    """
    video = None
    final_clip = None
    audio = None
    try:
        if progress_callback: progress_callback(0.0, "Loading video...")
        logging.info(f"Loading video: {video_path}")
        video = VideoFileClip(video_path)
        # --- Get total duration early for boundary checks ---
        video_duration = video.duration
        # ----------------------------------------------------
        audio = video.audio

        if audio is None:
            raise ValueError("Video file does not contain an audio track.")

        audio_fps = audio.fps
        # Ensure we request a consistent FPS, needed for array length calculation
        if progress_callback: progress_callback(0.1, "Extracting audio waveform...")
        logging.info("Extracting audio waveform...")
        # Use a specific FPS, otherwise it might vary; 44100 is common standard
        target_fps = audio_fps if audio_fps and audio_fps > 0 else 44100
        audio_array = audio.to_soundarray(fps=target_fps, nbytes=2, buffersize=2000, quantize=False) # Use defaults or specify if needed
        logging.info(f"Audio extracted: duration={audio.duration:.2f}s, fps={target_fps}, shape={audio_array.shape}")


        if progress_callback: progress_callback(0.2, "Detecting non-silent segments...")
        non_silent_intervals = detect_non_silent_intervals(
            audio_array, target_fps, silence_threshold_db, min_silence_len_sec, merge_gap_sec
        )

        if not non_silent_intervals:
            logging.warning("No non-silent segments detected. No changes will be made.")
            return False, "No non-silent segments found based on the criteria. Output not generated."

        logging.info(f"Extracting {len(non_silent_intervals)} non-silent subclips with padding ({start_padding_sec}s start, {end_padding_sec}s end)...")
        subclips = []
        total_segments = len(non_silent_intervals)

        # --- Iterate and apply padding ---
        adjusted_intervals = []
        last_kept_end_time = 0.0
        for i, (start_sec, end_sec) in enumerate(non_silent_intervals):
            # Apply padding
            padded_start = start_sec - start_padding_sec
            padded_end = end_sec + end_padding_sec

            # Ensure start doesn't go below zero or overlap significantly with the previous *kept* segment
            padded_start = max(0.0, padded_start)
            padded_start = max(last_kept_end_time, padded_start) # Prevent overlap after padding

            # Ensure end doesn't exceed video duration
            padded_end = min(video_duration, padded_end)

            # Ensure interval is valid (start < end) after padding/clamping
            if padded_end > padded_start:
                 adjusted_intervals.append((padded_start, padded_end))
                 last_kept_end_time = padded_end # Update the end time of the last segment we decided to keep
            else:
                 logging.warning(f"Skipping segment {i+1} after padding resulted in invalid interval: start={padded_start:.2f}, end={padded_end:.2f}")


        # --- Create subclips from adjusted intervals ---
        logging.info(f"Creating {len(adjusted_intervals)} subclips from adjusted intervals...")
        for i, (adj_start, adj_end) in enumerate(adjusted_intervals):
            segment_progress = 0.3 + (0.6 * (i / len(adjusted_intervals))) if adjusted_intervals else 0.3
            if progress_callback: progress_callback(segment_progress, f"Extracting segment {i+1}/{len(adjusted_intervals)} ({adj_start:.2f}s - {adj_end:.2f}s)")
            logging.debug(f"Creating subclip: {adj_start:.3f}s to {adj_end:.3f}s")
            subclips.append(video.subclipped(adj_start, adj_end))


        if not subclips:
             logging.error("Failed to create any valid subclips after padding.")
             # Clean up the original video object before returning
             if video: video.close()
             if audio: audio.close()
             return False, "Error: Could not extract any valid video segments after applying padding."


        if progress_callback: progress_callback(0.9, "Concatenating segments...")
        logging.info("Concatenating final video...")
        # Check if method='compose' helps with potential issues from padding overlaps if any sneak through
        final_clip = concatenate_videoclips(subclips, method="compose")

        # --- Prepare output directory ---
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            logging.info(f"Creating output directory: {output_dir}")
            os.makedirs(output_dir)


        # --- Write final video ---
        if progress_callback: progress_callback(0.95, f"Writing final video to {os.path.basename(output_path)}...")
        logging.info(f"Writing final video to {output_path}")
        # Use tqdm_params for progress bar in console, but relies on Streamlit for UI progress
        final_clip.write_videofile(
            output_path,
            codec="libx264",  # Common codec for MP4
            audio_codec="aac", # Common audio codec
            temp_audiofile='temp-audio.m4a', # Recommended by moviepy docs
            remove_temp=True,
            threads=4, # Use multiple threads if available
            logger='bar' # Shows moviepy's progress bar in console/logs
            # preset='medium' # Can adjust for speed vs compression ('ultrafast', 'fast', 'medium', 'slow', 'slower')
        )

        # Ensure final_clip is defined before returning success
        if final_clip:
             # ... (write_videofile call) ...
             if progress_callback: progress_callback(1.0, "Processing complete!")
             logging.info("Video processing finished successfully.")
             return True, output_path
        else:
             # Should have been caught earlier, but as a safeguard
             logging.error("Final clip object is unexpectedly None before writing.")
             return False, "Error: Failed to create the final concatenated video."


    except Exception as e:
        logging.error(f"Video processing failed: {e}", exc_info=True) # Log traceback
        if progress_callback: progress_callback(1.0, f"Error: {e}")
        return False, f"An error occurred during processing: {str(e)}"
    finally:
        # --- Resource Cleanup ---
        logging.debug("Cleaning up resources...")
        # Use try-except for each close operation
        if audio:
            try: audio.close()
            except Exception as e_close: logging.warning(f"Error closing audio object: {e_close}")
        if video:
            try: video.close()
            except Exception as e_close: logging.warning(f"Error closing video object: {e_close}")
        if final_clip:
            try: final_clip.close()
            except Exception as e_close: logging.warning(f"Error closing final clip object: {e_close}")
        # Clean up temporary audio file if it wasn't removed
        if os.path.exists('temp-audio.m4a'):
            try:
                os.remove('temp-audio.m4a')
                logging.debug("Removed temporary audio file.")
            except OSError as e_remove:
                 logging.warning(f"Could not remove temporary audio file 'temp-audio.m4a': {e_remove}")