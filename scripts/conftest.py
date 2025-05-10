"""
Configuration pour les tests pytest dans le répertoire scripts.
"""
import pytest

# Marquer les tests qui nécessitent des paramètres spécifiques comme skipped
pytestmark = pytest.mark.skip(reason="Ces scripts sont conçus pour être exécutés en ligne de commande, pas comme des tests pytest")

# Fixture pour les tests qui nécessitent des paramètres Supabase
@pytest.fixture
def supabase_project_ref():
    """Fixture pour le paramètre supabase_project_ref."""
    return "test-project-ref"

@pytest.fixture
def supabase_db_password():
    """Fixture pour le paramètre supabase_db_password."""
    return "test-password"

@pytest.fixture
def supabase_region():
    """Fixture pour le paramètre supabase_region."""
    return "test-region"

# Fixture pour les tests qui nécessitent un fichier audio
@pytest.fixture
def audio_file():
    """Fixture pour le paramètre audio_file."""
    return "test-audio-file.wav"