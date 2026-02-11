"""
Sistema de Memória Persistente para PULSE
Usa ChromaDB para busca vetorial semântica
"""

from datetime import datetime, timedelta
from pathlib import Path
import json
import uuid
import sys
from typing import List, Dict, Optional, Set
import logging
from dataclasses import dataclass, asdict
from enum import Enum

if sys.version_info >= (3, 14):
    raise RuntimeError(
        "Python 3.14 nao e suportado por parte das dependencias atuais deste projeto. "
        "Use Python 3.11, 3.12 ou 3.13."
    )

import chromadb
from chromadb.config import Settings
from chromadb.utils import embedding_functions

logger = logging.getLogger("pulse_agent.memory")


class FactCategory(Enum):
    """Categorias de fatos sobre o usuário"""
    TECH_STACK = "tech_stack"  # Linguagens, frameworks
    PROJECT = "project"  # Projetos em que trabalha
    PREFERENCE = "preference"  # Preferências pessoais
    LEARNING = "learning"  # O que está estudando
    PROBLEM = "problem"  # Problemas recorrentes
    SOLUTION = "solution"  # Soluções que funcionaram


@dataclass
class ConversationTurn:
    """Representa um turno da conversa"""
    id: str
    session_id: str
    user_id: str
    role: str 
    text: str
    timestamp: str
    metadata: Dict
    topics: Set[str]
    reasoning_used: bool = False
    

@dataclass
class UserFact:
    """Fato persistente sobre o usuário"""
    id: str
    user_id: str
    category: FactCategory
    content: str
    confidence: float  # 0-1
    first_mentioned: str
    last_mentioned: str
    mention_count: int


