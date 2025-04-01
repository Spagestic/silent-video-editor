# audio_utils.py
import numpy as np
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def calculate_rms(audio_array, frame_size):
    """Calculate RMS energy for audio frames."""
    # Convert to mono if stereo
    if len(audio_array.shape) > 1 and audio_array.shape[1] > 1:
        logging.debug("Audio is stereo, converting to mono.")
        audio_array = np.mean(audio_array, axis=1)
    elif len(audio_array.shape) > 1 and audio_array.shape[1] == 1:
         audio_array = audio_array.flatten() # Make sure it's 1D if shape is (N, 1)

    if len(audio_array) == 0:
        logging.warning("Received empty audio array for RMS calculation.")
        return np.array([])

    rms_energy = []
    num_frames = len(audio_array) // frame_size
    logging.debug(f"Calculating RMS for {num_frames} frames of size {frame_size}.")

    for i in range(0, len(audio_array), frame_size):
        frame = audio_array[i:i + frame_size]
        if frame.size == 0: # Avoid processing empty trailing frames
             continue
        rms = np.sqrt(np.mean(np.square(frame)))
        rms_energy.append(rms)

    return np.array(rms_energy)

def calculate_rms_db(audio_array, frame_size):
    """Calculate RMS energy in dB."""
    rms_energy = calculate_rms(audio_array, frame_size)
    if rms_energy.size == 0:
        return np.array([])
    # Add a small epsilon to avoid log10(0)
    rms_db = 20 * np.log10(rms_energy + 1e-9)
    return rms_db