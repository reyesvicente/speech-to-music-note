import os
from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
import assemblyai as aai
from typing import Dict, List, Optional
import tempfile
import re
import logging
import librosa
import numpy as np
import soundfile as sf
import asyncio
from concurrent.futures import ThreadPoolExecutor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Initialize FastAPI app
app = FastAPI()

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize AssemblyAI
aai.settings.api_key = os.getenv("ASSEMBLYAI_API_KEY")

# Define note frequencies (Hz) for multiple octaves
NOTE_FREQUENCIES = {
    # Octave 3
    'C3': 130.81, 'C#3': 138.59, 'D3': 146.83, 'D#3': 155.56,
    'E3': 164.81, 'F3': 174.61, 'F#3': 185.00, 'G3': 196.00,
    'G#3': 207.65, 'A3': 220.00, 'A#3': 233.08, 'B3': 246.94,
    # Octave 4 (Middle)
    'C4': 261.63, 'C#4': 277.18, 'D4': 293.66, 'D#4': 311.13,
    'E4': 329.63, 'F4': 349.23, 'F#4': 369.99, 'G4': 392.00,
    'G#4': 415.30, 'A4': 440.00, 'A#4': 466.16, 'B4': 493.88,
    # Octave 5
    'C5': 523.25, 'C#5': 554.37, 'D5': 587.33, 'D#5': 622.25,
    'E5': 659.26, 'F5': 698.46, 'F#5': 739.99, 'G5': 783.99,
    'G#5': 830.61, 'A5': 880.00, 'A#5': 932.33, 'B5': 987.77,
}

def get_note_name(frequency: float) -> str:
    """Convert frequency to note name with octave."""
    if frequency <= 0:
        return None
    
    # A4 is 440 Hz, which is MIDI note 69
    midi_note = round(12 * np.log2(frequency / 440.0) + 69)
    
    # Convert MIDI note to note name and octave
    note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    
    # Calculate octave and note index
    # MIDI note 60 is middle C (C4)
    octave = (midi_note - 12) // 12
    note_index = (midi_note - 12) % 12
    
    # Ensure reasonable octave range (C2 to C6)
    if octave < 2:
        octave = 2
    elif octave > 6:
        octave = 6
    
    return f"{note_names[note_index]}{octave}"

