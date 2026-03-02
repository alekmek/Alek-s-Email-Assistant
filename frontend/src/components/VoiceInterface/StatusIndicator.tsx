import type { ConnectionStatus, VoiceState } from '../../types';

interface StatusIndicatorProps {
  status: ConnectionStatus;
  voiceState: VoiceState;
}

export function StatusIndicator({ status, voiceState }: StatusIndicatorProps) {
  const getStatusColor = () => {
    switch (status) {
      case 'connected':
        return 'bg-green-500';
      case 'connecting':
        return 'bg-yellow-500 animate-pulse';
      case 'error':
        return 'bg-red-500';
      default:
        return 'bg-slate-500';
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'connected':
        return `Connected${voiceState !== 'idle' ? ` - ${voiceState}` : ''}`;
      case 'connecting':
        return 'Connecting...';
      case 'error':
        return 'Connection Error';
      default:
        return 'Disconnected';
    }
  };

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-slate-800/50 rounded-full">
      <div className={`w-2 h-2 rounded-full ${getStatusColor()}`} />
      <span className="text-sm text-slate-300">{getStatusText()}</span>
    </div>
  );
}
