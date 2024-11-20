import { useState, useRef } from 'react'

const LoadingSpinner = () => (
  <div className="flex justify-center items-center">
    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
  </div>
)

const NoteDisplay = ({ note, duration }) => {
  // Calculate the width based on duration (1 second = 100px)
  const width = Math.max(64, duration * 100)
  
  return (
    <div 
      className="flex flex-col items-center justify-center h-24 bg-white border-2 border-gray-300 rounded-lg mx-1 transition-all"
      style={{ width: `${width}px` }}
    >
      <span className="text-2xl font-bold text-gray-800">{note}</span>
      <div className="mt-2 w-8 h-1 bg-gray-800 rounded"></div>
      <span className="text-sm text-gray-500 mt-1">{duration.toFixed(2)}s</span>
    </div>
  )
}

function App() {
  const [isRecording, setIsRecording] = useState(false)
  const [audioBlob, setAudioBlob] = useState(null)
  const [transcribedText, setTranscribedText] = useState('')
  const [musicalNotes, setMusicalNotes] = useState([])
  const [isProcessing, setIsProcessing] = useState(false)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const mediaRecorderRef = useRef(null)
  const chunksRef = useRef([])

  const startRecording = async () => {
    try {
      setError(null)
      setMessage(null)
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaRecorderRef.current = new MediaRecorder(stream)
      
      mediaRecorderRef.current.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data)
        }
      }

      mediaRecorderRef.current.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/wav' })
        setAudioBlob(blob)
        chunksRef.current = []
      }

      mediaRecorderRef.current.start()
      setIsRecording(true)
      setTranscribedText('')
      setMusicalNotes([])
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
    formData.append('file', audioBlob, 'recording.wav')

    try {
      console.log('Sending request to backend...')
      const response = await fetch('http://localhost:8000/upload-audio', {
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
              Speech to Musical Notes
            </h2>
            
            <div className="text-center mb-6 text-gray-600">
              Speak musical note names (A, B, C, etc.) or solfège (do, re, mi) to convert them to notation
            </div>

            <div className="flex justify-center space-x-4 mb-8">
              {!isRecording ? (
                <button
                  onClick={startRecording}
                  className="bg-blue-500 text-white px-6 py-3 rounded-lg hover:bg-green-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed font-medium"
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
                <div className="flex flex-wrap justify-center gap-2">
                  {musicalNotes.map((note, index) => (
                    <NoteDisplay 
                      key={index} 
                      note={note.note} 
                      duration={note.duration}
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
