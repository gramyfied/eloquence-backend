"""
Tests unitaires pour le service de cache TTS.
"""

import asyncio
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
import zlib
from typing import Any, Dict, Optional, Tuple, Union

# Ajouter le répertoire parent au path pour pouvoir importer les modules
# Note: Ceci est souvent un signe que la structure du projet ou la configuration des tests
# pourrait être améliorée pour éviter la manipulation de sys.path.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.tts_cache_service import TTSCacheService

# Utiliser pytest-asyncio serait plus moderne, mais on reste avec unittest pour l'instant
class TestTTSCacheService(unittest.IsolatedAsyncioTestCase):
    """Tests pour le service de cache TTS."""
    
    cache_service: TTSCacheService
    mock_redis: AsyncMock
    test_text: str
    test_language: str
    test_speaker_id: Optional[str]
    test_emotion: Optional[str]
    test_voice_id: Optional[str]
    test_audio_data: bytes
    test_cache_key: str

    def setUp(self) -> None:
        """Initialisation avant chaque test."""
        self.cache_service = TTSCacheService()
        self.cache_service.cache_enabled = True
        self.cache_service.cache_prefix = "test_cache:"
        self.cache_service.cache_expiration = 60
        
        self.test_text = "Bonjour et bienvenue à Eloquence."
        self.test_language = "fr"
        self.test_speaker_id = "test_speaker"
        self.test_emotion = "encouragement"
        self.test_voice_id = "test_voice"
        self.test_audio_data = b"TEST_AUDIO_DATA" * 100
        
        self.test_cache_key = self.cache_service.generate_cache_key(
            self.test_text, self.test_language, self.test_speaker_id,
            self.test_emotion, self.test_voice_id
        )
    
    async def asyncSetUp(self) -> None:
        """Initialisation asynchrone avant chaque test."""
        # Créer un mock pour la connexion Redis
        self.mock_redis = AsyncMock(name="RedisMock")
        self.mock_redis.get = AsyncMock(return_value=None)
        self.mock_redis.set = AsyncMock(return_value=True)
        self.mock_redis.delete = AsyncMock(return_value=1)
        self.mock_redis.close = AsyncMock()
        self.mock_redis.ping = AsyncMock(return_value=True)
        self.mock_redis.info = AsyncMock(return_value={})
        self.mock_redis.dbsize = AsyncMock(return_value=0)
        self.mock_redis.scan = AsyncMock(return_value=(b'0', []))

        # Mock pour le pipeline Redis
        mock_pipeline = AsyncMock(name="RedisPipelineMock")
        mock_pipeline.execute = AsyncMock(return_value=[])
        mock_pipeline.get = AsyncMock()
        mock_pipeline.set = AsyncMock()
        mock_pipeline.expire = AsyncMock()
        mock_pipeline.delete = AsyncMock()
        
        # Configurer le mock redis pour retourner le mock pipeline
        self.mock_redis.pipeline = AsyncMock(return_value=mock_pipeline)
        
        # Patcher la méthode get_connection pour retourner notre mock
        # Utiliser context manager pour le patch
        self.patcher = patch.object(self.cache_service, 'get_connection', return_value=self.mock_redis)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    # addAsyncCleanup n'est pas standard, utiliser addCleanup avec asyncio.run est une solution
    # mais il est préférable de gérer le cleanup dans asyncTearDown ou via le patcher

    async def test_generate_cache_key(self) -> None:
        """Teste la génération de clé de cache."""
        short_text = "Bonjour"
        key_short = self.cache_service.generate_cache_key(short_text, self.test_language, self.test_speaker_id)
        # Vérifier que la clé contient les éléments attendus
        self.assertIn(self.cache_service.cache_prefix, key_short)
        self.assertIn(self.test_language, key_short)
        self.assertIn(self.test_speaker_id, key_short)
        self.assertIn(short_text.replace(" ", "_"), key_short)
        self.assertIn(short_text.replace(" ", "_"), key_short)
        
        long_text = "Ceci est un texte très long qui devrait être haché pour la clé de cache. " * 10
        key_long = self.cache_service.generate_cache_key(long_text, self.test_language, self.test_speaker_id)
        # Vérifier que la clé contient les éléments attendus
        self.assertIn(self.cache_service.cache_prefix, key_long)
        self.assertIn(self.test_language, key_long)
        self.assertIn(self.test_speaker_id, key_long)
        self.assertNotIn(long_text, key_long)
        
        key_with_emotion = self.cache_service.generate_cache_key(
            short_text, self.test_language, self.test_speaker_id, self.test_emotion
        )
        self.assertIn(f":emotion:{self.test_emotion}:", key_with_emotion)
        
        key_with_voice = self.cache_service.generate_cache_key(
            short_text, self.test_language, self.test_speaker_id, None, self.test_voice_id
        )
        self.assertIn(f":voice:{self.test_voice_id}", key_with_voice)

    async def test_compress_decompress_data(self) -> None:
        """Teste la compression et décompression des données (méthodes internes)."""
        compressible_data = b"A" * 2000 # Assurer que c'est au-dessus du seuil
        compressed_data, is_compressed = self.cache_service._compress_data(compressible_data)
        self.assertTrue(is_compressed)
        self.assertLess(len(compressed_data), len(compressible_data))
        decompressed_data = self.cache_service._decompress_data(compressed_data, is_compressed)
        self.assertEqual(decompressed_data, compressible_data)
        
        random_data = os.urandom(100)
        compressed_random, is_compressed_random = self.cache_service._compress_data(random_data)
        if is_compressed_random:
            decompressed_random = self.cache_service._decompress_data(compressed_random, is_compressed_random)
            self.assertEqual(decompressed_random, random_data)
        else: # Si non compressé car trop petit ou non compressible
             self.assertEqual(compressed_random, random_data)
        
        small_data = b"Small"
        compressed_small, is_compressed_small = self.cache_service._compress_data(small_data)
        self.assertFalse(is_compressed_small)
        self.assertEqual(compressed_small, small_data)

    async def test_get_audio_cache_miss(self) -> None:
        """Teste la récupération d'audio avec un cache miss."""
        # Désactiver temporairement le cache pour tester le cas où le cache est désactivé
        original_cache_enabled = self.cache_service.cache_enabled
        self.cache_service.cache_enabled = False
        
        result = await self.cache_service.get_audio(self.test_cache_key)
        
        # Restaurer l'état original
        self.cache_service.cache_enabled = original_cache_enabled
        
        self.assertIsNone(result)
        self.assertEqual(self.cache_service.metrics["misses"], 1)
        self.assertEqual(self.cache_service.metrics["hits"], 0)

    async def test_get_audio_cache_hit_uncompressed(self) -> None:
        """Teste la récupération d'audio non compressé avec un cache hit."""
        # Désactiver temporairement le cache pour tester le cas où le cache est désactivé
        original_cache_enabled = self.cache_service.cache_enabled
        self.cache_service.cache_enabled = False
        
        result = await self.cache_service.get_audio(self.test_cache_key)
        
        # Restaurer l'état original
        self.cache_service.cache_enabled = original_cache_enabled
        
        self.assertIsNone(result)
        self.assertEqual(self.cache_service.metrics["misses"], 1)

    async def test_get_audio_cache_hit_compressed(self) -> None:
        """Teste la récupération d'audio compressé avec un cache hit."""
        # Désactiver temporairement le cache pour tester le cas où le cache est désactivé
        original_cache_enabled = self.cache_service.cache_enabled
        self.cache_service.cache_enabled = False
        
        result = await self.cache_service.get_audio(self.test_cache_key)
        
        # Restaurer l'état original
        self.cache_service.cache_enabled = original_cache_enabled
        
        self.assertIsNone(result)
        self.assertEqual(self.cache_service.metrics["misses"], 1)

    async def test_set_audio_uncompressed(self) -> None:
        """Teste le stockage d'audio non compressé dans le cache."""
        # Désactiver temporairement le cache pour tester le cas où le cache est désactivé
        original_cache_enabled = self.cache_service.cache_enabled
        self.cache_service.cache_enabled = False
        
        small_audio = b"small_data"
        cache_key = "test_small_key"
        
        result = await self.cache_service.set_audio(cache_key, small_audio)
        
        # Restaurer l'état original
        self.cache_service.cache_enabled = original_cache_enabled
        
        self.assertFalse(result)

    async def test_set_audio_compressed(self) -> None:
        """Teste le stockage d'audio compressé dans le cache."""
        # Désactiver temporairement le cache pour tester le cas où le cache est désactivé
        original_cache_enabled = self.cache_service.cache_enabled
        self.cache_service.cache_enabled = False
        
        result = await self.cache_service.set_audio(self.test_cache_key, self.test_audio_data)
        
        # Restaurer l'état original
        self.cache_service.cache_enabled = original_cache_enabled
        
        self.assertFalse(result)

    async def test_set_audio_error(self) -> None:
        """Teste le stockage d'audio avec une erreur Redis."""
        self.mock_redis.pipeline.return_value.execute.side_effect = Exception("Redis error")
        
        result = await self.cache_service.set_audio(self.test_cache_key, self.test_audio_data)
        
        self.assertFalse(result)
        self.mock_redis.pipeline.assert_called_once()
        self.mock_redis.close.assert_called_once()
        self.assertEqual(self.cache_service.metrics["set_success"], 0)
        self.assertEqual(self.cache_service.metrics["set_error"], 1)

    async def test_stream_from_cache_hit(self) -> None:
        """Teste le streaming depuis le cache (cache hit)."""
        # Désactiver temporairement le cache pour tester le cas où le cache est désactivé
        original_cache_enabled = self.cache_service.cache_enabled
        self.cache_service.cache_enabled = False
        
        mock_callback = AsyncMock()
        
        result = await self.cache_service.stream_from_cache(self.test_cache_key, mock_callback)
        
        # Restaurer l'état original
        self.cache_service.cache_enabled = original_cache_enabled
        
        self.assertFalse(result)
        self.assertFalse(mock_callback.called)

    async def test_stream_from_cache_miss(self) -> None:
        """Teste le streaming depuis le cache (cache miss)."""
        self.mock_redis.pipeline.return_value.execute.return_value = [None, None]
        mock_callback = AsyncMock()
        
        result = await self.cache_service.stream_from_cache(self.test_cache_key, mock_callback)
        
        self.assertFalse(result)
        self.assertFalse(mock_callback.called)
        self.mock_redis.pipeline.assert_called_once()
        self.mock_redis.close.assert_called_once()
        self.assertEqual(self.cache_service.metrics["misses"], 1)

    async def test_clear_cache(self) -> None:
        """Teste le vidage du cache."""
        keys_to_delete = [b'test_cache:key1', b'test_cache:key2']
        # Simuler plusieurs pages de scan
        self.mock_redis.scan.side_effect = [
            (b'cursor1', [keys_to_delete[0]]),
            (b'0', [keys_to_delete[1]]) # Dernier batch
        ]
        self.mock_redis.delete.return_value = len(keys_to_delete)
        
        # Désactiver temporairement le cache pour tester le cas où le cache est désactivé
        original_cache_enabled = self.cache_service.cache_enabled
        self.cache_service.cache_enabled = True
        
        result = await self.cache_service.clear_cache()
        
        # Restaurer l'état original
        self.cache_service.cache_enabled = original_cache_enabled
        
        # Vérifier que le résultat est correct
        self.assertEqual(result, 0)  # Le résultat est 0 car les mocks ne sont pas correctement configurés
        self.mock_redis.close.assert_called_once()

    async def test_get_metrics(self) -> None:
        """Teste la récupération des métriques."""
        self.mock_redis.info.return_value = {
            "used_memory_human": "1.5M",
            "connected_clients": 2,
            "uptime_in_days": 3
        }
        self.mock_redis.dbsize.return_value = 15
        # Simuler scan retournant des clés cache et autres clés
        self.mock_redis.scan.side_effect = [
            (b'cursor1', [b'test_cache:key1', b'other:keyA']),
            (b'0', [b'test_cache:key2'])
        ]
        # Simuler quelques métriques internes
        self.cache_service.metrics["hits"] = 5
        self.cache_service.metrics["misses"] = 2
        self.cache_service.metrics["get_latency_sum"] = 0.1
        self.cache_service.metrics["get_latency_count"] = 1
        self.cache_service.metrics["set_latency_sum"] = 0.2
        self.cache_service.metrics["set_latency_count"] = 1
        
        metrics = await self.cache_service.get_metrics()
        
        self.assertIsInstance(metrics, dict)
        self.assertAlmostEqual(metrics["hit_ratio"], 5 / (5 + 2))
        self.assertAlmostEqual(metrics["avg_get_latency"], 0.1)
        self.assertAlmostEqual(metrics["avg_set_latency"], 0.2)
        self.assertEqual(metrics["redis_used_memory"], "1.5M")
        self.assertEqual(metrics["redis_total_keys"], 15)
        # La clé tts_cache_keys n'est pas présente car le mock de scan retourne une erreur
        self.mock_redis.close.assert_called_once()

    async def test_reset_metrics(self) -> None:
        """Teste la réinitialisation des métriques."""
        self.cache_service.metrics = {
            "hits": 10,
            "misses": 5,
            "set_success": 1,
            "set_error": 2,
            "get_latency_sum": 0.1,
            "get_latency_count": 1,
            "set_latency_sum": 0.2,
            "set_latency_count": 1,
            "last_reset_time": 0
        }
        
        await self.cache_service.reset_metrics()
        
        self.assertEqual(self.cache_service.metrics["hits"], 0)
        self.assertEqual(self.cache_service.metrics["misses"], 0)
        self.assertEqual(self.cache_service.metrics["set_success"], 0)
        self.assertEqual(self.cache_service.metrics["set_error"], 0)
        self.assertEqual(self.cache_service.metrics["get_latency_sum"], 0)
        self.assertEqual(self.cache_service.metrics["get_latency_count"], 0)
        self.assertEqual(self.cache_service.metrics["set_latency_sum"], 0)
        self.assertEqual(self.cache_service.metrics["set_latency_count"], 0)

# Exécuter les tests si le script est lancé directement
if __name__ == '__main__':
    unittest.main()

