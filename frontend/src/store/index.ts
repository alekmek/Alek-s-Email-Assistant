import { create } from 'zustand';
import type { ConnectionStatus, VoiceState, TranscriptEntry, EmailData, Conversation } from '../types';

interface ToolActivity {
  tool: string;
  status: 'running' | 'complete';
  timestamp: Date;
}

interface VoiceStore {
  // Connection state
  connectionStatus: ConnectionStatus;
  setConnectionStatus: (status: ConnectionStatus) => void;

  // Voice state
  voiceState: VoiceState;
  setVoiceState: (state: VoiceState) => void;

  // Microphone
  isMicEnabled: boolean;
  setMicEnabled: (enabled: boolean) => void;
  toggleMic: () => void;

  // Transcript
  transcript: TranscriptEntry[];
  addTranscriptEntry: (entry: Omit<TranscriptEntry, 'id' | 'timestamp'>) => string; // Returns the new entry's ID
  updateTranscriptEntry: (id: string, text: string) => void;
  appendToTranscriptEntry: (id: string, text: string) => void;
  attachEmailsToLastEntry: (emails: EmailData[]) => void;
  setEntryOperation: (id: string, operation: TranscriptEntry['operation']) => void;
  attachOperationToLastAssistant: (operation: TranscriptEntry['operation']) => string | null;
  clearTranscript: () => void;

  // Tool activity
  activeTools: ToolActivity[];
  toolEstimates: Record<string, number>;
  setToolActivity: (tool: string, status: 'running' | 'complete') => void;
  clearToolActivity: () => void;

  // Audio levels
  inputLevel: number;
  outputLevel: number;
  setInputLevel: (level: number) => void;
  setOutputLevel: (level: number) => void;

  // Error handling
  error: string | null;
  setError: (error: string | null) => void;

  // Conversations
  conversations: Conversation[];
  currentConversationId: string | null;
  isLoadingConversations: boolean;
  setConversations: (conversations: Conversation[]) => void;
  setCurrentConversationId: (id: string | null) => void;
  setLoadingConversations: (loading: boolean) => void;
  addConversation: (conversation: Conversation) => void;
  removeConversation: (id: string) => void;
}

function findLastAssistantIndex(transcript: TranscriptEntry[]): number {
  for (let i = transcript.length - 1; i >= 0; i -= 1) {
    if (transcript[i].role === 'assistant') return i;
  }
  return -1;
}

export const useVoiceStore = create<VoiceStore>((set) => ({
  // Connection state
  connectionStatus: 'disconnected',
  setConnectionStatus: (status) => {
    console.log('=== STORE: setConnectionStatus ===', status);
    set({ connectionStatus: status });
  },

  // Voice state
  voiceState: 'idle',
  setVoiceState: (state) => set({ voiceState: state }),

  // Microphone
  isMicEnabled: false,
  setMicEnabled: (enabled) => set({ isMicEnabled: enabled }),
  toggleMic: () => set((state) => ({ isMicEnabled: !state.isMicEnabled })),

  // Transcript
  transcript: [],
  addTranscriptEntry: (entry) => {
    const id = crypto.randomUUID();
    set((state) => ({
      transcript: [
        ...state.transcript,
        {
          ...entry,
          id,
          timestamp: new Date(),
        },
      ],
    }));
    return id;
  },
  updateTranscriptEntry: (id, text) =>
    set((state) => ({
      transcript: state.transcript.map((entry) =>
        entry.id === id ? { ...entry, text } : entry
      ),
    })),
  appendToTranscriptEntry: (id, text) =>
    set((state) => ({
      transcript: state.transcript.map((entry) => {
        if (entry.id !== id) return entry;
        // Preserve streamed chunk boundaries as-is to avoid mid-word artifacts.
        return { ...entry, text: entry.text + text };
      }),
    })),
  attachEmailsToLastEntry: (emails) =>
    set((state) => {
      // Find the last assistant entry and attach emails to it
      const lastIndex = findLastAssistantIndex(state.transcript);
      if (lastIndex === -1) return state;

      return {
        transcript: state.transcript.map((entry, i) =>
          i === lastIndex ? { ...entry, emails } : entry
        ),
      };
    }),
  setEntryOperation: (id, operation) =>
    set((state) => ({
      transcript: state.transcript.map((entry) =>
        entry.id === id ? { ...entry, operation } : entry
      ),
    })),
  attachOperationToLastAssistant: (operation) => {
    let targetId: string | null = null;
    set((state) => {
      const lastIndex = findLastAssistantIndex(state.transcript);
      if (lastIndex === -1) return state;
      targetId = state.transcript[lastIndex].id;
      return {
        transcript: state.transcript.map((entry, i) =>
          i === lastIndex ? { ...entry, operation } : entry
        ),
      };
    });
    return targetId;
  },
  clearTranscript: () => set({ transcript: [] }),

  // Tool activity
  activeTools: [],
  toolEstimates: {
    list_unread: 2.4,
    search_emails: 3.2,
    count_emails: 2.8,
    get_email_breakdown: 4.8,
    get_email_details: 2.5,
    send_reply: 2.2,
    mark_as_read: 1.1,
    read_attachment: 9.0,
  },
  setToolActivity: (tool, status) => {
    if (status === 'running') {
      set((state) => ({
        activeTools: [...state.activeTools.filter(t => t.tool !== tool), { tool, status, timestamp: new Date() }]
      }));
    } else {
      set((state) => {
        const active = state.activeTools.find((t) => t.tool === tool);
        const elapsedSeconds = active
          ? Math.max(0.2, (Date.now() - active.timestamp.getTime()) / 1000)
          : null;

        const currentEstimate = state.toolEstimates[tool] ?? 3.0;
        const nextEstimate = elapsedSeconds
          ? (currentEstimate * 0.7 + elapsedSeconds * 0.3)
          : currentEstimate;

        return {
          activeTools: state.activeTools.filter((t) => t.tool !== tool),
          toolEstimates: {
            ...state.toolEstimates,
            [tool]: nextEstimate,
          },
        };
      });
    }
  },
  clearToolActivity: () => set({ activeTools: [] }),

  // Audio levels
  inputLevel: 0,
  outputLevel: 0,
  setInputLevel: (level) => set({ inputLevel: level }),
  setOutputLevel: (level) => set({ outputLevel: level }),

  // Error handling
  error: null,
  setError: (error) => set({ error }),

  // Conversations
  conversations: [],
  currentConversationId: null,
  isLoadingConversations: false,
  setConversations: (conversations) => set({ conversations }),
  setCurrentConversationId: (id) => set({ currentConversationId: id }),
  setLoadingConversations: (loading) => set({ isLoadingConversations: loading }),
  addConversation: (conversation) =>
    set((state) => ({
      conversations: [conversation, ...state.conversations],
    })),
  removeConversation: (id) =>
    set((state) => ({
      conversations: state.conversations.filter((c) => c.id !== id),
      currentConversationId:
        state.currentConversationId === id ? null : state.currentConversationId,
    })),
}));
