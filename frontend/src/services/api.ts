import type { Conversation, ConversationMessage } from '../types';

const API_BASE = 'http://localhost:8000';

export const conversationApi = {
  async listConversations(limit = 50, offset = 0): Promise<Conversation[]> {
    const response = await fetch(
      `${API_BASE}/api/conversations?limit=${limit}&offset=${offset}`
    );
    if (!response.ok) {
      throw new Error('Failed to fetch conversations');
    }
    return response.json();
  },

  async createConversation(title?: string): Promise<Conversation> {
    const params = new URLSearchParams();
    if (title) params.set('title', title);

    const response = await fetch(
      `${API_BASE}/api/conversations?${params.toString()}`,
      { method: 'POST' }
    );
    if (!response.ok) {
      throw new Error('Failed to create conversation');
    }
    return response.json();
  },

  async getConversation(id: string): Promise<Conversation> {
    const response = await fetch(`${API_BASE}/api/conversations/${id}`);
    if (!response.ok) {
      throw new Error('Conversation not found');
    }
    return response.json();
  },

  async getMessages(conversationId: string): Promise<ConversationMessage[]> {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/messages`
    );
    if (!response.ok) {
      throw new Error('Failed to fetch messages');
    }
    return response.json();
  },

  async addMessage(
    conversationId: string,
    role: 'user' | 'assistant',
    content: string
  ): Promise<ConversationMessage> {
    const params = new URLSearchParams({ role, content });
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/messages?${params.toString()}`,
      { method: 'POST' }
    );
    if (!response.ok) {
      throw new Error('Failed to add message');
    }
    return response.json();
  },

  async deleteConversation(id: string): Promise<void> {
    const response = await fetch(`${API_BASE}/api/conversations/${id}`, {
      method: 'DELETE',
    });
    if (!response.ok) {
      throw new Error('Failed to delete conversation');
    }
  },
};

export interface SafetySettings {
  allow_send_emails: boolean;
  require_confirmation_for_send: boolean;
  allow_read_attachments: boolean;
  allow_read_email_body: boolean;
  allow_mark_as_read: boolean;
  allow_delete_emails: boolean;
  allow_archive_emails: boolean;
  excluded_senders: string[];
  excluded_folders: string[];
  excluded_subjects: string[];
  hide_sensitive_content: boolean;
  max_emails_per_search: number;
}

export type CredentialSource = 'profile' | 'env' | 'missing';

export interface CredentialStatus {
  configured: boolean;
  source: CredentialSource;
  preview: string;
}

export interface UserProfile {
  id: string;
  display_name: string;
  credentials: {
    anthropic_api_key: CredentialStatus;
    nylas_api_key: CredentialStatus;
    nylas_client_id: CredentialStatus;
    nylas_client_secret: CredentialStatus;
    nylas_grant_id: CredentialStatus;
    deepgram_api_key: CredentialStatus;
    cartesia_api_key: CredentialStatus;
  };
  created_at: string;
  updated_at: string;
}

export const settingsApi = {
  async getSettings(): Promise<SafetySettings> {
    const response = await fetch(`${API_BASE}/api/settings`);
    if (!response.ok) {
      throw new Error('Failed to fetch settings');
    }
    return response.json();
  },

  async updateSettings(settings: Partial<SafetySettings>): Promise<SafetySettings> {
    const params = new URLSearchParams();

    if (settings.allow_send_emails !== undefined) {
      params.set('allow_send_emails', String(settings.allow_send_emails));
    }
    if (settings.require_confirmation_for_send !== undefined) {
      params.set('require_confirmation_for_send', String(settings.require_confirmation_for_send));
    }
    if (settings.allow_read_attachments !== undefined) {
      params.set('allow_read_attachments', String(settings.allow_read_attachments));
    }
    if (settings.allow_read_email_body !== undefined) {
      params.set('allow_read_email_body', String(settings.allow_read_email_body));
    }
    if (settings.allow_mark_as_read !== undefined) {
      params.set('allow_mark_as_read', String(settings.allow_mark_as_read));
    }
    if (settings.allow_delete_emails !== undefined) {
      params.set('allow_delete_emails', String(settings.allow_delete_emails));
    }
    if (settings.allow_archive_emails !== undefined) {
      params.set('allow_archive_emails', String(settings.allow_archive_emails));
    }
    if (settings.excluded_senders !== undefined) {
      params.set('excluded_senders', JSON.stringify(settings.excluded_senders));
    }
    if (settings.excluded_folders !== undefined) {
      params.set('excluded_folders', JSON.stringify(settings.excluded_folders));
    }
    if (settings.excluded_subjects !== undefined) {
      params.set('excluded_subjects', JSON.stringify(settings.excluded_subjects));
    }
    if (settings.hide_sensitive_content !== undefined) {
      params.set('hide_sensitive_content', String(settings.hide_sensitive_content));
    }
    if (settings.max_emails_per_search !== undefined) {
      params.set('max_emails_per_search', String(settings.max_emails_per_search));
    }

    const response = await fetch(`${API_BASE}/api/settings?${params.toString()}`, {
      method: 'PUT',
    });
    if (!response.ok) {
      throw new Error('Failed to update settings');
    }
    return response.json();
  },
};

export interface ProfileUpdatePayload {
  display_name?: string;
}

export interface CredentialsUpdatePayload {
  anthropic_api_key?: string;
  nylas_api_key?: string;
  nylas_client_id?: string;
  nylas_client_secret?: string;
  nylas_grant_id?: string;
  deepgram_api_key?: string;
  cartesia_api_key?: string;
}

export const profileApi = {
  async getProfile(): Promise<UserProfile> {
    const response = await fetch(`${API_BASE}/api/profile`);
    if (!response.ok) {
      throw new Error('Failed to fetch profile');
    }
    return response.json();
  },

  async updateProfile(payload: ProfileUpdatePayload): Promise<UserProfile> {
    const params = new URLSearchParams();
    if (payload.display_name !== undefined) {
      params.set('display_name', payload.display_name);
    }

    const response = await fetch(`${API_BASE}/api/profile?${params.toString()}`, {
      method: 'PUT',
    });
    if (!response.ok) {
      throw new Error('Failed to update profile');
    }
    return response.json();
  },

  async updateCredentials(payload: CredentialsUpdatePayload): Promise<UserProfile> {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(payload)) {
      if (value !== undefined) {
        params.set(key, value);
      }
    }

    const response = await fetch(`${API_BASE}/api/profile/credentials?${params.toString()}`, {
      method: 'PUT',
    });
    if (!response.ok) {
      throw new Error('Failed to update credentials');
    }
    return response.json();
  },
};
