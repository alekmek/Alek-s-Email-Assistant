import { useEffect, useState } from 'react';
import {
  profileApi,
  settingsApi,
  type CredentialsUpdatePayload,
  type SafetySettings,
  type UserProfile,
} from '../../services/api';

interface SettingsProps {
  isOpen: boolean;
  onClose: () => void;
}

const CREDENTIAL_LABELS: Record<keyof CredentialsUpdatePayload, string> = {
  anthropic_api_key: 'Anthropic API Key',
  nylas_api_key: 'Nylas API Key',
  nylas_client_id: 'Nylas Client ID',
  nylas_client_secret: 'Nylas Client Secret',
  nylas_grant_id: 'Nylas Grant ID',
  deepgram_api_key: 'Deepgram API Key',
  cartesia_api_key: 'Cartesia API Key',
};

const CREDENTIAL_ORDER: Array<keyof CredentialsUpdatePayload> = [
  'anthropic_api_key',
  'nylas_api_key',
  'nylas_client_id',
  'nylas_client_secret',
  'nylas_grant_id',
  'deepgram_api_key',
  'cartesia_api_key',
];

function sourceBadge(source: string): string {
  if (source === 'profile') return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30';
  if (source === 'env') return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
  return 'bg-slate-600/20 text-slate-300 border-slate-500/40';
}

