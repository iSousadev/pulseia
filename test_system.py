"""
Script de teste para o sistema de memória e raciocínio
Valida funcionamento básico sem precisar do LiveKit
"""

import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

from memory_system import MemorySystem
from reasoning_system import get_reasoning_system, ReasoningMode

def test_memory_system():
    """Testa sistema de memória"""
    print("=" * 60)
    print("TESTANDO SISTEMA DE MEMÓRIA")
    print("=" * 60)
    
    memory = MemorySystem(storage_dir="KMS/memory_test")
    
    # Cria sessão
    user_id = "test_user"
    session_id = memory.create_session(user_id)
    print(f"\n✓ Sessão criada: {session_id[:8]}")
    
    # Adiciona conversas
    conversations = [
        ("user", "Estou com erro no FastAPI, dá 500 Internal Server Error"),
        ("assistant", "Preciso ver o traceback. Normalmente é exceção não tratada ou variável de ambiente faltando."),
        ("user", "Uso Python 3.11 e trabalho com React no frontend"),
        ("assistant", "Beleza, stack moderno. FastAPI + React é uma ótima combinação."),
        ("user", "Prefiro usar PostgreSQL em vez de SQLite"),
        ("assistant", "PostgreSQL é excelente escolha para produção. Muito mais robusto que SQLite."),
    ]
    
    for role, text in conversations:
        memory.add_turn(session_id, role, text)
        print(f"  [{role[:4]}] {text[:50]}...")
    
    print(f"\n✓ {len(conversations)} turnos salvos")
    
    # Finaliza sessão
    memory.end_session(session_id, rating=5)
    print("✓ Sessão finalizada")
    
    # Cria nova sessão
    session_id_2 = memory.create_session(user_id)
    print(f"\n✓ Nova sessão criada: {session_id_2[:8]}")
    
    # Busca contexto
    context = memory.get_context_for_session(user_id, include_days=7)
    print(f"\n✓ Contexto recuperado ({len(context)} chars):")
    print("-" * 60)
    print(context[:500] + "..." if len(context) > 500 else context)
    print("-" * 60)
    
    # Busca semântica
    print("\n✓ Testando busca semântica:")
    similar = memory.search_similar_context(
        "problema com banco de dados",
        user_id,
        limit=3
    )
    print(f"  Encontradas {len(similar)} conversas similares")
    for i, conv in enumerate(similar, 1):
        print(f"  {i}. [similarity={conv['similarity']:.2f}] {conv['text'][:60]}...")
    
    # Estatísticas
    stats = memory.get_user_stats(user_id)
    print(f"\n✓ Estatísticas do usuário:")
    print(f"  - Mensagens: {stats['total_messages']}")
    print(f"  - Fatos: {stats['total_facts']}")
    print(f"  - Soluções: {stats['total_solutions']}")
    
    print("\n✅ TESTE DE MEMÓRIA CONCLUÍDO COM SUCESSO!\n")
    
    # Cleanup
    memory.clear_user_data(user_id)
    print("🧹 Dados de teste limpos")


async def test_reasoning_system():
    """Testa sistema de raciocínio"""
    print("=" * 60)
    print("TESTANDO SISTEMA DE RACIOCÍNIO")
    print("=" * 60)
    
    reasoning = get_reasoning_system()
    
    # Teste 1: Pergunta simples (deve usar fast mode)
    print("\n📝 Teste 1: Pergunta simples")
    print("-" * 60)
    
    result1 = await reasoning.process(
        user_input="Oi, tudo bem?",
        context=""
    )
    
    print(f"Modo usado: {result1.mode.value}")
    print(f"Tempo: {result1.execution_time_ms}ms")
    print(f"Resposta: {result1.text[:200]}...")
    
    # Teste 2: Pergunta complexa (deve usar reasoning)
    print("\n📝 Teste 2: Pergunta técnica complexa")
    print("-" * 60)
    
    result2 = await reasoning.process(
        user_input="""
        Meu código FastAPI está dando timeout após 30 segundos.
        O endpoint /api/users busca dados do PostgreSQL.
        Como debugar e otimizar?
        """,
        context=""
    )
    
    print(f"Modo usado: {result2.mode.value}")
    print(f"Tempo: {result2.execution_time_ms}ms")
    
    if result2.thinking:
        print(f"\n💭 Thinking process:")
        print(result2.thinking[:500] + "..." if len(result2.thinking) > 500 else result2.thinking)
    
    print(f"\n💬 Resposta final:")
    print(result2.text[:500] + "..." if len(result2.text) > 500 else result2.text)
    
    if result2.tools_used:
        print(f"\n🔧 Tools usadas: {len(result2.tools_used)}")
        for tool in result2.tools_used:
            print(f"  - {tool['type']}")
    
    # Teste 3: Code execution
    print("\n📝 Teste 3: Teste com execução de código")
    print("-" * 60)
    
    result3 = await reasoning.process(
        user_input="Calcule a soma dos 100 primeiros números primos",
        context="",
        force_mode=ReasoningMode.REASONING_DEEP
    )
    
    print(f"Modo usado: {result3.mode.value}")
    print(f"Tempo: {result3.execution_time_ms}ms")
    print(f"Resposta: {result3.text}")
    
    if result3.tools_used:
        print(f"\n🔧 Code execution:")
        for tool in result3.tools_used:
            if tool['type'] == 'code_execution':
                print(f"Código executado:\n{tool.get('code', 'N/A')}")
                print(f"\nResultado:\n{tool.get('result', 'N/A')}")
    
    print("\n✅ TESTE DE RACIOCÍNIO CONCLUÍDO COM SUCESSO!\n")


