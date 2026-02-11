import asyncio
import logging
import os
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv
from livekit import agents
from livekit.agents import Agent, AgentSession, RoomInputOptions
from livekit.plugins import google, noise_cancellation

from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "KMS" / "logs"
LOG_FILE = LOG_DIR / "pulse_agent.log"
LOGGER_NAME = "pulse_agent"
PULSE_SIGNATURE_VOICE = "Pulcherrima"
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


def configure_logging() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

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
        raise RuntimeError(
            "PULSE_TEMPERATURE precisa ser um numero decimal valido."
        ) from exc

    if not 0 <= parsed <= 2:
        raise RuntimeError("PULSE_TEMPERATURE precisa estar entre 0 e 2.")
    return parsed


def load_runtime_config() -> RuntimeConfig:
    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise RuntimeError(
            "Variaveis obrigatorias ausentes no ambiente: " + ", ".join(missing)
        )

    return RuntimeConfig(
        voice=PULSE_SIGNATURE_VOICE,
        temperature=parse_temperature(
            os.getenv("PULSE_TEMPERATURE"), default=0.6
        ),
        video_enabled=parse_bool(
            os.getenv("PULSE_VIDEO_ENABLED"), default=False
        ),
    )


def ensure_event_loop() -> asyncio.AbstractEventLoop:
    try:
        return asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop


class Assistant(Agent):
    def __init__(self, config: RuntimeConfig) -> None:
        super().__init__(
            instructions=AGENT_INSTRUCTION,
            llm=google.beta.realtime.RealtimeModel(
                voice=config.voice,
                temperature=config.temperature,
            ),
        )


async def entrypoint(ctx: agents.JobContext) -> None:
    logger = configure_logging()
    config = load_runtime_config()
    session = AgentSession()

    logger.info(
        "Iniciando sessao. voice=%s temperature=%.2f video_enabled=%s",
        config.voice,
        config.temperature,
        config.video_enabled,
    )

    try:
        await ctx.connect()
        await session.start(
            room=ctx.room,
            agent=Assistant(config),
            room_input_options=RoomInputOptions(
                video_enabled=config.video_enabled,
                noise_cancellation=noise_cancellation.BVC(),
            ),
        )
        await session.generate_reply(instructions=SESSION_INSTRUCTION)
    except Exception:
        logger.exception("Falha durante execucao da sessao do agente.")
        raise


if __name__ == "__main__":
    load_dotenv()
    logger = configure_logging()
    try:
        load_runtime_config()
    except RuntimeError as exc:
        logger.error(str(exc))
        raise SystemExit(1) from exc

    logger.info("Configuracao validada. Subindo worker LiveKit.")
    ensure_event_loop()
    agents.cli.run_app(agents.WorkerOptions(entrypoint_fnc=entrypoint))
