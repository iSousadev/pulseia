"""Sistema de raciocinio profundo para PULSE - OTIMIZADO."""

import asyncio
from datetime import datetime
import os
import logging
import json
import sys
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import re
import time
import unicodedata
from urllib.error import URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

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


@dataclass
class RealtimeContext:
    """Contexto de busca atualizado para perguntas sensiveis a data."""
    text: str = ""
    sources: List[Dict[str, str]] = field(default_factory=list)


class RealtimeSearchService:
    """Busca leve em fontes publicas para reduzir respostas desatualizadas."""

    TIME_SENSITIVE_PATTERNS = [
        r"\bhoje\b",
        r"\bagora\b",
        r"\batual\b",
        r"\batualizado\b",
        r"\brecente\b",
        r"\bultim[oa]s?\b",
        r"\bessa semana\b",
        r"\beste mes\b",
        r"\bultimos?\s+\d+\s+(dias|semanas|meses)\b",
        r"\blatest\b",
        r"\bnews?\b",
        r"\brelease\b",
        r"\blancamento\b",
        r"\bchangelog\b",
        r"\bbreaking changes?\b",
        r"\bpreco\b",
        r"\bcotacao\b",
        r"\bversao\b",
        r"\bpresidente\b",
        r"\bceo\b",
        r"\blei\b",
        r"\bdecreto\b",
        r"\bregulacao\b",
        r"\broadmap\b",
        r"\b202[5-9]\b",
        r"\b20[3-9][0-9]\b",
    ]
    YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")

    def __init__(self):
        enabled_raw = os.getenv("PULSE_REALTIME_SEARCH_ENABLED", "true").strip().lower()
        self.enabled = enabled_raw in {"1", "true", "yes", "on"}
        self.max_results = self._parse_int("PULSE_REALTIME_SEARCH_MAX_RESULTS", default=3, min_value=1, max_value=5)
        self.cache_ttl_seconds = self._parse_int(
            "PULSE_REALTIME_SEARCH_CACHE_TTL_SECONDS",
            default=600,
            min_value=60,
            max_value=3600,
        )
        self._cache: Dict[str, tuple[float, RealtimeContext]] = {}
        self._headers = {"User-Agent": "PULSE-Agent/1.0 (realtime-search)"}

    @staticmethod
    def _parse_int(name: str, *, default: int, min_value: int, max_value: int) -> int:
        raw = os.getenv(name)
        if raw is None:
            return default
        try:
            value = int(raw)
        except ValueError:
            return default
        return max(min_value, min(max_value, value))

    @staticmethod
    def _normalize_for_match(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return ascii_only.lower()

    def should_search(self, user_input: str) -> bool:
        if not self.enabled:
            return False
        text = self._normalize_for_match(user_input)

        if any(re.search(pattern, text) for pattern in self.TIME_SENSITIVE_PATTERNS):
            return True

        for year in self.YEAR_PATTERN.findall(text):
            if int(year) >= 2025:
                return True

        return False

    def get_context(self, user_input: str) -> RealtimeContext:
        if not self.should_search(user_input):
            return RealtimeContext()

        key = user_input.strip().lower()
        now = time.time()
        cached = self._cache.get(key)
        if cached and cached[0] > now:
            return cached[1]

        snippets = self._search_news_rss(user_input)
        if not snippets:
            snippets = self._search_duckduckgo(user_input)

        if not snippets:
            context = RealtimeContext()
            self._cache[key] = (now + self.cache_ttl_seconds, context)
            return context

        lines = []
        sources: List[Dict[str, str]] = []
        for item in snippets[: self.max_results]:
            title = item.get("title", "").strip()
            url = item.get("url", "").strip()
            published = item.get("published_at", "").strip()
            if not title or not url:
                continue
            line = f"- {title}"
            if published:
                line += f" ({published})"
            line += f" | {url}"
            lines.append(line)
            sources.append(
                {
                    "title": title,
                    "url": url,
                    "published_at": published,
                }
            )

        if not lines:
            context = RealtimeContext()
            self._cache[key] = (now + self.cache_ttl_seconds, context)
            return context

        built = RealtimeContext(
            text=(
                "CONTEXTO EXTERNO ATUALIZADO (use somente como referencia factual):\n"
                + "\n".join(lines)
                + f"\nColetado em: {datetime.now().isoformat(timespec='seconds')}"
            ),
            sources=sources,
        )
        self._cache[key] = (now + self.cache_ttl_seconds, built)
        return built

    def _search_news_rss(self, query: str) -> List[Dict[str, str]]:
        url = f"https://news.google.com/rss/search?q={quote_plus(query)}"
        req = Request(url, headers=self._headers)
        try:
            with urlopen(req, timeout=5) as resp:
                content = resp.read()
        except (TimeoutError, URLError, OSError):
            return []

        try:
            root = ET.fromstring(content)
        except ET.ParseError:
            return []

        items = []
        for item in root.findall(".//item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or "").strip()
            if not title or not link:
                continue
            items.append(
                {
                    "title": title,
                    "url": link,
                    "published_at": pub_date,
                }
            )
            if len(items) >= self.max_results:
                break
        return items

    def _search_duckduckgo(self, query: str) -> List[Dict[str, str]]:
        url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_redirect=1&no_html=1"
        req = Request(url, headers=self._headers)
        try:
            with urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
        except (TimeoutError, URLError, OSError, json.JSONDecodeError):
            return []

        items: List[Dict[str, str]] = []

        abstract_text = str(data.get("AbstractText", "")).strip()
        abstract_url = str(data.get("AbstractURL", "")).strip()
        if abstract_text and abstract_url:
            items.append(
                {
                    "title": abstract_text[:160],
                    "url": abstract_url,
                    "published_at": "",
                }
            )

        related_topics = data.get("RelatedTopics", []) or []
        for topic in related_topics:
            if "Topics" in topic:
                nested_topics = topic.get("Topics", []) or []
            else:
                nested_topics = [topic]
            for entry in nested_topics:
                text = str(entry.get("Text", "")).strip()
                first_url = str(entry.get("FirstURL", "")).strip()
                if not text or not first_url:
                    continue
                items.append(
                    {
                        "title": text[:160],
                        "url": first_url,
                        "published_at": "",
                    }
                )
                if len(items) >= self.max_results:
                    return items
        return items


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
        self.realtime_search = RealtimeSearchService()

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
        time_sensitive = self.realtime_search.should_search(user_input)

        # OTIMIZAÃƒâ€¡ÃƒÆ’O: Verifica cache primeiro
        if not force_mode and not time_sensitive:
            cached = self.cache.get(user_input)
            if cached:
                logger.info("Cache HIT! Retornando resposta cacheada")
                cached.execution_time_ms = 5  # InstantÃƒÂ¢neo
                return cached

        complexity_score = self._compute_complexity_score(user_input)
        mode = force_mode if force_mode else self._select_mode(user_input)
        logger.info("Processando com modo: %s", mode.value)

        realtime_context = RealtimeContext()
        if time_sensitive:
            try:
                realtime_context = await asyncio.to_thread(
                    self.realtime_search.get_context,
                    user_input,
                )
                if realtime_context.text:
                    logger.info(
                        "Contexto atualizado obtido (%s fontes).",
                        len(realtime_context.sources),
                    )
            except Exception as exc:
                logger.warning("Falha ao buscar contexto atualizado: %s", exc)
                realtime_context = RealtimeContext()

        if time_sensitive and not realtime_context.text:
            result = self._build_unverified_realtime_result(user_input)
            result.execution_time_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Sem contexto externo recente para consulta temporal. Retornando resposta nao verificada.",
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

        if mode == ReasoningMode.VOICE_FAST:
            result = await self._fast_response(user_input, context, realtime_context)
        else:
            result = await self._deep_reasoning(user_input, context, realtime_context)

        if time_sensitive:
            result.text = self._enforce_temporal_output_contract(
                result.text,
                realtime_context.sources,
            )

        result.execution_time_ms = int((time.time() - start_time) * 1000)
        
        # OTIMIZAÃƒâ€¡ÃƒÆ’O: Salva no cache
        if not force_mode and not time_sensitive and result.confidence > 0.7:
            self.cache.set(user_input, result)

        if realtime_context.sources:
            if not result.tools_used:
                result.tools_used = []
            result.tools_used.append(
                {
                    "type": "realtime_search",
                    "source_count": len(realtime_context.sources),
                    "sources": realtime_context.sources,
                }
            )
        
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

    def _build_unverified_realtime_result(self, user_input: str) -> ReasoningResult:
        """Fallback quando pergunta temporal nao pode ser validada online."""
        checked_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        text = (
            "Essa pergunta depende de informacao atualizada e eu nao consegui validar "
            "fontes recentes agora.\n"
            "Status: nao verificado.\n"
            f"Data da verificacao: {checked_at}\n"
            "Fontes: indisponiveis nesta tentativa.\n"
            "Se quiser, tento novamente em instantes ou respondo apenas com fundamentos "
            "sem afirmar fatos recentes."
        )
        return ReasoningResult(
            mode=ReasoningMode.VOICE_FAST,
            text=text,
            thinking=None,
            tools_used=[
                {
                    "type": "realtime_search",
                    "status": "unavailable",
                    "query": user_input,
                }
            ],
            confidence=0.35,
        )

    def _enforce_temporal_output_contract(
        self,
        text: str,
        sources: List[Dict[str, str]] | None,
    ) -> str:
        """Padroniza saida para respostas dependentes de recencia."""
        cleaned_text = (text or "").strip()
        checked_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %z")
        has_sources = bool(sources)
        status = "verificado" if has_sources else "nao verificado"

        source_lines: List[str] = []
        if has_sources:
            source_lines.append("Fontes:")
            for index, source in enumerate((sources or [])[:5], start=1):
                title = (source.get("title") or "Fonte sem titulo").strip()
                url = (source.get("url") or "").strip()
                published = (source.get("published_at") or "sem data publica").strip()
                line = f"{index}. {title} ({published})"
                if url:
                    line += f" - {url}"
                source_lines.append(line)
        else:
            source_lines.append("Fontes: indisponiveis nesta tentativa.")

        if (
            "Status:" in cleaned_text
            and "Data da verificacao:" in cleaned_text
            and ("Fontes:" in cleaned_text or "Fontes: indisponiveis" in cleaned_text)
        ):
            return cleaned_text

        contract_block = [
            f"Status: {status}",
            f"Data da verificacao: {checked_at}",
            *source_lines,
        ]

        if cleaned_text:
            return f"{cleaned_text}\n\n" + "\n".join(contract_block)
        return "\n".join(contract_block)

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
    async def _fast_response(
        self,
        user_input: str,
        context: str,
        realtime_context: RealtimeContext,
    ) -> ReasoningResult:
        """Resposta rapida sem reasoning profundo."""
        prompt = self._build_fast_prompt(user_input, context, realtime_context)

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

    async def _deep_reasoning(
        self,
        user_input: str,
        context: str,
        realtime_context: RealtimeContext,
    ) -> ReasoningResult:
        """Raciocinio profundo com thinking e code execution."""
        prompt = self._build_reasoning_prompt(user_input, context, realtime_context)

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
            return await self._fast_response(user_input, context, realtime_context)

    def _build_fast_prompt(
        self,
        user_input: str,
        context: str,
        realtime_context: RealtimeContext,
    ) -> str:
        """Monta prompt para resposta rapida."""
        from prompts import AGENT_INSTRUCTION
        from temporal_context import build_temporal_guardrail

        realtime_block = ""
        if realtime_context.text:
            realtime_block = (
                "\n\n---\n"
                f"{realtime_context.text}\n"
                "Se houver conflito com memoria antiga, priorize o contexto atualizado.\n"
                "FORMATO OBRIGATORIO PARA RESPOSTA TEMPORAL:\n"
                "- Status: verificado ou nao verificado\n"
                "- Data da verificacao: YYYY-MM-DD HH:MM:SS +TZ\n"
                "- Fontes: lista numerada com titulo, data e link\n"
            )

        return f"""
{AGENT_INSTRUCTION}
{build_temporal_guardrail()}

{context}
{realtime_block}

---

Responda de forma DIRETA, NATURAL e CASUAL. Sem formalidades.

Usuario: {user_input}
""".strip()

    def _build_reasoning_prompt(
        self,
        user_input: str,
        context: str,
        realtime_context: RealtimeContext,
    ) -> str:
        """Monta prompt para raciocinio profundo."""
        from prompts import AGENT_INSTRUCTION
        from temporal_context import build_temporal_guardrail

        realtime_block = ""
        if realtime_context.text:
            realtime_block = (
                "\n\n---\n"
                f"{realtime_context.text}\n"
                "Use o contexto atualizado para fatos temporais e deixe isso claro na resposta.\n"
                "FORMATO OBRIGATORIO PARA RESPOSTA TEMPORAL:\n"
                "- Status: verificado ou nao verificado\n"
                "- Data da verificacao: YYYY-MM-DD HH:MM:SS +TZ\n"
                "- Fontes: lista numerada com titulo, data e link\n"
            )

        return f"""
{AGENT_INSTRUCTION}
{build_temporal_guardrail()}

{context}
{realtime_block}

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

