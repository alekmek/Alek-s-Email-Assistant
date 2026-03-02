import type { VoiceState } from '../../types';

interface MicrophoneButtonProps {
  isEnabled: boolean;
  onClick: () => void;
  voiceState: VoiceState;
}

export function MicrophoneButton({ isEnabled, onClick, voiceState }: MicrophoneButtonProps) {
  const isProcessing = voiceState === 'processing';
  const isSpeaking = voiceState === 'speaking';

  return (
    <div className="relative">
      {/* Pulse rings when active */}
      {isEnabled && (
        <>
          <div className="absolute inset-0 rounded-full bg-indigo-500/30 pulse-ring" />
          <div
            className="absolute inset-0 rounded-full bg-indigo-500/20 pulse-ring"
            style={{ animationDelay: '0.5s' }}
          />
        </>
      )}

      <button
        onClick={onClick}
        disabled={isProcessing || isSpeaking}
        className={`
          relative w-24 h-24 rounded-full flex items-center justify-center
          transition-all duration-300 ease-out
          ${
            isEnabled
              ? 'bg-red-500 hover:bg-red-600 scale-110'
              : 'bg-indigo-600 hover:bg-indigo-700 hover:scale-105'
          }
          ${isProcessing ? 'bg-yellow-500 cursor-wait' : ''}
          ${isSpeaking ? 'bg-green-500 cursor-not-allowed' : ''}
          disabled:opacity-70
          shadow-lg shadow-indigo-500/25
        `}
        aria-label={isEnabled ? 'Stop recording' : 'Start recording'}
      >
        {isProcessing ? (
          // Processing spinner
          <svg
            className="w-10 h-10 animate-spin text-white"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        ) : isSpeaking ? (
          // Speaking wave icon
          <svg className="w-10 h-10 text-white" fill="currentColor" viewBox="0 0 24 24">
            <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z" />
          </svg>
        ) : isEnabled ? (
          // Stop icon
          <svg className="w-10 h-10 text-white" fill="currentColor" viewBox="0 0 24 24">
            <rect x="6" y="6" width="12" height="12" rx="2" />
          </svg>
        ) : (
          // Microphone icon
          <svg className="w-10 h-10 text-white" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm-1 1.93c-3.94-.49-7-3.85-7-7.93h2c0 3.31 2.69 6 6 6s6-2.69 6-6h2c0 4.08-3.06 7.44-7 7.93V19h4v2H8v-2h4v-3.07z" />
          </svg>
        )}
      </button>
    </div>
  );
}
