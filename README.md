# RecoBot - Assistant de Recommandation de Films

RecoBot est un assistant conversationnel intelligent spécialisé dans la recommandation de films. Il utilise une base de données locale et des algorithmes d'analyse sémantique pour fournir des recommandations personnalisées en français.

## Fonctionnalités

- 🎯 Recherche intelligente basée sur :
  - Genres de films
  - Thèmes spécifiques
  - Périodes (films récents, classiques, etc.)
  - Qualité (films populaires, acclamés par la critique, pépites méconnues)
  - Ambiance (films légers, intenses, etc.)
- 📊 Système de notation intelligent combinant :
  - Notes moyennes
  - Nombre de votes
  - Popularité
- 🔍 Analyse sémantique avancée des requêtes
- 💾 Base de données locale pour des recherches rapides
- 🎨 Interface en ligne de commande intuitive

## Prérequis

- Python 3.8 ou supérieur
- pip (gestionnaire de paquets Python)
- SQLite3

## Installation

1. Clonez ce dépôt :
```bash
git clone [votre-repo]
cd recoBot
```

2. Installez les dépendances :
```bash
pip install -r requirements.txt
```

## Utilisation

1. Lancez le chatbot :
```bash
python chatbot.py
```

2. Types de requêtes possibles :
   - "Je cherche un film d'action récent avec des explosions"
   - "Un film drôle et léger pour toute la famille"
   - "Un thriller intense avec du suspense"
   - "Un film acclamé par la critique mais pas trop connu"

3. Commandes spéciales :
   - `list` : Affiche la liste des films (10 par page)
   - `list page X` : Affiche la page X de la liste des films
   - `add word [mot] [catégorie] [sous-catégorie]` : Ajoute un nouveau mot significatif
   - `add stop [mot]` : Ajoute un nouveau mot à ignorer
   - `quit` : Quitter le programme

## Fonctionnement

RecoBot utilise plusieurs composants pour fournir des recommandations pertinentes :

1. **Base de données locale** : Stockage efficace des informations sur les films
2. **Analyse sémantique** : 
   - Extraction de mots-clés significatifs
   - Filtrage des mots vides (stop words)
   - Pondération des termes selon leur source (titre, description, genres)
3. **Système de scoring** :
   - Note moyenne pondérée par le nombre de votes
   - Prise en compte de la popularité
   - Bonus pour les correspondances exactes de genres et thèmes

## Personnalisation

Le système est hautement personnalisable :
- Ajout de nouveaux mots significatifs
- Définition de nouveaux mots à ignorer
- Extension des catégories et sous-catégories
- Modification des poids de scoring

## Contribution

Les contributions sont les bienvenues ! N'hésitez pas à :
1. Fork le projet
2. Créer une branche pour votre fonctionnalité
3. Commiter vos changements
4. Pousser vers la branche
5. Ouvrir une Pull Request

## Licence

Ce projet est sous licence MIT. Voir le fichier `LICENSE` pour plus de détails. 