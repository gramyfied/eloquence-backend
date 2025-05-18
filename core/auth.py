"""
Module d'authentification et d'autorisation pour l'API Eloquence.
Fournit des fonctions pour vérifier l'identité de l'utilisateur et ses droits d'accès.
"""

import logging
from typing import Optional
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.config import settings

logger = logging.getLogger(__name__)

# Initialiser le schéma de sécurité HTTP Bearer
security = HTTPBearer(auto_error=False)

async def get_current_user_id(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> str:
    """
    Récupère l'ID de l'utilisateur actuel à partir du token d'authentification.
    En mode DEBUG, retourne un utilisateur de test.
    
    Args:
        request: Requête FastAPI
        credentials: Informations d'authentification HTTP Bearer
        
    Returns:
        str: ID de l'utilisateur authentifié
        
    Raises:
        HTTPException: Si l'authentification échoue
    """
    # En mode DEBUG, retourner un utilisateur de test
    if settings.DEBUG:
        logger.debug("Mode DEBUG activé, utilisation de l'utilisateur de test 'debug-user'")
        return "debug-user"
    
    # Vérifier si les informations d'authentification sont présentes
    if not credentials:
        # Vérifier si le token est dans les en-têtes de la requête
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.replace("Bearer ", "")
        else:
            logger.warning("Tentative d'accès sans token d'authentification")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Non authentifié",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        token = credentials.credentials
    
    # Vérifier le token (implémentation simplifiée)
    # Dans une vraie application, vous utiliseriez JWT ou OAuth
    if token == "test-token":
        return "test-user"
    
    # Simuler une vérification de token
    try:
        # Ici, vous implémenteriez la vérification réelle du token
        # Par exemple, avec JWT: payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        # Et vous récupéreriez l'ID utilisateur: user_id = payload.get("sub")
        
        # Pour l'exemple, on extrait simplement l'ID utilisateur du token
        user_id = token.split("-")[0]  # Exemple simpliste
        return user_id
    except Exception as e:
        logger.error(f"Erreur lors de la vérification du token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def check_user_access(user_id: str, resource_id: str, resource_type: str = "session") -> bool:
    """
    Vérifie si un utilisateur a accès à une ressource spécifique.
    
    Args:
        user_id: ID de l'utilisateur
        resource_id: ID de la ressource
        resource_type: Type de ressource (session, scenario, etc.)
        
    Returns:
        bool: True si l'utilisateur a accès, False sinon
    """
    # En mode DEBUG, autoriser tous les accès
    if settings.DEBUG:
        logger.debug(f"Mode DEBUG activé, accès autorisé pour user_id={user_id} à {resource_type}={resource_id}")
        return True
    
    # Implémentation simplifiée
    # Dans une vraie application, vous vérifieriez les droits dans une base de données
    
    # Pour l'exemple, on autorise l'accès si l'utilisateur est propriétaire de la ressource
    # ou s'il a un rôle spécial
    
    # Simuler une vérification en base de données
    # Par exemple: resource = await db.get(ResourceModel, resource_id)
    # return resource.owner_id == user_id
    
    # Pour l'exemple, on autorise toujours l'accès
    logger.info(f"Vérification d'accès pour user_id={user_id} à {resource_type}={resource_id} (autorisé par défaut)")
    return True