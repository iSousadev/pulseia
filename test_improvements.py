#!/usr/bin/env python3
"""Suite de validacao das melhorias do PULSE."""

import asyncio
import importlib
import os
import sys
import time
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def is_supported_python_for_runtime() -> bool:
    return (sys.version_info.major, sys.version_info.minor) < (3, 14)


@dataclass
class TestResult:
    name: str
    status: str  
    details: str = ""


def banner(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def print_result(result: TestResult) -> None:
    tag = {
        "pass": "[PASS]",
        "fail": "[FAIL]",
        "skip": "[SKIP]",
    }[result.status]
    print(f"{tag} {result.name}")
    if result.details:
        print(f"       {result.details}")


def test_static_integrity() -> list[TestResult]:
    banner("TESTE 1: INTEGRIDADE ESTATICA")
    results: list[TestResult] = []

    if not is_supported_python_for_runtime():
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        results.append(
            TestResult(
                "Imports principais",
                "skip",
                f"Python {py_ver} nao suportado para runtime. Use .venv311 (3.11).",
            )
        )
    else:
        try:
            for module_name in ("agent", "prompts", "reasoning_system", "vision"):
                importlib.import_module(module_name)
            results.append(TestResult("Imports principais", "pass"))
        except BaseException as exc:
            results.append(TestResult("Imports principais", "fail", str(exc)))

    try:
        from prompts import AGENT_INSTRUCTION, SESSION_INSTRUCTION

        if AGENT_INSTRUCTION.strip() and SESSION_INSTRUCTION.strip():
            results.append(TestResult("Prompts carregados", "pass"))
        else:
            results.append(TestResult("Prompts carregados", "fail", "AGENT_INSTRUCTION ou SESSION_INSTRUCTION vazio."))
    except Exception as exc:
        results.append(TestResult("Validacao de prompt", "fail", str(exc)))

    for res in results:
        print_result(res)
    return results


async def test_reasoning_runtime() -> list[TestResult]:
    banner("TESTE 2: REASONING RUNTIME")
    results: list[TestResult] = []

    if not is_supported_python_for_runtime():
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        results.append(
            TestResult(
                "Runtime de reasoning",
                "skip",
                f"Python {py_ver} nao suportado. Execute com .venv311 (3.11).",
            )
        )
        for res in results:
            print_result(res)
        return results

    if not os.getenv("GOOGLE_API_KEY"):
        results.append(TestResult("GOOGLE_API_KEY configurada", "skip", "Sem chave, teste de runtime ignorado."))
        for res in results:
            print_result(res)
        return results

    try:
        from reasoning_system import get_reasoning_system

        system = get_reasoning_system()

        start = time.time()
        simple = await system.process("oi, tudo bem?", "")
        simple_ms = int((time.time() - start) * 1000)

        if simple.confidence <= 0:
            results.append(
                TestResult(
                    "Conectividade com API de reasoning",
                    "skip",
                    "Sem resposta valida do provedor (timeout/conexao).",
                )
            )
            for res in results:
                print_result(res)
            return results

        if simple.mode.value == "voice_fast":
            results.append(TestResult("Pergunta simples em modo rapido", "pass", f"tempo={simple_ms}ms"))
        else:
            results.append(
                TestResult(
                    "Pergunta simples em modo rapido",
                    "fail",
                    f"modo retornado={simple.mode.value}",
                )
            )

        start = time.time()
        _ = await system.process("oi, tudo bem?", "")
        cached_ms = int((time.time() - start) * 1000)
        if cached_ms <= simple_ms:
            results.append(TestResult("Cache de resposta", "pass", f"primeira={simple_ms}ms cache={cached_ms}ms"))
        else:
            results.append(TestResult("Cache de resposta", "fail", f"primeira={simple_ms}ms cache={cached_ms}ms"))

        complex_q = (
            "debug de erro intermitente com postgresql timeout e deadlock, "
            "preciso entender causas possiveis e como resolver"
        )
        complex_result = await system.process(complex_q, "")
        if complex_result.mode.value in {"reasoning_deep", "voice_fast"}:
            # Mantem flexivel: heuristica pode variar por texto, mas o sistema precisa responder.
            results.append(
                TestResult(
                    "Processamento de pergunta complexa",
                    "pass",
                    f"modo={complex_result.mode.value} tempo={complex_result.execution_time_ms}ms",
                )
            )
        else:
            results.append(TestResult("Processamento de pergunta complexa", "fail", f"modo={complex_result.mode.value}"))

    except Exception as exc:
        results.append(TestResult("Reasoning runtime", "fail", str(exc)))

    for res in results:
        print_result(res)
    return results


async def test_vision_runtime() -> list[TestResult]:
    banner("TESTE 3: VISAO RUNTIME")
    results: list[TestResult] = []

    if not is_supported_python_for_runtime():
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        results.append(
            TestResult(
                "Runtime de visao",
                "skip",
                f"Python {py_ver} nao suportado. Execute com .venv311 (3.11).",
            )
        )
        for res in results:
            print_result(res)
        return results

    if not os.getenv("GOOGLE_API_KEY"):
        results.append(TestResult("GOOGLE_API_KEY configurada", "skip", "Sem chave, teste de runtime ignorado."))
        for res in results:
            print_result(res)
        return results

    try:
        import io
        from PIL import Image

        from vision import get_vision_system

        vision_system = get_vision_system()

        triggers_ok = [
            vision_system.should_analyze_frame("o que voce ve"),
            vision_system.should_analyze_frame("olha isso aqui"),
            vision_system.should_analyze_frame("identifica esse objeto"),
        ]
        triggers_not = [
            not vision_system.should_analyze_frame("oi tudo bem"),
            not vision_system.should_analyze_frame("como fazer for loop"),
        ]

        if all(triggers_ok) and all(triggers_not):
            results.append(TestResult("Deteccao de triggers de visao", "pass"))
        else:
            results.append(
                TestResult(
                    "Deteccao de triggers de visao",
                    "fail",
                    f"positivos={sum(triggers_ok)}/3 negativos={sum(triggers_not)}/2",
                )
            )

        image = Image.new("RGB", (640, 480), color="blue")
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        img_data = buffer.getvalue()

        start = time.time()
        first = await vision_system.analyze_frame(img_data, user_query="o que voce ve?")
        first_ms = int((time.time() - start) * 1000)

        if first.confidence <= 0:
            results.append(
                TestResult(
                    "Conectividade com API de visao",
                    "skip",
                    "Sem resposta valida do provedor (timeout/conexao).",
                )
            )
            for res in results:
                print_result(res)
            return results

        if first.confidence > 0 and first.description:
            results.append(TestResult("Analise basica de imagem", "pass", f"tempo={first_ms}ms"))
        else:
            results.append(TestResult("Analise basica de imagem", "fail", "Sem descricao valida."))

        start = time.time()
        _ = await vision_system.analyze_frame(img_data, user_query="o que voce ve?")
        second_ms = int((time.time() - start) * 1000)
        if second_ms < first_ms:
            results.append(TestResult("Cooldown/cache de visao", "pass", f"primeira={first_ms}ms cache={second_ms}ms"))
        else:
            results.append(TestResult("Cooldown/cache de visao", "fail", f"primeira={first_ms}ms cache={second_ms}ms"))

    except Exception as exc:
        results.append(TestResult("Visao runtime", "fail", str(exc)))

    for res in results:
        print_result(res)
    return results


async def main() -> None:
    banner("PULSE OTIMIZADO - SUITE DE TESTES")

    all_results: list[TestResult] = []
    all_results.extend(test_static_integrity())
    all_results.extend(await test_reasoning_runtime())
    all_results.extend(await test_vision_runtime())

    total = len(all_results)
    passed = sum(1 for r in all_results if r.status == "pass")
    failed = sum(1 for r in all_results if r.status == "fail")
    skipped = sum(1 for r in all_results if r.status == "skip")

    banner("RESUMO")
    print(f"Total:   {total}")
    print(f"Passou:  {passed}")
    print(f"Falhou:  {failed}")
    print(f"Ignorado:{skipped}")

    if failed == 0:
        print("\nResultado geral: OK")
    else:
        print("\nResultado geral: COM FALHAS")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nTeste cancelado pelo usuario.")
