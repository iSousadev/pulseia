# PULSE - LiveKit Agent com Memoria, Reasoning e Visao

Projeto de assistente de voz baseado em LiveKit com:
- Memoria persistente (ChromaDB)
- Reasoning adaptativo (Gemini)
- Visao computacional (Gemini Vision)
- Prompt customizavel

## Requisitos

- Python 3.11, 3.12 ou 3.13
- Python 3.14 nao suportado neste projeto (dependencias ainda instaveis)
- Conta LiveKit e Google API Key

## Estrutura principal

- `agent.py` - entrypoint do agente
- `prompts.py` - instrucoes do comportamento
- `memory_system.py` - memoria persistente
- `reasoning_system.py` - roteamento de raciocinio
- `vision.py` - analise de imagem e triggers de visao
- `test_system.py` - testes de memoria/reasoning
- `test_improvements.py` - validacao das melhorias recentes
- `memory_cli.py` - utilitarios de memoria

## Setup rapido (Windows)

```powershell
cd "C:\Users\rodol\OneDrive\Area de Trabalho\JarvisBot\Project"

# criar venv com Python 3.11
py -3.11 -m venv .venv311
.\.venv311\Scripts\Activate.ps1

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Configuracao de ambiente

1. Copie `.env.example` para `.env`
2. Preencha valores reais:

```env
LIVEKIT_URL=wss://...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
GOOGLE_API_KEY=...

PULSE_TEMPERATURE=0.7
PULSE_VIDEO_ENABLED=true
PULSE_VISION_ENABLED=true
PULSE_MEMORY_ENABLED=true
PULSE_REASONING_ENABLED=true
```

## Como rodar

### 1) Baixar assets do plugin

```powershell
python agent.py download-files
```

### 2) Rodar em desenvolvimento

```powershell
python agent.py dev
```

### 3) Rodar em console local (microfone)

```powershell
python agent.py console --list-devices
python agent.py console --input-device "Logitech G733"
```

### 4) Rodar testes de memoria/reasoning

```powershell
python test_system.py
```

### 5) Rodar validacao das melhorias

```powershell
python test_improvements.py
```

## Ferramentas de memoria

```powershell
python memory_cli.py list
python memory_cli.py stats default_user
python memory_cli.py context default_user
python memory_cli.py search default_user "fastapi"
```

## Troubleshooting

### Erro de Python 3.14

Use Python 3.11/3.12/3.13. O `agent.py` encerra com mensagem clara quando executado em 3.14.

### Erro de variaveis obrigatorias

Confirme se `.env` tem:
- `LIVEKIT_URL`
- `LIVEKIT_API_KEY`
- `LIVEKIT_API_SECRET`
- `GOOGLE_API_KEY`
- `PULSE_VIDEO_ENABLED`
- `PULSE_VISION_ENABLED`

### Erro de voz

As vozes dependem do modelo do Google. A assinatura atual do projeto esta fixa para `Pulcherrima`.

## Logs

- `KMS/logs/pulse_agent.log`
- `KMS/logs/reasoning_analytics.jsonl`

## Atualizacoes recentes

- Fluxo de visao/reasoning integrado ao runtime principal em `agent.py`.
- Gravacao de memoria mais robusta com recuperacao automatica de sessao quando necessario.
- Tratamento mais seguro de tasks assincronas para evitar falhas silenciosas em background.
- Ajustes de compatibilidade na chamada de visao para SDK atual em `vision.py`.
- Suite `test_improvements.py` atualizada para os modulos e configuracoes atuais.
