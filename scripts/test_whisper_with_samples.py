#!/usr/bin/env python3
"""
Script pour tester le service Whisper avec des échantillons audio.
Ce script envoie tous les fichiers audio du répertoire assets/test_audio
au service Whisper et affiche les résultats de transcription.
"""
import os
import sys
import requests
import json
import time
from pathlib import Path

# Configuration
WHISPER_URL = "http://localhost:8001"  # URL du service Whisper
AUDIO_DIR = Path(__file__).parent.parent / "assets" / "test_audio"  # Chemin vers les fichiers audio
SUPPORTED_FORMATS = [".wav", ".mp3", ".flac", ".ogg", ".m4a"]  # Formats audio supportés

def test_health():
    """Teste l'endpoint de santé du service Whisper."""
    try:
        response = requests.get(f"{WHISPER_URL}/health")
        print(f"Health check: {response.status_code}")
        if response.status_code == 200:
            print(f"Réponse: {response.text}")
            return True
        else:
            print(f"Erreur: {response.text}")
            return False
    except Exception as e:
        print(f"Erreur lors du health check: {e}")
        return False

def test_asr_endpoint(audio_file):
    """Teste l'endpoint /asr du service Whisper avec un fichier audio."""
    try:
        print(f"\nTest de l'endpoint /asr avec le fichier {audio_file}")
        
        # Vérifier que le fichier existe
        if not os.path.exists(audio_file):
            print(f"Erreur: Le fichier {audio_file} n'existe pas.")
            return False
            
        # Obtenir la taille du fichier
        file_size = os.path.getsize(audio_file)
        print(f"Taille du fichier: {file_size} octets")
        
        # Lire le contenu du fichier
        with open(audio_file, 'rb') as f:
            audio_data = f.read()
            
        # Envoyer la requête avec les données brutes
        headers = {'Content-Type': 'audio/wav'}
        start_time = time.time()
        response = requests.post(
            f"{WHISPER_URL}/asr",
            data=audio_data,
            headers=headers,
            timeout=60
        )
        elapsed_time = time.time() - start_time
        
        print(f"Statut de la réponse: {response.status_code} (temps: {elapsed_time:.2f}s)")
        
        if response.status_code == 200:
            try:
                result = response.json()
                print(f"Réponse JSON: {json.dumps(result, indent=2)}")
                return True
            except Exception as e:
                print(f"Erreur lors du décodage de la réponse JSON: {e}")
                print(f"Contenu brut de la réponse: {response.text}")
                return False
        else:
            print(f"Erreur: {response.text}")
            return False
    except Exception as e:
        print(f"Exception lors du test de /asr: {e}")
        return False

def test_transcribe_endpoint(audio_file):
    """Teste l'endpoint /transcribe du service Whisper avec un fichier audio."""
    try:
        print(f"\nTest de l'endpoint /transcribe avec le fichier {audio_file}")
        
        # Vérifier que le fichier existe
        if not os.path.exists(audio_file):
            print(f"Erreur: Le fichier {audio_file} n'existe pas.")
            return False
            
        # Obtenir la taille du fichier
        file_size = os.path.getsize(audio_file)
        print(f"Taille du fichier: {file_size} octets")
        
        # Préparer la requête multipart/form-data
        files = {
            'audio': (os.path.basename(audio_file), open(audio_file, 'rb'), 'audio/wav')
        }
        
        # Envoyer la requête avec un timeout suffisant
        start_time = time.time()
        response = requests.post(
            f"{WHISPER_URL}/transcribe",
            files=files,
            timeout=60
        )
        elapsed_time = time.time() - start_time
        
        print(f"Statut de la réponse: {response.status_code} (temps: {elapsed_time:.2f}s)")
        
        if response.status_code == 200:
            try:
                result = response.json()
                print(f"Réponse JSON: {json.dumps(result, indent=2)}")
                return True
            except Exception as e:
                print(f"Erreur lors du décodage de la réponse JSON: {e}")
                print(f"Contenu brut de la réponse: {response.text}")
                return False
        else:
            print(f"Erreur: {response.text}")
            return False
    except Exception as e:
        print(f"Exception lors du test de /transcribe: {e}")
        return False

def find_audio_files():
    """Trouve tous les fichiers audio dans le répertoire AUDIO_DIR."""
    if not os.path.exists(AUDIO_DIR):
        print(f"Erreur: Le répertoire {AUDIO_DIR} n'existe pas.")
        return []
        
    audio_files = []
    for root, _, files in os.walk(AUDIO_DIR):
        for file in files:
            if any(file.lower().endswith(ext) for ext in SUPPORTED_FORMATS):
                audio_files.append(os.path.join(root, file))
                
    return audio_files

def main():
    """Fonction principale."""
    print("=== Test du service Whisper avec des échantillons audio ===")
    
    # Tester l'endpoint de santé
    if not test_health():
        print("Erreur: Le service Whisper n'est pas disponible.")
        return 1
        
    # Trouver les fichiers audio
    audio_files = find_audio_files()
    if not audio_files:
        print(f"Aucun fichier audio trouvé dans {AUDIO_DIR}")
        return 1
        
    print(f"Nombre de fichiers audio trouvés: {len(audio_files)}")
    
    # Tester chaque fichier audio
    success_count = 0
    for audio_file in audio_files:
        print(f"\n=== Test du fichier {os.path.basename(audio_file)} ===")
        
        # Tester l'endpoint /asr
        if test_asr_endpoint(audio_file):
            success_count += 1
            
        # Tester l'endpoint /transcribe
        if test_transcribe_endpoint(audio_file):
            success_count += 1
    
    total_tests = len(audio_files) * 2  # 2 tests par fichier audio
    print(f"\n=== Résumé des tests ===")
    print(f"Tests réussis: {success_count}/{total_tests} ({success_count/total_tests*100:.1f}%)")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
