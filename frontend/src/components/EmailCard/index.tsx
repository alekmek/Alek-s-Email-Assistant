import { useState } from 'react';
import type { EmailData } from '../../types';

const MAX_VISIBLE_EMAILS = 10;

interface EmailCardProps {
  email: EmailData;
  compact?: boolean;
}

export function EmailCard({ email, compact = false }: EmailCardProps) {
  // Handle from field - can be string, array of objects, or object
  const getFromDisplay = () => {
    if (!email.from) return 'Unknown';
    if (typeof email.from === 'string') return email.from;
    if (Array.isArray(email.from) && email.from.length > 0) {
      const sender = email.from[0];
      if (typeof sender === 'string') return sender;
      if (sender && typeof sender === 'object') {
        return sender.name || sender.email || 'Unknown';
      }
    }
    if (typeof email.from === 'object' && !Array.isArray(email.from)) {
      const sender = email.from as { name?: string; email?: string };
      return sender.name || sender.email || 'Unknown';
    }
    return 'Unknown';
  };

  return (
    <div className={`bg-slate-800 rounded-lg border border-slate-600 overflow-hidden ${compact ? 'p-3' : 'p-4'}`}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            {email.unread && (
              <span className="w-2 h-2 bg-blue-500 rounded-full flex-shrink-0"></span>
            )}
            <span className="text-sm font-medium text-white truncate">
              {getFromDisplay()}
            </span>
          </div>
          <h3 className="text-sm text-slate-200 font-medium truncate">
            {email.subject || '(No subject)'}
          </h3>
        </div>
        {email.date && (
          <span className="text-xs text-slate-500 flex-shrink-0">
            {formatDate(email.date)}
          </span>
        )}
      </div>

      {/* Snippet */}
      {email.snippet && !compact && (
        <p className="text-xs text-slate-400 line-clamp-2 mb-2">
          {email.snippet}
        </p>
      )}

      {/* Attachments */}
      {email.hasAttachments && (
        <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-slate-700">
          <svg className="w-3.5 h-3.5 text-purple-400" fill="currentColor" viewBox="0 0 24 24">
            <path d="M16.5 6v11.5c0 2.21-1.79 4-4 4s-4-1.79-4-4V5c0-1.38 1.12-2.5 2.5-2.5s2.5 1.12 2.5 2.5v10.5c0 .55-.45 1-1 1s-1-.45-1-1V6H10v9.5c0 1.38 1.12 2.5 2.5 2.5s2.5-1.12 2.5-2.5V5c0-2.21-1.79-4-4-4S7 2.79 7 5v12.5c0 3.04 2.46 5.5 5.5 5.5s5.5-2.46 5.5-5.5V6h-1.5z"/>
          </svg>
          <span className="text-xs text-purple-400">
            {email.attachments?.length || 1} attachment{(email.attachments?.length || 1) > 1 ? 's' : ''}
          </span>
        </div>
      )}
    </div>
  );
}

interface EmailListProps {
  emails: EmailData[];
}

export function EmailList({ emails }: EmailListProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (emails.length === 0) return null;

  const hasMore = emails.length > MAX_VISIBLE_EMAILS;
  const visibleEmails = isExpanded ? emails : emails.slice(0, MAX_VISIBLE_EMAILS);
  const hiddenCount = emails.length - MAX_VISIBLE_EMAILS;

  return (
    <div className="mt-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-xs text-slate-400">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/>
          </svg>
          <span>{emails.length} email{emails.length > 1 ? 's' : ''} found</span>
        </div>
        {hasMore && (
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
          >
            {isExpanded ? 'Show less' : `Show all ${emails.length}`}
          </button>
        )}
      </div>
      <div className="space-y-2">
        {visibleEmails.map((email, index) => (
          <EmailCard key={email.id || index} email={email} compact={emails.length > 3} />
        ))}
      </div>
      {hasMore && !isExpanded && (
        <button
          onClick={() => setIsExpanded(true)}
          className="w-full py-2 text-sm text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors"
        >
          Show {hiddenCount} more email{hiddenCount > 1 ? 's' : ''}
        </button>
      )}
    </div>
  );
}

function formatDate(dateInput: string | number): string {
  try {
    // Handle Unix timestamp (seconds) or date string
    let date: Date;
    if (typeof dateInput === 'number') {
      // Unix timestamp in seconds - convert to milliseconds
      date = new Date(dateInput * 1000);
    } else {
      date = new Date(dateInput);
    }

    if (isNaN(date.getTime())) return String(dateInput);

    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

    if (diffDays === 0) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (diffDays === 1) {
      return 'Yesterday';
    } else if (diffDays < 7) {
      return date.toLocaleDateString([], { weekday: 'short' });
    } else {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
  } catch {
    return String(dateInput);
  }
}
