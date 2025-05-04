#!/usr/bin/env python3
"""
Script pour tester les performances du service TTS optimisé avec cache Redis.
Ce script compare les performances du service TTS avec et sans cache.
"""

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import List, Dict, Any

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
        logging.FileHandler('test_tts_optimization.log')
    ]
)
logger = logging.getLogger(__name__)

# Phrases de test
TEST_PHRASES = [
    "Bonjour et bienvenue à cette session de coaching vocal.",
    "Essayez d'articuler davantage sur cette phrase.",
    "Très bien ! Votre prononciation s'améliore.",
    "Essayez de ralentir un peu sur cette partie.",
    "Passons maintenant à l'exercice suivant.",
    "Merci pour votre participation à cette session.",
    "Je vous écoute.",
    "Cette phrase est plus longue et contient des mots plus complexes comme anticonstitutionnellement.",
    "Voici une phrase avec des nombres: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10.",
    "Voici une phrase avec des caractères spéciaux: é, è, ê, à, ù, ç, œ, æ, ï, ü."
]

# Émotions de test
TEST_EMOTIONS = [
    None,  # Neutre
    "encouragement",
    "empathie",
    "enthousiasme_modere",
    "curiosite",
    "reflexion"
]

async def run_tts_performance_test(phrases: List[str], emotions: List[str],
                              iterations: int = 1, clear_cache: bool = False) -> Dict[str, Any]:
    """
    Teste les performances du service TTS avec et sans cache.
    
    Args:
        phrases: Liste des phrases à tester.
        emotions: Liste des émotions à tester.
        iterations: Nombre d'itérations pour chaque phrase.
        clear_cache: Indique si le cache doit être vidé avant le test.
        
    Returns:
        Dict[str, Any]: Résultats du test.
    """
    # Vider le cache si demandé
    if clear_cache and tts_cache_service.cache_enabled:
        logger.info("Vidage du cache TTS...")
        keys_deleted = await tts_cache_service.clear_cache()
        logger.info(f"Cache TTS vidé: {keys_deleted} clés supprimées.")
    
    # Résultats
    results = {
        "total_phrases": len(phrases) * len(emotions) * iterations,
        "cache_enabled": tts_cache_service.cache_enabled,
        "first_run": {
            "total_time": 0,
            "avg_time": 0,
            "min_time": float('inf'),
            "max_time": 0,
            "details": []
        },
        "second_run": {
            "total_time": 0,
            "avg_time": 0,
            "min_time": float('inf'),
            "max_time": 0,
            "details": []
        }
    }
    
    # Premier passage (sans cache ou cache miss)
    logger.info("=== Premier passage (sans cache ou cache miss) ===")
    for emotion in emotions:
        emotion_name = emotion or "neutre"
        logger.info(f"Émotion: {emotion_name}")
        
        for phrase in phrases:
            for i in range(iterations):
                # Mesurer le temps
                start_time = time.time()
                
                # Synthétiser le texte
                audio_data = await tts_service_optimized.synthesize_text(
                    text=phrase,
                    language="fr",
                    emotion=emotion
                )
                
                # Calculer le temps écoulé
                elapsed_time = time.time() - start_time
                
                # Enregistrer les résultats
                results["first_run"]["total_time"] += elapsed_time
                results["first_run"]["min_time"] = min(results["first_run"]["min_time"], elapsed_time)
                results["first_run"]["max_time"] = max(results["first_run"]["max_time"], elapsed_time)
                
                results["first_run"]["details"].append({
                    "phrase": phrase[:30] + "..." if len(phrase) > 30 else phrase,
                    "emotion": emotion_name,
                    "iteration": i + 1,
                    "time": elapsed_time,
                    "size": len(audio_data) if audio_data else 0
                })
                
                logger.info(f"Phrase: '{phrase[:30]}...' - Temps: {elapsed_time:.3f}s")
    
    # Calculer la moyenne
    if results["first_run"]["details"]:
        results["first_run"]["avg_time"] = results["first_run"]["total_time"] / len(results["first_run"]["details"])
    
    # Deuxième passage (avec cache si activé)
    logger.info("\n=== Deuxième passage (avec cache si activé) ===")
    for emotion in emotions:
        emotion_name = emotion or "neutre"
        logger.info(f"Émotion: {emotion_name}")
        
        for phrase in phrases:
            for i in range(iterations):
                # Mesurer le temps
                start_time = time.time()
                
                # Synthétiser le texte
                audio_data = await tts_service_optimized.synthesize_text(
                    text=phrase,
                    language="fr",
                    emotion=emotion
                )
                
                # Calculer le temps écoulé
                elapsed_time = time.time() - start_time
                
                # Enregistrer les résultats
                results["second_run"]["total_time"] += elapsed_time
                results["second_run"]["min_time"] = min(results["second_run"]["min_time"], elapsed_time)
                results["second_run"]["max_time"] = max(results["second_run"]["max_time"], elapsed_time)
                
                results["second_run"]["details"].append({
                    "phrase": phrase[:30] + "..." if len(phrase) > 30 else phrase,
                    "emotion": emotion_name,
                    "iteration": i + 1,
                    "time": elapsed_time,
                    "size": len(audio_data) if audio_data else 0
                })
                
                logger.info(f"Phrase: '{phrase[:30]}...' - Temps: {elapsed_time:.3f}s")
    
    # Calculer la moyenne
    if results["second_run"]["details"]:
        results["second_run"]["avg_time"] = results["second_run"]["total_time"] / len(results["second_run"]["details"])
    
    # Calculer l'amélioration
    if results["first_run"]["avg_time"] > 0:
        improvement = (results["first_run"]["avg_time"] - results["second_run"]["avg_time"]) / results["first_run"]["avg_time"] * 100
        results["improvement_percent"] = improvement
    else:
        results["improvement_percent"] = 0
    
    # Récupérer les métriques du cache
    if tts_cache_service.cache_enabled:
        results["cache_metrics"] = await tts_cache_service.get_metrics()
    
    return results

