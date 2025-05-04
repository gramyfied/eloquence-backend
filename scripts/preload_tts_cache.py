#!/usr/bin/env python3
"""
Script pour précharger le cache TTS avec des phrases courantes.
Ce script peut être exécuté périodiquement pour maintenir le cache à jour.
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import List, Dict, Any, Optional

# Ajouter le répertoire parent au path pour pouvoir importer les modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tts_service_optimized import tts_service_optimized
from services.tts_cache_service import tts_cache_service
from core.config import settings

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('preload_tts_cache.log')
    ]
)
logger = logging.getLogger(__name__)

# Phrases courantes pour différentes catégories
COMMON_PHRASES = {
    "greetings": [
        "Bonjour et bienvenue à cette session de coaching vocal.",
        "Bonjour, je suis votre coach vocal. Comment puis-je vous aider aujourd'hui ?",
        "Bienvenue à Eloquence. Je suis là pour vous aider à améliorer votre expression orale.",
        "Bonjour, ravi de vous retrouver pour cette session de coaching.",
        "Bonjour, prêt à travailler sur votre expression orale aujourd'hui ?"
    ],
    "instructions": [
        "Parlez clairement et à un rythme modéré.",
        "Essayez d'articuler davantage sur cette phrase.",
        "Prenez votre temps et respirez entre les phrases.",
        "Concentrez-vous sur la prononciation de ces sons particuliers.",
        "Essayons de travailler sur votre intonation."
    ],
    "feedback_positive": [
        "Très bien ! Votre prononciation s'améliore.",
        "Excellent travail sur cette phrase.",
        "Je remarque une nette amélioration dans votre fluidité.",
        "Votre rythme est beaucoup plus naturel maintenant.",
        "Bravo pour cet effort, c'est exactement ce que je voulais entendre."
    ],
    "feedback_constructive": [
        "Essayez de ralentir un peu sur cette partie.",
        "Vous pourriez améliorer la prononciation de ce son.",
        "Attention à ne pas avaler la fin de vos phrases.",
        "Essayez de mettre plus d'énergie dans votre voix.",
        "Travaillons encore sur cette intonation."
    ],
    "transitions": [
        "Passons maintenant à l'exercice suivant.",
        "Continuons avec un autre type d'exercice.",
        "Maintenant, essayons quelque chose de différent.",
        "Avançons vers la prochaine étape.",
        "Changeons d'approche et essayons ceci."
    ],
    "conclusions": [
        "Merci pour votre participation à cette session.",
        "Vous avez fait de bons progrès aujourd'hui.",
        "N'oubliez pas de pratiquer régulièrement ces exercices.",
        "À bientôt pour une nouvelle session de coaching.",
        "Continuez à pratiquer et vous verrez des améliorations rapides."
    ],
    "interruptions": [
        "Je vous écoute.",
        "Oui, allez-y.",
        "Bien sûr, je vous en prie.",
        "Je vous laisse continuer.",
        "Pardon, je vous ai interrompu."
    ]
}

# Émotions disponibles
EMOTIONS = [
    "neutre",
    "encouragement",
    "empathie",
    "enthousiasme_modere",
    "curiosite",
    "reflexion"
]

async def preload_category(category: str, phrases: List[str], emotion: Optional[str] = None) -> Dict[str, Any]:
    """
    Précharge une catégorie de phrases dans le cache TTS.
    
    Args:
        category: Nom de la catégorie.
        phrases: Liste des phrases à précharger.
        emotion: Émotion à appliquer (optionnel).
        
    Returns:
        Dict[str, Any]: Statistiques sur le préchargement.
    """
    logger.info(f"Préchargement de la catégorie '{category}' avec l'émotion '{emotion or 'neutre'}'...")
    
    result = await tts_service_optimized.preload_common_phrases(
        phrases=phrases,
        language="fr",
        emotion=emotion
    )
    
    logger.info(f"Catégorie '{category}' préchargée: "
               f"{result['newly_cached']} nouvelles phrases, "
               f"{result['already_cached']} déjà en cache, "
               f"{result['failed']} échecs")
    
    return result

async def preload_all_categories(categories: Optional[List[str]] = None, 
                                emotions: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Précharge toutes les catégories de phrases dans le cache TTS.
    
    Args:
        categories: Liste des catégories à précharger (optionnel).
        emotions: Liste des émotions à appliquer (optionnel).
        
    Returns:
        Dict[str, Any]: Statistiques sur le préchargement.
    """
    # Utiliser toutes les catégories si non spécifiées
    if not categories:
        categories = list(COMMON_PHRASES.keys())
    
    # Utiliser toutes les émotions si non spécifiées
    if not emotions:
        emotions = EMOTIONS
    
    # Ajouter None pour l'émotion neutre par défaut
    if "neutre" in emotions and None not in emotions:
        emotions.append(None)
    
    # Statistiques globales
    stats = {
        "total": 0,
        "already_cached": 0,
        "newly_cached": 0,
        "failed": 0,
        "categories": {},
        "emotions": {}
    }
    
    # Précharger chaque catégorie avec chaque émotion
    for category in categories:
        if category not in COMMON_PHRASES:
            logger.warning(f"Catégorie '{category}' non trouvée, ignorée.")
            continue
        
        phrases = COMMON_PHRASES[category]
        stats["categories"][category] = {
            "total": len(phrases) * len(emotions),
            "already_cached": 0,
            "newly_cached": 0,
            "failed": 0
        }
        
        for emotion in emotions:
            # Précharger la catégorie avec l'émotion
            result = await preload_category(category, phrases, emotion)
            
            # Mettre à jour les statistiques globales
            stats["total"] += result["total"]
            stats["already_cached"] += result["already_cached"]
            stats["newly_cached"] += result["newly_cached"]
            stats["failed"] += result["failed"]
            
            # Mettre à jour les statistiques de la catégorie
            stats["categories"][category]["already_cached"] += result["already_cached"]
            stats["categories"][category]["newly_cached"] += result["newly_cached"]
            stats["categories"][category]["failed"] += result["failed"]
            
            # Mettre à jour les statistiques de l'émotion
            emotion_key = emotion or "neutre"
            if emotion_key not in stats["emotions"]:
                stats["emotions"][emotion_key] = {
                    "total": 0,
                    "already_cached": 0,
                    "newly_cached": 0,
                    "failed": 0
                }
            
            stats["emotions"][emotion_key]["total"] += result["total"]
            stats["emotions"][emotion_key]["already_cached"] += result["already_cached"]
            stats["emotions"][emotion_key]["newly_cached"] += result["newly_cached"]
            stats["emotions"][emotion_key]["failed"] += result["failed"]
    
    return stats