class MemorySystem:
    """
    Sistema de memória com 3 níveis:
    1. Working Memory - sessão atual (RAM)
    2. Short-term Memory - últimos dias (ChromaDB + filtros temporais)
    3. Long-term Memory - fatos consolidados (ChromaDB + alta relevância)
    """
    
    def __init__(self, storage_dir: str = "KMS/memory"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Inicializando sistema de memória em {self.storage_dir}")
        
        # ChromaDB com embeddings do sentence-transformers
        # Modelo multilingual (suporta português)
        self.embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="paraphrase-multilingual-MiniLM-L12-v2"
        )
        
        self.chroma_client = chromadb.PersistentClient(
            path=str(self.storage_dir / "chroma"),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Coleções
        self.conversations = self._get_or_create_collection(
            "conversations",
            "Histórico completo de conversas"
        )
        
        self.user_facts = self._get_or_create_collection(
            "user_facts",
            "Fatos e preferências consolidados"
        )
        
        self.solutions = self._get_or_create_collection(
            "solutions",
            "Soluções que funcionaram para problemas"
        )
        
        # Working memory (sessão ativa)
        self.active_sessions: Dict[str, Dict] = {}
        self.sessions_file = self.storage_dir / "active_sessions.json"
        self._load_active_sessions()
        
    def _get_or_create_collection(self, name: str, description: str):
        """Cria ou recupera coleção do ChromaDB"""
        try:
            return self.chroma_client.get_collection(
                name=name,
                embedding_function=self.embedding_fn
            )
        except Exception:
            return self.chroma_client.create_collection(
                name=name,
                embedding_function=self.embedding_fn,
                metadata={"description": description}
            )
    
    # ==================== SESSoES ====================
    
    def create_session(self, user_id: str) -> str:
        """Inicia nova sessão de conversa"""
        session_id = str(uuid.uuid4())
        
        session = {
            "id": session_id,
            "user_id": user_id,
            "start_time": datetime.now().isoformat(),
            "messages": [],
            "topics": set(),
            "reasoning_count": 0,
            "total_turns": 0,
        }
        
        self.active_sessions[session_id] = session
        self._save_active_sessions()
        
        logger.info(f"Sessão {session_id[:8]} criada para usuário {user_id}")
        return session_id
    
    def add_turn(
        self,
        session_id: str,
        role: str,
        text: str,
        metadata: Optional[Dict] = None,
        reasoning_used: bool = False
    ) -> str:
        """
        Adiciona turno à conversa
        Salva em working memory E ChromaDB
        """
        if session_id not in self.active_sessions:
            raise ValueError(f"Sessão {session_id} não encontrada")
        
        session = self.active_sessions[session_id]
        turn_id = str(uuid.uuid4())
        
        # Extrai tópicos técnicos do texto
        topics = self._extract_topics(text)
        
        turn = ConversationTurn(
            id=turn_id,
            session_id=session_id,
            user_id=session["user_id"],
            role=role,
            text=text,
            timestamp=datetime.now().isoformat(),
            metadata=metadata or {},
            topics=topics,
            reasoning_used=reasoning_used
        )
        
        # Adiciona à working memory
        session["messages"].append(asdict(turn))
        session["topics"].update(topics)
        session["total_turns"] += 1
        if reasoning_used:
            session["reasoning_count"] += 1
        
        # Salva no ChromaDB para persistência
        self.conversations.add(
            documents=[text],
            metadatas=[{
                "session_id": session_id,
                "user_id": session["user_id"],
                "role": role,
                "timestamp": turn.timestamp,
                "topics": ",".join(topics),
                "reasoning_used": reasoning_used,
            }],
            ids=[turn_id]
        )
        
        # Se for mensagem do usuário, extrai fatos
        if role == "user":
            self._extract_and_save_facts(session["user_id"], text, topics)
        
        # Se for solução bem-sucedida, salva
        if role == "assistant" and self._is_solution(text):
            self._save_solution(session["user_id"], text, topics)
        
        self._save_active_sessions()
        
        logger.debug(f"Turno {turn_id[:8]} adicionado à sessão {session_id[:8]}")
        return turn_id
    
    def end_session(self, session_id: str, rating: Optional[int] = None):
        """Finaliza sessão e consolida memória"""
        if session_id not in self.active_sessions:
            return
        
        session = self.active_sessions[session_id]
        session["end_time"] = datetime.now().isoformat()
        session["rating"] = rating
        
        # Estatísticas da sessão
        duration = (
            datetime.fromisoformat(session["end_time"]) -
            datetime.fromisoformat(session["start_time"])
        ).total_seconds() / 60
        
        logger.info(
            f"Sessão {session_id[:8]} finalizada. "
            f"Duração: {duration:.1f}min, "
            f"Turnos: {session['total_turns']}, "
            f"Reasoning: {session['reasoning_count']}, "
            f"Rating: {rating or 'N/A'}"
        )
        
        # Remove da working memory
        del self.active_sessions[session_id]
        self._save_active_sessions()
    
    # ==================== RECUPERAÇÃO DE CONTEXTO ====================
    
    def get_context_for_session(
        self,
        user_id: str,
        include_days: int = 7,
        max_conversations: int = 3,
        max_facts: int = 10
    ) -> str:
        """
        Monta contexto completo para injetar no prompt
        
        Retorna string formatada com:
        - Conversas recentes relevantes
        - Fatos consolidados sobre o usuário
        - Soluções que funcionaram antes
        """
        context_parts = []
        
        # 1. Conversas recentes
        recent_context = self._get_recent_conversations(
            user_id, include_days, max_conversations
        )
        if recent_context:
            context_parts.append("# CONVERSAS RECENTES")
            context_parts.append(recent_context)
        
        # 2. Fatos sobre o usuário
        facts_context = self._get_user_facts_context(user_id, max_facts)
        if facts_context:
            context_parts.append("\n# INFORMAÇÕES SOBRE O USUÁRIO")
            context_parts.append(facts_context)
        
        # 3. Soluções anteriores
        solutions_context = self._get_solutions_context(user_id, limit=5)
        if solutions_context:
            context_parts.append("\n# SOLUÇÕES QUE FUNCIONARAM ANTES")
            context_parts.append(solutions_context)
        
        if not context_parts:
            return "# Primeira conversa com este usuário.\n"
        
        return "\n".join(context_parts)
    
    def _get_recent_conversations(
        self,
        user_id: str,
        days: int,
        max_sessions: int
    ) -> str:
        """Busca conversas recentes do usuário"""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        
        try:
            results = self.conversations.query(
                query_texts=[""],  # Empty = get by metadata only
                n_results=50,
                where={
                    "$and": [
                        {"user_id": user_id},
                        {"timestamp": {"$gte": cutoff}}
                    ]
                }
            )
        except Exception as e:
            logger.warning(f"Erro ao buscar conversas recentes: {e}")
            return ""
        
        if not results['documents'][0]:
            return ""
        
        # Agrupa por sessão
        sessions_data = {}
        for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
            sid = meta['session_id']
            if sid not in sessions_data:
                sessions_data[sid] = {
                    "messages": [],
                    "timestamp": meta['timestamp']
                }
            sessions_data[sid]["messages"].append({
                "role": meta['role'],
                "text": doc,
                "timestamp": meta['timestamp']
            })
        
        # Ordena por data (mais recentes primeiro) e pega N últimas
        sorted_sessions = sorted(
            sessions_data.items(),
            key=lambda x: x[1]["timestamp"],
            reverse=True
        )[:max_sessions]
        
        # Formata para o contexto
        formatted = []
        for sid, data in sorted_sessions:
            session_date = datetime.fromisoformat(
                data["timestamp"]
            ).strftime("%d/%m/%Y às %H:%M")
            
            formatted.append(f"\n## Sessão de {session_date}")
            
            # Pega últimas 6 mensagens da sessão
            for msg in data["messages"][-6:]:
                role = "Usuário" if msg["role"] == "user" else "Você"
                text = msg["text"][:250]  # Trunca para economizar tokens
                if len(msg["text"]) > 250:
                    text += "..."
                formatted.append(f"**{role}:** {text}")
        
        return "\n".join(formatted)
    
    def _get_user_facts_context(self, user_id: str, limit: int) -> str:
        """Busca fatos consolidados sobre o usuário"""
        try:
            results = self.user_facts.query(
                query_texts=[""],
                n_results=limit,
                where={"user_id": user_id}
            )
        except Exception as e:
            logger.warning(f"Erro ao buscar fatos do usuário: {e}")
            return ""
        
        if not results['documents'][0]:
            return ""
        
        # Agrupa por categoria
        facts_by_category = {}
        for doc, meta in zip(results['documents'][0], results['metadatas'][0]):
            category = meta['category']
            if category not in facts_by_category:
                facts_by_category[category] = []
            facts_by_category[category].append(doc)
        
        # Formata
        formatted = []
        category_labels = {
            "tech_stack": "🛠️ Stack Técnica",
            "project": "📂 Projetos",
            "preference": "⭐ Preferências",
            "learning": "📚 Estudando",
            "problem": "⚠️ Problemas Comuns",
            "solution": "✅ Soluções Favoritas"
        }
        
        for category, facts in facts_by_category.items():
            label = category_labels.get(category, category)
            formatted.append(f"\n**{label}:**")
            for fact in facts[:3]:  # Max 3 por categoria
                formatted.append(f"  - {fact}")
        
        return "\n".join(formatted)
    
    def _get_solutions_context(self, user_id: str, limit: int) -> str:
        """Busca soluções que funcionaram antes"""
        try:
            results = self.solutions.query(
                query_texts=[""],
                n_results=limit,
                where={"user_id": user_id}
            )
        except Exception as e:
            logger.warning(f"Erro ao buscar soluções: {e}")
            return ""
        
        if not results['documents'][0]:
            return ""
        
        formatted = []
        for i, (doc, meta) in enumerate(
            zip(results['documents'][0], results['metadatas'][0]),
            1
        ):
            topics = meta.get('topics', '').split(',')
            topics_str = ', '.join(topics[:3]) if topics else 'geral'
            formatted.append(f"\n{i}. **[{topics_str}]** {doc[:200]}")
        
        return "\n".join(formatted)
    
    def search_similar_context(
        self,
        query: str,
        user_id: str,
        limit: int = 5
    ) -> List[Dict]:
        """
        Busca semântica: encontra conversas/soluções similares à query
        Útil para "lembra quando falamos sobre X?"
        """
        results = self.conversations.query(
            query_texts=[query],
            n_results=limit,
            where={"user_id": user_id}
        )
        
        similar = []
        if results['documents'][0]:
            for doc, meta, distance in zip(
                results['documents'][0],
                results['metadatas'][0],
                results['distances'][0]
            ):
                similarity = 1 - distance
                if similarity > 0.5:  # Threshold de relevância
                    similar.append({
                        "text": doc,
                        "role": meta['role'],
                        "timestamp": meta['timestamp'],
                        "topics": meta.get('topics', '').split(','),
                        "similarity": similarity
                    })
        
        return similar
    
    # ==================== EXTRAÇÃO DE INFORMAÇÕES ====================
    
    def _extract_topics(self, text: str) -> Set[str]:
        """
        Extrai tópicos técnicos do texto
        Lista expandida de termos relevantes
        """
        tech_keywords = {
            # Linguagens
            "python", "javascript", "typescript", "java", "c#", "go", "rust",
            "php", "ruby", "swift", "kotlin", "sql",
            
            # Frameworks/Libs Backend
            "fastapi", "django", "flask", "express", "nestjs", "spring",
            "rails", ".net", "laravel",
            
            # Frontend
            "react", "vue", "angular", "nextjs", "svelte", "solid",
            
            # Banco de dados
            "postgresql", "mysql", "mongodb", "redis", "sqlite",
            "dynamodb", "cassandra",
            
            # DevOps/Infra
            "docker", "kubernetes", "aws", "azure", "gcp", "terraform",
            "ansible", "jenkins", "github actions", "ci/cd",
            
            # Conceitos
            "api", "rest", "graphql", "websocket", "microservices",
            "monolith", "serverless", "async", "sync", "orm",
            "cache", "queue", "pub/sub", "event-driven",
            
            # Problemas comuns
            "bug", "erro", "exception", "crash", "timeout", "deadlock",
            "memory leak", "performance", "latency", "bottleneck",
            
            # Atividades
            "deploy", "deployment", "migration", "refactor", "debug",
            "test", "testing", "ci", "cd", "monitoring", "logging",
        }
        
        text_lower = text.lower()
        found = set()
        
        for keyword in tech_keywords:
            if keyword in text_lower:
                found.add(keyword)
        
        return found
    
    def _extract_and_save_facts(
        self,
        user_id: str,
        text: str,
        topics: Set[str]
    ):
        """
        Extrai e salva fatos sobre o usuário
        Usa patterns para identificar informações relevantes
        """
        fact_patterns = {
            FactCategory.TECH_STACK: [
                "uso", "trabalho com", "programo em", "desenvolvo em",
                "meu stack", "tecnologias que uso"
            ],
            FactCategory.PROJECT: [
                "estou fazendo", "trabalhando em", "projeto", "aplicação",
                "sistema que", "desenvolvendo"
            ],
            FactCategory.PREFERENCE: [
                "prefiro", "gosto de", "não gosto", "melhor usar",
                "costumo usar", "sempre uso"
            ],
            FactCategory.LEARNING: [
                "estudando", "aprendendo", "curso de", "tutorial",
                "quero aprender", "vou estudar"
            ],
            FactCategory.PROBLEM: [
                "sempre dá erro", "problema recorrente", "todo vez",
                "não consigo", "dificuldade com"
            ],
        }
        
        text_lower = text.lower()
        
        for category, patterns in fact_patterns.items():
            for pattern in patterns:
                if pattern in text_lower:
                    # Salva o fato
                    fact_id = f"{user_id}_{category.value}_{uuid.uuid4()}"
                    
                    self.user_facts.add(
                        documents=[text],
                        metadatas=[{
                            "user_id": user_id,
                            "category": category.value,
                            "timestamp": datetime.now().isoformat(),
                            "topics": ",".join(topics) if topics else "",
                            "confidence": 0.8,  # Pode ser ajustado
                        }],
                        ids=[fact_id]
                    )
                    
                    logger.debug(f"Fato extraído: {category.value} - {text[:50]}...")
                    break  # Evita duplicatas do mesmo texto
    
    def _is_solution(self, text: str) -> bool:
        """Detecta se o texto contém uma solução"""
        solution_indicators = [
            "funciona assim", "solução", "correção", "fix",
            "para resolver", "basta", "você pode",
            "recomendo", "sugestão", "tente",
        ]
        
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in solution_indicators)
    
    def _save_solution(self, user_id: str, text: str, topics: Set[str]):
        """Salva solução que funcionou"""
        solution_id = f"{user_id}_sol_{uuid.uuid4()}"
        
        self.solutions.add(
            documents=[text],
            metadatas=[{
                "user_id": user_id,
                "timestamp": datetime.now().isoformat(),
                "topics": ",".join(topics) if topics else "",
            }],
            ids=[solution_id]
        )
        
        logger.debug(f"Solução salva: {text[:50]}...")
    
    # ==================== PERSISTÊNCIA ====================
    
    def _load_active_sessions(self):
        """Carrega sessões ativas do disco"""
        if not self.sessions_file.exists():
            return
        
        try:
            with open(self.sessions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            # Reconstrói sets (JSON não suporta)
            for session in data.values():
                session['topics'] = set(session.get('topics', []))
            
            self.active_sessions = data
            logger.info(f"{len(self.active_sessions)} sessões ativas carregadas")
        except Exception as e:
            logger.error(f"Erro ao carregar sessões: {e}")
            self.active_sessions = {}
    
    def _save_active_sessions(self):
        """Salva sessões ativas no disco"""
        try:
            # Converte sets para listas
            data = {}
            for sid, session in self.active_sessions.items():
                session_copy = session.copy()
                session_copy['topics'] = list(session_copy.get('topics', set()))
                data[sid] = session_copy
            
            with open(self.sessions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Erro ao salvar sessões: {e}")
    
    # ==================== UTILIDADES ====================
    
    def get_user_stats(self, user_id: str) -> Dict:
        """Estatísticas sobre o usuário"""
        try:
            # Total de conversas
            conv_results = self.conversations.query(
                query_texts=[""],
                n_results=10000,  # Alto para pegar tudo
                where={"user_id": user_id}
            )
            total_messages = len(conv_results['documents'][0])
            
            # Fatos
            facts_results = self.user_facts.query(
                query_texts=[""],
                n_results=1000,
                where={"user_id": user_id}
            )
            total_facts = len(facts_results['documents'][0])
            
            # Soluções
            sol_results = self.solutions.query(
                query_texts=[""],
                n_results=1000,
                where={"user_id": user_id}
            )
            total_solutions = len(sol_results['documents'][0])
            
            return {
                "total_messages": total_messages,
                "total_facts": total_facts,
                "total_solutions": total_solutions,
            }
        except Exception as e:
            logger.error(f"Erro ao obter stats: {e}")
            return {}
    
    def clear_user_data(self, user_id: str):
        """
        CUIDADO: Remove todos os dados de um usuário
        Útil para testes ou reset
        """
        logger.warning(f"Limpando todos os dados do usuário {user_id}")
        
        # Remove das coleções
        for collection in [self.conversations, self.user_facts, self.solutions]:
            try:
                # ChromaDB não tem delete direto por metadata
                # Precisamos buscar IDs primeiro
                results = collection.query(
                    query_texts=[""],
                    n_results=10000,
                    where={"user_id": user_id}
                )
                
                if results['ids'][0]:
                    collection.delete(ids=results['ids'][0])
            except Exception as e:
                logger.error(f"Erro ao limpar coleção: {e}")
