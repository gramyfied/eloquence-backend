"""
Configuration pour les tests.
Ce module est destiné à être importé (ou utilisé comme conftest.py) 
pour appliquer des patches globaux avant l'exécution des tests.
"""
import os
import sys
import logging
from unittest.mock import patch, MagicMock
from typing import Any, Optional, Union
import pathlib

# Créer le répertoire logs s'il n'existe pas (peut être commenté si non nécessaire)
# os.makedirs('/home/ubuntu/eloquence_backend_py/logs', exist_ok=True)

# --- Patch du logging --- 

# Mock pour remplacer logging.FileHandler et éviter l'écriture de fichiers logs
class MockFileHandler(logging.Handler):
    """Un mock de logging.FileHandler qui n'écrit rien."""
    def __init__(self, filename: Union[str, os.PathLike], mode: str = 'a', encoding: Optional[str] = None, delay: bool = False):
        super().__init__()
        self.filename = filename
        self.mode = mode
        self.encoding = encoding
        self.delay = delay
        self.baseFilename = os.path.abspath(filename) # Attribut attendu par certains formateurs
        
    def emit(self, record: logging.LogRecord) -> None:
        """Ne fait rien lors de l'émission d'un enregistrement."""
        pass # Ne rien faire

# Sauvegarder l'original et appliquer le patch
original_file_handler = logging.FileHandler
logging.FileHandler = MockFileHandler

# --- Patch de os.makedirs --- 

# Sauvegarder l'original
original_makedirs = os.makedirs

# Fonction mockée pour os.makedirs
def mock_makedirs_func(path: Union[str, os.PathLike], mode: int = 0o777, exist_ok: bool = False) -> None:
    """Mock de os.makedirs qui évite la création de répertoires spécifiques (ex: logs)."""
    try:
        # Convertir en objet Path pour une manipulation plus facile
        path_obj = pathlib.Path(path)
        # Vérifier si 'logs' est un composant du chemin
        # Adapter cette condition si nécessaire pour cibler d'autres répertoires
        if 'logs' in path_obj.parts:
            # print(f"Mock makedirs: Skipping creation of {path}")
            # Si exist_ok est False et le chemin existe déjà (même si c'est un fichier), 
            # simuler l'erreur FileExistsError comme le ferait l'original.
            # Note: Cette simulation d'erreur est basique.
            if not exist_ok and os.path.exists(path):
                 # Ne lève pas d'erreur si c'est le répertoire 'logs' lui-même et exist_ok=True
                 if not (path_obj.name == 'logs' and exist_ok):
                    # Tenter de simuler FileExistsError si ce n'est pas le répertoire logs lui-même
                    # ou si exist_ok est False.
                    # Pour simplifier, on ne lève pas d'erreur ici, car le but est d'éviter la création.
                    pass 
            return # Ne rien faire pour les chemins contenant 'logs'
    except Exception:
        # En cas d'erreur dans la logique du mock, passer à l'original
        pass 
        
    # Appeler la fonction originale pour tous les autres chemins
    return original_makedirs(path, mode=mode, exist_ok=exist_ok)

# Appliquer le patch
os.makedirs = mock_makedirs_func

# Message indiquant que le setup a été appliqué (peut être utile pour le débogage des tests)
# print("Test setup applied: Logging and directory creation mocked.")

