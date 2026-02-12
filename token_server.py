"""Token server para o frontend React obter JWT de acesso ao LiveKit."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import timedelta
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from livekit import api
from livekit.api.twirp_client import TwirpError

load_dotenv()
logger = logging.getLogger("pulse_token_server")


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Variavel de ambiente obrigatoria ausente: {name}")
    return value


LIVEKIT_URL = _required_env("LIVEKIT_URL")
LIVEKIT_API_KEY = _required_env("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = _required_env("LIVEKIT_API_SECRET")
DEFAULT_ROOM = os.getenv("LIVEKIT_DEFAULT_ROOM", "pulse-room").strip() or "pulse-room"
DEFAULT_TOKEN_TTL_SECONDS = 3600
MAX_TOKEN_TTL_SECONDS = 24 * 3600

raw_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:8080,http://127.0.0.1:8080,http://localhost:5173,http://127.0.0.1:5173",
)
ALLOWED_ORIGINS = [item.strip() for item in raw_origins.split(",") if item.strip()]

app = FastAPI(title="PULSE LiveKit Token Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TokenRequest(BaseModel):
    identity: str | None = None
    name: str | None = None
    room: str | None = None
    metadata: dict[str, Any] | None = None
    ttl_seconds: int = Field(default=DEFAULT_TOKEN_TTL_SECONDS, ge=60, le=MAX_TOKEN_TTL_SECONDS)


class TokenResponse(BaseModel):
    token: str
    url: str
    room: str
    identity: str


class DispatchRequest(BaseModel):
    room: str | None = None
    metadata: dict[str, Any] | None = None
    force_new: bool = False


class DispatchResponse(BaseModel):
    room: str
    dispatch_id: str
    created: bool


async def ensure_agent_dispatch(room_name: str, metadata: dict[str, Any] | None = None) -> tuple[str, bool]:
    """Garante que exista dispatch ativo para o agente entrar na sala."""
    async with api.LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lkapi:
        try:
            await lkapi.room.create_room(api.CreateRoomRequest(name=room_name))
        except TwirpError as exc:
            if exc.code != "already_exists":
                raise

        existing = await lkapi.agent_dispatch.list_dispatch(room_name)
        if existing:
            return existing[0].id, False

        dispatch_metadata = metadata or {}
        created = await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                room=room_name,
                metadata=json.dumps(dispatch_metadata),
            )
        )
        logger.info("Dispatch criado para sala %s", room_name)
        return created.id, True


async def force_new_agent_dispatch(
    room_name: str,
    metadata: dict[str, Any] | None = None,
) -> tuple[str, bool]:
    async with api.LiveKitAPI(
        url=LIVEKIT_URL,
        api_key=LIVEKIT_API_KEY,
        api_secret=LIVEKIT_API_SECRET,
    ) as lkapi:
        try:
            await lkapi.room.create_room(api.CreateRoomRequest(name=room_name))
        except TwirpError as exc:
            if exc.code != "already_exists":
                raise

        existing = await lkapi.agent_dispatch.list_dispatch(room_name)
        for dispatch in existing:
            await lkapi.agent_dispatch.delete_dispatch(dispatch.id, room_name)

        dispatch_metadata = metadata or {}
        created = await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                room=room_name,
                metadata=json.dumps(dispatch_metadata),
            )
        )
        logger.info("Dispatch recriado para sala %s", room_name)
        return created.id, True


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "dispatch-v2"}


@app.post("/api/livekit/token", response_model=TokenResponse)
async def create_token(payload: TokenRequest) -> TokenResponse:
    identity = (payload.identity or "").strip() or f"web-{uuid.uuid4().hex[:8]}"
    room_name = (payload.room or "").strip() or DEFAULT_ROOM
    participant_name = (payload.name or "").strip() or identity

    try:
        token = (
            api.AccessToken(api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
            .with_identity(identity)
            .with_name(participant_name)
            .with_metadata(json.dumps(payload.metadata or {"user_id": identity}))
            .with_ttl(timedelta(seconds=payload.ttl_seconds))
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                    can_publish_data=True,
                )
            )
            .to_jwt()
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Falha ao gerar token: {exc}") from exc

    try:
        await ensure_agent_dispatch(room_name, payload.metadata)
    except TwirpError as exc:
        # Em alguns ambientes a sala ainda nao existe neste momento; o frontend
        # faz o dispatch novamente apos conectar.
        if exc.code != "not_found":
            raise HTTPException(
                status_code=502,
                detail=f"Token gerado, mas falha ao criar dispatch do agente: {exc}",
            ) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=502,
            detail=f"Token gerado, mas falha ao criar dispatch do agente: {exc}",
        ) from exc

    return TokenResponse(token=token, url=LIVEKIT_URL, room=room_name, identity=identity)


@app.post("/api/livekit/dispatch", response_model=DispatchResponse)
async def dispatch_agent(payload: DispatchRequest) -> DispatchResponse:
    room_name = (payload.room or "").strip() or DEFAULT_ROOM

    try:
        if payload.force_new:
            dispatch_id, created = await force_new_agent_dispatch(room_name, payload.metadata)
        else:
            dispatch_id, created = await ensure_agent_dispatch(room_name, payload.metadata)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Falha ao criar dispatch: {exc}") from exc

    return DispatchResponse(room=room_name, dispatch_id=dispatch_id, created=created)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("token_server:app", host="0.0.0.0", port=8787, reload=False)
