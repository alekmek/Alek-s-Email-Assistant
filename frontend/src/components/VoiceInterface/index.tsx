import { useEffect, useRef, useCallback, useState, type ReactNode } from 'react';
import { AudioVisualizer } from './AudioVisualizer';
import { useVoiceSession } from '../../hooks/useVoiceSession';
import { useVoiceStore } from '../../store';
import { EmailList } from '../EmailCard';
import { ConversationHistory } from '../ConversationHistory';
import { Settings } from '../Settings';
import type { ConversationMessage, TranscriptEntry } from '../../types';

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

function getToolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool.replace(/_/g, ' ');
}

function formatEta(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return '<1s';
  if (seconds < 10) return `${seconds.toFixed(1)}s`;
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return remainder === 0 ? `${minutes}m` : `${minutes}m ${remainder}s`;
}

function getRemainingSeconds(estimateSeconds: number, startedAtMs: number): number {
  const elapsed = Math.max(0, (Date.now() - startedAtMs) / 1000);
  return Math.max(0.2, estimateSeconds - elapsed);
}

function normalizeTranscriptText(text: string): string {
  if (!text) return '';

  return text
    .replace(/\u00a0/g, ' ')
    .replace(/\r\n/g, '\n')
    .replace(/\s+([.,!?;:])/g, '$1')
    .replace(/([.,!?;:])([A-Za-z])/g, '$1 $2')
    .replace(/(\w)\s+'(s|t|re|ve|ll|d|m)\b/gi, "$1'$2")
    .replace(/(^|\s)'\s+([A-Za-z])/g, "$1'$2")
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/\n[ \t]+/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .replace(/\bThis may take a few seconds\.?\b/gi, '')
    .trim();
}

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const tokenPattern = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|\*\*([^*\n]+)\*\*|`([^`\n]+)`|\*([^*\n]+)\*/;
  const nodes: ReactNode[] = [];
  let rest = text;
  let tokenIndex = 0;

  while (rest.length > 0) {
    const match = rest.match(tokenPattern);
    if (!match || match.index === undefined) {
      nodes.push(rest);
      break;
    }

    if (match.index > 0) {
      nodes.push(rest.slice(0, match.index));
    }

    const token = match[0];
    const key = `${keyPrefix}-token-${tokenIndex++}`;

    if (match[1] && match[2]) {
      nodes.push(
        <a
          key={key}
          href={match[2]}
          target="_blank"
          rel="noreferrer"
          className="text-blue-300 underline decoration-blue-400/60 underline-offset-2 hover:text-blue-200"
        >
          {match[1]}
        </a>
      );
    } else if (match[3]) {
      nodes.push(
        <strong key={key} className="font-semibold text-white">
          {match[3]}
        </strong>
      );
    } else if (match[4]) {
      nodes.push(
        <code key={key} className="rounded bg-slate-900/70 px-1 py-0.5 font-mono text-[0.85em] text-slate-100">
          {match[4]}
        </code>
      );
    } else if (match[5]) {
      nodes.push(
        <em key={key} className="italic text-slate-200">
          {match[5]}
        </em>
      );
    } else {
      nodes.push(token);
    }

    rest = rest.slice(match.index + token.length);
  }

  return nodes;
}

function renderInlineWithBreaks(text: string, keyPrefix: string): ReactNode[] {
  const lines = text.split('\n');
  const nodes: ReactNode[] = [];

  lines.forEach((line, index) => {
    nodes.push(...renderInlineMarkdown(line, `${keyPrefix}-line-${index}`));
    if (index < lines.length - 1) {
      nodes.push(<br key={`${keyPrefix}-br-${index}`} />);
    }
  });

  return nodes;
}

function renderMarkdownText(text: string, entryId: string): ReactNode {
  const normalized = normalizeTranscriptText(text);
  if (!normalized) return null;

  const lines = normalized.split('\n');
  const blocks: ReactNode[] = [];
  let i = 0;
  let blockIndex = 0;

  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }

    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      const content = heading[2];
      const key = `${entryId}-h-${blockIndex++}`;

      if (level === 1) {
        blocks.push(
          <h1 key={key} className="mb-2 text-base font-semibold text-white">
            {renderInlineWithBreaks(content, `${key}-inline`)}
          </h1>
        );
      } else if (level === 2) {
        blocks.push(
          <h2 key={key} className="mb-2 text-[15px] font-semibold text-white">
            {renderInlineWithBreaks(content, `${key}-inline`)}
          </h2>
        );
      } else {
        blocks.push(
          <h3 key={key} className="mb-2 text-sm font-semibold text-slate-100">
            {renderInlineWithBreaks(content, `${key}-inline`)}
          </h3>
        );
      }

      i += 1;
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, '').trim());
        i += 1;
      }

      const key = `${entryId}-ul-${blockIndex++}`;
      blocks.push(
        <ul key={key} className="mb-3 list-disc space-y-1 pl-5 last:mb-0">
          {items.map((item, itemIndex) => (
            <li key={`${key}-item-${itemIndex}`}>{renderInlineWithBreaks(item, `${key}-${itemIndex}`)}</li>
          ))}
        </ul>
      );
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*\d+\.\s+/, '').trim());
        i += 1;
      }

      const key = `${entryId}-ol-${blockIndex++}`;
      blocks.push(
        <ol key={key} className="mb-3 list-decimal space-y-1 pl-5 last:mb-0">
          {items.map((item, itemIndex) => (
            <li key={`${key}-item-${itemIndex}`}>{renderInlineWithBreaks(item, `${key}-${itemIndex}`)}</li>
          ))}
        </ol>
      );
      continue;
    }

    const paragraphLines: string[] = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,3})\s+/.test(lines[i]) &&
      !/^\s*[-*]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i])
    ) {
      paragraphLines.push(lines[i]);
      i += 1;
    }

    const paragraph = paragraphLines.join('\n');
    const key = `${entryId}-p-${blockIndex++}`;
    blocks.push(
      <p key={key} className="mb-3 last:mb-0">
        {renderInlineWithBreaks(paragraph, `${key}-inline`)}
      </p>
    );
  }

  return blocks;
}

function getOperationChipText(operation: NonNullable<TranscriptEntry['operation']>): string {
  const label = operation.label || getToolLabel(operation.tool);
  if (operation.status === 'complete') {
    const duration = operation.elapsedSeconds ?? operation.estimatedSeconds;
    return `${label} | done in ${formatEta(duration)}`;
  }

  const startedAtMs = Date.parse(operation.startedAt);
  const remaining = Number.isFinite(startedAtMs)
    ? getRemainingSeconds(operation.estimatedSeconds, startedAtMs)
    : operation.estimatedSeconds;

  return `${label} | ETA ${formatEta(remaining)}`;
}

export function VoiceInterface() {
  const { connect, disconnect, toggleMicrophone, connectionStatus, voiceState, isMicEnabled, interruptSpeaking } =
    useVoiceSession();
  const { transcript, inputLevel, error, clearTranscript, activeTools, addTranscriptEntry, toolEstimates } = useVoiceStore();
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Handle loading a conversation from history
  const handleLoadConversation = useCallback((messages: ConversationMessage[]) => {
    clearTranscript();
    messages.forEach((msg) => {
      addTranscriptEntry({
        role: msg.role,
        text: msg.content,
      });
    });
  }, [clearTranscript, addTranscriptEntry]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript]);

  const getStatusText = () => {
    if (error) return error;
    switch (connectionStatus) {
      case 'disconnected': return 'Click Connect to start';
      case 'connecting': return 'Connecting to server...';
      case 'error': return 'Connection failed - try again';
      case 'connected':
        if (!isMicEnabled && voiceState === 'idle') return 'Click the microphone to speak';
        switch (voiceState) {
          case 'listening':
            return 'Listening... speak your question';
          case 'thinking':
          case 'processing':
            if (activeTools.length > 0) {
              const details = activeTools.map((tool) => {
                const estimate = toolEstimates[tool.tool] ?? 3;
                const remaining = getRemainingSeconds(estimate, tool.timestamp.getTime());
                return `${getToolLabel(tool.tool)} (ETA ${formatEta(remaining)})`;
              });
              return `Working: ${details.join(', ')}`;
            }
            return 'Thinking...';
          case 'speaking':
            return 'Assistant is responding...';
          default:
            return 'Ready';
        }
      default:
        return '';
    }
  };

  return (
    <div className="flex h-screen bg-slate-900">
      {/* Left Panel - Controls */}
      <div className="w-80 flex-shrink-0 border-r border-slate-700 flex flex-col">
        {/* Header */}
        <div className="p-6 border-b border-slate-700 flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-white">Alek&apos;s email assistant</h1>
            <p className="text-sm text-slate-400 mt-1">Talk to manage your inbox</p>
          </div>
          <button
            onClick={() => setSettingsOpen(true)}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
            title="Settings"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
          </button>
        </div>

        {/* Connection Status */}
        <div className="px-6 py-4 border-b border-slate-700">
          <div className="flex items-center gap-2">
            <div className={`w-2.5 h-2.5 rounded-full ${
              connectionStatus === 'connected' ? 'bg-emerald-500' :
              connectionStatus === 'connecting' ? 'bg-yellow-500 animate-pulse' :
              connectionStatus === 'error' ? 'bg-red-500' :
              'bg-slate-500'
            }`} />
            <span className="text-sm text-slate-300">
              {connectionStatus === 'connected' ? 'Connected' :
               connectionStatus === 'connecting' ? 'Connecting...' :
               connectionStatus === 'error' ? 'Error' :
               'Disconnected'}
            </span>
          </div>
        </div>

        {/* Main Control Area */}
        <div className="flex-1 flex flex-col items-center justify-center p-6">
          {connectionStatus === 'disconnected' || connectionStatus === 'error' ? (
            <button
              onClick={connect}
              className="w-28 h-28 rounded-full bg-indigo-600 hover:bg-indigo-700 text-white font-medium transition-all transform hover:scale-105 shadow-lg shadow-indigo-500/25 flex items-center justify-center"
            >
              Connect
            </button>
          ) : connectionStatus === 'connecting' ? (
            <div className="w-28 h-28 rounded-full bg-indigo-600/50 flex items-center justify-center">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-white border-t-transparent"></div>
            </div>
          ) : (
            <>
              {/* State indicator */}
              <div className="mb-4 text-center h-6">
                {(voiceState === 'thinking' || voiceState === 'processing') && (
                  <div className="flex items-center justify-center gap-2 text-yellow-400">
                    <div className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse"></div>
                    <span className="text-sm font-medium">Thinking...</span>
                  </div>
                )}
                {voiceState === 'speaking' && (
                  <div className="flex items-center justify-center gap-2 text-blue-400">
                    <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse"></div>
                    <span className="text-sm font-medium">Assistant speaking...</span>
                  </div>
                )}
                {isMicEnabled && voiceState === 'listening' && (
                  <div className="flex items-center justify-center gap-2 text-red-400">
                    <div className="w-3 h-3 rounded-full bg-red-500 animate-pulse"></div>
                    <span className="text-sm font-medium">Recording - click DONE when finished</span>
                  </div>
                )}
                {!isMicEnabled && voiceState === 'idle' && (
                  <div className="flex items-center justify-center gap-2 text-slate-400">
                    <span className="text-sm">Ready for your question</span>
                  </div>
                )}
              </div>

              {/* Mic Button, Thinking Indicator, or Stop Button */}
              {voiceState === 'speaking' ? (
                <button
                  onClick={interruptSpeaking}
                  className="w-32 h-32 rounded-full bg-orange-500 hover:bg-orange-600 shadow-lg shadow-orange-500/25 transition-all transform hover:scale-105 flex flex-col items-center justify-center"
                >
                  <svg className="w-10 h-10 text-white" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M6 6h12v12H6z"/>
                  </svg>
                  <span className="text-white text-xs font-bold mt-1">STOP</span>
                </button>
              ) : voiceState === 'thinking' || voiceState === 'processing' ? (
                <div className="w-32 h-32 rounded-full bg-yellow-500/80 shadow-lg shadow-yellow-500/25 flex flex-col items-center justify-center">
                  <div className="animate-spin rounded-full h-10 w-10 border-4 border-white border-t-transparent"></div>
                  <span className="text-white text-xs font-bold mt-2">THINKING...</span>
                </div>
              ) : (
                <button
                  onClick={toggleMicrophone}
                  className={`w-32 h-32 rounded-full transition-all transform hover:scale-105 flex flex-col items-center justify-center shadow-lg ${
                    isMicEnabled
                      ? 'bg-red-500 hover:bg-red-600 shadow-red-500/25 animate-pulse'
                      : 'bg-emerald-500 hover:bg-emerald-600 shadow-emerald-500/25'
                  }`}
                >
                  {isMicEnabled ? (
                    <svg className="w-10 h-10 text-white" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M6 6h12v12H6z"/>
                    </svg>
                  ) : (
                    <svg className="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.8}
                        d="M12 15a3 3 0 003-3V5.25a3 3 0 10-6 0V12a3 3 0 003 3zm0 0a6.75 6.75 0 006.75-6.75m-13.5 0A6.75 6.75 0 0012 15m0 0v3m-3 0h6"
                      />
                    </svg>
                  )}
                  <span className="text-white text-xs font-bold mt-1">
                    {isMicEnabled ? 'DONE' : 'SPEAK'}
                  </span>
                </button>
              )}

              {/* Instructions */}
              <p className="mt-3 text-xs text-slate-400 text-center max-w-[200px]">
                {voiceState === 'speaking'
                  ? 'Click STOP to interrupt the assistant'
                  : voiceState === 'thinking' || voiceState === 'processing'
                  ? 'Processing your request'
                  : isMicEnabled
                  ? 'Speak your question, then click DONE'
                  : 'Click SPEAK, ask your question, then click DONE'}
              </p>

              {/* Audio Visualizer */}
              <div className="mt-4 h-16 w-full">
                <AudioVisualizer level={inputLevel} isActive={isMicEnabled || voiceState === 'speaking'} />
              </div>

              {/* Status Text */}
              <p className={`mt-4 text-sm text-center ${
                error ? 'text-red-400' :
                voiceState === 'thinking' || voiceState === 'processing' ? 'text-yellow-400' :
                voiceState === 'speaking' ? 'text-blue-400' :
                isMicEnabled ? 'text-emerald-400' :
                'text-slate-400'
              }`}>
                {getStatusText()}
              </p>

              {/* Tool activity indicator */}
              {activeTools.length > 0 && (
                <div className="mt-4 px-4 py-3 bg-slate-800 rounded-lg border border-slate-600 space-y-2">
                  {activeTools.map((tool) => {
                    const isAttachment = tool.tool === 'read_attachment';
                    const estimate = toolEstimates[tool.tool] ?? 3;
                    const remaining = getRemainingSeconds(estimate, tool.timestamp.getTime());
                    const label = getToolLabel(tool.tool);

                    return (
                      <div key={tool.tool} className="flex items-center gap-3">
                        <div className={`h-4 w-4 rounded-full border-2 border-t-transparent animate-spin ${isAttachment ? 'border-purple-400' : 'border-yellow-400'}`} />
                        <span className={`text-xs ${isAttachment ? 'text-purple-200 font-medium' : 'text-slate-300'}`}>
                          {label}
                        </span>
                        <span className="ml-auto rounded bg-slate-700 px-2 py-0.5 text-[10px] text-slate-300">
                          ETA {formatEta(remaining)}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}
            </>
          )}
        </div>

        {/* Bottom Actions */}
        {connectionStatus === 'connected' && (
          <div className="p-4 border-t border-slate-700 flex gap-2">
            <button
              onClick={clearTranscript}
              className="flex-1 px-3 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-800 rounded transition-colors"
            >
              Clear
            </button>
            <button
              onClick={disconnect}
              className="flex-1 px-3 py-2 text-sm text-slate-400 hover:text-red-400 hover:bg-slate-800 rounded transition-colors"
            >
              Disconnect
            </button>
          </div>
        )}
      </div>

      {/* Right Panel - Conversation */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Conversation Header */}
        <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-white">Conversation</h2>
          {transcript.length > 0 && (
            <span className="text-sm text-slate-500">{transcript.length} messages</span>
          )}
        </div>

        {/* Messages Area */}
        <div className="flex-1 overflow-y-auto p-6">
          {transcript.length === 0 ? (
            <div className="h-full flex flex-col items-center justify-center text-center">
              <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center mb-4">
                <svg className="w-8 h-8 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </div>
              <p className="text-slate-400 mb-6">No messages yet</p>

              {connectionStatus === 'connected' && (
                <div className="space-y-2">
                  <p className="text-sm text-slate-500">Try saying:</p>
                  <div className="flex flex-wrap gap-2 justify-center max-w-sm">
                    {[
                      'What unread emails do I have?',
                      'Read my latest email',
                      'Find emails from today',
                    ].map((prompt) => (
                      <span
                        key={prompt}
                        className="px-3 py-1.5 bg-slate-800 rounded-full text-sm text-slate-400"
                      >
                        {prompt}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-4 max-w-3xl mx-auto">
              {transcript.map((entry) => {
                const normalizedText = normalizeTranscriptText(entry.text).toLowerCase();
                const isAttachmentContent = entry.role === 'assistant' && (
                  normalizedText.includes('attachment') ||
                  normalizedText.includes('document') ||
                  normalizedText.includes('pdf') ||
                  normalizedText.includes('image')
                );

                return (
                  <div
                    key={entry.id}
                    className={`flex ${entry.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`relative max-w-[85%] px-4 py-3 rounded-2xl transition-all duration-300 ${
                        entry.operation && entry.role === 'assistant' ? 'pt-8' : ''
                      } ${
                        entry.role === 'user'
                          ? 'bg-indigo-600 text-white rounded-br-md'
                          : isAttachmentContent
                          ? 'bg-gradient-to-br from-purple-900/60 to-slate-700 text-slate-100 rounded-bl-md border border-purple-500/30'
                          : 'bg-slate-700 text-slate-100 rounded-bl-md'
                      }`}
                    >
                      {entry.role === 'assistant' && entry.operation && (
                        <div className="absolute right-2 top-2 rounded bg-slate-900/60 px-2 py-0.5 text-[10px] text-slate-200 border border-slate-500/40">
                          {getOperationChipText(entry.operation)}
                        </div>
                      )}

                      <div className={`flex items-center gap-2 text-xs mb-1 ${entry.role === 'user' ? 'text-indigo-200' : 'text-slate-400'}`}>
                        <span>{entry.role === 'user' ? 'You' : 'Assistant'}</span>
                        {isAttachmentContent && <span className="text-purple-300 text-[10px]">Attachment info</span>}
                      </div>

                      <div className="text-sm leading-relaxed break-words">
                        {renderMarkdownText(entry.text, entry.id)}
                      </div>

                      {/* Render structured email data if available */}
                      {entry.emails && entry.emails.length > 0 && (
                        <EmailList emails={entry.emails} />
                      )}
                    </div>
                  </div>
                );
              })}

              {/* Show attachment processing indicator only when reading attachments */}
              {(voiceState === 'thinking' || voiceState === 'processing') && activeTools.some((tool) => tool.tool === 'read_attachment') && (
                <div className="flex justify-start">
                  <div className="bg-gradient-to-br from-purple-900/60 to-slate-700 text-slate-100 rounded-2xl rounded-bl-md px-4 py-3 border border-purple-500/30">
                    <div className="flex items-center gap-2 text-xs text-purple-300 mb-2">
                      <span>Analyzing attachment</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="relative w-6 h-6">
                        <div className="absolute inset-0 rounded-full border-2 border-purple-400 border-t-transparent animate-spin"></div>
                        <div className="absolute inset-1 rounded-full border border-purple-300 border-b-transparent animate-spin" style={{ animationDirection: 'reverse', animationDuration: '0.8s' }}></div>
                      </div>
                      {(() => {
                        const attachmentTool = activeTools.find((tool) => tool.tool === 'read_attachment');
                        const estimate = toolEstimates.read_attachment ?? 9;
                        const remaining = attachmentTool
                          ? getRemainingSeconds(estimate, attachmentTool.timestamp.getTime())
                          : estimate;
                        return <span className="text-xs text-slate-300">ETA {formatEta(remaining)}</span>;
                      })()}
                    </div>
                  </div>
                </div>
              )}
              <div ref={transcriptEndRef} />
            </div>
          )}
        </div>

        {/* Error Banner */}
        {error && (
          <div className="mx-6 mb-4 px-4 py-3 bg-red-500/10 border border-red-500/30 rounded-lg">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}
      </div>

      {/* Right Panel - Conversation History */}
      <ConversationHistory onLoadConversation={handleLoadConversation} />

      {/* Settings Modal */}
      <Settings isOpen={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
