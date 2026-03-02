import { useCallback, useEffect, useRef } from 'react';
import { useVoiceStore } from '../store';
import { conversationApi } from '../services/api';

const WEBSOCKET_URL = 'ws://localhost:8000/ws/audio';
const SAMPLE_RATE = 16000;

// WebSocket reconnection and heartbeat configuration
const WS_CONFIG = {
  maxReconnectAttempts: 5,
  initialReconnectDelay: 1000,
  maxReconnectDelay: 30000,
  heartbeatInterval: 30000,
  heartbeatTimeout: 10000,
};

const TOOL_LABELS: Record<string, string> = {
  list_unread: 'Checking unread',
  search_emails: 'Searching inbox',
  count_emails: 'Counting emails',
  get_email_breakdown: 'Analyzing categories',
  get_email_details: 'Reading email',
  send_reply: 'Preparing reply',
  mark_as_read: 'Updating email',
  read_attachment: 'Analyzing attachment',
};

// Global debug function exposed on window for cross-module debugging
declare global {
  interface Window {
    wsDebug: (msg: string) => void;
  }
}
window.wsDebug = (msg: string) => {
  const timestamp = new Date().toLocaleTimeString();
  console.log(`[WS DEBUG ${timestamp}] ${msg}`);
};

export function useVoiceSession() {
  const wsRef = useRef<WebSocket | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const processorRef = useRef<ScriptProcessorNode | null>(null);

  const {
    connectionStatus,
    setConnectionStatus,
    voiceState,
    setVoiceState,
    isMicEnabled,
    setMicEnabled,
    setInputLevel,
    setError,
    addTranscriptEntry,
    appendToTranscriptEntry,
    setToolActivity,
    attachEmailsToLastEntry,
  } = useVoiceStore();

  // Track current streaming entry for accumulation
  const currentStreamingRef = useRef<{ role: 'user' | 'assistant'; id: string; savedToDb: boolean } | null>(null);
  const toolEntryRef = useRef<Record<string, { entryId: string; startedAtMs: number; startedAtIso: string; label: string }>>({});
  const streamingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Track accumulated text for DB save
  const accumulatedTextRef = useRef<string>('');

  // Track ALL active audio sources for interruption (multiple chunks can arrive)
  const activeAudioSourcesRef = useRef<Set<{ source: AudioBufferSourceNode; context: AudioContext }>>(new Set());
  // Flag to ignore incoming audio after interrupt until next interaction
  const ignoreAudioRef = useRef<boolean>(false);
  // Flag to stop sending audio (set when stopMicrophone is called)
  const stopSendingAudioRef = useRef<boolean>(false);

  // Reconnection and heartbeat management
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const heartbeatIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const heartbeatTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef<number>(0);
  const isManualDisconnectRef = useRef<boolean>(false);

  // Safety timeout to recover from stuck "thinking" state
  const thinkingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Connect to WebSocket
  const connect = useCallback(async () => {
    window.wsDebug('connect() called');
    window.wsDebug(`wsRef.current: ${wsRef.current}, readyState: ${wsRef.current?.readyState}`);

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      window.wsDebug('Already connected, returning');
      return;
    }

    window.wsDebug('Setting status to connecting');
    setConnectionStatus('connecting');
    setError(null);

    let eventFired = false;

    // Inline message handler to avoid closure issues
    const handleIncomingMessage = (message: { type: string; data?: unknown }) => {
      window.wsDebug(`Handling message type: ${message.type}`);
      switch (message.type) {
        case 'transcript':
          if (message.data && typeof message.data === 'object') {
            const data = message.data as { role: string; text: string };
            const role = data.role as 'user' | 'assistant';
            const text = data.text;

            // Clear any existing timeout
            if (streamingTimeoutRef.current) {
              clearTimeout(streamingTimeoutRef.current);
            }

            // Check if we should append to existing entry or create new one
            if (currentStreamingRef.current && currentStreamingRef.current.role === role) {
              // Same role - append to existing entry
              appendToTranscriptEntry(currentStreamingRef.current.id, text);
              // Accumulate text for DB save
              accumulatedTextRef.current += text;
            } else {
              // Different role or no current streaming - create new entry
              const id = addTranscriptEntry({ role, text });
              currentStreamingRef.current = { role, id, savedToDb: false };
              accumulatedTextRef.current = text;
            }

            // Set timeout to save to DB and clear streaming state after 1 second of no new text
            streamingTimeoutRef.current = setTimeout(async () => {
              // Save to database if we have a conversation and haven't saved yet
              const conversationId = useVoiceStore.getState().currentConversationId;
              if (conversationId && currentStreamingRef.current && !currentStreamingRef.current.savedToDb) {
                try {
                  await conversationApi.addMessage(
                    conversationId,
                    currentStreamingRef.current.role,
                    accumulatedTextRef.current
                  );
                  currentStreamingRef.current.savedToDb = true;
                  window.wsDebug(`Saved ${currentStreamingRef.current.role} message to DB`);
                } catch (err) {
                  window.wsDebug(`Failed to save message to DB: ${err}`);
                }
              }
              currentStreamingRef.current = null;
              accumulatedTextRef.current = '';
            }, 1000);
          }
          break;
        case 'state':
          if (message.data && typeof message.data === 'string') {
            const newState = message.data as 'idle' | 'listening' | 'processing' | 'thinking' | 'speaking';
            window.wsDebug(`State change from backend: ${newState}`);

            // Clear thinking timeout when we get a response
            if ((newState === 'speaking' || newState === 'idle') && thinkingTimeoutRef.current) {
              clearTimeout(thinkingTimeoutRef.current);
              thinkingTimeoutRef.current = null;
            }

            // If transitioning to idle but audio is still playing, defer the state change
            // The audio onended handler will set idle when audio truly finishes
            if (newState === 'idle' && activeAudioSourcesRef.current.size > 0) {
              window.wsDebug(`Deferring idle state - ${activeAudioSourcesRef.current.size} audio sources still playing`);
              // Don't set idle yet, let audio onended handle it
            } else {
              setVoiceState(newState);
            }
          }
          break;
        case 'audio_received':
          break;
        case 'error':
          if (message.data && typeof message.data === 'string') {
            setError(message.data);
          }
          break;
        case 'tool_activity':
          if (message.data && typeof message.data === 'object') {
            const data = message.data as { tool: string; status: 'running' | 'complete' };
            setToolActivity(data.tool, data.status);

            const label = TOOL_LABELS[data.tool] ?? data.tool;
            const storeState = useVoiceStore.getState();

            if (data.status === 'running') {
              const startedAtMs = Date.now();
              const startedAtIso = new Date(startedAtMs).toISOString();
              const estimatedSeconds = storeState.toolEstimates[data.tool] ?? 3;

              let entryId: string | null =
                currentStreamingRef.current?.role === 'assistant'
                  ? currentStreamingRef.current.id
                  : storeState.attachOperationToLastAssistant({
                      tool: data.tool,
                      label,
                      status: 'running',
                      estimatedSeconds,
                      startedAt: startedAtIso,
                    });

              if (entryId) {
                storeState.setEntryOperation(entryId, {
                  tool: data.tool,
                  label,
                  status: 'running',
                  estimatedSeconds,
                  startedAt: startedAtIso,
                });
                toolEntryRef.current[data.tool] = { entryId, startedAtMs, startedAtIso, label };
              }
            } else {
              const tracked = toolEntryRef.current[data.tool];
              if (tracked) {
                const elapsedSeconds = Math.max(0.1, (Date.now() - tracked.startedAtMs) / 1000);
                const estimatedSeconds = useVoiceStore.getState().toolEstimates[data.tool] ?? elapsedSeconds;
                storeState.setEntryOperation(tracked.entryId, {
                  tool: data.tool,
                  label: tracked.label,
                  status: 'complete',
                  estimatedSeconds,
                  startedAt: tracked.startedAtIso,
                  elapsedSeconds,
                });
                delete toolEntryRef.current[data.tool];
              }
            }
          }
          break;
        case 'email_data':
          if (message.data && Array.isArray(message.data)) {
            window.wsDebug(`Received ${message.data.length} emails for display`);
            attachEmailsToLastEntry(message.data);
          }
          break;
        case 'pong':
          // Clear heartbeat timeout - server responded
          if (heartbeatTimeoutRef.current) {
            clearTimeout(heartbeatTimeoutRef.current);
            heartbeatTimeoutRef.current = null;
          }
          window.wsDebug('Received pong from server');
          break;
        default:
          window.wsDebug(`Unknown message type: ${message.type}`);
      }
    };

    // Inline audio player to avoid closure issues
    const playIncomingAudio = async (blob: Blob) => {
      // Skip audio if we've been interrupted
      if (ignoreAudioRef.current) {
        window.wsDebug('Ignoring audio - interrupted');
        return;
      }

      // Skip very small blobs that are likely incomplete/corrupt
      if (blob.size < 100) {
        window.wsDebug(`Skipping tiny audio blob: ${blob.size} bytes`);
        return;
      }

      let audioContext: AudioContext | null = null;
      try {
        window.wsDebug(`Playing audio blob of size ${blob.size}`);
        const arrayBuffer = await blob.arrayBuffer();
        audioContext = new AudioContext();
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

        const source = audioContext.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(audioContext.destination);
        source.start();

        // Track this audio source for potential interruption
        const audioEntry = { source, context: audioContext };
        activeAudioSourcesRef.current.add(audioEntry);

        setVoiceState('speaking');

        source.onended = () => {
          // Remove from active sources
          activeAudioSourcesRef.current.delete(audioEntry);
          audioContext?.close();
          // Only set idle if no more audio is playing and not ignored
          if (activeAudioSourcesRef.current.size === 0 && !ignoreAudioRef.current) {
            setVoiceState('idle');
          }
        };
      } catch (err) {
        window.wsDebug(`Failed to play audio: ${err}`);
        // Always close the audio context on error to prevent memory leaks
        if (audioContext) {
          try {
            audioContext.close();
          } catch (closeErr) {
            // Ignore close errors
          }
        }
      }
    };

    try {
      window.wsDebug(`Creating WebSocket to ${WEBSOCKET_URL}`);
      const ws = new WebSocket(WEBSOCKET_URL);
      window.wsDebug(`WebSocket created, readyState: ${ws.readyState} (0=CONNECTING, 1=OPEN)`);

      // Timeout to detect if no events fire
      const timeout = setTimeout(() => {
        if (!eventFired) {
          window.wsDebug('TIMEOUT: No WebSocket events fired in 5 seconds!');
          window.wsDebug(`Current readyState: ${ws.readyState}`);
          setError('Connection timeout - no response from server');
          setConnectionStatus('error');
        }
      }, 5000);

      ws.onopen = () => {
        eventFired = true;
        clearTimeout(timeout);
        window.wsDebug('ONOPEN fired - connection successful!');
        setConnectionStatus('connected');
        setVoiceState('idle');
        setError(null);

        // Reset reconnect attempts on successful connection
        reconnectAttemptsRef.current = 0;
        isManualDisconnectRef.current = false;

        // Start heartbeat
        const startHeartbeat = () => {
          heartbeatIntervalRef.current = setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({ type: 'ping' }));
              window.wsDebug('Sent ping to server');

              // Set timeout for pong response
              heartbeatTimeoutRef.current = setTimeout(() => {
                window.wsDebug('Heartbeat timeout - no pong received');
                ws.close();
              }, WS_CONFIG.heartbeatTimeout);
            }
          }, WS_CONFIG.heartbeatInterval);
        };
        startHeartbeat();
      };

      ws.onmessage = async (event) => {
        window.wsDebug(`ONMESSAGE: ${event.data instanceof Blob ? `Blob(${event.data.size})` : event.data}`);
        try {
          if (event.data instanceof Blob) {
            await playIncomingAudio(event.data);
          } else {
            const message = JSON.parse(event.data);
            handleIncomingMessage(message);
          }
        } catch (err) {
          window.wsDebug(`Error processing message: ${err}`);
        }
      };

      ws.onerror = (error) => {
        eventFired = true;
        clearTimeout(timeout);
        window.wsDebug('ONERROR fired');
        window.wsDebug(`Error event: ${JSON.stringify(error, Object.getOwnPropertyNames(error))}`);
        setError('Connection error');
        setConnectionStatus('error');
      };

      ws.onclose = (event) => {
        eventFired = true;
        clearTimeout(timeout);
        window.wsDebug(`ONCLOSE: code=${event.code}, reason=${event.reason}, clean=${event.wasClean}`);

        // Clean up heartbeat
        if (heartbeatIntervalRef.current) {
          clearInterval(heartbeatIntervalRef.current);
          heartbeatIntervalRef.current = null;
        }
        if (heartbeatTimeoutRef.current) {
          clearTimeout(heartbeatTimeoutRef.current);
          heartbeatTimeoutRef.current = null;
        }

        // Reset UI state
        setVoiceState('idle');
        setMicEnabled(false);
        setInputLevel(0);
        toolEntryRef.current = {};

        // Attempt reconnect if not a clean/manual close
        if (!event.wasClean && !isManualDisconnectRef.current && reconnectAttemptsRef.current < WS_CONFIG.maxReconnectAttempts) {
          const delay = Math.min(
            WS_CONFIG.initialReconnectDelay * Math.pow(2, reconnectAttemptsRef.current),
            WS_CONFIG.maxReconnectDelay
          );

          setConnectionStatus('connecting');
          setError(`Connection lost. Reconnecting in ${Math.round(delay / 1000)}s...`);
          window.wsDebug(`Scheduling reconnect attempt ${reconnectAttemptsRef.current + 1} in ${delay}ms`);

          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectAttemptsRef.current++;
            wsRef.current = null;
            connect();
          }, delay);
        } else if (reconnectAttemptsRef.current >= WS_CONFIG.maxReconnectAttempts) {
          setConnectionStatus('error');
          setError('Connection failed after multiple attempts. Please try again.');
        } else {
          setConnectionStatus('disconnected');
        }
      };

      wsRef.current = ws;
      window.wsDebug('WebSocket stored in ref');
    } catch (err) {
      window.wsDebug(`EXCEPTION: ${err}`);
      setError('Failed to connect');
      setConnectionStatus('error');
    }
  }, [setConnectionStatus, setVoiceState, setError, addTranscriptEntry, appendToTranscriptEntry, setToolActivity, attachEmailsToLastEntry]);

  // Stop microphone - defined early so other functions can reference it
  const stopMicrophone = useCallback(() => {
    window.wsDebug('=== stopMicrophone called ===');

    // Immediately stop sending audio
    stopSendingAudioRef.current = true;

    // Send end_of_speech signal to backend to finalize transcription
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: 'end_of_speech' }));
        window.wsDebug('Sent end_of_speech signal');
      } catch (e) {
        window.wsDebug(`Failed to send end_of_speech: ${e}`);
      }
    }

    // Stop the audio processor first to prevent any more audio from being sent
    if (processorRef.current) {
      window.wsDebug('Disconnecting audio processor');
      processorRef.current.onaudioprocess = null; // Remove handler first
      processorRef.current.disconnect();
      processorRef.current = null;
    }

    if (mediaStreamRef.current) {
      window.wsDebug(`Stopping ${mediaStreamRef.current.getTracks().length} media tracks`);
      mediaStreamRef.current.getTracks().forEach((track) => {
        track.stop();
        window.wsDebug(`Track ${track.kind} stopped: ${track.readyState}`);
      });
      mediaStreamRef.current = null;
    }

    if (audioContextRef.current) {
      window.wsDebug(`Closing audio context (state: ${audioContextRef.current.state})`);
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    setMicEnabled(false);
    setInputLevel(0);
    setVoiceState('thinking'); // Show thinking state until assistant speaks

    // Set a safety timeout to recover from stuck thinking state (60 seconds)
    if (thinkingTimeoutRef.current) {
      clearTimeout(thinkingTimeoutRef.current);
    }
    thinkingTimeoutRef.current = setTimeout(() => {
      window.wsDebug('Thinking timeout - resetting to idle');
      setVoiceState('idle');
    }, 60000);

    window.wsDebug('=== stopMicrophone complete ===');
  }, [setMicEnabled, setInputLevel, setVoiceState]);

  // Disconnect from WebSocket
  const disconnect = useCallback(() => {
    // Mark as manual disconnect to prevent auto-reconnect
    isManualDisconnectRef.current = true;
    reconnectAttemptsRef.current = 0;

    // Clear any pending reconnect
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }

    // Clear heartbeat timers
    if (heartbeatIntervalRef.current) {
      clearInterval(heartbeatIntervalRef.current);
      heartbeatIntervalRef.current = null;
    }
    if (heartbeatTimeoutRef.current) {
      clearTimeout(heartbeatTimeoutRef.current);
      heartbeatTimeoutRef.current = null;
    }

    // Inline cleanup to avoid closure issues
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setConnectionStatus('disconnected');
    setVoiceState('idle');
    setMicEnabled(false);
    setInputLevel(0);
    setError(null);
  }, [setConnectionStatus, setVoiceState, setMicEnabled, setInputLevel, setError]);

  // Start microphone
  const startMicrophone = useCallback(async () => {
    // Reset flags for new interaction
    ignoreAudioRef.current = false;
    stopSendingAudioRef.current = false;

    // Auto-create a conversation if one doesn't exist
    const conversationId = useVoiceStore.getState().currentConversationId;
    if (!conversationId) {
      try {
        const conversation = await conversationApi.createConversation();
        useVoiceStore.getState().addConversation(conversation);
        useVoiceStore.getState().setCurrentConversationId(conversation.id);
        window.wsDebug(`Auto-created conversation: ${conversation.id}`);
      } catch (err) {
        window.wsDebug(`Failed to auto-create conversation: ${err}`);
      }
    }

    // Signal backend to start listening (push-to-talk)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: 'start_listening' }));
        window.wsDebug('Sent start_listening signal');
      } catch (e) {
        window.wsDebug(`Failed to send start_listening: ${e}`);
      }
    }

    try {
      // Request microphone access
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      mediaStreamRef.current = stream;

      // Create audio context
      const audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
      audioContextRef.current = audioContext;

      // Create audio source
      const source = audioContext.createMediaStreamSource(stream);

      // Create processor for sending audio
      const processor = audioContext.createScriptProcessor(4096, 1, 1);
      processorRef.current = processor;

      processor.onaudioprocess = (event) => {
        // Don't send audio if we've been told to stop
        if (stopSendingAudioRef.current) {
          return;
        }

        if (wsRef.current?.readyState === WebSocket.OPEN) {
          const inputData = event.inputBuffer.getChannelData(0);

          // Calculate input level for visualization
          const level = Math.sqrt(
            inputData.reduce((sum, val) => sum + val * val, 0) / inputData.length
          );
          setInputLevel(Math.min(level * 3, 1));

          // Convert to Int16 and send
          const int16Data = new Int16Array(inputData.length);
          for (let i = 0; i < inputData.length; i++) {
            const s = Math.max(-1, Math.min(1, inputData[i]));
            int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
          }

          wsRef.current.send(int16Data.buffer);
        }
      };

      source.connect(processor);
      processor.connect(audioContext.destination);

      setMicEnabled(true);
      setVoiceState('listening');
    } catch (err) {
      console.error('Failed to start microphone:', err);
      setError('Failed to access microphone');
    }
  }, [setMicEnabled, setVoiceState, setInputLevel, setError]);

  // Toggle microphone
  const toggleMicrophone = useCallback(() => {
    window.wsDebug(`=== toggleMicrophone called: isMicEnabled=${isMicEnabled} ===`);
    if (isMicEnabled) {
      stopMicrophone();
    } else {
      startMicrophone();
    }
  }, [isMicEnabled, startMicrophone, stopMicrophone]);

  // Interrupt/stop the assistant speaking
  const interruptSpeaking = useCallback(() => {
    window.wsDebug('Interrupting speech');

    // Set flag to ignore any incoming audio
    ignoreAudioRef.current = true;

    // Stop ALL active audio playback
    activeAudioSourcesRef.current.forEach((audioEntry) => {
      try {
        audioEntry.source.stop();
        audioEntry.context.close();
      } catch (e) {
        window.wsDebug(`Error stopping audio: ${e}`);
      }
    });
    activeAudioSourcesRef.current.clear();

    // Send interrupt signal to backend
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      try {
        wsRef.current.send(JSON.stringify({ type: 'interrupt' }));
        window.wsDebug('Sent interrupt signal');
      } catch (e) {
        window.wsDebug(`Failed to send interrupt: ${e}`);
      }
    }

    // Clear any active tool activity
    useVoiceStore.getState().clearToolActivity();
    toolEntryRef.current = {};

    setVoiceState('idle');
  }, [setVoiceState]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      isManualDisconnectRef.current = true;
      stopMicrophone();

      // Clear all timers
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (heartbeatIntervalRef.current) {
        clearInterval(heartbeatIntervalRef.current);
      }
      if (heartbeatTimeoutRef.current) {
        clearTimeout(heartbeatTimeoutRef.current);
      }

      if (wsRef.current) {
        wsRef.current.close();
      }
      toolEntryRef.current = {};
    };
  }, [stopMicrophone]);

  return {
    // State
    connectionStatus,
    voiceState,
    isMicEnabled,

    // Actions
    connect,
    disconnect,
    toggleMicrophone,
    startMicrophone,
    stopMicrophone,
    interruptSpeaking,
  };
}
