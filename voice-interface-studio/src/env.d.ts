/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_LIVEKIT_URL: string;
  readonly VITE_LIVEKIT_TOKEN_ENDPOINT: string;
  readonly VITE_LIVEKIT_ROOM?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