export function Settings({ isOpen, onClose }: SettingsProps) {
  const [settings, setSettings] = useState<SafetySettings | null>(null);
  const [profile, setProfile] = useState<UserProfile | null>(null);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);

  const [displayNameInput, setDisplayNameInput] = useState('');
  const [credentialsInput, setCredentialsInput] = useState<CredentialsUpdatePayload>({});

  const [newExcludedSender, setNewExcludedSender] = useState('');
  const [newExcludedFolder, setNewExcludedFolder] = useState('');
  const [newExcludedSubject, setNewExcludedSubject] = useState('');

  useEffect(() => {
    if (isOpen) {
      loadSettingsAndProfile();
    }
  }, [isOpen]);

  const loadSettingsAndProfile = async () => {
    setLoading(true);
    try {
      const [settingsData, profileData] = await Promise.all([
        settingsApi.getSettings(),
        profileApi.getProfile(),
      ]);
      setSettings(settingsData);
      setProfile(profileData);
      setDisplayNameInput(profileData.display_name || '');
      setCredentialsInput({});
    } catch (error) {
      console.error('Failed to load settings/profile:', error);
    } finally {
      setLoading(false);
    }
  };

  const updateSetting = async <K extends keyof SafetySettings>(
    key: K,
    value: SafetySettings[K]
  ) => {
    if (!settings) return;

    const newSettings = { ...settings, [key]: value };
    setSettings(newSettings);

    setSaving(true);
    try {
      await settingsApi.updateSettings({ [key]: value });
    } catch (error) {
      console.error('Failed to save setting:', error);
      setSettings(settings);
    } finally {
      setSaving(false);
    }
  };

  const saveDisplayName = async () => {
    const next = displayNameInput.trim();
    if (!next) return;

    setProfileSaving(true);
    try {
      const updated = await profileApi.updateProfile({ display_name: next });
      setProfile(updated);
      setDisplayNameInput(updated.display_name || next);
    } catch (error) {
      console.error('Failed to save display name:', error);
    } finally {
      setProfileSaving(false);
    }
  };

  const saveCredentials = async () => {
    const payload: CredentialsUpdatePayload = {};

    for (const key of CREDENTIAL_ORDER) {
      const value = credentialsInput[key];
      if (typeof value === 'string' && value.trim()) {
        payload[key] = value.trim();
      }
    }

    if (Object.keys(payload).length === 0) return;

    setProfileSaving(true);
    try {
      const updated = await profileApi.updateCredentials(payload);
      setProfile(updated);
      setCredentialsInput({});
    } catch (error) {
      console.error('Failed to save credentials:', error);
    } finally {
      setProfileSaving(false);
    }
  };

  const updateCredentialInput = (key: keyof CredentialsUpdatePayload, value: string) => {
    setCredentialsInput((prev) => ({ ...prev, [key]: value }));
  };

  const addExcludedItem = async (
    type: 'excluded_senders' | 'excluded_folders' | 'excluded_subjects',
    value: string
  ) => {
    if (!settings || !value.trim()) return;

    const newList = [...settings[type], value.trim()];
    await updateSetting(type, newList);

    if (type === 'excluded_senders') setNewExcludedSender('');
    if (type === 'excluded_folders') setNewExcludedFolder('');
    if (type === 'excluded_subjects') setNewExcludedSubject('');
  };

  const removeExcludedItem = async (
    type: 'excluded_senders' | 'excluded_folders' | 'excluded_subjects',
    value: string
  ) => {
    if (!settings) return;
    const newList = settings[type].filter((item) => item !== value);
    await updateSetting(type, newList);
  };

  if (!isOpen) return null;

  const hasCredentialChanges = CREDENTIAL_ORDER.some((key) => {
    const value = credentialsInput[key];
    return typeof value === 'string' && value.trim().length > 0;
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="max-h-[90vh] w-full max-w-4xl overflow-hidden rounded-xl bg-slate-800 shadow-2xl">
        <div className="flex items-center justify-between border-b border-slate-700 px-6 py-4">
          <div>
            <h2 className="text-xl font-semibold text-white">Settings</h2>
            <p className="mt-1 text-sm text-slate-400">Profile, credentials, and assistant controls</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 transition-colors hover:bg-slate-700 hover:text-white"
          >
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="max-h-[calc(90vh-80px)] overflow-y-auto p-6">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-blue-500 border-t-transparent"></div>
            </div>
          ) : settings && profile ? (
            <div className="space-y-8">
              <section>
                <h3 className="mb-4 text-lg font-medium text-white">Profile & Credentials</h3>
                <div className="space-y-4 rounded-xl border border-slate-700 bg-slate-900/30 p-4">
                  <div className="flex flex-col gap-2 md:flex-row md:items-center">
                    <label className="text-sm font-medium text-slate-200 md:w-40">Display Name</label>
                    <input
                      type="text"
                      value={displayNameInput}
                      onChange={(e) => setDisplayNameInput(e.target.value)}
                      className="flex-1 rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                      placeholder="Your name"
                    />
                    <button
                      onClick={saveDisplayName}
                      disabled={profileSaving || !displayNameInput.trim()}
                      className="rounded-lg bg-slate-600 px-3 py-2 text-sm text-white transition-colors hover:bg-slate-500 disabled:opacity-50"
                    >
                      Save Name
                    </button>
                  </div>

                  <div className="grid gap-3 md:grid-cols-2">
                    {CREDENTIAL_ORDER.map((key) => {
                      const status = profile.credentials[key];
                      return (
                        <div key={key} className="rounded-lg border border-slate-700 bg-slate-800/70 p-3">
                          <div className="mb-2 flex items-center justify-between gap-2">
                            <p className="text-xs font-medium text-slate-200">{CREDENTIAL_LABELS[key]}</p>
                            <span className={`rounded border px-2 py-0.5 text-[10px] uppercase tracking-wide ${sourceBadge(status.source)}`}>
                              {status.source}
                            </span>
                          </div>
                          <input
                            type="password"
                            autoComplete="off"
                            value={credentialsInput[key] ?? ''}
                            onChange={(e) => updateCredentialInput(key, e.target.value)}
                            placeholder={status.preview || 'Not configured'}
                            className="w-full rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                          />
                        </div>
                      );
                    })}
                  </div>

                  <div className="flex items-center justify-between gap-3">
                    <p className="text-xs text-slate-400">
                      Enter only fields you want to update. Empty fields are ignored.
                    </p>
                    <button
                      onClick={saveCredentials}
                      disabled={!hasCredentialChanges || profileSaving}
                      className="rounded-lg bg-blue-600 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
                    >
                      Save Credentials
                    </button>
                  </div>
                </div>
              </section>

              <section>
                <h3 className="mb-4 text-lg font-medium text-white">Permissions</h3>
                <div className="space-y-4">
                  <ToggleSetting
                    label="Allow sending emails"
                    description="AI can send emails on your behalf"
                    enabled={settings.allow_send_emails}
                    onChange={(v) => updateSetting('allow_send_emails', v)}
                    danger
                  />
                  <ToggleSetting
                    label="Require confirmation for sending"
                    description="Always ask before sending any email"
                    enabled={settings.require_confirmation_for_send}
                    onChange={(v) => updateSetting('require_confirmation_for_send', v)}
                  />
                  <ToggleSetting
                    label="Allow reading attachments"
                    description="AI can analyze email attachments"
                    enabled={settings.allow_read_attachments}
                    onChange={(v) => updateSetting('allow_read_attachments', v)}
                  />
                  <ToggleSetting
                    label="Allow reading email body"
                    description="AI can read full email contents"
                    enabled={settings.allow_read_email_body}
                    onChange={(v) => updateSetting('allow_read_email_body', v)}
                  />
                  <ToggleSetting
                    label="Allow marking as read"
                    description="AI can mark emails as read"
                    enabled={settings.allow_mark_as_read}
                    onChange={(v) => updateSetting('allow_mark_as_read', v)}
                  />
                  <ToggleSetting
                    label="Allow deleting emails"
                    description="AI can delete emails"
                    enabled={settings.allow_delete_emails}
                    onChange={(v) => updateSetting('allow_delete_emails', v)}
                    danger
                  />
                  <ToggleSetting
                    label="Allow archiving emails"
                    description="AI can archive emails"
                    enabled={settings.allow_archive_emails}
                    onChange={(v) => updateSetting('allow_archive_emails', v)}
                  />
                </div>
              </section>

              <section>
                <h3 className="mb-4 text-lg font-medium text-white">Privacy</h3>
                <div className="space-y-4">
                  <ToggleSetting
                    label="Hide sensitive content"
                    description="Don't read passwords, API keys, or tokens aloud"
                    enabled={settings.hide_sensitive_content}
                    onChange={(v) => updateSetting('hide_sensitive_content', v)}
                  />
                  <div className="flex items-center justify-between py-2">
                    <div>
                      <p className="text-sm font-medium text-white">Max emails per search</p>
                      <p className="text-xs text-slate-400">Limit search results</p>
                    </div>
                    <select
                      value={settings.max_emails_per_search}
                      onChange={(e) => updateSetting('max_emails_per_search', Number(e.target.value))}
                      className="rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value={10}>10</option>
                      <option value={25}>25</option>
                      <option value={50}>50</option>
                      <option value={100}>100</option>
                    </select>
                  </div>
                </div>
              </section>

              <section>
                <h3 className="mb-4 text-lg font-medium text-white">Exclusions</h3>
                <div className="space-y-6">
                  <ExclusionList
                    label="Excluded Senders"
                    description="AI won't read emails from these addresses"
                    items={settings.excluded_senders}
                    placeholder="email@example.com"
                    value={newExcludedSender}
                    onChange={setNewExcludedSender}
                    onAdd={() => addExcludedItem('excluded_senders', newExcludedSender)}
                    onRemove={(v) => removeExcludedItem('excluded_senders', v)}
                  />

                  <ExclusionList
                    label="Excluded Folders"
                    description="AI won't access these folders"
                    items={settings.excluded_folders}
                    placeholder="folder name"
                    value={newExcludedFolder}
                    onChange={setNewExcludedFolder}
                    onAdd={() => addExcludedItem('excluded_folders', newExcludedFolder)}
                    onRemove={(v) => removeExcludedItem('excluded_folders', v)}
                  />

                  <ExclusionList
                    label="Excluded Subject Keywords"
                    description="AI won't read emails with these words in subject"
                    items={settings.excluded_subjects}
                    placeholder="keyword"
                    value={newExcludedSubject}
                    onChange={setNewExcludedSubject}
                    onAdd={() => addExcludedItem('excluded_subjects', newExcludedSubject)}
                    onRemove={(v) => removeExcludedItem('excluded_subjects', v)}
                  />
                </div>
              </section>
            </div>
          ) : (
            <p className="text-center text-slate-400">Failed to load settings</p>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-slate-700 px-6 py-4">
          <p className="text-xs text-slate-500">
            {saving || profileSaving ? 'Saving...' : 'Changes save automatically'}
          </p>
          <button
            onClick={onClose}
            className="rounded-lg bg-blue-600 px-4 py-2 font-medium text-white transition-colors hover:bg-blue-700"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}

interface ToggleSettingProps {
  label: string;
  description: string;
  enabled: boolean;
  onChange: (value: boolean) => void;
  danger?: boolean;
}

function ToggleSetting({ label, description, enabled, onChange, danger }: ToggleSettingProps) {
  return (
    <div className="flex items-center justify-between py-2">
      <div className="flex-1">
        <p className={`text-sm font-medium ${danger && enabled ? 'text-red-400' : 'text-white'}`}>
          {label}
        </p>
        <p className="text-xs text-slate-400">{description}</p>
      </div>
      <button
        onClick={() => onChange(!enabled)}
        className={`relative h-6 w-11 rounded-full transition-colors ${
          enabled
            ? danger
              ? 'bg-red-500'
              : 'bg-blue-500'
            : 'bg-slate-600'
        }`}
      >
        <span
          className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${
            enabled ? 'translate-x-5' : ''
          }`}
        />
      </button>
    </div>
  );
}

interface ExclusionListProps {
  label: string;
  description: string;
  items: string[];
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  onAdd: () => void;
  onRemove: (value: string) => void;
}

function ExclusionList({
  label,
  description,
  items,
  placeholder,
  value,
  onChange,
  onAdd,
  onRemove,
}: ExclusionListProps) {
  return (
    <div>
      <p className="text-sm font-medium text-white">{label}</p>
      <p className="mb-2 text-xs text-slate-400">{description}</p>

      <div className="mb-2 flex gap-2">
        <input
          type="text"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onAdd()}
          placeholder={placeholder}
          className="flex-1 rounded-lg border border-slate-600 bg-slate-700 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={onAdd}
          disabled={!value.trim()}
          className="rounded-lg bg-slate-600 px-3 py-2 text-white transition-colors hover:bg-slate-500 disabled:opacity-50"
        >
          Add
        </button>
      </div>

      {items.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {items.map((item) => (
            <span
              key={item}
              className="inline-flex items-center gap-1 rounded-lg bg-slate-700 px-2 py-1 text-sm text-slate-300"
            >
              {item}
              <button onClick={() => onRemove(item)} className="text-slate-400 hover:text-red-400">
                <svg className="h-3.5 w-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
