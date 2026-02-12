const trim = (value: string | undefined): string => (value ?? '').trim();

export const livekitConfig = {
  url: trim(import.meta.env.VITE_LIVEKIT_URL),
  tokenEndpoint: trim(import.meta.env.VITE_LIVEKIT_TOKEN_ENDPOINT),
  roomName: trim(import.meta.env.VITE_LIVEKIT_ROOM) || 'pulse-room',
};

export function assertLivekitConfig() {
  if (!livekitConfig.url) {
    throw new Error('VITE_LIVEKIT_URL nao configurada.');
  }
  if (!livekitConfig.tokenEndpoint) {
    throw new Error('VITE_LIVEKIT_TOKEN_ENDPOINT nao configurada.');
  }
}
