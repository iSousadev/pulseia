export type SessionState = 'idle' | 'connecting' | 'connected' | 'listening' | 'thinking' | 'speaking' | 'error';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  source?: 'chat' | 'transcription';
}

export interface SessionInfo {
  id: string;
  startedAt: Date;
  duration: number; // seconds
  state: SessionState;
}
