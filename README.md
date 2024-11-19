# Speech to Musical Notes Converter

This application converts spoken words into musical notes using FastAPI, React, and AssemblyAI.

## Prerequisites

- Python 3.8+
- Node.js and npm
- AssemblyAI API key

## Setup

1. Clone the repository
2. Set up the backend:
   ```bash
   # Install Python dependencies
   pip install -r requirements.txt
   
   # Set up your AssemblyAI API key in .env file
   # Replace 'your_api_key_here' with your actual API key
   ```

3. Set up the frontend:
   ```bash
   cd frontend
   npm install
   ```

## Running the Application

1. Start the backend server:
   ```bash
   uvicorn main:app --reload
   ```

2. Start the frontend development server:
   ```bash
   cd frontend
   npm run dev
   ```

3. Open your browser and navigate to the URL shown in the frontend terminal output (usually http://localhost:5173)

## Usage

1. Click the "Start Recording" button to begin recording audio
2. Speak into your microphone
3. Click "Stop Recording" when finished
4. Click "Process Audio" to send the recording to the server
5. The transcribed text will appear below

## Features

- Audio recording using the Web Audio API
- Real-time audio processing
- Speech-to-text conversion using AssemblyAI
- Modern UI with TailwindCSS
