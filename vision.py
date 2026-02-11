"""Sistema de visão computacional para PULSE usando Gemini Vision."""

import asyncio
import logging
import os
from dataclasses import dataclass
from typing import Optional, List
from io import BytesIO

from google import genai
from google.genai import types
from PIL import Image

logger = logging.getLogger("pulse_agent.vision")


@dataclass
class VisionResult:
    """Resultado da análise de visão."""
    description: str
    objects_detected: List[str]
    confidence: float
    processing_time_ms: int


class VisionSystem:
    """Sistema de visão computacional usando Gemini Vision."""
    
    def __init__(self):
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GOOGLE_API_KEY nao encontrada")
        
        self.client = genai.Client(api_key=api_key)
        self.model = "gemini-2.0-flash-exp"  # Modelo rápido com visão
        
        self.config = types.GenerateContentConfig(
            temperature=0.4,  # Mais determinístico para visão
            max_output_tokens=512,  # Descrições curtas
        )
        
        # Cache de últimas detecções para evitar reprocessar frames similares
        self.last_detection = None
        self.detection_cooldown = 2.0  # Segundos entre detecções
        self.last_detection_time = 0
        
        logger.info("Sistema de visão inicializado")
    
    async def analyze_frame(
        self, 
        image_data: bytes,
        context: str = "",
        user_query: Optional[str] = None
    ) -> VisionResult:
        """
        Analisa um frame da webcam.
        
        Args:
            image_data: Bytes da imagem (JPEG, PNG, etc)
            context: Contexto da conversa
            user_query: Pergunta específica do usuário sobre a imagem
        """
        import time
        start_time = time.time()
        
        # Cooldown para evitar sobrecarga
        current_time = time.time()
        if current_time - self.last_detection_time < self.detection_cooldown:
            logger.debug("Vision cooldown ativo, usando cache")
            if self.last_detection:
                return self.last_detection
        
        try:
            # Monta prompt baseado no contexto
            if user_query:
                prompt = f"""
Analise esta imagem e responda a pergunta do usuário.

Pergunta: {user_query}

Seja direto e natural. Se for um objeto específico que ele tá mostrando, 
descreva o que você vê de forma casual e útil.
"""
            else:
                prompt = """
Descreva brevemente o que você vê nesta imagem.

Foque em:
- Objetos principais
- Ações ou contexto
- Qualquer coisa tecnicamente relevante

Seja casual e direto, tipo: "Vejo um notebook com código Python na tela" 
ou "Você tá segurando um Arduino Uno".
"""
            
            # Chama API do Gemini Vision
            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model,
                contents=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_bytes(
                        data=image_data,
                        mime_type="image/jpeg"
                    )
                ],
                config=self.config,
            )
            
            description = response.text or "Não consegui identificar nada específico."
            
            # Extrai objetos mencionados (simples parsing)
            objects = self._extract_objects(description)
            
            result = VisionResult(
                description=description,
                objects_detected=objects,
                confidence=0.85,  # Gemini é confiável
                processing_time_ms=int((time.time() - start_time) * 1000)
            )
            
            # Atualiza cache
            self.last_detection = result
            self.last_detection_time = current_time
            
            logger.info(
                "Visão processada em %sms: %s objetos detectados",
                result.processing_time_ms,
                len(objects)
            )
            
            return result
            
        except Exception as e:
            logger.error("Erro no processamento de visão: %s", e)
            return VisionResult(
                description="Desculpa, tive problema ao processar a imagem.",
                objects_detected=[],
                confidence=0.0,
                processing_time_ms=int((time.time() - start_time) * 1000)
            )
    
    def _extract_objects(self, description: str) -> List[str]:
        """
        Extrai objetos mencionados na descrição.
        Parser simples baseado em keywords.
        """
        objects = []
        
        # Lista de objetos comuns em contexto de programação
        common_objects = [
            "notebook", "laptop", "computador", "teclado", "mouse",
            "arduino", "raspberry pi", "esp32", "esp8266",
            "breadboard", "protoboard", "led", "sensor",
            "livro", "caderno", "monitor", "tela",
            "cabo", "fio", "placa", "circuito",
            "celular", "smartphone", "tablet",
            "café", "caneca", "garrafa",
        ]
        
        description_lower = description.lower()
        
        for obj in common_objects:
            if obj in description_lower:
                objects.append(obj)
        
        return objects
    
    async def quick_object_detection(self, image_data: bytes) -> Optional[str]:
        """
        Detecção rápida: retorna apenas o objeto principal.
        Útil para "o que eu tô segurando?"
        """
        result = await self.analyze_frame(
            image_data,
            user_query="Qual o objeto principal que você vê? Responda em uma palavra ou frase curta."
        )
        
        if result.confidence > 0.5:
            # Pega primeira frase da descrição
            first_sentence = result.description.split('.')[0].strip()
            return first_sentence
        
        return None
    
    def should_analyze_frame(self, user_input: str) -> bool:
        """
        Decide se deve analisar frame baseado na pergunta do usuário.
        """
        vision_triggers = [
            "o que você vê",
            "o que voce ve",
            "o que é isso",
            "o que e isso",
            "o que eu tô",
            "o que eu to",
            "tá vendo",
            "ta vendo",
            "olha isso",
            "veja isso",
            "o que é este",
            "o que e este",
            "identifica",
            "reconhece",
            "descreve isso",
            "que objeto",
        ]
        
        user_lower = user_input.lower()
        return any(trigger in user_lower for trigger in vision_triggers)


class VisionCache:
    """Cache inteligente para frames similares."""
    
    def __init__(self, cache_size: int = 10):
        self.cache = {}
        self.cache_size = cache_size
    
    def _compute_hash(self, image_data: bytes) -> str:
        """Hash rápido da imagem."""
        import hashlib
        return hashlib.md5(image_data[::100]).hexdigest()[:12]  # Sample da imagem
    
    def get(self, image_data: bytes) -> Optional[VisionResult]:
        """Busca resultado similar no cache."""
        img_hash = self._compute_hash(image_data)
        return self.cache.get(img_hash)
    
    def set(self, image_data: bytes, result: VisionResult):
        """Salva resultado no cache."""
        if len(self.cache) >= self.cache_size:
            # Remove mais antigo
            oldest = next(iter(self.cache))
            del self.cache[oldest]
        
        img_hash = self._compute_hash(image_data)
        self.cache[img_hash] = result


_vision_system = None


def get_vision_system() -> VisionSystem:
    """Factory para sistema de visão (singleton)."""
    global _vision_system
    if _vision_system is None:
        _vision_system = VisionSystem()
    return _vision_system
