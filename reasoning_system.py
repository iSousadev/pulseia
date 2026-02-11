"""Sistema de raciocinio profundo para PULSE - OTIMIZADO."""

import asyncio
from datetime import datetime
import os
import logging
import json
import sys
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
import hashlib

if sys.version_info >= (3, 14):
    raise RuntimeError(
        "Python 3.14 nao e suportado por parte das dependencias atuais deste projeto. "
        "Use Python 3.11, 3.12 ou 3.13."
    )

from google import genai
from google.genai import types

logger = logging.getLogger("pulse_agent.reasoning")


class ReasoningMode(Enum):
    """Modos de processamento."""
    VOICE_FAST = "voice_fast"
    REASONING_DEEP = "reasoning_deep"
    HYBRID = "hybrid"


@dataclass
class ReasoningResult:
    """Resultado do processamento."""
    mode: ReasoningMode
    text: str
    thinking: Optional[str] = None
    tools_used: Optional[List[Dict]] = None
    confidence: float = 1.0
    execution_time_ms: int = 0


class ResponseCache:
    """Cache simples para respostas similares."""
    
    def __init__(self, max_size: int = 50):
        self.cache = {}
        self.max_size = max_size
    
    def _hash_key(self, text: str) -> str:
        """Gera hash da pergunta."""
        return hashlib.md5(text.lower().strip().encode()).hexdigest()[:12]
    
    def get(self, user_input: str) -> Optional[ReasoningResult]:
        """Busca resposta similar no cache."""
        key = self._hash_key(user_input)
        return self.cache.get(key)
    
    def set(self, user_input: str, result: ReasoningResult):
        """Salva resposta no cache."""
        if len(self.cache) >= self.max_size:
            # Remove entrada mais antiga
            oldest = next(iter(self.cache))
            del self.cache[oldest]
        
        key = self._hash_key(user_input)
        self.cache[key] = result
        logger.debug(f"Cache: salvou resposta para {key}")


