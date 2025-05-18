# Sécurité du Backend Eloquence

Ce document décrit les mesures de sécurité implémentées dans le backend Eloquence.

## Mesures de Sécurité Implémentées

1. **Authentification par API Key**
   - Toutes les requêtes API doivent inclure une clé API valide dans l'en-tête `X-API-Key`
   - Protection contre les tentatives d'accès non autorisées

2. **Validation des Entrées**
   - Validation stricte de toutes les entrées utilisateur
   - Protection contre les injections et les attaques par manipulation de données

3. **Limitation du Taux de Requêtes (Rate Limiting)**
   - Limitation du nombre de requêtes par minute pour chaque adresse IP
   - Protection contre les attaques par déni de service (DoS)

4. **Protection CORS**
   - Restriction des origines autorisées à accéder à l'API
   - Protection contre les attaques CSRF

5. **Journalisation de Sécurité**
   - Journalisation détaillée de toutes les requêtes et actions
   - Détection des activités suspectes

6. **Gestion Sécurisée des Sessions**
   - Vérification de l'IP pour les opérations sensibles
   - Nettoyage automatique des sessions inactives

7. **En-têtes de Sécurité HTTP**
   - En-têtes de sécurité pour prévenir les attaques XSS, clickjacking, etc.
   - Strict-Transport-Security pour forcer HTTPS

8. **Blocage Temporaire après Tentatives Échouées**
   - Blocage temporaire des adresses IP après plusieurs tentatives d'authentification échouées
   - Protection contre les attaques par force brute

## Configuration

Les paramètres de sécurité sont configurables via des variables d'environnement :

```
API_KEY=votre_clé_api_secrète
JWT_SECRET=votre_secret_jwt
ALLOWED_ORIGINS=http://localhost:3000,https://eloquence.app
TRUSTED_IPS=127.0.0.1,::1
MAX_REQUESTS_PER_MINUTE=60
```

## Bonnes Pratiques

1. **Changez régulièrement les clés API et les secrets**
   - Rotation régulière des clés pour limiter l'impact d'une fuite

2. **Utilisez HTTPS en production**
   - Toutes les communications doivent être chiffrées

3. **Surveillez les journaux de sécurité**
   - Analyse régulière des journaux pour détecter les activités suspectes

4. **Mettez à jour les dépendances**
   - Maintien à jour des bibliothèques pour corriger les vulnérabilités connues