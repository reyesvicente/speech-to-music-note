import { useState, useRef, useCallback, memo } from 'react'

const LoadingSpinner = () => (
  <div className="flex justify-center items-center">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
  </div>
)

// Base frequencies for middle octave (4)
const NOTE_FREQUENCIES = {
  'C': 261.63,
  'C#': 277.18,
  'D': 293.66,
  'D#': 311.13,
  'E': 329.63,
  'F': 349.23,
  'F#': 369.99,
  'G': 392.00,
  'G#': 415.30,
  'A': 440.00,
  'A#': 466.16,
  'B': 493.88
}

const getFrequencyWithOctave = (note, octave) => {
  const baseFreq = NOTE_FREQUENCIES[note];
  if (!baseFreq) return 440; // Default to A4 if note not found
  
  // Adjust frequency based on octave difference from middle octave (4)
  return baseFreq * Math.pow(2, octave - 4);
}

const debounce = (func, wait) => {
  let timeout;
  return function(...args) {
    const context = this;
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => {
      timeout = null;
      func.apply(context, args);
    }, wait);
  };
};

const NoteDisplay = memo(({ note, octave, duration, isPlaying }) => (
  <div 
    className={`p-3 rounded-lg shadow-sm transition-colors duration-200 ${
      isPlaying ? 'bg-blue-100' : 'bg-white'
    }`}
  >
    <div className="text-lg font-semibold">{note}{octave}</div>
    <div className="text-xs text-gray-500">
      {(duration * 1000).toFixed(0)}ms
    </div>
  </div>
))

