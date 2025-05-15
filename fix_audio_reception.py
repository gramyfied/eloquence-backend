#!/usr/bin/env python3
"""
Script pour corriger les problèmes de réception audio dans l'application Eloquence.
Ce script modifie les fichiers nécessaires pour assurer que le serveur confirme correctement
le début du streaming audio et traite les données audio de manière fiable.
"""

import os
import re
import logging
import shutil
import sys
from datetime import datetime

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("fix_audio_reception")

# Chemins des fichiers à modifier
WEBSOCKET_SIMPLE_PATH = "eloquence_backend_py/app/routes/websocket_simple.py"
ASR_SERVICE_PATH = "eloquence_backend_py/services/asr_service.py"
ORCHESTRATOR_PATH = "eloquence_backend_py/core/orchestrator.py"

def backup_file(file_path):
    """Crée une sauvegarde du fichier avant modification."""
    if not os.path.exists(file_path):
        logger.error(f"Le fichier {file_path} n'existe pas.")
        return False
    
    backup_path = f"{file_path}.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
    try:
        shutil.copy2(file_path, backup_path)
        logger.info(f"Sauvegarde créée: {backup_path}")
        return True
    except Exception as e:
        logger.error(f"Erreur lors de la création de la sauvegarde: {e}")
        return False

def fix_websocket_simple():
    """Modifie le gestionnaire WebSocket pour confirmer le début du streaming."""
    if not os.path.exists(WEBSOCKET_SIMPLE_PATH):
        logger.error(f"Le fichier {WEBSOCKET_SIMPLE_PATH} n'existe pas.")
        return False
    
    if not backup_file(WEBSOCKET_SIMPLE_PATH):
        return False
    
    try:
        with open(WEBSOCKET_SIMPLE_PATH, 'r') as file:
            content = file.read()
        
        # Ajouter l'attribut pour suivre l'état de confirmation du streaming
        if "self.stream_started = False" not in content:
            content = re.sub(
                r'(def __init__\([^)]*\):\s+[^\n]*\n)',
                r'\1        self.stream_started = False\n',
                content
            )
        
        # Ajouter la gestion des messages de type "start_stream"
        if "start_stream_confirmed" not in content:
            # Trouver la méthode on_receive
            on_receive_pattern = r'async def on_receive\(self, websocket, data\):'
            on_receive_match = re.search(on_receive_pattern, content)
            
            if on_receive_match:
                # Position de début de la méthode on_receive
                start_pos = on_receive_match.start()
                
                # Trouver le bloc qui gère les messages JSON
                json_handling_pattern = r'if isinstance\(data, str\):\s+try:\s+json_data = json\.loads\(data\)'
                json_handling_match = re.search(json_handling_pattern, content[start_pos:])
                
                if json_handling_match:
                    # Position relative dans la méthode on_receive
                    json_handling_pos = json_handling_match.end() + start_pos
                    
                    # Trouver le bloc qui traite les types de messages
                    message_type_pattern = r'if "type" in json_data:'
                    message_type_match = re.search(message_type_pattern, content[json_handling_pos:])
                    
                    if message_type_match:
                        # Position du bloc de traitement des types de messages
                        message_type_pos = message_type_match.end() + json_handling_pos
                        
                        # Ajouter le traitement du message "start_stream"
                        start_stream_handler = """
                            if json_data["type"] == "start_stream":
                                logger.info(f"Début de streaming audio demandé par le client: {json_data}")
                                self.stream_started = True
                                # Envoyer une confirmation au client
                                await websocket.send(json.dumps({
                                    "type": "start_stream_confirmed",
                                    "message": "Streaming audio démarré avec succès"
                                }))
                                return
                        """
                        
                        # Insérer le gestionnaire de start_stream après le bloc "if 'type' in json_data:"
                        content = content[:message_type_pos] + start_stream_handler + content[message_type_pos:]
        
        # Écrire les modifications dans le fichier
        with open(WEBSOCKET_SIMPLE_PATH, 'w') as file:
            file.write(content)
        
        logger.info(f"Le fichier {WEBSOCKET_SIMPLE_PATH} a été modifié avec succès.")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la modification de {WEBSOCKET_SIMPLE_PATH}: {e}")
        return False