async def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(description="Précharge le cache TTS avec des phrases courantes.")
    parser.add_argument("--categories", nargs="+", help="Catégories à précharger")
    parser.add_argument("--emotions", nargs="+", help="Émotions à appliquer")
    parser.add_argument("--clear", action="store_true", help="Vider le cache avant de précharger")
    parser.add_argument("--output", help="Fichier de sortie pour les statistiques (JSON)")
    args = parser.parse_args()
    
    # Vérifier si le cache est activé
    if not tts_cache_service.cache_enabled:
        logger.error("Le cache TTS est désactivé. Activez-le dans les paramètres.")
        return
    
    # Afficher l'état du cache
    logger.info(f"Cache TTS activé avec préfixe '{tts_cache_service.cache_prefix}' "
               f"et expiration de {tts_cache_service.cache_expiration} secondes.")
    
    # Vider le cache si demandé
    if args.clear:
        logger.info("Vidage du cache TTS...")
        keys_deleted = await tts_cache_service.clear_cache()
        logger.info(f"Cache TTS vidé: {keys_deleted} clés supprimées.")
    
    # Précharger les catégories
    logger.info("Préchargement du cache TTS...")
    stats = await preload_all_categories(args.categories, args.emotions)
    
    # Afficher les statistiques
    logger.info(f"Préchargement terminé: "
               f"{stats['newly_cached']} nouvelles phrases, "
               f"{stats['already_cached']} déjà en cache, "
               f"{stats['failed']} échecs.")
    
    # Enregistrer les statistiques dans un fichier si demandé
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        logger.info(f"Statistiques enregistrées dans '{args.output}'.")

if __name__ == "__main__":
    asyncio.run(main())