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
        # Load the audio file with a lower sample rate
        y, sr = librosa.load(audio_path, sr=16000)
        
        # Reduce audio length if it's too long
        if len(y) > sr * 10:  # Limit to 10 seconds
            y = y[:sr * 10]
        
        # Perform pitch detection with optimized parameters
        pitches, magnitudes = librosa.piptrack(
            y=y, 
            sr=sr,
            hop_length=hop_length,
            fmin=librosa.note_to_hz('C2'),  # Starting from C2
            fmax=librosa.note_to_hz('C6'),  # Up to C6
            n_fft=2048
        )
        
        # Get timing information
        times = librosa.times_like(pitches, sr=sr, hop_length=hop_length)
        
        notes = []
        current_note = None
        note_start = 0
        min_note_duration = 0.3
        confidence_threshold = 0.5
        
        # Process frames
        for time_idx in range(0, len(times), 2):
            time = times[time_idx]
            
            # Get the highest magnitude frequency at this time
            index = magnitudes[:, time_idx].argmax()
            pitch = pitches[index, time_idx]
            magnitude = magnitudes[index, time_idx]
            
            if pitch > 0 and magnitude > confidence_threshold:
                note_name = get_note_name(pitch)
                
                # Validate note_name and octave
                if note_name and len(note_name) >= 2:
                    try:
                        note_letter = note_name[:-1]
                        octave = int(note_name[-1])
                        
                        # Only process notes within valid range
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
                try:
                    notes.append({
                        'note': current_note[:-1],
                        'octave': int(current_note[-1]),
                        'start': float(note_start),
                        'end': float(time),
                        'frequency': float(pitches[index, time_idx - 1]),
                        'confidence': float(magnitudes[index, time_idx - 1])
                    })
                except (ValueError, IndexError):
                    pass
                current_note = None
        
        # Double-check all notes are within valid range
        notes = [note for note in notes if 2 <= note['octave'] <= 6]
        
        # Limit the number of notes returned
        max_notes = 20
        if len(notes) > max_notes:
            notes = notes[:max_notes]
        
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

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)) -> Dict:
    """Handle audio file upload, perform pitch detection and transcription."""
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
            notes = [Note(note['note'], note['octave'], note['start'], note['end']) for note in detected_notes]
            
            # Convert notes to response format
            notes_data = [
                {
                    "note": note.note,
                    "octave": note.octave,
                    "start": note.start,
                    "end": note.end,
                    "duration": note.end - note.start
                }
                for note in notes
            ]

            # Perform AssemblyAI transcription
            try:
                # Create a transcriber
                transcriber = aai.Transcriber()
                
                # Start transcription
                transcript = transcriber.transcribe(temp_file.name)
                
                # Get the transcribed text
                transcribed_text = transcript.text if transcript.text else ""
                logger.info("Transcribed text: %s", transcribed_text)
                
            except Exception as e:
                logger.error("Error in transcription: %s", str(e))
                transcribed_text = ""
            
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