class GeminiReasoningSystem:
    """Raciocinio adaptativo usando o SDK google-genai - OTIMIZADO."""

    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY nao encontrada")

        self.client = genai.Client(api_key=api_key)
        self.cache = ResponseCache(max_size=50)

        # OTIMIZAÃƒâ€¡ÃƒÆ’O: Usar mesmo modelo para ambos (mais rÃƒÂ¡pido)
        self.fast_model = "gemini-2.0-flash-exp"
        self.reasoning_model = "gemini-2.0-flash-exp"  # Mudado de 2.5 para 2.0 (mais rÃƒÂ¡pido)

        # OTIMIZAÃƒâ€¡ÃƒÆ’O: Tokens reduzidos para respostas mais rÃƒÂ¡pidas
        self.fast_config = types.GenerateContentConfig(
            temperature=0.7,  # Aumentado para mais naturalidade
            top_p=0.95,
            top_k=40,
            max_output_tokens=1024,  # Reduzido de 2048
        )

        self.reasoning_config = types.GenerateContentConfig(
            temperature=0.8,  # Mais criativo
            top_p=0.95,
            top_k=64,
            max_output_tokens=4096,  # Reduzido de 8192
            tools=[types.Tool(code_execution=types.ToolCodeExecution())],
            thinking_config=types.ThinkingConfig(
                include_thoughts=True,
                thinking_budget=1024,  # Reduzido de 2048 para mais velocidade
            ),
        )

        logger.info("Sistema de raciocinio OTIMIZADO inicializado")

    async def process(
        self,
        user_input: str,
        context: str,
        force_mode: Optional[ReasoningMode] = None,
    ) -> ReasoningResult:
        """Processa input com modo rapido ou profundo."""
        import time

        start_time = time.time()

        # OTIMIZAÃƒâ€¡ÃƒÆ’O: Verifica cache primeiro
        if not force_mode:
            cached = self.cache.get(user_input)
            if cached:
                logger.info("Cache HIT! Retornando resposta cacheada")
                cached.execution_time_ms = 5  # InstantÃƒÂ¢neo
                return cached

        complexity_score = self._compute_complexity_score(user_input)
        mode = force_mode if force_mode else self._select_mode(user_input)
        logger.info("Processando com modo: %s", mode.value)

        if mode == ReasoningMode.VOICE_FAST:
            result = await self._fast_response(user_input, context)
        else:
            result = await self._deep_reasoning(user_input, context)

        result.execution_time_ms = int((time.time() - start_time) * 1000)
        
        # OTIMIZAÃƒâ€¡ÃƒÆ’O: Salva no cache
        if not force_mode and result.confidence > 0.7:
            self.cache.set(user_input, result)
        
        logger.info(
            "Processamento concluido em %sms (modo: %s)",
            result.execution_time_ms,
            result.mode.value,
        )
        try:
            get_analytics().log_decision(
                user_input=user_input,
                selected_mode=mode,
                complexity_score=complexity_score,
                result=result,
            )
        except Exception as exc:
            logger.debug("Falha ao registrar analytics: %s", exc)
        return result

    def _compute_complexity_score(self, user_input: str) -> int:
        """Calcula score de complexidade para decidir o modo."""
        text_lower = user_input.lower()
        word_count = len(user_input.split())

        # OTIMIZACAO: Keywords mais especificas
        critical_keywords = [
            "debug", "debugar",
            "erro critico", "erro crítico", "exception", "traceback",
            "crash", "nao funciona de jeito nenhum", "não funciona de jeito nenhum",
            "comparar tecnologias", "qual biblioteca usar",
            "arquitetura do sistema", "design pattern",
            "otimizacao de performance", "otimização de performance", "bottleneck",
            "refatoracao complexa", "refatoração complexa", "algoritmo eficiente",
        ]

        has_code_block = "```" in user_input
        is_very_long = word_count > 60
        has_multiple_questions = user_input.count("?") > 2

        complexity_score = 0
        for keyword in critical_keywords:
            if keyword in text_lower:
                complexity_score += 3

        if has_code_block:
            complexity_score += 4
        if is_very_long:
            complexity_score += 3
        if has_multiple_questions:
            complexity_score += 3

        return complexity_score

    def _select_mode(self, user_input: str) -> ReasoningMode:
        """Heuristica OTIMIZADA - usa reasoning apenas quando REALMENTE necessario."""
        complexity_score = self._compute_complexity_score(user_input)

        # OTIMIZACAO: Threshold MUITO mais alto (8 ao inves de 5)
        if complexity_score >= 8:
            logger.debug("Complexity score: %s -> REASONING_DEEP", complexity_score)
            return ReasoningMode.REASONING_DEEP

        logger.debug("Complexity score: %s -> VOICE_FAST", complexity_score)
        return ReasoningMode.VOICE_FAST
    async def _fast_response(self, user_input: str, context: str) -> ReasoningResult:
        """Resposta rapida sem reasoning profundo."""
        prompt = self._build_fast_prompt(user_input, context)

        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.fast_model,
                contents=prompt,
                config=self.fast_config,
            )
            return ReasoningResult(
                mode=ReasoningMode.VOICE_FAST,
                text=response.text or "",
                thinking=None,
                tools_used=[],
                confidence=0.9,
            )
        except Exception as e:
            logger.error("Erro no fast response: %s", e)
            return ReasoningResult(
                mode=ReasoningMode.VOICE_FAST,
                text="Porra, deu ruim aqui. Tenta de novo?",
                confidence=0.0,
            )

    async def _deep_reasoning(self, user_input: str, context: str) -> ReasoningResult:
        """Raciocinio profundo com thinking e code execution."""
        prompt = self._build_reasoning_prompt(user_input, context)

        try:
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.reasoning_model,
                contents=prompt,
                config=self.reasoning_config,
            )

            final_text = response.text or ""
            thinking_parts: List[str] = []
            tools_used: List[Dict] = []

            if response.parts:
                for part in response.parts:
                    if part.thought and part.text:
                        thinking_parts.append(part.text.strip())

                    if part.executable_code is not None:
                        tools_used.append(
                            {
                                "type": "code_execution",
                                "code": part.executable_code.code,
                                "language": part.executable_code.language,
                            }
                        )

                    if part.code_execution_result is not None and tools_used:
                        tools_used[-1]["result"] = part.code_execution_result.output

            thinking = "\n\n".join(p for p in thinking_parts if p).strip() or None

            return ReasoningResult(
                mode=ReasoningMode.REASONING_DEEP,
                text=final_text,
                thinking=thinking,
                tools_used=tools_used,
                confidence=0.95,
            )
        except Exception as e:
            logger.error("Erro no deep reasoning: %s", e)
            return await self._fast_response(user_input, context)

    def _build_fast_prompt(self, user_input: str, context: str) -> str:
        """Monta prompt para resposta rapida."""
        from prompts import AGENT_INSTRUCTION

        return f"""
{AGENT_INSTRUCTION}

{context}

---

Responda de forma DIRETA, NATURAL e CASUAL. Sem formalidades.

Usuario: {user_input}
""".strip()

    def _build_reasoning_prompt(self, user_input: str, context: str) -> str:
        """Monta prompt para raciocinio profundo."""
        from prompts import AGENT_INSTRUCTION

        return f"""
{AGENT_INSTRUCTION}

{context}

---

# RACIOCINIO PROFUNDO

Problema tÃƒÂ©cnico complexo detectado. Pense estruturadamente:

<thinking>
1. ENTENDIMENTO: Qual ÃƒÂ© o problema exato?
2. ANÃƒÂLISE: Causas possÃƒÂ­veis
3. SOLUÃƒâ€¡ÃƒÆ’O: Melhor abordagem
4. VALIDAÃƒâ€¡ÃƒÆ’O: Como testar
</thinking>

<answer>
[Resposta clara e acionÃƒÂ¡vel]

**PrÃƒÂ³ximos passos:**
1. [AÃƒÂ§ÃƒÂ£o especÃƒÂ­fica]
2. [Como validar]
</answer>

Usuario: {user_input}
""".strip()


