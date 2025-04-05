import numpy as np
import librosa
import torch
from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor

class FillerWordDetector:
    def __init__(self):
        # Load pre-trained speech recognition model
        self.processor = Wav2Vec2Processor.from_pretrained("facebook/wav2vec2-base-960h")
        self.model = Wav2Vec2ForCTC.from_pretrained("facebook/wav2vec2-base-960h")
        
        # Common filler words to detect
        self.filler_words = ["um", "uh", "hmm", "er", "like", "you know", "actually"]
        
    def detect_fillers(self, audio_array, sample_rate):
        """
        Detect timestamps of filler words in audio
        
        Returns:
            List of (start_time, end_time) tuples for segments with fillers
        """
        # Resample to 16kHz if needed (required by wav2vec)
        if sample_rate != 16000:
            audio_array = librosa.resample(audio_array, orig_sr=sample_rate, target_sr=16000)
            sample_rate = 16000
            
        # Process audio in chunks for memory efficiency
        chunk_size = 10 * sample_rate  # 10 seconds
        filler_segments = []
        
        for i in range(0, len(audio_array), chunk_size):
            chunk = audio_array[i:i+chunk_size]
            
            # Skip very short chunks
            if len(chunk) < sample_rate:
                continue
                
            # Get model inputs
            inputs = self.processor(chunk, sampling_rate=sample_rate, return_tensors="pt", padding=True)
            
            with torch.no_grad():
                logits = self.model(inputs.input_values).logits
            
            # Get predicted IDs and transcribe
            predicted_ids = torch.argmax(logits, dim=-1)
            transcription = self.processor.batch_decode(predicted_ids)[0].lower()
            
            # Find filler words
            for filler in self.filler_words:
                if filler in transcription:
                    # Approximate timestamp - this is simplified
                    # In a real implementation, use word alignment for precise timestamps
                    start_time = i / sample_rate
                    end_time = (i + len(chunk)) / sample_rate
                    filler_segments.append((start_time, end_time))
                    break  # Found a filler in this segment
                    
        return filler_segments