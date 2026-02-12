# pulseia

Monorepo com backend Python (agente PULSE) + frontend React (interface de voz).

## Estrutura

- `agent.py` - agente LiveKit (voz + memoria + reasoning + visao)
- `token_server.py` - servidor HTTP que gera token/dispatch do LiveKit
- `voice-interface-studio/` - frontend React + Vite

## Requisitos

- Python 3.11, 3.12 ou 3.13 (nao usar 3.14)
- Node.js 18+
- Conta LiveKit Cloud
- `GOOGLE_API_KEY`

## 1) Configurar backend (`.env`)

Copie `.env.example` para `.env` na raiz do projeto e preencha:

```env
LIVEKIT_URL=wss://SEU_PROJETO.livekit.cloud
LIVEKIT_API_KEY=SUA_API_KEY
LIVEKIT_API_SECRET=SUA_API_SECRET
GOOGLE_API_KEY=SUA_GOOGLE_API_KEY

LIVEKIT_DEFAULT_ROOM=pulse-room
CORS_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080
```

## 2) Configurar frontend (`voice-interface-studio/.env`)

Crie `voice-interface-studio/.env`:

```env
VITE_LIVEKIT_URL=wss://SEU_PROJETO.livekit.cloud
VITE_LIVEKIT_TOKEN_ENDPOINT=http://localhost:8787/api/livekit/token
VITE_LIVEKIT_ROOM=pulse-room
```

## 3) Instalar dependencias

### Backend

```powershell
cd Project
py -3.11 -m venv .venv311
.\.venv311\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### Frontend

```powershell
cd Project\voice-interface-studio
npm install
```

## 4) Rodar sem erro (ordem obrigatoria)

Use 3 terminais:

### Terminal A - Token server

```powershell
cd Project
.\.venv311\Scripts\Activate.ps1
python token_server.py
```

Healthcheck:

```powershell
curl http://localhost:8787/health
```

### Terminal B - Agente

```powershell
cd Project
.\.venv311\Scripts\Activate.ps1
python agent.py start
```

### Terminal C - Frontend

```powershell
cd Project\voice-interface-studio
npm run dev
```

Abra `http://localhost:8080`.

## Troubleshooting rapido

- `VITE_LIVEKIT_URL nao configurada`: faltou `voice-interface-studio/.env`.
- `ERR_CONNECTION_REFUSED` em `/api/livekit/token`: `token_server.py` nao esta rodando.
- `Falha ao obter token LiveKit (404)`: endpoint errado em `VITE_LIVEKIT_TOKEN_ENDPOINT`.
- `Conectado. Aguardando agente entrar na sala...`: subir `python agent.py start`.

## Arquivos sensiveis

- `.env` nao e versionado.
- `LIVEKIT_API_SECRET` fica somente no backend.
