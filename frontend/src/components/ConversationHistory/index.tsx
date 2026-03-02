import { useEffect, useState } from 'react';
import { useVoiceStore } from '../../store';
import { conversationApi } from '../../services/api';
import type { Conversation, ConversationMessage } from '../../types';

interface ConversationHistoryProps {
  onLoadConversation: (messages: ConversationMessage[]) => void;
}

export function ConversationHistory({ onLoadConversation }: ConversationHistoryProps) {
  const {
    conversations,
    currentConversationId,
    isLoadingConversations,
    setConversations,
    setCurrentConversationId,
    setLoadingConversations,
    addConversation,
    removeConversation,
    clearTranscript,
  } = useVoiceStore();

  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Load conversations on mount
  useEffect(() => {
    loadConversations();
  }, []);

  const loadConversations = async () => {
    setLoadingConversations(true);
    try {
      const data = await conversationApi.listConversations();
      setConversations(data);
    } catch (error) {
      console.error('Failed to load conversations:', error);
    } finally {
      setLoadingConversations(false);
    }
  };

  const handleNewConversation = async () => {
    try {
      const conversation = await conversationApi.createConversation();
      addConversation(conversation);
      setCurrentConversationId(conversation.id);
      clearTranscript();
    } catch (error) {
      console.error('Failed to create conversation:', error);
    }
  };

  const handleSelectConversation = async (conversation: Conversation) => {
    if (currentConversationId === conversation.id) return;

    setCurrentConversationId(conversation.id);
    try {
      const messages = await conversationApi.getMessages(conversation.id);
      onLoadConversation(messages);
    } catch (error) {
      console.error('Failed to load messages:', error);
    }
  };

  const handleDeleteConversation = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeletingId(id);
    try {
      await conversationApi.deleteConversation(id);
      removeConversation(id);
    } catch (error) {
      console.error('Failed to delete conversation:', error);
    } finally {
      setDeletingId(null);
    }
  };

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const diffDays = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return date.toLocaleDateString([], { weekday: 'short' });
    } else {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
  };

  const formatConversationName = (dateString: string) => {
    const date = new Date(dateString);
    return date.toLocaleString([], {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  return (
    <div className="w-72 bg-gray-900/50 border-l border-gray-700 flex flex-col h-full">
      {/* Header */}
      <div className="p-4 border-b border-gray-700">
        <button
          onClick={handleNewConversation}
          className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors flex items-center justify-center gap-2"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Conversation
        </button>
      </div>

      {/* Conversation List */}
      <div className="flex-1 overflow-y-auto">
        {isLoadingConversations ? (
          <div className="p-4 text-center text-gray-400">
            <div className="animate-spin w-6 h-6 border-2 border-gray-400 border-t-transparent rounded-full mx-auto mb-2"></div>
            Loading...
          </div>
        ) : conversations.length === 0 ? (
          <div className="p-4 text-center text-gray-500">
            <p className="text-sm">No conversations yet</p>
            <p className="text-xs mt-1">Click "New Conversation" to start</p>
          </div>
        ) : (
          <ul className="py-2">
            {conversations.map((conversation) => (
              <li
                key={conversation.id}
                onClick={() => handleSelectConversation(conversation)}
                onMouseEnter={() => setHoveredId(conversation.id)}
                onMouseLeave={() => setHoveredId(null)}
                className={`
                  relative px-4 py-3 cursor-pointer transition-colors
                  ${currentConversationId === conversation.id
                    ? 'bg-blue-600/20 border-l-2 border-blue-500'
                    : 'hover:bg-gray-800/50 border-l-2 border-transparent'
                  }
                `}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-200 truncate">
                      {formatConversationName(conversation.created_at)}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      Started {formatDate(conversation.created_at)}
                    </p>
                  </div>

                  {/* Delete button */}
                  {(hoveredId === conversation.id || deletingId === conversation.id) && (
                    <button
                      onClick={(e) => handleDeleteConversation(conversation.id, e)}
                      disabled={deletingId === conversation.id}
                      className="p-1 text-gray-400 hover:text-red-400 transition-colors"
                      title="Delete conversation"
                    >
                      {deletingId === conversation.id ? (
                        <div className="w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin"></div>
                      ) : (
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                      )}
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
