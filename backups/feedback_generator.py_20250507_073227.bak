"""
Service de génération de feedback personnalisé basé sur les résultats de l'analyse Kaldi.
Utilise le LLM pour générer des suggestions d'amélioration contextuelles et personnalisées.
"""

import logging
import json
from typing import Dict, List, Any, Optional

from services.llm_service import LlmService
from core.config import settings

logger = logging.getLogger(__name__)

class FeedbackGenerator:
    """
    Service de génération de feedback personnalisé basé sur les résultats de l'analyse Kaldi.
    """
    
    def __init__(self, llm_service: Optional[LlmService] = None):
        """
        Initialise le générateur de feedback.
        
        Args:
            llm_service: Service LLM à utiliser (optionnel, sinon crée une nouvelle instance)
        """
        self.llm_service = llm_service or LlmService()
        logger.info("Initialisation du générateur de feedback personnalisé")
    
    async def generate_feedback(self, 
                               kaldi_results: Dict[str, Any], 
                               transcription: str,
                               user_level: str = "intermédiaire",
                               session_history: Optional[List[Dict[str, Any]]] = None,
                               focus_areas: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Génère un feedback personnalisé basé sur les résultats de l'analyse Kaldi.
        
        Args:
            kaldi_results: Résultats de l'analyse Kaldi
            transcription: Transcription du segment audio
            user_level: Niveau de l'utilisateur (débutant, intermédiaire, avancé)
            session_history: Historique des segments précédents (optionnel)
            focus_areas: Domaines sur lesquels se concentrer (prononciation, fluidité, etc.) (optionnel)
            
        Returns:
            Dict[str, Any]: Feedback personnalisé
        """
        # Extraire les différentes parties des résultats Kaldi
        pronunciation_results = kaldi_results.get("pronunciation_scores", {})
        fluency_results = kaldi_results.get("fluency_metrics", {})
        lexical_results = kaldi_results.get("lexical_metrics", {})
        prosody_results = kaldi_results.get("prosody_metrics", {})
        
        # Construire le prompt pour le LLM
        prompt = self._build_feedback_prompt(
            pronunciation_results=pronunciation_results,
            fluency_results=fluency_results,
            lexical_results=lexical_results,
            prosody_results=prosody_results,
            transcription=transcription,
            user_level=user_level,
            session_history=session_history,
            focus_areas=focus_areas
        )
        
        # Générer le feedback avec le LLM
        try:
            llm_response = await self.llm_service.generate(
                history=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "Génère un feedback personnalisé basé sur ces résultats d'analyse vocale."}
                ],
                is_interrupted=False
            )
            
            # Extraire le texte de la réponse
            feedback_text = llm_response.get("text_response", "")
            
            # Essayer d'extraire les suggestions structurées du texte
            structured_suggestions = self._extract_structured_suggestions(feedback_text)
            
            # Construire le résultat
            result = {
                "feedback_text": feedback_text,
                "structured_suggestions": structured_suggestions,
                "emotion": llm_response.get("emotion_label", "encouragement")
            }
            
            return result
        
        except Exception as e:
            logger.error(f"Erreur lors de la génération du feedback personnalisé: {e}")
            # Retourner un feedback par défaut en cas d'erreur
            return {
                "feedback_text": "Nous avons analysé votre prononciation. Continuez à pratiquer régulièrement.",
                "structured_suggestions": [],
                "emotion": "encouragement"
            }
    
    def _build_feedback_prompt(self,
                              pronunciation_results: Dict[str, Any],
                              fluency_results: Dict[str, Any],
                              lexical_results: Dict[str, Any],
                              prosody_results: Dict[str, Any],
                              transcription: str,
                              user_level: str,
                              session_history: Optional[List[Dict[str, Any]]] = None,
                              focus_areas: Optional[List[str]] = None) -> str:
        """
        Construit le prompt pour le LLM.
        
        Args:
            pronunciation_results: Résultats de prononciation
            fluency_results: Résultats de fluidité
            lexical_results: Résultats de richesse lexicale
            prosody_results: Résultats de prosodie
            transcription: Transcription du segment audio
            user_level: Niveau de l'utilisateur
            session_history: Historique des segments précédents (optionnel)
            focus_areas: Domaines sur lesquels se concentrer (optionnel)
            
        Returns:
            str: Prompt pour le LLM
        """
        # Extraire les informations clés des résultats
        overall_pronunciation_score = pronunciation_results.get("overall_gop_score", 0)
        problematic_phonemes = pronunciation_results.get("problematic_phonemes", [])
        speech_rate = fluency_results.get("speech_rate_wpm", 0)
        silence_ratio = fluency_results.get("silence_ratio", 0)
        filled_pauses = fluency_results.get("filled_pauses_count", 0)
        type_token_ratio = lexical_results.get("type_token_ratio", 0)
        repeated_words = lexical_results.get("repeated_words", [])
        
        # Construire le prompt
        prompt = f"""Tu es un coach vocal expert qui fournit des feedbacks personnalisés et constructifs.

CONTEXTE:
- Niveau de l'apprenant: {user_level}
- Transcription: "{transcription}"

RÉSULTATS D'ANALYSE:

1. PRONONCIATION:
   - Score global: {overall_pronunciation_score}/1.0
   - Phonèmes problématiques: {', '.join([f"{p.get('ph', '')} ({p.get('score', 0):.2f})" for p in problematic_phonemes[:5]])}

2. FLUIDITÉ:
   - Débit: {speech_rate} mots/minute
   - Ratio de silence: {silence_ratio}
   - Pauses remplies (hésitations): {filled_pauses}

3. RICHESSE LEXICALE:
   - Ratio type/token: {type_token_ratio}
   - Mots répétés: {', '.join(repeated_words[:5])}

4. PROSODIE:
   - Variation de hauteur: {prosody_results.get('pitch_variation', 'N/A')}
   - Variation d'énergie: {prosody_results.get('energy_variation', 'N/A')}
"""

        # Ajouter l'historique des segments précédents si disponible
        if session_history and len(session_history) > 0:
            prompt += "\nHISTORIQUE DES SESSIONS PRÉCÉDENTES:\n"
            for i, segment in enumerate(session_history[-3:]):  # Limiter à 3 segments
                prompt += f"- Session {i+1}: Score prononciation: {segment.get('pronunciation_score', 'N/A')}, "
                prompt += f"Fluidité: {segment.get('fluency_score', 'N/A')}\n"

        # Ajouter les domaines sur lesquels se concentrer si disponibles
        if focus_areas and len(focus_areas) > 0:
            prompt += f"\nDOMAINES DE CONCENTRATION: {', '.join(focus_areas)}\n"

        # Instructions pour le LLM
        prompt += """
TÂCHE:
1. Analyse ces résultats et génère un feedback personnalisé, encourageant et constructif.
2. Commence par un point positif, puis suggère 2-3 améliorations spécifiques et réalisables.
3. Adapte ton feedback au niveau de l'apprenant.
4. Fournis des exercices pratiques spécifiques pour chaque suggestion.
5. Structure ton feedback en sections claires.
6. Termine par un encouragement.

FORMAT DE RÉPONSE:
- Commence par un paragraphe général d'introduction positif
- Utilise des sections avec des titres pour chaque domaine d'amélioration
- Pour chaque suggestion, inclus un exercice pratique
- Termine par un encouragement
- Utilise un ton bienveillant et motivant
- Limite ta réponse à environ 250-300 mots

IMPORTANT: Inclus une section "SUGGESTIONS STRUCTURÉES" à la fin de ta réponse, au format JSON, avec cette structure:
```json
{
  "points_forts": ["point fort 1", "point fort 2"],
  "points_amélioration": [
    {"domaine": "prononciation", "description": "description", "exercice": "exercice pratique"},
    {"domaine": "fluidité", "description": "description", "exercice": "exercice pratique"}
  ],
  "priorité": "domaine prioritaire"
}
```
"""

        return prompt
    
    def _extract_structured_suggestions(self, feedback_text: str) -> Dict[str, Any]:
        """
        Extrait les suggestions structurées du texte de feedback.
        
        Args:
            feedback_text: Texte de feedback généré par le LLM
            
        Returns:
            Dict[str, Any]: Suggestions structurées
        """
        # Valeurs par défaut
        structured_suggestions = {
            "points_forts": [],
            "points_amélioration": [],
            "priorité": ""
        }
        
        try:
            # Chercher la section JSON dans le texte
            json_start = feedback_text.find("```json")
            json_end = feedback_text.rfind("```")
            
            if json_start != -1 and json_end != -1 and json_end > json_start:
                # Extraire le JSON
                json_text = feedback_text[json_start + 7:json_end].strip()
                # Parser le JSON
                suggestions = json.loads(json_text)
                # Mettre à jour les suggestions structurées
                structured_suggestions.update(suggestions)
        except Exception as e:
            logger.warning(f"Erreur lors de l'extraction des suggestions structurées: {e}")
        
        return structured_suggestions

# Instance singleton
feedback_generator = FeedbackGenerator()