async def main():
    """Fonction principale."""
    parser = argparse.ArgumentParser(description="Teste les performances du service TTS optimisé.")
    parser.add_argument("--phrases", type=int, default=5, help="Nombre de phrases à tester")
    parser.add_argument("--emotions", type=int, default=2, help="Nombre d'émotions à tester")
    parser.add_argument("--iterations", type=int, default=1, help="Nombre d'itérations pour chaque phrase")
    parser.add_argument("--clear-cache", action="store_true", help="Vider le cache avant le test")
    parser.add_argument("--disable-cache", action="store_true", help="Désactiver le cache pour le test")
    args = parser.parse_args()
    
    # Limiter le nombre de phrases et d'émotions
    phrases = TEST_PHRASES[:min(args.phrases, len(TEST_PHRASES))]
    emotions = TEST_EMOTIONS[:min(args.emotions, len(TEST_EMOTIONS))]
    
    # Désactiver le cache si demandé
    if args.disable_cache:
        tts_cache_service.cache_enabled = False
        logger.info("Cache TTS désactivé pour le test.")
    
    # Afficher les paramètres du test
    logger.info(f"Test avec {len(phrases)} phrases, {len(emotions)} émotions, {args.iterations} itérations")
    logger.info(f"Cache TTS: {'Activé' if tts_cache_service.cache_enabled else 'Désactivé'}")
    
    # Exécuter le test
    results = await test_tts_performance(phrases, emotions, args.iterations, args.clear_cache)
    
    # Afficher les résultats
    logger.info("\n=== Résultats ===")
    logger.info(f"Nombre total de synthèses: {results['total_phrases']}")
    logger.info(f"Cache TTS: {'Activé' if results['cache_enabled'] else 'Désactivé'}")
    
    logger.info("\nPremier passage:")
    logger.info(f"Temps total: {results['first_run']['total_time']:.3f}s")
    logger.info(f"Temps moyen: {results['first_run']['avg_time']:.3f}s")
    logger.info(f"Temps min: {results['first_run']['min_time']:.3f}s")
    logger.info(f"Temps max: {results['first_run']['max_time']:.3f}s")
    
    logger.info("\nDeuxième passage:")
    logger.info(f"Temps total: {results['second_run']['total_time']:.3f}s")
    logger.info(f"Temps moyen: {results['second_run']['avg_time']:.3f}s")
    logger.info(f"Temps min: {results['second_run']['min_time']:.3f}s")
    logger.info(f"Temps max: {results['second_run']['max_time']:.3f}s")
    
    logger.info(f"\nAmélioration: {results['improvement_percent']:.2f}%")
    
    if tts_cache_service.cache_enabled and "cache_metrics" in results:
        logger.info("\nMétriques du cache:")
        logger.info(f"Hits: {results['cache_metrics']['hits']}")
        logger.info(f"Misses: {results['cache_metrics']['misses']}")
        logger.info(f"Hit ratio: {results['cache_metrics']['hit_ratio']:.2f}")

if __name__ == "__main__":
    asyncio.run(main())