#!/usr/bin/env python3
"""
Script pour corriger la fonction startup_event dans main.py
"""

import os

# Fichier à modifier
MAIN_PY_PATH = "/home/ubuntu/eloquence_backend_py/app/main.py"

def fix_main_py():
    """
    Modifie la fonction startup_event dans main.py pour éviter l'initialisation
    de l'orchestrateur avec une session de base de données
    """
    print("🔧 Modification de la fonction startup_event dans main.py...")
    
    with open(MAIN_PY_PATH, 'r') as file:
        content = file.read()
    
    # Remplacer la fonction init_orchestrator_background
    old_init_orchestrator = """    # Initialiser l'orchestrateur en arrière-plan pour ne pas bloquer le démarrage
    async def init_orchestrator_background():
        try:
            if AsyncSessionLocal:
                async with AsyncSessionLocal() as db:
                    orchestrator = await get_orchestrator(db)
                    logger.info("Orchestrateur initialisé avec succès")
            else:
                logger.error("Impossible d'initialiser l'Orchestrateur: Session DB non disponible.")
        except Exception as e:
            logger.error(f"Erreur lors de l'initialisation de l'orchestrateur: {e}", exc_info=True)

    # Lancer l'initialisation en arrière-plan
    asyncio.create_task(init_orchestrator_background())
    logger.info("Initialisation de l'orchestrateur lancée en arrière-plan")"""
    
    new_init_orchestrator = """    # Mode sans base de données: initialisation simplifiée de l'orchestrateur
    logger.warning("⚠️ Mode sans base de données: initialisation simplifiée de l'orchestrateur")
    try:
        # Créer un orchestrateur sans session de base de données
        from services.orchestrator import Orchestrator
        orchestrator = Orchestrator()
        # Stocker l'orchestrateur dans le module websocket
        from app.routes.websocket import set_orchestrator
        set_orchestrator(orchestrator)
        logger.info("✅ Orchestrateur initialisé en mode sans base de données")
    except Exception as e:
        logger.error(f"❌ Erreur lors de l'initialisation de l'orchestrateur: {e}", exc_info=True)"""
    
    # Remplacer la fonction create_tables
    old_create_tables = """# Création des tables dans la base de données
async def create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)"""
    
    new_create_tables = """# Création des tables dans la base de données (désactivée en mode sans base de données)
async def create_tables():
    logger.warning("⚠️ Mode sans base de données: création des tables désactivée")
    pass"""
    
    # Remplacer l'appel à create_tables dans startup_event
    old_create_tables_call = """    # Créer les tables dans la base de données
    await create_tables()"""
    
    new_create_tables_call = """    # Mode sans base de données: pas de création de tables
    logger.warning("⚠️ Mode sans base de données: pas de création de tables")"""
    
    # Effectuer les remplacements
    content = content.replace(old_init_orchestrator, new_init_orchestrator)
    content = content.replace(old_create_tables, new_create_tables)
    content = content.replace(old_create_tables_call, new_create_tables_call)
    
    # Écrire le contenu modifié
    with open(MAIN_PY_PATH, 'w') as file:
        file.write(content)
    
    print("✅ Fonction startup_event modifiée avec succès.")
    return True

# Ajouter la fonction set_orchestrator dans websocket.py
def add_set_orchestrator():
    """
    Ajoute la fonction set_orchestrator dans websocket.py
    """
    print("🔧 Ajout de la fonction set_orchestrator dans websocket.py...")
    
    websocket_py_path = "/home/ubuntu/eloquence_backend_py/app/routes/websocket.py"
    
    with open(websocket_py_path, 'r') as file:
        content = file.read()
    
    # Vérifier si la fonction existe déjà
    if "def set_orchestrator(" in content:
        print("✅ La fonction set_orchestrator existe déjà.")
        return True
    
    # Ajouter la fonction set_orchestrator et la variable globale
    add_after_imports = """
# Variable globale pour stocker l'orchestrateur en mode sans base de données
_orchestrator_instance = None

def set_orchestrator(orchestrator):
    # Définit l'instance globale de l'orchestrateur pour le mode sans base de données
    global _orchestrator_instance
    _orchestrator_instance = orchestrator
    return orchestrator

"""
    
    # Effectuer les remplacements
    if "# Variable globale pour stocker l'orchestrateur" not in content:
        # Trouver la position après les imports
        import_end = content.find("_orchestrator_instance = None")
        if import_end == -1:
            # Si on ne trouve pas la variable globale, on la cherche après les imports
            import_end = content.find("import")
            import_end = content.find("\n", import_end)
            content = content[:import_end+1] + add_after_imports + content[import_end+1:]
    
    # Écrire le contenu modifié
    with open(websocket_py_path, 'w') as file:
        file.write(content)
    
    print("✅ Fonction set_orchestrator ajoutée avec succès.")
    return True

if __name__ == "__main__":
    add_set_orchestrator()
    fix_main_py()
    print("🔄 Redémarrez le service pour appliquer les modifications.")