function App() {
  const [isRecording, setIsRecording] = useState(false)
  const [audioBlob, setAudioBlob] = useState(null)
  const [transcribedText, setTranscribedText] = useState('')
  const [musicalNotes, setMusicalNotes] = useState([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentNoteIndex, setCurrentNoteIndex] = useState(-1)
  const [fileName, setFileName] = useState('')
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])
  const audioContextRef = useRef(null)
  const fileInputRef = useRef(null)

  // Accepted audio file types
  const acceptedFileTypes = [
    'audio/wav',
    'audio/mp3',
    'audio/mpeg',
    'audio/ogg',
    'audio/webm',
    'audio/x-m4a'
  ]

  const handleFileUpload = (event) => {
    const file = event.target.files[0]
    if (!file) return

    // Check file type
    if (!acceptedFileTypes.includes(file.type)) {
      setError('Invalid file type. Please upload an audio file (WAV, MP3, OGG, etc.)')
      return
    }

    // Check file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      setError('File is too large. Maximum size is 10MB.')
      return
    }

    setFileName(file.name)
    setAudioBlob(file)
    setError(null)
    setMessage(null)
    setTranscribedText('')
    setMusicalNotes([])
    setCurrentNoteIndex(-1)
  }

  const triggerFileInput = () => {
    fileInputRef.current?.click()
  }

  // Debounced version of setCurrentNoteIndex to reduce renders
  const debouncedSetCurrentNote = useCallback(
    debounce((index) => setCurrentNoteIndex(index), 50),
    []
  )

  // Initialize audio context on first user interaction
  const initAudioContext = () => {
    if (!audioContextRef.current) {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)()
    }
    return audioContextRef.current
  }

  const playNote = useCallback(async (note, octave, duration) => {
    const audioContext = initAudioContext()
    const oscillator = audioContext.createOscillator()
    const gainNode = audioContext.createGain()

    // Use the new frequency calculation function
    const frequency = getFrequencyWithOctave(note, octave)
    oscillator.type = 'sine'
    oscillator.frequency.setValueAtTime(frequency, audioContext.currentTime)

    gainNode.gain.setValueAtTime(0, audioContext.currentTime)
    gainNode.gain.linearRampToValueAtTime(0.3, audioContext.currentTime + 0.05)
    gainNode.gain.linearRampToValueAtTime(0, audioContext.currentTime + duration)

    oscillator.connect(gainNode)
    gainNode.connect(audioContext.destination)

    oscillator.start(audioContext.currentTime)
    oscillator.stop(audioContext.currentTime + duration)

    return new Promise(resolve => {
      setTimeout(resolve, duration * 1000)
    })
  }, [])

  const playAllNotes = useCallback(async () => {
    if (isPlaying || !musicalNotes.length) return

    setIsPlaying(true)
    
    for (let i = 0; i < musicalNotes.length; i++) {
      debouncedSetCurrentNote(i)
      const { note, octave, duration } = musicalNotes[i]
      await playNote(note, octave, duration)
    }

    setIsPlaying(false)
    debouncedSetCurrentNote(-1)
  }, [musicalNotes, isPlaying, playNote])

  const startRecording = async () => {
    try {
      setError(null)
      setMessage(null)
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaRecorderRef.current = new MediaRecorder(stream)
      
      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: 'audio/wav' })
        setAudioBlob(blob)
        audioChunksRef.current = []
      }

      mediaRecorderRef.current.start()
      setIsRecording(true)
      setTranscribedText('')
      setMusicalNotes([])
      setCurrentNoteIndex(-1)
    } catch (error) {
      console.error('Error accessing microphone:', error)
      setError('Error accessing microphone. Please ensure you have granted microphone permissions.')
    }
  }

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop()
      setIsRecording(false)
      mediaRecorderRef.current.stream.getTracks().forEach(track => track.stop())
    }
  }

  const uploadAudio = async () => {
    if (!audioBlob) return

    setIsProcessing(true)
    setError(null)

    const formData = new FormData()
    formData.append('file', audioBlob, fileName || 'recording.wav')

    try {
      console.log('Sending request to backend...')
      const response = await fetch('https://speech-to-music-note.onrender.com/upload-audio', {
        method: 'POST',
        body: formData,
      })

      const data = await response.json()
      console.log('Received response:', data)

      if (!response.ok) {
        throw new Error(data.message || `HTTP error! status: ${response.status}`)
      }

      if (data.status === 'success') {
        setTranscribedText(data.text || '')
        setMusicalNotes(data.notes || [])
        if (data.message) {
          setMessage(data.message)
        } else {
          setMessage(null)
        }
      } else {
        setError(data.message || 'An error occurred while processing the audio')
      }
    } catch (error) {
      console.error('Error uploading audio:', error)
      setError('Error processing audio. Please try again.')
    } finally {
      setIsProcessing(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center">
      <div className="w-full max-w-4xl mx-auto p-6">
        <div className="bg-white rounded-2xl shadow-xl p-8 md:p-12">
          <div className="max-w-3xl mx-auto">
            <h2 className="text-3xl font-bold mb-8 text-center text-gray-900">
              Speech to Musical Notation
            </h2>
            
            <div className="text-center mb-6 text-gray-600">
              Sing a melody and we'll detect the musical notes! Try singing individual notes or a simple tune.
            </div>
            
            <div className="text-center mb-6 text-gray-600">
              The backend sleeps when it detects no activity for 50 seconds. Please be patient.
            </div>

            {/* File Upload Section */}
            <div className="mb-8">
              <div className="flex flex-col items-center justify-center w-full">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept={acceptedFileTypes.join(',')}
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <button
                  onClick={triggerFileInput}
                  className="bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium mb-2"
                  disabled={isProcessing || isRecording}
                >
                  Upload Audio File
                </button>
                <p className="text-sm text-gray-500 text-center">
                  Accepted formats: WAV, MP3, OGG, WebM, M4A (Max 10MB)
                </p>
                {fileName && (
                  <p className="mt-2 text-sm text-gray-700">
                    Selected file: {fileName}
                  </p>
                )}
              </div>
            </div>

            {/* Divider */}
            <div className="relative mb-8">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-gray-200"></div>
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-white text-gray-500">OR</span>
              </div>
            </div>

            <div className="flex justify-center space-x-4 mb-8">
              {!isRecording ? (
                <button
                  onClick={startRecording}
                  className="bg-green-500 text-white px-6 py-3 rounded-lg hover:bg-green-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
                  disabled={isProcessing}
                >
                  Start Recording
                </button>
              ) : (
                <button
                  onClick={stopRecording}
                  className="bg-red-500 text-white px-6 py-3 rounded-lg hover:bg-red-600 transition-colors font-medium"
                >
                  Stop Recording
                </button>
              )}
              
              {audioBlob && !isRecording && (
                <button
                  onClick={uploadAudio}
                  className="bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-blue-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 font-medium"
                  disabled={isProcessing}
                >
                  {isProcessing ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Processing...
                    </>
                  ) : (
                    'Process Audio'
                  )}
                </button>
              )}

              {musicalNotes.length > 0 && !isRecording && !isProcessing && (
                <button
                  onClick={playAllNotes}
                  className={`bg-purple-500 text-white px-6 py-3 rounded-lg hover:bg-purple-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium flex items-center gap-2`}
                  disabled={isPlaying}
                >
                  {isPlaying ? (
                    <>
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white"></div>
                      Playing...
                    </>
                  ) : (
                    <>
                      <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z" clipRule="evenodd" />
                      </svg>
                      Play Notes
                    </>
                  )}
                </button>
              )}
            </div>

            {error && (
              <div className="mt-6 p-4 bg-red-100 text-red-700 rounded-lg">
                {error}
              </div>
            )}

            {message && (
              <div className="mt-6 p-4 bg-blue-100 text-blue-700 rounded-lg">
                {message}
              </div>
            )}

            {isProcessing && (
              <div className="mt-8 text-center">
                <LoadingSpinner />
                <p className="mt-2 text-gray-600">Processing your audio...</p>
              </div>
            )}

            {musicalNotes && musicalNotes.length > 0 && (
              <div className="mt-8">
                <h3 className="text-xl font-semibold mb-4">Musical Notes:</h3>
                <div className="flex flex-wrap justify-center gap-4">
                  {musicalNotes.map((note, index) => (
                    <NoteDisplay 
                      key={index} 
                      note={note.note} 
                      octave={note.octave}
                      duration={note.duration}
                      isPlaying={index === currentNoteIndex}
                    />
                  ))}
                </div>
                <div className="mt-4 text-center text-sm text-gray-500">
                  Note: Width represents duration (1 second = 100px)
                </div>
              </div>
            )}

            {transcribedText && (
              <div className="mt-8">
                <h3 className="text-xl font-semibold mb-2">Transcribed Text:</h3>
                <p className="p-4 bg-gray-50 rounded-lg">{transcribedText}</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default App