class ReasoningAnalytics:
    """Rastreia metricas do sistema de raciocinio."""

    def __init__(self, log_file: str = "KMS/logs/reasoning_analytics.jsonl"):
        self.log_file = log_file
        from pathlib import Path
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    def log_decision(
        self,
        user_input: str,
        selected_mode: ReasoningMode,
        complexity_score: int,
        result: ReasoningResult,
    ):
        """Registra decisao de modo para analise posterior."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "user_input_length": len(user_input),
            "word_count": len(user_input.split()),
            "selected_mode": selected_mode.value,
            "complexity_score": complexity_score,
            "execution_time_ms": result.execution_time_ms,
            "confidence": result.confidence,
            "tools_used_count": len(result.tools_used or []),
        }

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Erro ao logar analytics: %s", e)

    def get_stats(self) -> Dict:
        """Estatisticas de uso do sistema."""
        from pathlib import Path
        from collections import defaultdict

        if not Path(self.log_file).exists():
            return {}

        stats = {
            "total_requests": 0,
            "by_mode": defaultdict(int),
            "avg_time_ms": defaultdict(list),
            "avg_confidence": defaultdict(list),
        }

        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    entry = json.loads(line)
                    stats["total_requests"] += 1

                    mode = entry["selected_mode"]
                    stats["by_mode"][mode] += 1
                    stats["avg_time_ms"][mode].append(entry["execution_time_ms"])
                    stats["avg_confidence"][mode].append(entry["confidence"])

            for mode in stats["by_mode"].keys():
                stats["avg_time_ms"][mode] = sum(stats["avg_time_ms"][mode]) / len(
                    stats["avg_time_ms"][mode]
                )
                stats["avg_confidence"][mode] = sum(
                    stats["avg_confidence"][mode]
                ) / len(stats["avg_confidence"][mode])

            return dict(stats)
        except Exception as e:
            logger.error("Erro ao calcular stats: %s", e)
            return {}


_reasoning_system = None
_analytics = None


def get_reasoning_system() -> GeminiReasoningSystem:
    """Factory para sistema de raciocinio (singleton)."""
    global _reasoning_system
    if _reasoning_system is None:
        _reasoning_system = GeminiReasoningSystem()
    return _reasoning_system


def get_analytics() -> ReasoningAnalytics:
    """Factory para analytics (singleton)."""
    global _analytics
    if _analytics is None:
        _analytics = ReasoningAnalytics()
    return _analytics

