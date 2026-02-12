# Voice Interface Studio

Frontend React + Vite para conversar por voz com o agente PULSE via LiveKit.

## Requisitos

- Node.js 18+
- Python 3.11, 3.12 ou 3.13 (nao usar 3.14)
- Projeto backend `Project` (token server + `agent.py`) na mesma maquina
- Credenciais LiveKit Cloud e `GOOGLE_API_KEY`

## Variaveis de ambiente

### 1) Frontend (`voice-interface-studio/.env`)

Copie `.env.example` para `.env` e ajuste:

```env
VITE_LIVEKIT_URL=wss://SEU_PROJETO.livekit.cloud
VITE_LIVEKIT_TOKEN_ENDPOINT=http://localhost:8787/api/livekit/token
VITE_LIVEKIT_ROOM=pulse-room
```

### 2) Backend (`Project/.env`)

No repositorio backend (`Project`), configure:

```env
LIVEKIT_URL=wss://SEU_PROJETO.livekit.cloud
LIVEKIT_API_KEY=SUA_API_KEY
LIVEKIT_API_SECRET=SUA_API_SECRET
GOOGLE_API_KEY=SUA_GOOGLE_API_KEY

LIVEKIT_DEFAULT_ROOM=pulse-room
CORS_ALLOWED_ORIGINS=http://localhost:8080,http://127.0.0.1:8080
```

## Instalacao

### Frontend

```bash
cd voice-interface-studio
npm install
```

### Backend (Project)

```bash
cd Project
py -3.11 -m venv .venv311
.\.venv311\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Como rodar sem erro (ordem obrigatoria)

Use 3 terminais.

### Terminal 1 - Token server

```bash
cd Project
.\.venv311\Scripts\activate
python token_server.py
```

Teste rapido:

```bash
curl http://localhost:8787/health
```

Resposta esperada:

```json
{"status":"ok","version":"dispatch-v2"}
```

### Terminal 2 - Agente

```bash
cd Project
.\.venv311\Scripts\activate
python agent.py start
```

### Terminal 3 - Frontend

```bash
cd voice-interface-studio
npm run dev
```

Abrir: `http://localhost:8080`

## Build

```bash
npm run build
npm run preview
```

## Erros comuns

### `VITE_LIVEKIT_URL nao configurada`

Crie/ajuste `voice-interface-studio/.env` e reinicie `npm run dev`.

### `ERR_CONNECTION_REFUSED` no token endpoint

`token_server.py` nao esta rodando ou porta errada.

### `Falha ao obter token LiveKit (404)`

`VITE_LIVEKIT_TOKEN_ENDPOINT` esta mal formatada. Exemplo correto:
`http://localhost:8787/api/livekit/token`

### `Conectado. Aguardando agente entrar na sala...`

O frontend conectou, mas o agente nao entrou. Suba `python agent.py start`.

### Porta 8787 em uso

Suba token server em outra porta e atualize `.env` do frontend:

```bash
cd Project
.\.venv311\Scripts\activate
python -m uvicorn token_server:app --host 0.0.0.0 --port 8788
```

Depois ajuste:

```env
VITE_LIVEKIT_TOKEN_ENDPOINT=http://localhost:8788/api/livekit/token
```
