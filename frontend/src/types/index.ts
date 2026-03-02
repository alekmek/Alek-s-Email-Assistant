export type ConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export type VoiceState = 'idle' | 'listening' | 'processing' | 'thinking' | 'speaking';

export interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ConversationMessage {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface EmailSender {
  name: string;
  email: string;
}

export interface EmailData {
  id: string;
  from: EmailSender[] | string;  // Can be array of {name, email} or string
  to?: EmailSender[] | string;
  subject: string;
  snippet?: string;
  date?: number | string;  // Unix timestamp or date string
  unread?: boolean;
  hasAttachments?: boolean;
  thread_id?: string;
  attachments?: Array<{ filename?: string; contentType?: string; id?: string }>;
}

export interface TranscriptEntry {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  timestamp: Date;
  emails?: EmailData[]; // Structured email data for display
  isAttachmentContent?: boolean; // Flag for attachment-related content
  operation?: {
    tool: string;
    label: string;
    status: 'running' | 'complete';
    estimatedSeconds: number;
    startedAt: string;
    elapsedSeconds?: number;
  };
}

export interface AudioConfig {
  sampleRate: number;
  channels: number;
  bitsPerSample: number;
}

export interface WebSocketMessage {
  type: string;
  data?: unknown;
}
