"""Agent PULSE otimizado com memoria, reasoning e visao integrados."""

import asyncio
import json
import logging
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 14):
    raise SystemExit(
        "Python 3.14 nao e suportado por parte das dependencias atuais deste projeto. "
        "Use Python 3.11, 3.12 ou 3.13."
    )

from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import Agent, AgentSession, RoomInputOptions
from livekit.agents.utils import images as lk_images
from livekit.plugins import google, noise_cancellation

from memory_system import MemorySystem
from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION
from reasoning_system import ReasoningMode, get_reasoning_system
from vision import get_vision_system

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "KMS" / "logs"
LOG_FILE = LOG_DIR / "pulse_agent.log"
LOGGER_NAME = "pulse_agent"
PULSE_SIGNATURE_VOICE = "Pulcherrima"
DEFAULT_USER_ID = "default_user"
REQUIRED_ENV_VARS = (
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "GOOGLE_API_KEY",
)


@dataclass(frozen=True)
class RuntimeConfig:
    voice: str
    temperature: float
    video_enabled: bool
    memory_enabled: bool
    reasoning_enabled: bool
    vision_enabled: bool


@dataclass
class FrameSnapshotBuffer:
    """Mantem o ultimo frame da camera convertido para JPEG."""

    jpeg_bytes: bytes | None = None
    captured_at_monotonic: float = 0.0

    def update(self, frame: rtc.VideoFrame) -> None:
        try:
            self.jpeg_bytes = lk_images.encode(
                frame,
                lk_images.EncodeOptions(format="JPEG", quality=80),
            )
            self.captured_at_monotonic = time.monotonic()
        except Exception:
            # Nao bloqueia o pipeline de audio/video por falha de encode
            return

    def get_latest(self, *, max_age_seconds: float = 5.0) -> bytes | None:
        if not self.jpeg_bytes:
            return None
        if (time.monotonic() - self.captured_at_monotonic) > max_age_seconds:
            return None
        return self.jpeg_bytes


class FrameCaptureVideoSampler:
    """Sampler de video com throttling, guardando o ultimo frame localmente."""

    def __init__(
        self,
        frame_buffer: FrameSnapshotBuffer,
        *,
        speaking_fps: float = 1.0,
        silent_fps: float = 0.3,
    ) -> None:
        self._frame_buffer = frame_buffer
        self._speaking_fps = speaking_fps
        self._silent_fps = silent_fps
        self._last_sampled_time: float | None = None

    def __call__(self, frame: rtc.VideoFrame, session: AgentSession) -> bool:
        now = time.monotonic()
        is_speaking = getattr(session, "user_state", None) == "speaking"
        target_fps = self._speaking_fps if is_speaking else self._silent_fps

        if target_fps <= 0:
            return False

        min_interval = 1.0 / target_fps
        if self._last_sampled_time is None or (now - self._last_sampled_time) >= min_interval:
            self._last_sampled_time = now
            self._frame_buffer.update(frame)
            return True

        return False


def configure_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


def parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_temperature(value: str | None, *, default: float) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
    except ValueError as exc:
        raise RuntimeError("PULSE_TEMPERATURE precisa ser um numero decimal valido.") from exc

    if not 0 <= parsed <= 2:
        raise RuntimeError("PULSE_TEMPERATURE precisa estar entre 0 e 2.")
    return parsed


def load_runtime_config() -> RuntimeConfig:
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise RuntimeError("Variaveis obrigatorias ausentes no ambiente: " + ", ".join(missing))

    return RuntimeConfig(
        voice=PULSE_SIGNATURE_VOICE,
        temperature=parse_temperature(os.getenv("PULSE_TEMPERATURE"), default=0.7),
        video_enabled=parse_bool(os.getenv("PULSE_VIDEO_ENABLED"), default=True),
        memory_enabled=parse_bool(os.getenv("PULSE_MEMORY_ENABLED"), default=True),
        reasoning_enabled=parse_bool(os.getenv("PULSE_REASONING_ENABLED"), default=True),
        vision_enabled=parse_bool(os.getenv("PULSE_VISION_ENABLED"), default=True),
    )


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


def resolve_user_id(room_metadata: str | None) -> str:
    """Room.metadata no SDK e string; pode vir JSON ou valor simples."""
    if not room_metadata:
        return DEFAULT_USER_ID

    raw = room_metadata.strip()
    if not raw:
        return DEFAULT_USER_ID

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            candidate = parsed.get("user_id")
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
            return DEFAULT_USER_ID
    except json.JSONDecodeError:
        pass

    return raw if len(raw) <= 128 else DEFAULT_USER_ID


