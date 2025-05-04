from celery import Celery
from core.config import settings

# Créer l'instance de l'application Celery
# Le premier argument est le nom du module courant, important pour l'auto-découverte des tâches.
# Le broker et le backend sont configurés via les settings.
celery_app = Celery(
    "worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["services.kaldi_service"] # Spécifier les modules où chercher les tâches
)

# Configuration optionnelle de Celery (timeouts, etc.)
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],  # Accepter seulement le contenu JSON
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    # task_track_started=True, # Utile pour le monitoring
    # worker_prefetch_multiplier=1, # Traiter une tâche à la fois par worker (prudent pour Kaldi)
    # task_acks_late=True, # Acquitter la tâche après son exécution (plus sûr en cas de crash worker)
)

# Si vous utilisez des schedules (non nécessaire ici mais pour info):
# celery_app.conf.beat_schedule = {
#     'add-every-30-seconds': {
#         'task': 'tasks.add',
#         'schedule': 30.0,
#         'args': (16, 16)
#     },
# }

if __name__ == '__main__':
    # Permet de lancer le worker depuis la ligne de commande
    # Exemple: python -m core.celery_app worker --loglevel=info
    celery_app.start()