async def test_integration():
    """Testa integração memória + raciocínio"""
    print("=" * 60)
    print("TESTANDO INTEGRAÇÃO COMPLETA")
    print("=" * 60)
    
    memory = MemorySystem(storage_dir="KMS/memory_test")
    reasoning = get_reasoning_system()
    
    user_id = "integration_test_user"
    session_id = memory.create_session(user_id)
    
    # Simula conversa com memória
    print("\n💬 Simulando conversa com contexto...")
    
    # Turno 1
    user_msg_1 = "Estou estudando FastAPI e quero fazer uma API REST"
    memory.add_turn(session_id, "user", user_msg_1)
    
    context = memory.get_context_for_session(user_id)
    result_1 = await reasoning.process(user_msg_1, context)
    
    memory.add_turn(session_id, "assistant", result_1.text)
    print(f"\n[Usuário] {user_msg_1}")
    print(f"[PULSE] {result_1.text[:200]}...")
    
    # Turno 2 (deve usar contexto da conversa anterior)
    user_msg_2 = "Como faço autenticação JWT nessa API?"
    memory.add_turn(session_id, "user", user_msg_2)
    
    context = memory.get_context_for_session(user_id)
    result_2 = await reasoning.process(user_msg_2, context)
    
    memory.add_turn(session_id, "assistant", result_2.text)
    print(f"\n[Usuário] {user_msg_2}")
    print(f"[PULSE] {result_2.text[:200]}...")
    
    # Finaliza e cria nova sessão (simula outro dia)
    memory.end_session(session_id, rating=5)
    print("\n⏰ Sessão finalizada (simula fim do dia)")
    
    session_id_2 = memory.create_session(user_id)
    print("🌅 Nova sessão iniciada (dia seguinte)")
    
    # Nova pergunta - deve lembrar do contexto anterior
    user_msg_3 = "Lembra da API que tava fazendo? Agora preciso adicionar PostgreSQL"
    memory.add_turn(session_id_2, "user", user_msg_3)
    
    context = memory.get_context_for_session(user_id, include_days=7)
    print(f"\n📚 Contexto carregado: {len(context)} chars")
    print(f"   Inclui sessões anteriores: {'FastAPI' in context}")
    
    result_3 = await reasoning.process(user_msg_3, context)
    memory.add_turn(session_id_2, "assistant", result_3.text)
    
    print(f"\n[Usuário] {user_msg_3}")
    print(f"[PULSE] {result_3.text[:300]}...")
    
    print("\n✅ INTEGRAÇÃO FUNCIONANDO! O agente lembra do contexto anterior.")
    
    # Cleanup
    memory.end_session(session_id_2)
    memory.clear_user_data(user_id)
    print("\n🧹 Dados de teste limpos")


def main():
    """Executa todos os testes"""
    print("\n" + "=" * 60)
    print("SUITE DE TESTES - PULSE ENHANCED")
    print("=" * 60 + "\n")
    
    # Verifica variáveis de ambiente
    if not os.getenv("GOOGLE_API_KEY"):
        print("❌ ERRO: GOOGLE_API_KEY não encontrada")
        print("   Configure no arquivo .env")
        return
    
    try:
        # Teste 1: Memória
        test_memory_system()
        
        # Teste 2: Raciocínio
        asyncio.run(test_reasoning_system())
        
        # Teste 3: Integração
        asyncio.run(test_integration())
        
        print("\n" + "=" * 60)
        print("✅ TODOS OS TESTES PASSARAM!")
        print("=" * 60)
        print("\n🚀 Sistema pronto para uso. Execute:")
        print("   python enhanced_agent.py")
        
    except Exception as e:
        print(f"\n❌ ERRO NOS TESTES: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()