def fix_asr_service():
    """Améliore la gestion des erreurs dans le service ASR."""
    if not os.path.exists(ASR_SERVICE_PATH):
        logger.error(f"Le fichier {ASR_SERVICE_PATH} n'existe pas.")
        return False
    
    if not backup_file(ASR_SERVICE_PATH):
        return False
    
    try:
        with open(ASR_SERVICE_PATH, 'r') as file:
            content = file.read()
        
        # Améliorer la journalisation des erreurs de transcription
        if "Erreur lors de la transcription audio" not in content:
            # Trouver la méthode transcribe_audio
            transcribe_pattern = r'async def transcribe_audio\(self, audio_data\):'
            transcribe_match = re.search(transcribe_pattern, content)
            
            if transcribe_match:
                # Position de début de la méthode transcribe_audio
                start_pos = transcribe_match.start()
                
                # Trouver le bloc try/except
                try_except_pattern = r'try:.*?except Exception as e:'
                try_except_match = re.search(try_except_pattern, content[start_pos:], re.DOTALL)
                
                if try_except_match:
                    # Position du bloc except
                    except_pos = try_except_match.end() + start_pos
                    
                    # Trouver la fin du bloc except
                    except_end_pattern = r'return None'
                    except_end_match = re.search(except_end_pattern, content[except_pos:])
                    
                    if except_end_match:
                        # Position de "return None"
                        return_none_pos = except_end_match.start() + except_pos
                        
                        # Améliorer la journalisation des erreurs
                        improved_logging = """
            logger.error(f"Erreur lors de la transcription audio: {e}")
            logger.error(f"Taille des données audio: {len(audio_data) if audio_data else 'None'} octets")
            """
                        
                        # Insérer la journalisation améliorée avant "return None"
                        content = content[:return_none_pos] + improved_logging + content[return_none_pos:]
        
        # Ajouter une vérification des données audio vides ou trop petites
        if "Données audio vides ou trop petites" not in content:
            # Trouver le début de la méthode transcribe_audio
            transcribe_pattern = r'async def transcribe_audio\(self, audio_data\):'
            transcribe_match = re.search(transcribe_pattern, content)
            
            if transcribe_match:
                # Position de début de la méthode transcribe_audio
                start_pos = transcribe_match.end()
                
                # Trouver le début du bloc try
                try_pattern = r'try:'
                try_match = re.search(try_pattern, content[start_pos:])
                
                if try_match:
                    # Position du bloc try
                    try_pos = try_match.start() + start_pos
                    
                    # Ajouter la vérification des données audio
                    audio_check = """
        # Vérifier si les données audio sont valides
        if not audio_data or len(audio_data) < 1000:  # Moins de 1KB est probablement trop petit
            logger.warning(f"Données audio vides ou trop petites: {len(audio_data) if audio_data else 'None'} octets")
            return None
            
        """
                    
                    # Insérer la vérification avant le bloc try
                    content = content[:try_pos] + audio_check + content[try_pos:]
        
        # Écrire les modifications dans le fichier
        with open(ASR_SERVICE_PATH, 'w') as file:
            file.write(content)
        
        logger.info(f"Le fichier {ASR_SERVICE_PATH} a été modifié avec succès.")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la modification de {ASR_SERVICE_PATH}: {e}")
        return False

