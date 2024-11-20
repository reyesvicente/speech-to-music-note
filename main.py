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

# Define note frequencies (Hz)
NOTE_FREQUENCIES = {
    'C4': 261.63,
    'C#4/Db4': 277.18,
    'D4': 293.66,
    'D#4/Eb4': 311.13,
    'E4': 329.63,
    'F4': 349.23,
    'F#4/Gb4': 369.99,
    'G4': 392.00,
    'G#4/Ab4': 415.30,
    'A4': 440.00,
    'A#4/Bb4': 466.16,
    'B4': 493.88,
}

def detect_pitch(audio_path: str, hop_length: int = 512) -> List[Dict]:
    """
    Detect musical notes from an audio file using pitch detection.
    Returns a list of notes with their timing information.
    """
    try:
        # Load the audio file
        y, sr = librosa.load(audio_path)
        
        # Perform pitch detection
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr, hop_length=hop_length)
        
        # Get timing information
        times = librosa.times_like(pitches, sr=sr, hop_length=hop_length)
        
        notes = []
        current_note = None
        note_start = 0
        min_note_duration = 0.1  # Minimum duration for a note in seconds
        
        for time_idx, time in enumerate(times):
            # Get the highest magnitude frequency at this time
            index = magnitudes[:, time_idx].argmax()
            pitch = pitches[index, time_idx]
            
            if pitch > 0:  # If a pitch was detected
                # Find the closest note
                closest_note = None
                min_diff = float('inf')
                
                for note, freq in NOTE_FREQUENCIES.items():
                    diff = abs(12 * np.log2(pitch/freq))
                    if diff < min_diff and diff < 0.5:  # Only match if within half semitone
                        min_diff = diff
                        closest_note = note
                
                # Handle note transitions
                if closest_note != current_note:
                    if current_note and time - note_start >= min_note_duration:
                        notes.append({
                            'note': current_note.split('/')[0][:1],  # Get just the note letter
                            'start': float(note_start),
                            'end': float(time),
                            'frequency': float(pitch)
                        })
                    current_note = closest_note
                    note_start = time
            
            elif current_note and time - note_start >= min_note_duration:
                notes.append({
                    'note': current_note.split('/')[0][:1],  # Get just the note letter
                    'start': float(note_start),
                    'end': float(time),
                    'frequency': float(pitches[index, time_idx - 1])
                })
                current_note = None
        
        # Add the last note if it exists
        if current_note and times[-1] - note_start >= min_note_duration:
            notes.append({
                'note': current_note.split('/')[0][:1],  # Get just the note letter
                'start': float(note_start),
                'end': float(times[-1]),
                'frequency': float(pitch)
            })
        
        return notes
    
    except Exception as e:
        logger.error(f"Error in pitch detection: {str(e)}")
        return []

class Note:
    def __init__(self, note: str, start: float, end: float):
        self.note = note
        self.start = start
        self.end = end
        self.duration = end - start

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)) -> Dict:
    """Handle audio file upload and perform pitch detection."""
    try:
        logger.info("Received audio file: %s", file.filename)
        
        # Create a temporary file to store the uploaded audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            # Write the uploaded file content to the temporary file
            content = await file.read()
            temp_file.write(content)
            temp_file.flush()
            
            logger.info("Temporary file created: %s", temp_file.name)
            
            # Perform pitch detection
            detected_notes = detect_pitch(temp_file.name)
            logger.info("Detected notes: %s", detected_notes)
            
            # Convert detected notes to Note objects
            notes = [Note(note['note'], note['start'], note['end']) for note in detected_notes]
            
            # Convert notes to response format
            notes_data = [
                {
                    "note": note.note,
                    "start": note.start,
                    "end": note.end,
                    "duration": note.end - note.start
                }
                for note in notes
            ]
            
            # Clean up the temporary file
            os.unlink(temp_file.name)
            
            response_data = {
                "status": "success",
                "notes": notes_data
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
    return {"message": "Speech to Musical Notes API"}