class OptimizedAssistant(Agent):
    """Assistente com sistemas auxiliares integrados ao fluxo de sessao."""

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        frame_buffer: FrameSnapshotBuffer,
        user_id: str = DEFAULT_USER_ID,
        session_id: str | None = None,
    ) -> None:
        self.config = config
        self.user_id = user_id
        self.logger = logging.getLogger(LOGGER_NAME)
        self.frame_buffer = frame_buffer

        self.memory = None
        self.session_id = None
        self.memory_context = ""
        self.reasoning = None
        self.analytics = None
        self.reasoning_mode_deep = None
        self.vision = None

        self._pending_user_meta: deque[dict[str, Any]] = deque()
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._aux_lock = asyncio.Lock()
        self._latest_vision_hint = ""
        self._shutting_down = False

        if config.memory_enabled:
            try:
                self.memory = MemorySystem()
                if session_id and session_id in self.memory.active_sessions:
                    self.session_id = session_id
                else:
                    self.session_id = self.memory.create_session(user_id)
                self.memory_context = self.memory.get_context_for_session(
                    user_id,
                    include_days=7,
                    max_conversations=3,
                    max_facts=10,
                )
                self.logger.info("Memoria carregada: %s chars de contexto", len(self.memory_context))
            except Exception:
                self.logger.exception("Falha ao inicializar memoria.")
                self.memory = None
                self.session_id = None
                self.memory_context = ""

        if config.reasoning_enabled:
            try:
                self.reasoning = get_reasoning_system()
                from reasoning_system import get_analytics

                self.analytics = get_analytics()
                self.reasoning_mode_deep = ReasoningMode.REASONING_DEEP
            except Exception:
                self.logger.exception("Falha ao inicializar reasoning.")
                self.reasoning = None
                self.analytics = None
                self.reasoning_mode_deep = None

        if config.vision_enabled:
            try:
                self.vision = get_vision_system()
                self.logger.info("Sistema de visao ativado")
            except Exception:
                self.logger.exception("Falha ao inicializar visao.")
                self.vision = None

        super().__init__(
            instructions=self._build_enhanced_instruction(),
            llm=google.beta.realtime.RealtimeModel(
                voice=config.voice,
                temperature=config.temperature,
            ),
        )

        self.logger.info("OptimizedAssistant inicializado para usuario %s", user_id)

    def _build_enhanced_instruction(self) -> str:
        parts = [AGENT_INSTRUCTION]

        if self.memory_context:
            parts.append("\n---\n")
            parts.append(self.memory_context)
            parts.append("\n---\n")
            parts.append(
                "Use o contexto acima pra personalizar as respostas "
                "e manter continuidade entre sessoes."
            )

        if self.vision:
            parts.append("\n---\n")
            parts.append(
                "VISAO ATIVADA: Voce pode ver o que a camera mostra. "
                "Se o usuario perguntar 'o que voce ve' ou mostrar algo, "
                "descreva de forma natural e direta."
            )

        if self._latest_vision_hint:
            parts.append("\n---\n")
            parts.append(
                "CONTEXTO VISUAL RECENTE: "
                f"{self._latest_vision_hint}\n"
                "Use esse contexto quando a pergunta atual for sobre o que esta sendo mostrado."
            )

        return "\n".join(parts)

    async def on_user_turn_completed(self, turn_ctx, new_message) -> None:
        """Hook mantido para compatibilidade; o fluxo principal usa eventos da sessao."""
        return

    def track_background_task(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.add(task)

        def _cleanup(done_task: asyncio.Task[Any]) -> None:
            self._background_tasks.discard(done_task)
            if done_task.cancelled():
                return
            exc = done_task.exception()
            if exc is not None:
                self.logger.exception("Task de background falhou: %s", exc)

        task.add_done_callback(_cleanup)

    def _ensure_memory_session(self) -> bool:
        if not self.memory or self._shutting_down:
            return False
        if self.session_id and self.session_id in self.memory.active_sessions:
            return True

        self.session_id = self.memory.create_session(self.user_id)
        self.logger.warning(
            "Sessao de memoria ausente. Nova sessao criada: %s",
            self.session_id[:8],
        )
        return True

    def _safe_memory_add_turn(
        self,
        *,
        role: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        reasoning_used: bool = False,
    ) -> None:
        if not self.memory or self._shutting_down:
            return

        for _ in range(2):
            if not self._ensure_memory_session():
                return

            try:
                self.memory.add_turn(
                    session_id=self.session_id,  # type: ignore[arg-type]
                    role=role,
                    text=text,
                    metadata=metadata,
                    reasoning_used=reasoning_used,
                )
                return
            except ValueError as exc:
                self.logger.warning(
                    "Sessao de memoria invalida durante add_turn (%s). Recriando...",
                    exc,
                )
                self.session_id = None
            except Exception:
                self.logger.exception("Falha inesperada ao adicionar turno na memoria.")
                return

        self.logger.error("Nao foi possivel adicionar turno na memoria apos retentativa.")

    def on_conversation_item_added(self, item: Any) -> None:
        if self._shutting_down:
            return

        role = getattr(item, "role", None)
        text = (getattr(item, "text_content", None) or "").strip()
        if not role or not text:
            return

        if role == "user":
            task = asyncio.create_task(self._handle_user_message(text))
            self.track_background_task(task)
        elif role == "assistant":
            task = asyncio.create_task(self._handle_assistant_message(text))
            self.track_background_task(task)

    async def _handle_user_message(self, text: str) -> None:
        try:
            async with self._aux_lock:
                reasoning_used = False
                mode_value = "realtime"
                vision_objects: list[str] = []
                had_vision = False
                reasoning_preview = ""

                if self.reasoning and self.reasoning_mode_deep:
                    selected_mode = self.reasoning._select_mode(text)
                    reasoning_used = selected_mode == self.reasoning_mode_deep
                    mode_value = selected_mode.value

                image_data = self.frame_buffer.get_latest(max_age_seconds=5.0)
                should_run_aux = bool(
                    self.reasoning
                    and (
                        reasoning_used
                        or (
                            self.vision
                            and image_data is not None
                            and self.vision.should_analyze_frame(text)
                        )
                    )
                )

                if should_run_aux:
                    result = await self.process_with_vision(
                        user_input=text,
                        image_data=image_data,
                        persist_memory=False,
                    )
                    mode_value = result.get("mode", mode_value)
                    reasoning_used = bool(
                        self.reasoning_mode_deep
                        and mode_value == self.reasoning_mode_deep.value
                    )

                    vision_result = result.get("vision_result") or {}
                    had_vision = bool(vision_result)
                    vision_objects = vision_result.get("objects", []) or []
                    reasoning_preview = (result.get("text") or "").strip()[:600]

                    if had_vision and vision_result.get("description"):
                        self._latest_vision_hint = str(vision_result["description"]).strip()
                        try:
                            await self.update_instructions(self._build_enhanced_instruction())
                        except Exception:
                            self.logger.debug("Falha ao atualizar instrucoes com contexto visual.")

                self._pending_user_meta.append(
                    {
                        "mode": mode_value,
                        "reasoning_used": reasoning_used,
                        "had_vision": had_vision,
                        "vision_objects": vision_objects,
                        "reasoning_preview": reasoning_preview,
                    }
                )
                self._safe_memory_add_turn(
                    role="user",
                    text=text,
                    metadata={"mode": mode_value, "had_vision": had_vision},
                    reasoning_used=reasoning_used,
                )
        except Exception:
            self.logger.exception("Falha ao processar mensagem do usuario.")

    async def _handle_assistant_message(self, text: str) -> None:
        try:
            meta = self._pending_user_meta.popleft() if self._pending_user_meta else {}
            metadata: dict[str, Any] = {"mode": meta.get("mode", "realtime")}
            if meta.get("vision_objects"):
                metadata["vision_objects"] = meta["vision_objects"]
            if meta.get("reasoning_preview"):
                metadata["reasoning_preview"] = meta["reasoning_preview"]

            self._safe_memory_add_turn(
                role="assistant",
                text=text,
                metadata=metadata,
                reasoning_used=bool(meta.get("reasoning_used", False)),
            )
        except Exception:
            self.logger.exception("Falha ao processar mensagem do assistente.")

    async def process_with_vision(
        self,
        user_input: str,
        image_data: bytes | None = None,
        *,
        persist_memory: bool = True,
    ) -> dict[str, Any]:
        """Processa mensagem com visao opcional e reasoning seletivo."""
        result: dict[str, Any] = {
            "text": "",
            "thinking": None,
            "mode": "voice_fast",
            "tools_used": [],
            "vision_result": None,
            "confidence": 0.0,
        }

        vision_description = None
        if self.vision and image_data and self.vision.should_analyze_frame(user_input):
            self.logger.info("Acionando visao computacional...")
            vision_result = await self.vision.analyze_frame(
                image_data=image_data,
                context=self.memory_context,
                user_query=user_input,
            )

            vision_description = vision_result.description
            result["vision_result"] = {
                "description": vision_description,
                "objects": vision_result.objects_detected,
                "confidence": vision_result.confidence,
            }
            user_input_enhanced = f"{user_input}\n\n[VISAO: {vision_description}]"
        else:
            user_input_enhanced = user_input

        if not self.reasoning:
            result["text"] = "Reasoning desabilitado."
            return result

        reasoning_result = await self.reasoning.process(
            user_input=user_input_enhanced,
            context=self.memory_context,
        )

        result.update(
            {
                "text": reasoning_result.text,
                "thinking": reasoning_result.thinking,
                "mode": reasoning_result.mode.value,
                "tools_used": reasoning_result.tools_used or [],
                "confidence": reasoning_result.confidence,
            }
        )

        if persist_memory and self.memory and not self._shutting_down:
            reasoning_used = bool(
                self.reasoning_mode_deep and reasoning_result.mode == self.reasoning_mode_deep
            )

            self._safe_memory_add_turn(
                role="user",
                text=user_input,
                metadata={
                    "mode": reasoning_result.mode.value,
                    "had_vision": bool(vision_description),
                },
                reasoning_used=reasoning_used,
            )

            self._safe_memory_add_turn(
                role="assistant",
                text=reasoning_result.text,
                metadata={
                    "thinking": reasoning_result.thinking,
                    "vision_objects": (result.get("vision_result") or {}).get("objects", []),
                },
                reasoning_used=reasoning_used,
            )

        return result

    async def finalize_session(self, rating: int | None = None) -> None:
        self._shutting_down = True

        if self._background_tasks:
            tasks = list(self._background_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

        if self.memory and self.session_id:
            self.memory.end_session(self.session_id, rating=rating)
            self.logger.info("Sessao %s finalizada", self.session_id[:8])
            self.session_id = None


async def entrypoint(ctx: agents.JobContext) -> None:
    logger = configure_logging()
    config = load_runtime_config()
    frame_buffer = FrameSnapshotBuffer()

    user_id = resolve_user_id(getattr(ctx.room, "metadata", ""))

    logger.info(
        "Iniciando sessao OTIMIZADA. user_id=%s video=%s vision=%s memory=%s reasoning=%s",
        user_id,
        config.video_enabled,
        config.vision_enabled,
        config.memory_enabled,
        config.reasoning_enabled,
    )

    optimized_agent = OptimizedAssistant(
        config=config,
        user_id=user_id,
        frame_buffer=frame_buffer,
    )

    if config.video_enabled:
        session = AgentSession(video_sampler=FrameCaptureVideoSampler(frame_buffer))
    else:
        session = AgentSession()

    def _on_conversation_item_added(ev) -> None:
        try:
            optimized_agent.on_conversation_item_added(ev.item)
        except Exception:
            logger.exception("Falha ao processar evento conversation_item_added.")

    session.on("conversation_item_added", _on_conversation_item_added)

    try:
        await ctx.connect()
        await session.start(
            room=ctx.room,
            agent=optimized_agent,
            room_input_options=RoomInputOptions(
                video_enabled=config.video_enabled,
                noise_cancellation=noise_cancellation.BVC(),
            ),
        )

        if config.memory_enabled and optimized_agent.memory_context:
            greeting = "E ai! Bom te ver de novo. Bora resolver uns codigos?"
        else:
            greeting = SESSION_INSTRUCTION

        await session.generate_reply(instructions=greeting)

    except Exception:
        logger.exception("Falha durante execucao da sessao do agente.")
        raise
    finally:
        if config.memory_enabled:
            await optimized_agent.finalize_session()


if __name__ == "__main__":
    load_dotenv()
    logger = configure_logging()

    try:
        load_runtime_config()
    except RuntimeError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc

    logger.info("Configuracao validada. Subindo worker LiveKit OTIMIZADO.")
    ensure_event_loop()
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
