#!/usr/bin/env python3
"""
Utilitário de gerenciamento de memória do PULSE

Uso:
    python memory_cli.py stats <user_id>           # Estatísticas
    python memory_cli.py search <user_id> <query>  # Busca semântica
    python memory_cli.py clear <user_id>           # Limpa dados
    python memory_cli.py export <user_id> <file>   # Exporta conversas
    python memory_cli.py list                      # Lista usuários
"""

import sys
import json
from pathlib import Path
from datetime import datetime

from memory_system import MemorySystem


def print_header(text: str):
    """Imprime cabeçalho formatado"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70 + "\n")


def cmd_stats(user_id: str):
    """Mostra estatísticas do usuário"""
    print_header(f"Estatísticas - {user_id}")
    
    memory = MemorySystem()
    stats = memory.get_user_stats(user_id)
    
    if not stats:
        print("❌ Nenhum dado encontrado para este usuário")
        return
    
    print(f"📊 Mensagens totais:  {stats['total_messages']}")
    print(f"💡 Fatos salvos:      {stats['total_facts']}")
    print(f"✅ Soluções:          {stats['total_solutions']}")
    
    # Busca última atividade
    try:
        context = memory.get_context_for_session(user_id, include_days=365)
        if "Sessão de" in context:
            # Extrai data da última sessão
            import re
            dates = re.findall(r'Sessão de (\d{2}/\d{2}/\d{4})', context)
            if dates:
                print(f"🕒 Última atividade: {dates[0]}")
    except:
        pass
    
    print()


def cmd_search(user_id: str, query: str):
    """Busca semântica nas conversas"""
    print_header(f"Busca: '{query}'")
    
    memory = MemorySystem()
    results = memory.search_similar_context(query, user_id, limit=5)
    
    if not results:
        print("❌ Nenhum resultado encontrado")
        return
    
    print(f"✓ Encontrados {len(results)} resultados:\n")
    
    for i, result in enumerate(results, 1):
        role_emoji = "👤" if result['role'] == 'user' else "🤖"
        similarity_bar = "█" * int(result['similarity'] * 10)
        
        print(f"{i}. [{similarity_bar:10}] {result['similarity']:.2f}")
        print(f"   {role_emoji} {result['text'][:100]}...")
        
        if result['topics']:
            topics_str = ", ".join(result['topics'][:3])
            print(f"   🏷️  {topics_str}")
        
        date = datetime.fromisoformat(result['timestamp'])
        print(f"   📅 {date.strftime('%d/%m/%Y %H:%M')}")
        print()


def cmd_clear(user_id: str):
    """Limpa todos os dados do usuário"""
    print_header(f"ATENÇÃO: Limpeza de dados - {user_id}")
    
    confirm = input("⚠️  Isso vai DELETAR TODOS os dados do usuário. Confirma? (yes/no): ")
    
    if confirm.lower() != "yes":
        print("❌ Operação cancelada")
        return
    
    memory = MemorySystem()
    
    # Mostra stats antes
    stats = memory.get_user_stats(user_id)
    print(f"\n📊 Deletando:")
    print(f"   - {stats['total_messages']} mensagens")
    print(f"   - {stats['total_facts']} fatos")
    print(f"   - {stats['total_solutions']} soluções")
    
    # Deleta
    memory.clear_user_data(user_id)
    
    print("\n✅ Dados deletados com sucesso!")


def cmd_export(user_id: str, output_file: str):
    """Exporta conversas para JSON"""
    print_header(f"Exportando conversas - {user_id}")
    
    memory = MemorySystem()
    
    # Busca todas as conversas
    try:
        results = memory.conversations.query(
            query_texts=[""],
            n_results=10000,  # Todas
            where={"user_id": user_id}
        )
    except Exception as e:
        print(f"❌ Erro ao buscar conversas: {e}")
        return
    
    if not results['documents'][0]:
        print("❌ Nenhuma conversa encontrada")
        return
    
    # Organiza por sessão
    sessions = {}
    for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
        session_id = meta['session_id']
        
        if session_id not in sessions:
            sessions[session_id] = {
                "session_id": session_id,
                "messages": []
            }
        
        sessions[session_id]["messages"].append({
            "role": meta['role'],
            "text": doc,
            "timestamp": meta['timestamp'],
            "topics": meta.get('topics', '').split(','),
        })
    
    # Ordena mensagens por timestamp
    for session in sessions.values():
        session["messages"].sort(key=lambda x: x['timestamp'])
    
    # Exporta
    export_data = {
        "user_id": user_id,
        "export_date": datetime.now().isoformat(),
        "total_sessions": len(sessions),
        "total_messages": len(results['documents'][0]),
        "sessions": list(sessions.values())
    }
    
    output_path = Path(output_file)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ Exportado com sucesso!")
    print(f"   📁 Arquivo: {output_path.absolute()}")
    print(f"   📊 Sessões: {len(sessions)}")
    print(f"   💬 Mensagens: {len(results['documents'][0])}")


def cmd_list():
    """Lista todos os usuários com dados"""
    print_header("Usuários com Dados")
    
    memory = MemorySystem()
    
    # Busca todos os user_ids únicos
    try:
        # Conversations
        conv_results = memory.conversations.query(
            query_texts=[""],
            n_results=10000
        )
        
        user_ids = set()
        if conv_results['metadatas'][0]:
            for meta in conv_results['metadatas'][0]:
                user_ids.add(meta['user_id'])
        
        if not user_ids:
            print("❌ Nenhum usuário encontrado")
            return
        
        print(f"✓ Encontrados {len(user_ids)} usuários:\n")
        
        for user_id in sorted(user_ids):
            stats = memory.get_user_stats(user_id)
            print(f"👤 {user_id}")
            print(f"   📊 {stats['total_messages']} msgs | "
                  f"{stats['total_facts']} fatos | "
                  f"{stats['total_solutions']} soluções")
            print()
            
    except Exception as e:
        print(f"❌ Erro: {e}")


def cmd_context(user_id: str):
    """Mostra contexto que seria carregado"""
    print_header(f"Contexto Atual - {user_id}")
    
    memory = MemorySystem()
    context = memory.get_context_for_session(
        user_id,
        include_days=7,
        max_conversations=3,
        max_facts=10
    )
    
    if not context or context == "# Primeira conversa com este usuário.\n":
        print("❌ Nenhum contexto disponível")
        return
    
    print(context)
    print(f"\n📏 Tamanho: {len(context)} caracteres")


def show_usage():
    """Mostra ajuda de uso"""
    print(__doc__)
    sys.exit(1)


def main():
    if len(sys.argv) < 2:
        show_usage()
    
    command = sys.argv[1]
    
    try:
        if command == "stats":
            if len(sys.argv) < 3:
                print("❌ Uso: memory_cli.py stats <user_id>")
                sys.exit(1)
            cmd_stats(sys.argv[2])
        
        elif command == "search":
            if len(sys.argv) < 4:
                print("❌ Uso: memory_cli.py search <user_id> <query>")
                sys.exit(1)
            query = " ".join(sys.argv[3:])
            cmd_search(sys.argv[2], query)
        
        elif command == "clear":
            if len(sys.argv) < 3:
                print("❌ Uso: memory_cli.py clear <user_id>")
                sys.exit(1)
            cmd_clear(sys.argv[2])
        
        elif command == "export":
            if len(sys.argv) < 4:
                print("❌ Uso: memory_cli.py export <user_id> <output_file>")
                sys.exit(1)
            cmd_export(sys.argv[2], sys.argv[3])
        
        elif command == "list":
            cmd_list()
        
        elif command == "context":
            if len(sys.argv) < 3:
                print("❌ Uso: memory_cli.py context <user_id>")
                sys.exit(1)
            cmd_context(sys.argv[2])
        
        else:
            print(f"❌ Comando desconhecido: {command}")
            show_usage()
    
    except KeyboardInterrupt:
        print("\n\n❌ Operação cancelada pelo usuário")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erro: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()