def detect_pitch(audio_path: str, hop_length: int = 1024) -> List[Dict]:
    """
    Detect musical notes from an audio file using pitch detection.
    Returns a list of notes with their timing information.
    """
    try:
        # Load the audio file with optimized parameters
        y, sr = librosa.load(audio_path, sr=22050, duration=10)  # Higher sample rate for better detection
        
        # Use smaller hop length for better time resolution
        pitches, magnitudes = librosa.piptrack(
            y=y, 
            sr=sr,
            hop_length=hop_length,
            fmin=librosa.note_to_hz('C2'),
            fmax=librosa.note_to_hz('C6'),
            n_fft=2048,  # Smaller FFT window for better time resolution
            threshold=0.05  # Lower threshold to catch more potential notes
        )
        
        # Get timing information
        times = librosa.times_like(pitches, sr=sr, hop_length=hop_length)
        
        notes = []
        current_note = None
        note_start = 0
        min_note_duration = 0.1  # Shorter minimum duration for quick sounds
        confidence_threshold = 0.5  # Lower threshold to catch more notes
        
        # Process frames more frequently
        for time_idx in range(0, len(times), 2):  # Process every 2nd frame
            time = times[time_idx]
            
            # Vectorized operation for finding max magnitude
            frame_magnitudes = magnitudes[:, time_idx]
            if not np.any(frame_magnitudes > confidence_threshold):
                if current_note and time - note_start >= min_note_duration:
                    notes.append({
                        'note': current_note[:-1],
                        'octave': int(current_note[-1]),
                        'start': float(note_start),
                        'end': float(time),
                        'frequency': float(pitches[:, time_idx - 1].max()),
                        'confidence': float(magnitudes[:, time_idx - 1].max())
                    })
                    current_note = None
                continue
                
            index = frame_magnitudes.argmax()
            pitch = pitches[index, time_idx]
            magnitude = frame_magnitudes[index]
            
            if pitch > 0 and magnitude > confidence_threshold:
                note_name = get_note_name(pitch)
                
                if note_name and len(note_name) >= 2:
                    try:
                        octave = int(note_name[-1])
                        
                        if 2 <= octave <= 6:
                            if note_name != current_note:
                                if current_note and time - note_start >= min_note_duration:
                                    notes.append({
                                        'note': current_note[:-1],
                                        'octave': int(current_note[-1]),
                                        'start': float(note_start),
                                        'end': float(time),
                                        'frequency': float(pitch),
                                        'confidence': float(magnitude)
                                    })
                                current_note = note_name
                                note_start = time
                    except (ValueError, IndexError):
                        continue
            
            elif current_note and time - note_start >= min_note_duration:
                notes.append({
                    'note': current_note[:-1],
                    'octave': int(current_note[-1]),
                    'start': float(note_start),
                    'end': float(time),
                    'frequency': float(pitches[:, time_idx - 1].max()),
                    'confidence': float(magnitudes[:, time_idx - 1].max())
                })
                current_note = None
        
        # Add the last note if it exists
        if current_note and (times[-1] - note_start) >= min_note_duration:
            notes.append({
                'note': current_note[:-1],
                'octave': int(current_note[-1]),
                'start': float(note_start),
                'end': float(times[-1]),
                'frequency': float(pitches[:, -1].max()),
                'confidence': float(magnitudes[:, -1].max())
            })
        
        # Filter notes but allow more through
        notes = [note for note in notes if 2 <= note['octave'] <= 6][:30]  # Increased max notes
        
        return notes
    
    except Exception as e:
        logger.error(f"Error in pitch detection: {str(e)}")
        return []

class Note:
    def __init__(self, note: str, octave: int, start: float, end: float):
        self.note = note
        self.octave = octave
        self.start = start
        self.end = end
        self.duration = end - start

async def transcribe_audio(file_path: str) -> str:
    """Async function to handle transcription."""
    try:
        transcriber = aai.Transcriber()
        transcript = await asyncio.to_thread(transcriber.transcribe, file_path)
        return transcript.text if transcript.text else ""
    except Exception as e:
        logger.error(f"Error in transcription: {str(e)}")
        return ""

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)) -> Dict:
    """Handle audio file upload, perform pitch detection and transcription."""
    try:
        logger.info("Received audio file: %s", file.filename)
        
        # Create a temporary file to store the uploaded audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file.flush()
            
            logger.info("Temporary file created: %s", temp_file.name)
            
            # Run pitch detection and transcription concurrently
            pitch_detection_task = asyncio.create_task(
                asyncio.to_thread(detect_pitch, temp_file.name)
            )
            transcription_task = asyncio.create_task(
                transcribe_audio(temp_file.name)
            )
            
            # Wait for both tasks to complete
            detected_notes, transcribed_text = await asyncio.gather(
                pitch_detection_task,
                transcription_task
            )
            
            logger.info("Detected notes: %s", detected_notes)
            
            # Convert detected notes to Note objects
            notes = [Note(note['note'], note['octave'], note['start'], note['end']) 
                    for note in detected_notes]
            
            # Convert notes to response format using list comprehension
            notes_data = [{
                "note": note.note,
                "octave": note.octave,
                "start": note.start,
                "end": note.end,
                "duration": note.end - note.start
            } for note in notes]
            
            # Clean up the temporary file
            os.unlink(temp_file.name)
            
            response_data = {
                "status": "success",
                "notes": notes_data,
                "text": transcribed_text
            }
            
            if not notes_data:
                response_data["message"] = "No musical notes detected in the audio. Try singing a clear melody."
            
            logger.info("Sending response: %s", response_data)
            return JSONResponse(content=response_data)
            
    except Exception as e:
        logger.error("Error processing audio: %s", str(e))
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )

@app.get("/")
async def root():
    return {"Ping": "Pong!"}