"""
Tests unitaires pour le module de mémoire conversationnelle.
"""

import asyncio
import os
import sys
import unittest
import time
from typing import Dict, List, Optional

# Ajouter le répertoire parent au path pour pouvoir importer les modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.conversation_memory import ConversationMemory

class TestConversationMemory(unittest.TestCase):
    """Tests pour la classe ConversationMemory."""
    
    def setUp(self):
        """Initialisation avant chaque test."""
        self.memory = ConversationMemory()
        self.session_id = "test-session-123"
        self.topic = "Test de prononciation des voyelles nasales"
        self.last_message = "Nous travaillons sur la prononciation des voyelles nasales en français."
    
    def test_save_and_get_context(self):
        """Teste l'enregistrement et la récupération du contexte."""
        # Enregistrer le contexte
        self.memory.save_context(self.session_id, self.topic, self.last_message)
        
        # Récupérer le contexte
        context = self.memory.get_context(self.session_id)
        
        # Vérifier que le contexte est correctement récupéré
        self.assertIsNotNone(context)
        self.assertEqual(context["topic"], self.topic)
        self.assertEqual(context["last_message"], self.last_message)
        self.assertEqual(context["interruption_count"], 1)
        self.assertIn("timestamp", context)
        self.assertIn("importance", context)
    
    def test_clear_context(self):
        """Teste l'effacement du contexte."""
        # Enregistrer le contexte
        self.memory.save_context(self.session_id, self.topic, self.last_message)
        
        # Vérifier que le contexte existe
        self.assertIsNotNone(self.memory.get_context(self.session_id))
        
        # Effacer le contexte
        self.memory.clear_context(self.session_id)
        
        # Vérifier que le contexte n'existe plus
        self.assertIsNone(self.memory.get_context(self.session_id))
    
    def test_context_expiration(self):
        """Teste l'expiration du contexte."""
        # Modifier la durée de vie du contexte pour le test
        original_ttl = self.memory.context_ttl
        self.memory.context_ttl = 0.1  # 100ms
        
        # Enregistrer le contexte
        self.memory.save_context(self.session_id, self.topic, self.last_message)
        
        # Vérifier que le contexte existe immédiatement
        self.assertIsNotNone(self.memory.get_context(self.session_id))
        
        # Attendre que le contexte expire
        time.sleep(0.2)
        
        # Vérifier que le contexte a expiré
        self.assertIsNone(self.memory.get_context(self.session_id))
        
        # Restaurer la durée de vie originale
        self.memory.context_ttl = original_ttl
    
    def test_extract_topic(self):
        """Teste l'extraction du sujet de la conversation."""
        # Créer un historique de conversation
        history = [
            {"role": "user", "content": "Bonjour, j'aimerais travailler sur ma prononciation."},
            {"role": "assistant", "content": "Bonjour ! Sur quels aspects de votre prononciation souhaitez-vous travailler ?"},
            {"role": "user", "content": "Les voyelles nasales comme 'an', 'in', 'on'."},
            {"role": "assistant", "content": "Excellent choix ! Les voyelles nasales sont souvent difficiles pour les apprenants."}
        ]
        
        # Extraire le sujet
        topic = self.memory.extract_topic(history)
        
        # Vérifier que le sujet contient des mots clés pertinents
        self.assertIn("prononciation", topic.lower())
        
        # Tester avec un historique court
        short_history = [
            {"role": "user", "content": "Bonjour"},
            {"role": "assistant", "content": "Bonjour ! Comment puis-je vous aider ?"}
        ]
        short_topic = self.memory.extract_topic(short_history)
        self.assertIsNotNone(short_topic)
    
    def test_generate_continuity_phrases(self):
        """Teste la génération de phrases de continuité."""
        # Créer un contexte
        context = {
            "topic": self.topic,
            "last_message": self.last_message,
            "interruption_count": 1,
            "timestamp": time.time(),
            "importance": 0.7
        }
        
        # Générer des phrases de continuité pour différents types d'interruption
        question_phrases = self.memory.generate_continuity_phrases(context, "question")
        comment_phrases = self.memory.generate_continuity_phrases(context, "comment")
        general_phrases = self.memory.generate_continuity_phrases(context, "general")
        
        # Vérifier que des phrases sont générées
        self.assertTrue(len(question_phrases) > 0)
        self.assertTrue(len(comment_phrases) > 0)
        self.assertTrue(len(general_phrases) > 0)
        
        # Vérifier que les phrases contiennent le sujet
        for phrase in question_phrases + comment_phrases + general_phrases:
            if self.topic in phrase:
                break
        else:
            self.fail("Aucune phrase ne contient le sujet")
        
        # Tester avec un nombre d'interruptions élevé
        context["interruption_count"] = 3
        many_interruptions = self.memory.generate_continuity_phrases(context)
        self.assertTrue(any("plusieurs fois" in phrase.lower() for phrase in many_interruptions))

if __name__ == '__main__':
    unittest.main()