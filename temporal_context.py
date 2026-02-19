"""Contexto temporal dinamico para reduzir respostas desatualizadas."""

from datetime import datetime


def build_temporal_guardrail(now: datetime | None = None) -> str:
    """Gera instrucoes de recencia para prompts do agente."""
    current = now or datetime.now().astimezone()
    absolute_date = current.strftime("%Y-%m-%d")
    absolute_time = current.strftime("%H:%M:%S %z")

    return f"""
# CONTEXTO TEMPORAL DA SESSAO
- Data atual (sistema): {absolute_date}
- Hora atual (sistema): {absolute_time}

# REGRAS DE RECENCIA
- Nunca afirme que seu conhecimento "vai ate 2024" como resposta padrao.
- Para fatos sensiveis a tempo (hoje, atual, latest, 2025+, versao, preco, lei, noticia, agenda, resultado), trate como potencialmente mutavel.
- Se nao houver verificacao externa recente no contexto, diga explicitamente que a informacao nao esta verificada.
- Quando houver dado recente confirmado, cite data e origem na resposta.
""".strip()

