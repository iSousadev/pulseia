import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ConnectionState,
  LocalVideoTrack,
  Participant,
  Room,
  RoomEvent,
  Track,
  type ChatMessage as LKChatMessage,
  type DisconnectReason,
  type TranscriptionSegment,
} from 'livekit-client';

import { assertLivekitConfig, livekitConfig } from '@/config/livekit';
import type { ChatMessage, SessionInfo, SessionState } from '@/types/voice-assistant';
import { requestLivekitDispatch, requestLivekitToken } from '@/services/livekit/tokenClient';

const IDENTITY_STORAGE_KEY = 'pulse.voice.identity';
const ASSISTANT_JOIN_TIMEOUT_MS = 7000;

const resolveDispatchEndpoint = (tokenEndpoint: string): string => {
  const normalized = tokenEndpoint.trim();
  if (/\/token\/?$/i.test(normalized)) {
    return normalized.replace(/\/token\/?$/i, '/dispatch');
  }
  return `${normalized.replace(/\/$/, '')}/dispatch`;
};

const createId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
};

const getOrCreateIdentity = () => {
  if (typeof window === 'undefined') {
    return `web-${createId().slice(0, 8)}`;
  }
  const existing = window.localStorage.getItem(IDENTITY_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const created = `web-${createId().slice(0, 8)}`;
  window.localStorage.setItem(IDENTITY_STORAGE_KEY, created);
  return created;
};

const toRole = (participant?: Participant): 'user' | 'assistant' => {
  if (!participant || participant.isLocal) {
    return 'user';
  }
  return 'assistant';
};

const toHumanError = (error: unknown): string => {
  if (error instanceof Error && error.message) {
    const message = error.message.trim();

    if (/nao foi possivel acessar o endpoint de token/i.test(message) || /failed to fetch/i.test(message)) {
      return `${message}\nDica: rode 'python token_server.py' na pasta Project e confirme VITE_LIVEKIT_TOKEN_ENDPOINT.`;
    }

    if (/notallowederror|permission denied|permission dismissed/i.test(message)) {
      return 'Permissao de microfone negada no navegador. Libere o microfone e tente novamente.';
    }

    return message;
  }
  return 'Falha desconhecida na sessao LiveKit.';
};

export interface LivekitSessionController {
  state: SessionState;
  session: SessionInfo;
  messages: ChatMessage[];
  liveCaption: string;
  errorMessage: string | null;
  assistantConnected: boolean;
  isMuted: boolean;
  isCameraOn: boolean;
  localVideoTrack: LocalVideoTrack | null;
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  toggleMute: () => Promise<void>;
  toggleCamera: () => Promise<void>;
  sendMessage: (message: string) => Promise<void>;
  clearError: () => void;
}

export function useLivekitSession(): LivekitSessionController {
  const roomRef = useRef<Room | null>(null);
  const cleanupListenersRef = useRef<(() => void) | null>(null);
  const audioElementsRef = useRef<Map<string, HTMLAudioElement>>(new Map());
  const localVideoTrackRef = useRef<LocalVideoTrack | null>(null);
  const processedTranscriptionsRef = useRef<Set<string>>(new Set());
  const pendingSpeakingTimeoutRef = useRef<number | null>(null);
  const assistantWaitTimeoutRef = useRef<number | null>(null);
  const isMutedRef = useRef(true);
  const identityRef = useRef(getOrCreateIdentity());

  const [state, setState] = useState<SessionState>('idle');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [liveCaption, setLiveCaption] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [assistantConnected, setAssistantConnected] = useState(false);
  const [isMuted, setIsMuted] = useState(true);
  const [isCameraOn, setIsCameraOn] = useState(false);
  const [localVideoTrack, setLocalVideoTrack] = useState<LocalVideoTrack | null>(null);
  const [sessionStartedAt, setSessionStartedAt] = useState<Date>(new Date());
  const [sessionDurationSeconds, setSessionDurationSeconds] = useState(0);
  const [sessionId, setSessionId] = useState(() => createId());

  const clearPendingSpeakingTimeout = () => {
    if (pendingSpeakingTimeoutRef.current !== null) {
      window.clearTimeout(pendingSpeakingTimeoutRef.current);
      pendingSpeakingTimeoutRef.current = null;
    }
  };

  const clearAssistantWaitTimeout = () => {
    if (assistantWaitTimeoutRef.current !== null) {
      window.clearTimeout(assistantWaitTimeoutRef.current);
      assistantWaitTimeoutRef.current = null;
    }
  };

  const scheduleBackToListening = useCallback(() => {
    clearPendingSpeakingTimeout();
    pendingSpeakingTimeoutRef.current = window.setTimeout(() => {
      setState((current) => {
        if (current === 'error' || current === 'idle' || current === 'connecting') {
          return current;
        }
        return isMutedRef.current ? 'connected' : 'listening';
      });
    }, 1400);
  }, []);

  const appendMessage = useCallback((message: ChatMessage) => {
    setMessages((current) => {
      if (current.some((item) => item.id === message.id)) {
        return current;
      }
      return [...current, message];
    });
  }, []);

  const detachAndRemoveAllAudioElements = useCallback(() => {
    for (const [trackSid, audioElement] of audioElementsRef.current) {
      try {
        audioElement.pause();
        audioElement.remove();
      } catch {
        // noop
      }
      audioElementsRef.current.delete(trackSid);
    }
  }, []);

  const cleanupRoom = useCallback(async (room: Room | null) => {
    clearPendingSpeakingTimeout();
    clearAssistantWaitTimeout();
    cleanupListenersRef.current?.();
    cleanupListenersRef.current = null;

    detachAndRemoveAllAudioElements();
    processedTranscriptionsRef.current.clear();

    const track = localVideoTrackRef.current;
    if (track) {
      track.detach();
      track.stop();
      localVideoTrackRef.current = null;
    }
    setLocalVideoTrack(null);
    setIsCameraOn(false);
    setAssistantConnected(false);

    if (room) {
      try {
        await room.disconnect(true);
      } catch {
        // noop
      }
    }
    roomRef.current = null;
  }, [detachAndRemoveAllAudioElements]);

  const connect = useCallback(async () => {
    if (roomRef.current) {
      return;
    }

    setErrorMessage(null);
    setState('connecting');
    setLiveCaption('');
    setMessages([]);
    setAssistantConnected(false);
    setSessionId(createId());
    setSessionStartedAt(new Date());
    setSessionDurationSeconds(0);

    try {
      assertLivekitConfig();

      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
        stopLocalTrackOnUnpublish: true,
      });

      roomRef.current = room;

      const onConnected = () => {
        setErrorMessage(null);
        setState('connected');
      };

      const onConnectionStateChanged = (connection: ConnectionState) => {
        if (connection === ConnectionState.Connecting || connection === ConnectionState.Reconnecting) {
          setState('connecting');
          return;
        }

        if (connection === ConnectionState.Connected) {
          setState((current) => (current === 'idle' ? 'connected' : current));
          return;
        }

        if (connection === ConnectionState.Disconnected) {
          setState('idle');
        }
      };

      const onDisconnected = (reason?: DisconnectReason) => {
        clearAssistantWaitTimeout();
        setLiveCaption('');
        setAssistantConnected(false);
        if (reason) {
          setErrorMessage(`Sessao encerrada (${reason}).`);
        }
        setState('idle');
      };

      const onParticipantConnected = (participant: Participant) => {
        if (!participant.isLocal) {
          setAssistantConnected(true);
          clearAssistantWaitTimeout();
          setLiveCaption('Assistente conectado.');
          window.setTimeout(() => {
            setLiveCaption((current) => (current === 'Assistente conectado.' ? '' : current));
          }, 1500);
        }
      };

      const onParticipantDisconnected = (participant: Participant) => {
        if (!participant.isLocal) {
          window.setTimeout(() => {
            setAssistantConnected(room.remoteParticipants.size > 0);
          }, 0);
          setLiveCaption('Assistente saiu da sala. Aguardando reconexao...');
        }
      };

      const onTrackSubscribed = (track: Track, _publication: unknown, participant: Participant) => {
        if (track.kind !== Track.Kind.Audio || participant.isLocal) {
          return;
        }
        setAssistantConnected(true);
        clearAssistantWaitTimeout();
        const audioElement = track.attach() as HTMLAudioElement;
        audioElement.autoplay = true;
        audioElement.muted = false;
        audioElement.volume = 1;
        audioElement.dataset.trackSid = track.sid;
        audioElement.style.display = 'none';
        document.body.appendChild(audioElement);
        audioElementsRef.current.set(track.sid, audioElement);

        // Alguns browsers exigem play() explicito mesmo apos attach/autoplay.
        void audioElement.play().catch(() => {
          setErrorMessage(
            'Audio remoto bloqueado pelo navegador. Clique na tela e tente reconectar.',
          );
        });
      };

      const onTrackUnsubscribed = (track: Track) => {
        const audioElement = audioElementsRef.current.get(track.sid);
        if (!audioElement) {
          return;
        }
        audioElement.pause();
        audioElement.remove();
        audioElementsRef.current.delete(track.sid);
      };

      const onActiveSpeakersChanged = (speakers: Participant[]) => {
        const assistantSpeaking = speakers.some((participant) => !participant.isLocal && participant.isSpeaking);
        const localSpeaking = speakers.some((participant) => participant.isLocal && participant.isSpeaking);

        if (assistantSpeaking) {
          setState('speaking');
          return;
        }

        if (localSpeaking) {
          setState('listening');
          return;
        }

        setState((current) => {
          if (current === 'error' || current === 'idle' || current === 'connecting' || current === 'thinking') {
            return current;
          }
          return isMutedRef.current ? 'connected' : 'listening';
        });
      };

      const onChatMessage = (message: LKChatMessage, participant?: Participant) => {
        const role = toRole(participant);
        appendMessage({
          id: `chat-${message.id}`,
          role,
          content: message.message,
          timestamp: new Date(message.timestamp),
          source: 'chat',
        });

        if (role === 'assistant') {
          setState('speaking');
          scheduleBackToListening();
        } else {
          setState('thinking');
        }
      };

      const onTranscriptionReceived = (segments: TranscriptionSegment[], participant?: Participant) => {
        if (!segments.length) {
          return;
        }
        const role = toRole(participant);

        for (const segment of segments) {
          if (!segment.final) {
            setLiveCaption(role === 'user' ? `Voce: ${segment.text}` : `Assistente: ${segment.text}`);
            setState(role === 'user' ? 'listening' : 'speaking');
            continue;
          }

          if (processedTranscriptionsRef.current.has(segment.id)) {
            continue;
          }
          processedTranscriptionsRef.current.add(segment.id);
          setLiveCaption('');

          appendMessage({
            id: `tx-${segment.id}`,
            role,
            content: segment.text,
            timestamp: new Date(),
            source: 'transcription',
          });

          if (role === 'assistant') {
            setState('speaking');
            scheduleBackToListening();
          } else {
            setState('thinking');
          }
        }
      };

      room.on(RoomEvent.Connected, onConnected);
      room.on(RoomEvent.ConnectionStateChanged, onConnectionStateChanged);
      room.on(RoomEvent.Disconnected, onDisconnected);
      room.on(RoomEvent.ParticipantConnected, onParticipantConnected);
      room.on(RoomEvent.ParticipantDisconnected, onParticipantDisconnected);
      room.on(RoomEvent.TrackSubscribed, onTrackSubscribed);
      room.on(RoomEvent.TrackUnsubscribed, onTrackUnsubscribed);
      room.on(RoomEvent.ActiveSpeakersChanged, onActiveSpeakersChanged);
      room.on(RoomEvent.ChatMessage, onChatMessage);
      room.on(RoomEvent.TranscriptionReceived, onTranscriptionReceived);

      cleanupListenersRef.current = () => {
        room.off(RoomEvent.Connected, onConnected);
        room.off(RoomEvent.ConnectionStateChanged, onConnectionStateChanged);
        room.off(RoomEvent.Disconnected, onDisconnected);
        room.off(RoomEvent.ParticipantConnected, onParticipantConnected);
        room.off(RoomEvent.ParticipantDisconnected, onParticipantDisconnected);
        room.off(RoomEvent.TrackSubscribed, onTrackSubscribed);
        room.off(RoomEvent.TrackUnsubscribed, onTrackUnsubscribed);
        room.off(RoomEvent.ActiveSpeakersChanged, onActiveSpeakersChanged);
        room.off(RoomEvent.ChatMessage, onChatMessage);
        room.off(RoomEvent.TranscriptionReceived, onTranscriptionReceived);
      };

      if (typeof window !== 'undefined') {
        const tokenUrl = new URL(livekitConfig.tokenEndpoint, window.location.origin);
        const pageHost = window.location.hostname;
        const tokenHost = tokenUrl.hostname;
        const pageIsLocal = pageHost === 'localhost' || pageHost === '127.0.0.1';
        const tokenIsLocal = tokenHost === 'localhost' || tokenHost === '127.0.0.1';

        if (tokenIsLocal && !pageIsLocal) {
          throw new Error(
            `Endpoint de token invalido para ambiente hospedado: ${livekitConfig.tokenEndpoint}. Configure um endpoint HTTPS publico.`,
          );
        }
      }

      const tokenResponse = await requestLivekitToken(livekitConfig.tokenEndpoint, {
        identity: identityRef.current,
        room: livekitConfig.roomName,
        metadata: {
          user_id: identityRef.current,
          source: 'voice-interface-studio',
        },
      });

      const livekitUrl = tokenResponse.url || livekitConfig.url;
      await room.connect(livekitUrl, tokenResponse.token, {
        autoSubscribe: true,
      });
      setAssistantConnected(room.remoteParticipants.size > 0);

      const dispatchEndpoint = resolveDispatchEndpoint(livekitConfig.tokenEndpoint);
      try {
        await requestLivekitDispatch(dispatchEndpoint, {
          room: tokenResponse.room || livekitConfig.roomName,
          metadata: {
            user_id: identityRef.current,
            source: 'voice-interface-studio',
          },
          force_new: true,
        });
      } catch (dispatchError) {
        setErrorMessage(
          `${toHumanError(dispatchError)}\nSem dispatch, o agente nao entra na sala.`,
        );
      }

      await room.startAudio();
      await room.localParticipant.setMicrophoneEnabled(true);

      isMutedRef.current = false;
      setIsMuted(false);
      setState('listening');

      if (room.remoteParticipants.size === 0) {
        setLiveCaption('Conectado. Aguardando agente entrar na sala...');
      }

      clearAssistantWaitTimeout();
      assistantWaitTimeoutRef.current = window.setTimeout(() => {
        if (!roomRef.current || roomRef.current !== room) {
          return;
        }
        if (room.remoteParticipants.size === 0) {
          setErrorMessage(
            'Conectado ao LiveKit, mas nenhum agente entrou na sala. Suba o agent.py e reconecte.',
          );
          setState('connected');
        }
      }, ASSISTANT_JOIN_TIMEOUT_MS);
    } catch (error) {
      const message = toHumanError(error);
      setErrorMessage(message);
      setState('error');
      await cleanupRoom(roomRef.current);
    }
  }, [appendMessage, cleanupRoom, scheduleBackToListening]);

  const disconnect = useCallback(async () => {
    setLiveCaption('');
    setErrorMessage(null);
    clearAssistantWaitTimeout();
    await cleanupRoom(roomRef.current);
    isMutedRef.current = true;
    setIsMuted(true);
    setState('idle');
  }, [cleanupRoom]);

  const toggleMute = useCallback(async () => {
    const room = roomRef.current;
    if (!room) {
      return;
    }

    try {
      const nextMuted = !isMutedRef.current;
      await room.localParticipant.setMicrophoneEnabled(!nextMuted);
      isMutedRef.current = nextMuted;
      setIsMuted(nextMuted);
      setState(nextMuted ? 'connected' : 'listening');
    } catch (error) {
      setErrorMessage(toHumanError(error));
      setState('error');
    }
  }, []);

  const toggleCamera = useCallback(async () => {
    const room = roomRef.current;
    if (!room) {
      return;
    }

    try {
      const nextEnabled = !isCameraOn;
      const publication = await room.localParticipant.setCameraEnabled(nextEnabled);

      if (nextEnabled) {
        const track = publication?.track;
        if (track instanceof LocalVideoTrack) {
          localVideoTrackRef.current = track;
          setLocalVideoTrack(track);
        }
        setIsCameraOn(true);
      } else {
        if (localVideoTrackRef.current) {
          localVideoTrackRef.current.detach();
          localVideoTrackRef.current.stop();
        }
        localVideoTrackRef.current = null;
        setLocalVideoTrack(null);
        setIsCameraOn(false);
      }
    } catch (error) {
      setErrorMessage(toHumanError(error));
      setState('error');
    }
  }, [isCameraOn]);

  const sendMessage = useCallback(async (message: string) => {
    const room = roomRef.current;
    if (!room) {
      throw new Error('Sessao nao conectada.');
    }

    setState('thinking');
    try {
      const sent = await room.localParticipant.sendChatMessage(message);
      appendMessage({
        id: `chat-${sent.id}`,
        role: 'user',
        content: sent.message,
        timestamp: new Date(sent.timestamp),
        source: 'chat',
      });
    } catch (error) {
      setErrorMessage(toHumanError(error));
      setState('error');
    }
  }, [appendMessage]);

  const clearError = useCallback(() => {
    setErrorMessage(null);
    setState((current) => (current === 'error' ? 'idle' : current));
  }, []);

  useEffect(() => {
    if (state === 'idle' || state === 'error' || state === 'connecting') {
      return;
    }

    const timer = window.setInterval(() => {
      setSessionDurationSeconds(Math.max(0, Math.floor((Date.now() - sessionStartedAt.getTime()) / 1000)));
    }, 1000);

    return () => window.clearInterval(timer);
  }, [sessionStartedAt, state]);

  useEffect(() => {
    return () => {
      void cleanupRoom(roomRef.current);
    };
  }, [cleanupRoom]);

  const session = useMemo<SessionInfo>(() => ({
    id: sessionId,
    startedAt: sessionStartedAt,
    duration: sessionDurationSeconds,
    state,
  }), [sessionDurationSeconds, sessionId, sessionStartedAt, state]);

  return {
    state,
    session,
    messages,
    liveCaption,
    errorMessage,
    assistantConnected,
    isMuted,
    isCameraOn,
    localVideoTrack,
    connect,
    disconnect,
    toggleMute,
    toggleCamera,
    sendMessage,
    clearError,
  };
}
