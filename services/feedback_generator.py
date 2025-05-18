"""
Générateur de feedback pour les résultats d'analyse Kaldi.
Ce module génère des feedbacks personnalisés basés sur les résultats d'analyse de prononciation.
"""

import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class FeedbackGenerator:
    """
    Générateur de feedback pour les résultats d'analyse Kaldi.
    """
    
    async def generate_feedback(
        self,
        kaldi_results: Dict[str, Any],
        transcription: str,
        user_level: str = "intermédiaire",
        session_history: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Génère un feedback personnalisé basé sur les résultats de l'analyse Kaldi.
        
        Args:
            kaldi_results: Résultats de l'analyse Kaldi
            transcription: Transcription du segment audio
            user_level: Niveau de l'utilisateur (débutant, intermédiaire, avancé)
            session_history: Historique des segments précédents
            
        Returns:
            Dict[str, Any]: Feedback personnalisé
        """
        try:
            # Extraire les scores de prononciation
            pronunciation_scores = kaldi_results.get("pronunciation_scores", {})
            overall_score = pronunciation_scores.get("overall_gop_score", 0)
            problematic_phonemes = pronunciation_scores.get("problematic_phonemes", [])
            
            # Extraire les métriques de fluidité
            fluency_metrics = kaldi_results.get("fluency_metrics", {})
            speech_rate = fluency_metrics.get("speech_rate_wpm", 0)
            silence_ratio = fluency_metrics.get("silence_ratio", 0)
            filled_pauses = fluency_metrics.get("filled_pauses_count", 0)
            
            # Extraire les métriques lexicales
            lexical_metrics = kaldi_results.get("lexical_metrics", {})
            
            # Générer un feedback adapté au niveau de l'utilisateur
            feedback_text = ""
            structured_suggestions = []
            emotion = "neutre"
            
            # Feedback sur la prononciation
            if overall_score < 0.6:
                feedback_text += "Votre prononciation nécessite encore du travail. "
                emotion = "encouragement"
            elif overall_score < 0.8:
                feedback_text += "Votre prononciation est correcte mais peut être améliorée. "
                emotion = "neutre"
            else:
                feedback_text += "Votre prononciation est très bonne. "
                emotion = "positif"
            
            # Ajouter des suggestions spécifiques pour les phonèmes problématiques
            if problematic_phonemes and len(problematic_phonemes) > 0:
                phoneme_count = min(3, len(problematic_phonemes))
                phonemes_to_work = [p["ph"] for p in problematic_phonemes[:phoneme_count]]
                
                feedback_text += f"Concentrez-vous sur l'amélioration des sons suivants : {', '.join(phonemes_to_work)}. "
                
                structured_suggestions.append({
                    "type": "pronunciation",
                    "focus": "phonemes",
                    "elements": phonemes_to_work,
                    "suggestion": f"Pratiquez ces sons en isolation puis dans des mots complets."
                })
            
            # Feedback sur la fluidité
            if speech_rate < 100:
                feedback_text += "Votre débit de parole est un peu lent. Essayez de parler plus naturellement. "
                structured_suggestions.append({
                    "type": "fluency",
                    "focus": "speech_rate",
                    "suggestion": "Essayez de parler plus rapidement tout en maintenant une bonne articulation."
                })
            elif speech_rate > 180:
                feedback_text += "Votre débit de parole est très rapide. Ralentissez un peu pour améliorer votre clarté. "
                structured_suggestions.append({
                    "type": "fluency",
                    "focus": "speech_rate",
                    "suggestion": "Ralentissez légèrement votre débit pour améliorer la clarté."
                })
            
            if silence_ratio > 0.3:
                feedback_text += "Vos pauses sont un peu longues. Essayez de maintenir un flux de parole plus continu. "
                structured_suggestions.append({
                    "type": "fluency",
                    "focus": "pauses",
                    "suggestion": "Réduisez la durée de vos pauses pour un discours plus fluide."
                })
            
            if filled_pauses > 3:
                feedback_text += "Vous utilisez beaucoup de pauses remplies ('euh', 'um'). Essayez de les réduire. "
                structured_suggestions.append({
                    "type": "fluency",
                    "focus": "filled_pauses",
                    "suggestion": "Remplacez les 'euh' par de courtes pauses silencieuses."
                })
            
            # Adapter le feedback au niveau de l'utilisateur
            if user_level == "débutant":
                feedback_text += "Continuez à pratiquer régulièrement, vous progressez bien ! "
                emotion = "encouragement"
            elif user_level == "intermédiaire":
                feedback_text += "Vous avez une bonne base, continuez à travailler sur les détails. "
            elif user_level == "avancé":
                feedback_text += "Concentrez-vous sur les nuances fines pour perfectionner votre prononciation. "
            
            # Retourner le feedback structuré
            return {
                "feedback_text": feedback_text.strip(),
                "structured_suggestions": structured_suggestions,
                "emotion": emotion
            }
            
        except Exception as e:
            logger.error(f"Erreur lors de la génération du feedback: {e}", exc_info=True)
            return {
                "feedback_text": "Nous avons analysé votre prononciation. Continuez à pratiquer régulièrement.",
                "structured_suggestions": [],
                "emotion": "encouragement"
            }

# Instance singleton du générateur de feedback
feedback_generator = FeedbackGenerator()