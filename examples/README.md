# Exemples de Scénarios Hybrides et Multi-Agents pour Eloquence

Ce répertoire contient des exemples pour illustrer l'utilisation des fonctionnalités de scénarios hybrides et multi-agents dans le système de coaching vocal Eloquence.

## Scénarios Hybrides

Les scénarios hybrides permettent de créer des parcours d'apprentissage structurés avec des étapes prédéfinies, tout en laissant une certaine flexibilité au LLM pour adapter les réponses en fonction du contexte.

### Structure d'un Scénario Hybride

Un scénario hybride est défini par un fichier JSON avec la structure suivante :

```json
{
  "id": "identifiant_unique",
  "name": "Nom du scénario",
  "description": "Description du scénario",
  "initial_prompt": "Message initial pour démarrer le scénario",
  "variables": {
    "variable1": {
      "name": "Nom de la variable",
      "description": "Description de la variable",
      "type": "text|number|boolean|choice",
      "default_value": "Valeur par défaut",
      "required": true|false
    },
    ...
  },
  "steps": {
    "etape1": {
      "id": "etape1",
      "name": "Nom de l'étape",
      "description": "Description de l'étape",
      "prompt_template": "Template de prompt avec {variables}",
      "expected_variables": ["variable1", "variable2"],
      "next_steps": ["etape2", "etape3"],
      "is_final": false
    },
    ...
  },
  "first_step": "etape1"
}
```

### Exemple de Scénario

Le fichier `scenario_entretien_embauche.json` est un exemple de scénario hybride pour simuler un entretien d'embauche. Il comprend plusieurs étapes (présentation, parcours professionnel, compétences techniques, etc.) et des variables pour stocker les informations du candidat.

## Agents IA

Les agents IA sont des participants virtuels dans une session de coaching. Chaque agent a un profil qui définit son rôle, sa personnalité et son comportement.

### Structure d'un Profil d'Agent

Un profil d'agent est défini par un fichier JSON avec la structure suivante :

```json
{
  "id": "identifiant_unique",
  "name": "Nom de l'agent",
  "description": "Description de l'agent",
  "system_prompt": "Prompt système pour définir le comportement de l'agent",
  "voice_id": "ID de la voix à utiliser pour cet agent"
}
```

### Exemple de Profil d'Agent

Le fichier `agent_recruteur.json` est un exemple de profil d'agent pour un recruteur professionnel. Il définit le comportement du recruteur dans le scénario d'entretien d'embauche.

## Sessions Multi-Agents

Une session multi-agents permet d'avoir plusieurs participants dans une même session de coaching, chacun avec son propre rôle et comportement.

### Création d'une Session Multi-Agents

Le script `create_scenario_session.py` montre comment créer une session multi-agents avec un scénario hybride et des agents IA. Il comprend les étapes suivantes :

1. Création d'un template de scénario à partir d'un fichier JSON
2. Création d'un profil d'agent à partir d'un fichier JSON
3. Création d'une session avec ce scénario et cet agent
4. Création des participants (utilisateur et agent) pour cette session

### Test d'une Session Multi-Agents

Le script `test_multi_agent_session.py` montre comment tester une session multi-agents en simulant une interaction entre un utilisateur et un agent IA. Il comprend les étapes suivantes :

1. Récupération d'une session existante
2. Affichage des informations de la session (scénario, étape actuelle, variables, participants)
3. Simulation d'une réponse utilisateur
4. Traitement de cette réponse par l'orchestrateur
5. Affichage de l'état mis à jour de la session

## Utilisation

Pour utiliser ces exemples, suivez ces étapes :

1. Assurez-vous que le backend Eloquence est installé et configuré
2. Créez un template de scénario et un profil d'agent en utilisant les exemples fournis
3. Exécutez le script `create_scenario_session.py` pour créer une session
4. Utilisez l'URL WebSocket fournie pour interagir avec la session

```bash
# Créer une session
python examples/create_scenario_session.py

# Tester une session
python examples/test_multi_agent_session.py
```

## Extension

Vous pouvez étendre ces exemples en créant vos propres scénarios et profils d'agents. Utilisez les fichiers JSON fournis comme modèles et adaptez-les à vos besoins.

Pour créer un scénario plus complexe, vous pouvez ajouter plus d'étapes, de variables et de conditions. Pour créer un agent plus sophistiqué, vous pouvez enrichir son prompt système et définir des comportements spécifiques pour différentes situations.