"""
Module de gestion de la mémoire conversationnelle pour le système Eloquence.
Ce module permet de stocker et de récupérer le contexte de la conversation,
notamment pour gérer les interruptions et assurer la continuité thématique.
"""

import logging
import json
import time
from typing import Dict, List, Optional, Any, Tuple

from core.config import settings

logger = logging.getLogger(__name__)

class ConversationMemory:
    """
    Classe gérant la mémoire conversationnelle pour assurer la continuité
    des conversations, notamment après des interruptions.
    """
    
    def __init__(self):
        """Initialise la mémoire conversationnelle."""
        # Dictionnaire stockant les contextes de conversation par session
        self.conversation_contexts: Dict[str, Dict[str, Any]] = {}
        # Durée de vie des contextes en secondes (par défaut: 30 minutes)
        self.context_ttl = getattr(settings, "CONVERSATION_CONTEXT_TTL_S", 1800)
        logger.info(f"Initialisation de la mémoire conversationnelle (TTL: {self.context_ttl}s)")
    
    def save_context(self, session_id: str, topic: str, last_assistant_message: str, 
                    importance: float = 0.5) -> None:
        """
        Sauvegarde le contexte de la conversation pour une session donnée.
        
        Args:
            session_id: Identifiant de la session
            topic: Sujet principal de la conversation
            last_assistant_message: Dernier message de l'assistant avant interruption
            importance: Importance du contexte (0.0 à 1.0)
        """
        self.conversation_contexts[session_id] = {
            "topic": topic,
            "last_message": last_assistant_message,
            "importance": importance,
            "timestamp": time.time(),
            "interruption_count": self.conversation_contexts.get(session_id, {}).get("interruption_count", 0) + 1
        }
        logger.info(f"Contexte de conversation sauvegardé pour session {session_id}: {topic}")
    
    def get_context(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Récupère le contexte de la conversation pour une session donnée.
        
        Args:
            session_id: Identifiant de la session
            
        Returns:
            Optional[Dict[str, Any]]: Contexte de la conversation ou None si non trouvé ou expiré
        """
        context = self.conversation_contexts.get(session_id)
        if not context:
            return None
        
        # Vérifier si le contexte est expiré
        if time.time() - context["timestamp"] > self.context_ttl:
            logger.info(f"Contexte de conversation expiré pour session {session_id}")
            del self.conversation_contexts[session_id]
            return None
        
        return context
    
    def clear_context(self, session_id: str) -> None:
        """
        Efface le contexte de la conversation pour une session donnée.
        
        Args:
            session_id: Identifiant de la session
        """
        if session_id in self.conversation_contexts:
            del self.conversation_contexts[session_id]
            logger.info(f"Contexte de conversation effacé pour session {session_id}")
    
    def extract_topic(self, history: List[Dict[str, str]], max_messages: int = 6) -> str:
        """
        Extrait le sujet principal de la conversation à partir de l'historique.
        
        Args:
            history: Historique de la conversation
            max_messages: Nombre maximum de messages à considérer
            
        Returns:
            str: Sujet principal de la conversation
        """
        # Prendre les derniers messages
        recent_history = history[-max_messages:] if len(history) > max_messages else history
        
        # Extraire le texte des messages
        messages_text = []
        for msg in recent_history:
            if msg["role"] == "assistant":
                messages_text.append(f"Coach: {msg['content']}")
            else:
                messages_text.append(f"Utilisateur: {msg['content']}")
        
        # Joindre les messages
        conversation_text = "\n".join(messages_text)
        
        # Extraire le sujet (implémentation simple)
        # Dans une version plus avancée, on pourrait utiliser un modèle d'IA pour extraire le sujet
        words = conversation_text.split()
        if len(words) > 20:
            topic = " ".join(words[:20]) + "..."
        else:
            topic = conversation_text
        
        return topic
    
    def generate_continuity_phrases(self, context: Dict[str, Any], 
                                   interruption_type: str = "question") -> List[str]:
        """
        Génère des phrases de continuité adaptées au contexte.
        
        Args:
            context: Contexte de la conversation
            interruption_type: Type d'interruption (question, commentaire, etc.)
            
        Returns:
            List[str]: Liste de phrases de continuité
        """
        # Phrases de base pour différents types d'interruption
        continuity_phrases = {
            "question": [
                "Pour revenir à notre sujet,",
                "Maintenant que j'ai répondu à votre question, revenons à",
                "Bien, reprenons où nous en étions.",
                "Pour continuer sur ce que nous disions,"
            ],
            "comment": [
                "Je note votre commentaire. Pour revenir à notre discussion,",
                "Merci pour cette précision. Revenons à",
                "C'est bien noté. Continuons avec",
                "Je comprends. Pour poursuivre notre conversation,"
            ],
            "general": [
                "Revenons à notre conversation sur",
                "Pour reprendre le fil de notre discussion,",
                "Où en étions-nous ? Ah oui,",
                "Reprenons notre travail sur"
            ]
        }
        
        # Sélectionner le type de phrases
        phrases = continuity_phrases.get(interruption_type, continuity_phrases["general"])
        
        # Adapter les phrases au contexte
        topic = context.get("topic", "notre sujet")
        adapted_phrases = []
        for phrase in phrases:
            if phrase.endswith(",") or phrase.endswith(":"):
                adapted_phrases.append(f"{phrase} {topic}")
            else:
                adapted_phrases.append(phrase)
        
        # Ajouter des phrases spécifiques basées sur le nombre d'interruptions
        interruption_count = context.get("interruption_count", 1)
        if interruption_count > 2:
            adapted_phrases.append("Nous avons été interrompus plusieurs fois, mais continuons avec notre sujet principal.")
        
        return adapted_phrases

# Instance singleton
conversation_memory = ConversationMemory()