def fix_orchestrator():
    """Améliore la journalisation des messages audio dans l'orchestrateur."""
    if not os.path.exists(ORCHESTRATOR_PATH):
        logger.error(f"Le fichier {ORCHESTRATOR_PATH} n'existe pas.")
        return False
    
    if not backup_file(ORCHESTRATOR_PATH):
        return False
    
    try:
        with open(ORCHESTRATOR_PATH, 'r') as file:
            content = file.read()
        
        # Améliorer la journalisation des messages audio
        if "Réception de données audio binaires" not in content:
            # Trouver la méthode handle_binary_message
            binary_pattern = r'async def handle_binary_message\(self, websocket, data\):'
            binary_match = re.search(binary_pattern, content)
            
            if binary_match:
                # Position de début de la méthode handle_binary_message
                start_pos = binary_match.end()
                
                # Trouver le début du corps de la méthode
                method_body_pattern = r'\n\s+'
                method_body_match = re.search(method_body_pattern, content[start_pos:])
                
                if method_body_match:
                    # Position du début du corps de la méthode
                    method_body_pos = method_body_match.end() + start_pos
                    
                    # Améliorer la journalisation
                    improved_logging = """
        logger.info(f"Réception de données audio binaires: {len(data)} octets")
        """
                    
                    # Insérer la journalisation améliorée au début de la méthode
                    content = content[:method_body_pos] + improved_logging + content[method_body_pos:]
        
        # Améliorer la gestion des erreurs de transcription
        if "Erreur de transcription audio" not in content:
            # Trouver la méthode handle_binary_message
            binary_pattern = r'async def handle_binary_message\(self, websocket, data\):'
            binary_match = re.search(binary_pattern, content)
            
            if binary_match:
                # Position de début de la méthode handle_binary_message
                start_pos = binary_match.start()
                
                # Trouver le bloc qui appelle transcribe_audio
                transcribe_pattern = r'transcription = await self\.asr_service\.transcribe_audio\(data\)'
                transcribe_match = re.search(transcribe_pattern, content[start_pos:])
                
                if transcribe_match:
                    # Position après l'appel à transcribe_audio
                    transcribe_pos = transcribe_match.end() + start_pos
                    
                    # Trouver le bloc qui vérifie si la transcription est None
                    check_none_pattern = r'if transcription is None:'
                    check_none_match = re.search(check_none_pattern, content[transcribe_pos:])
                    
                    if check_none_match:
                        # Position du bloc if transcription is None
                        check_none_pos = check_none_match.end() + transcribe_pos
                        
                        # Trouver la fin de la ligne
                        line_end_pattern = r'\n'
                        line_end_match = re.search(line_end_pattern, content[check_none_pos:])
                        
                        if line_end_match:
                            # Position de la fin de la ligne
                            line_end_pos = line_end_match.start() + check_none_pos
                            
                            # Améliorer la gestion des erreurs
                            improved_error_handling = """
            logger.error("Erreur de transcription audio: La transcription a échoué")
            await websocket.send(json.dumps({
                "type": "transcription_error",
                "message": "La transcription audio a échoué"
            }))
            return"""
                            
                            # Remplacer le contenu après "if transcription is None:"
                            content = content[:check_none_pos] + improved_error_handling + content[line_end_pos:]
        
        # Écrire les modifications dans le fichier
        with open(ORCHESTRATOR_PATH, 'w') as file:
            file.write(content)
        
        logger.info(f"Le fichier {ORCHESTRATOR_PATH} a été modifié avec succès.")
        return True
    
    except Exception as e:
        logger.error(f"Erreur lors de la modification de {ORCHESTRATOR_PATH}: {e}")
        return False

def main():
    """Fonction principale qui exécute toutes les corrections."""
    logger.info("Début des corrections pour la réception audio dans Eloquence")
    
    # Vérifier si les fichiers existent
    files_exist = True
    for file_path in [WEBSOCKET_SIMPLE_PATH, ASR_SERVICE_PATH, ORCHESTRATOR_PATH]:
        if not os.path.exists(file_path):
            logger.error(f"Le fichier {file_path} n'existe pas.")
            files_exist = False
    
    if not files_exist:
        logger.error("Certains fichiers nécessaires n'existent pas. Vérifiez les chemins.")
        return False
    
    # Appliquer les corrections
    websocket_fixed = fix_websocket_simple()
    asr_fixed = fix_asr_service()
    orchestrator_fixed = fix_orchestrator()
    
    # Résumé des modifications
    logger.info("\n=== Résumé des modifications ===")
    logger.info(f"WebSocket Simple: {'✅ Corrigé' if websocket_fixed else '❌ Échec'}")
    logger.info(f"Service ASR: {'✅ Corrigé' if asr_fixed else '❌ Échec'}")
    logger.info(f"Orchestrateur: {'✅ Corrigé' if orchestrator_fixed else '❌ Échec'}")
    
    if websocket_fixed and asr_fixed and orchestrator_fixed:
        logger.info("\n✅ Toutes les corrections ont été appliquées avec succès.")
        logger.info("Pour appliquer les changements, redémarrez le service API:")
        logger.info("  sudo systemctl restart eloquence-api-service")
        return True
    else:
        logger.error("\n❌ Certaines corrections n'ont pas pu être appliquées.")
        logger.error("Vérifiez les erreurs ci-dessus et essayez à nouveau.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
