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

# Define note mapping
NOTE_MAPPING = {
    'a': 'A',
    'b': 'B',
    'c': 'C',
    'd': 'D',
    'e': 'E',
    'f': 'F',
    'g': 'G',
    'do': 'C',
    're': 'D',
    'mi': 'E',
    'fa': 'F',
    'sol': 'G',
    'la': 'A',
    'si': 'B',
    'ti': 'B',
    # Add phonetic variations
    'ay': 'A',
    'bee': 'B',
    'see': 'C',
    'dee': 'D',
    'ee': 'E',
    'ef': 'F',
    'gee': 'G',
    'doh': 'C',
    'ray': 'D',
    'me': 'E',
    'fah': 'F',
    'soh': 'G',
    'lah': 'A',
    'tee': 'B'
}

class Note:
    def __init__(self, note: str, start: float, end: float):
        self.note = note
        self.start = start
        self.end = end
        self.duration = end - start

def find_note_in_word(word: str) -> Optional[str]:
    """Find a musical note within a word."""
    word = word.lower()
    
    # First check if the entire word is a note
    if word in NOTE_MAPPING:
        return NOTE_MAPPING[word]
    
    # Then check word beginnings
    for note_name in NOTE_MAPPING:
        if word.startswith(note_name):
            return NOTE_MAPPING[note_name]
    
    return None

def text_to_notes(words: List[Dict]) -> List[Note]:
    """Convert transcribed words to musical notes with timing information."""
    notes = []
    
    for word in words:
        # Handle AssemblyAI Word objects
        text = word.text.lower() if hasattr(word, 'text') else str(word).lower()
        start = float(word.start) / 1000.0 if hasattr(word, 'start') else 0  # Convert to seconds
        end = float(word.end) / 1000.0 if hasattr(word, 'end') else 0
        
        # Remove punctuation from text
        text = re.sub(r'[^\w\s]', '', text)
        
        note = find_note_in_word(text)
        if note:
            notes.append(Note(note, start, end))
    
    return notes

@app.post("/upload-audio")
async def upload_audio(file: UploadFile = File(...)) -> Dict:
    try:
        logger.info("Received audio file: %s", file.filename)
        
        # Create a temporary file to store the uploaded audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_file:
            # Write the uploaded file content to the temporary file
            content = await file.read()
            temp_file.write(content)
            temp_file.flush()
            
            logger.info("Temporary file created: %s", temp_file.name)
            
            # Create a transcriber with word-level timestamps
            config = aai.TranscriptionConfig(
                word_boost=list(NOTE_MAPPING.keys())  # Boost recognition of note names
            )
            transcriber = aai.Transcriber()
            
            # Start transcription
            logger.info("Starting transcription...")
            transcript = transcriber.transcribe(temp_file.name, config)
            
            logger.info(f"Raw transcript: {transcript.__dict__}")  # Debug log
            
            if not transcript or not hasattr(transcript, 'text'):
                logger.warning("No transcription received")
                return JSONResponse(
                    status_code=400,
                    content={
                        "status": "error",
                        "message": "No speech detected in the audio. Please try speaking more clearly or check your microphone."
                    }
                )
            
            logger.info("Transcription completed: %s", transcript.text)
            
            # Clean up the temporary file
            os.unlink(temp_file.name)
            
            # Get words with timing information
            words = []
            if hasattr(transcript, 'words'):
                words = transcript.words
            elif hasattr(transcript, 'utterances'):
                for utterance in transcript.utterances:
                    if hasattr(utterance, 'words'):
                        words.extend(utterance.words)
            
            logger.info(f"Words with timing: {words}")  # Debug log
            
            # Convert transcribed words to musical notes with timing
            notes = text_to_notes(words)
            logger.info(f"Detected notes: {notes}")  # Debug log
            
            # Convert notes to a format suitable for JSON response
            notes_data = [
                {
                    "note": note.note,
                    "start": note.start,
                    "end": note.end,
                    "duration": note.end - note.start
                }
                for note in notes
            ]
            
            logger.info(f"Final notes data: {notes_data}")  # Debug log
            
            response_data = {
                "text": transcript.text,
                "notes": notes_data,
                "status": "success"
            }
            
            if not notes_data:
                response_data["message"] = "No musical notes detected in the speech. Try saying note names like 'A', 'B', 'C' or 'do', 're', 'mi'."
            
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