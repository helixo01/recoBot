from movie_db import LocalMovieDatabase
import os
import shutil
from datetime import datetime
import asyncio
import logging
import colorlog
import re
import sqlite3
from collections import Counter

# Configuration du logger
def setup_logger():
    """Configure le système de logging avec des couleurs."""
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s %(levelname)s: %(message)s',
        datefmt='%H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    ))
    
    logger = colorlog.getLogger('ChatBot')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

logger = setup_logger()

# Définition des mappings pour l'analyse
GENRE_MAPPING = {
    'action': ['action', 'combat', 'explosion', 'aventure'],
    'comédie': ['comédie', 'humour', 'drôle', 'rire'],
    'drame': ['drame', 'dramatique', 'émouvant'],
    'science-fiction': ['science-fiction', 'sci-fi', 'futur', 'espace'],
    'horreur': ['horreur', 'épouvante', 'peur', 'effrayant'],
    'thriller': ['thriller', 'suspense', 'mystère'],
    'romance': ['romance', 'amour', 'romantique'],
    'animation': ['animation', 'animé', 'dessin animé'],
    'documentaire': ['documentaire', 'docu'],
    'famille': ['famille', 'familial', 'enfant', 'jeunesse'],
    'guerre': ['guerre', 'militaire', 'bataille', 'soldat', 'armée', 'combat']
}

MOOD_MAPPING = {
    'intense': ['intense', 'palpitant', 'adrénaline', 'action'],
    'léger': ['léger', 'amusant', 'divertissant', 'feel-good'],
    'sérieux': ['sérieux', 'profond', 'réflexion', 'pensée'],
    'émotionnel': ['émotion', 'touchant', 'sensible', 'bouleversant'],
    'effrayant': ['peur', 'terrifiant', 'angoissant', 'stress'],
    'mystérieux': ['mystère', 'intrigue', 'énigme', 'suspense']
}

PERIOD_MAPPING = {
    'recent': ['récent', 'nouveau', 'nouveauté', 'derniers', '2023', '2024'],
    'classique': ['classique', 'culte', 'ancien', 'vintage'],
    'moderne': ['moderne', 'contemporain']
}

QUALITY_INDICATORS = {
    'populaire': ['populaire', 'connu', 'célèbre', 'succès', 'blockbuster'],
    'critique': ['acclamé', 'critique', 'récompense', 'oscar', 'césar'],
    'inconnu': ['méconnu', 'rare', 'confidentiel', 'découverte', 'indie']
}

# Ajout des mappings thématiques
THEME_MAPPING = {
    'voiture': ['voiture', 'course', 'automobile', 'racing', 'fast', 'furious', 'vitesse', 'pilote'],
    'super-héros': ['super-héros', 'superhéros', 'marvel', 'dc', 'comics', 'superman', 'batman', 'avengers'],
    'sport': ['sport', 'football', 'basketball', 'tennis', 'boxe', 'athlète', 'champion'],
    'guerre': ['guerre', 'militaire', 'bataille', 'soldat', 'armée', 'combat'],
    'fantasy': ['fantasy', 'magie', 'dragon', 'sorcier', 'magique', 'médiéval'],
    'western': ['western', 'cowboy', 'far west', 'ranch', 'shérif'],
    'espionnage': ['espion', 'agent secret', 'cia', 'mission', 'infiltration'],
    'catastrophe': ['catastrophe', 'désastre', 'apocalypse', 'tsunami', 'tremblement', 'météorite'],
    'musical': ['musical', 'musique', 'danse', 'chant', 'concert', 'comédie musicale'],
    'historique': ['historique', 'histoire', 'période', 'époque', 'biographie']
}

# Liste des mots à ignorer (stop words) en français
STOP_WORDS = {
    'le', 'la', 'les', 'un', 'une', 'des', 'ce', 'ces', 'sa', 'ses', 'son', 'mes', 'mon', 'ma',
    'et', 'ou', 'mais', 'donc', 'car', 'ni', 'or', 'que', 'qui', 'quoi', 'dont', 'où',
    'dans', 'sur', 'sous', 'par', 'pour', 'en', 'vers', 'avec', 'sans', 'de', 'à',
    'je', 'tu', 'il', 'elle', 'nous', 'vous', 'ils', 'elles', 'on',
    'être', 'avoir', 'faire', 'dire', 'aller', 'voir', 'vouloir', 'pouvoir', 'falloir',
    'plus', 'moins', 'très', 'bien', 'mal', 'tout', 'tous', 'toute', 'toutes',
    'autre', 'autres', 'même', 'aussi', 'alors', 'donc', 'après', 'avant',
    'oui', 'non', 'peut', 'être', 'comme', 'entre', 'chaque', 'sans', 'puis',
    'est', 'sont', 'sera', 'été', 'était', 'étaient', 'soit', 'suis', 'sommes',
    'film', 'films', 'histoire', 'année', 'années', 'fois', 'fait', 'faire',
    'cette', 'cet', 'ces', 'celui', 'celle', 'ceux', 'celles'
}

def initialize_db():
    """Initialise la base de données et crée les tables nécessaires."""
    logger.info("Initialisation de la base de données...")
    movie_db = LocalMovieDatabase()
    
    try:
        # Création de la table des mots significatifs si elle n'existe pas
        movie_db.cursor.execute("""
        CREATE TABLE IF NOT EXISTS significant_words (
            word TEXT PRIMARY KEY,
            category TEXT,  -- 'genre' ou 'theme'
            subcategory TEXT,  -- nom du genre ou du thème
            weight INTEGER DEFAULT 1
        )
        """)
        
        # Création de la table des stop words si elle n'existe pas
        movie_db.cursor.execute("""
        CREATE TABLE IF NOT EXISTS stop_words (
            word TEXT PRIMARY KEY
        )
        """)
        
        movie_db.cursor.connection.commit()
        
        # Vérifier si nous devons initialiser les mots significatifs
        movie_db.cursor.execute("SELECT COUNT(*) FROM significant_words")
        if movie_db.cursor.fetchone()[0] == 0:
            initialize_significant_words(movie_db)
        
        # Vérifier si nous devons initialiser les stop words
        movie_db.cursor.execute("SELECT COUNT(*) FROM stop_words")
        if movie_db.cursor.fetchone()[0] == 0:
            initialize_stop_words(movie_db)
        
        # Vérification de la table movies
        movie_db.cursor.execute("SELECT COUNT(*) FROM movies")
        count = movie_db.cursor.fetchone()[0]
        logger.info(f"Nombre de films dans la base : {count}")
        
        if count == 0:
            logger.info("Base de données vide, importation des films depuis TMDB...")
            movie_db.import_movies_from_tmdb()
    
    except sqlite3.Error as e:
        logger.error(f"Erreur lors de l'initialisation de la base de données : {e}")
    
    logger.info("Initialisation terminée")
    return movie_db

def initialize_significant_words(movie_db):
    """Initialise la table des mots significatifs avec les mappings par défaut."""
    try:
        # Préparation des données pour l'insertion
        words_to_insert = []
        
        # Ajout des mots de genre
        for genre, keywords in GENRE_MAPPING.items():
            for word in keywords:
                words_to_insert.append((word, 'genre', genre, 2))
        
        # Ajout des mots de thème
        for theme, keywords in THEME_MAPPING.items():
            for word in keywords:
                words_to_insert.append((word, 'theme', theme, 1))
        
        # Insertion des mots
        movie_db.cursor.executemany("""
        INSERT OR REPLACE INTO significant_words (word, category, subcategory, weight)
        VALUES (?, ?, ?, ?)
        """, words_to_insert)
        
        movie_db.cursor.connection.commit()
        logger.info("Mots significatifs initialisés avec succès")
        
    except sqlite3.Error as e:
        logger.error(f"Erreur lors de l'initialisation des mots significatifs : {e}")
        movie_db.cursor.connection.rollback()

def initialize_stop_words(movie_db):
    """Initialise la table des stop words."""
    try:
        # Conversion du set en liste de tuples pour l'insertion
        stop_words_data = [(word,) for word in STOP_WORDS]
        
        # Insertion des stop words
        movie_db.cursor.executemany("""
        INSERT OR REPLACE INTO stop_words (word)
        VALUES (?)
        """, stop_words_data)
        
        movie_db.cursor.connection.commit()
        logger.info("Stop words initialisés avec succès")
        
    except sqlite3.Error as e:
        logger.error(f"Erreur lors de l'initialisation des stop words : {e}")
        movie_db.cursor.connection.rollback()

def get_significant_words(movie_db, text):
    """Extrait les mots significatifs d'un texte en utilisant la base de données."""
    try:
        # Normalisation du texte
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Récupération des stop words depuis la base de données
        movie_db.cursor.execute("SELECT word FROM stop_words")
        stop_words = {row['word'] for row in movie_db.cursor.fetchall()}
        
        # Filtrage initial des mots
        filtered_words = [
            word for word in words
            if len(word) > 2
            and word not in stop_words
            and not word.isdigit()
        ]
        
        # Recherche des mots significatifs dans la base de données
        placeholders = ','.join('?' * len(filtered_words))
        if filtered_words:
            query = f"""
            SELECT word, category, subcategory, weight
            FROM significant_words
            WHERE word IN ({placeholders})
            """
            movie_db.cursor.execute(query, filtered_words)
            return movie_db.cursor.fetchall()
        return []
        
    except sqlite3.Error as e:
        logger.error(f"Erreur lors de la récupération des mots significatifs : {e}")
        return []

def analyze_request(movie_db, text):
    """Analyse une requête pour extraire les filtres pertinents en utilisant la base de données."""
    text = text.lower()
    filters = {
        'genres': [],
        'themes': [],
        'mood': None,
        'period': None,
        'year': None,
        'rating_min': None,
        'sort_by': 'weighted_score',
        'keywords': [],
        'prefer_unknown': False,
        'exclude_genres': []
    }
    
    # Extraction de l'année
    year = extract_year(text)
    if year:
        filters['year'] = year
    
    # Analyse des mots significatifs
    significant_words = get_significant_words(movie_db, text)
    for word_info in significant_words:
        if word_info['category'] == 'genre':
            if word_info['subcategory'] not in filters['genres']:
                filters['genres'].append(word_info['subcategory'])
        elif word_info['category'] == 'theme':
            if word_info['subcategory'] not in filters['themes']:
                filters['themes'].append(word_info['subcategory'])
        filters['keywords'].append(word_info['word'])
    
    # Détection des indicateurs de qualité (inchangé)
    if any(keyword in text for keyword in QUALITY_INDICATORS['populaire']):
        filters['sort_by'] = 'popularity'
    elif any(keyword in text for keyword in QUALITY_INDICATORS['critique']):
        filters['sort_by'] = 'rating'
        filters['rating_min'] = 7.0
    elif any(keyword in text for keyword in QUALITY_INDICATORS['inconnu']):
        filters['prefer_unknown'] = True
        filters['rating_min'] = 6.5
    
    return filters

def normalize_word(word):
    """Normalise un mot en le mettant en minuscules et en retirant la ponctuation."""
    return re.sub(r'[^\w\s]', '', word.lower())

def extract_significant_words(text):
    """Extrait les mots significatifs d'un texte."""
    if not text:
        return []
    
    # Normalisation et tokenization
    words = re.findall(r'\b\w+\b', text.lower())
    
    # Filtrage des mots
    significant_words = [
        word for word in words
        if len(word) > 2  # Ignorer les mots trop courts
        and word not in STOP_WORDS  # Ignorer les stop words
        and not word.isdigit()  # Ignorer les nombres
    ]
    
    return significant_words

def extract_and_store_keywords(movie_db):
    """Extrait et stocke les mots-clés pour tous les films."""
    logger.info("Extraction des mots-clés pour tous les films...")
    
    try:
        # Récupérer tous les films
        movie_db.cursor.execute("SELECT rowid, title, overview, genres FROM movies")
        movies = movie_db.cursor.fetchall()
        
        for movie in movies:
            # Extraire les mots-clés du titre
            title_words = Counter(extract_significant_words(movie['title']))
            
            # Extraire les mots-clés de la description
            overview_words = Counter(extract_significant_words(movie['overview']))
            
            # Extraire les mots-clés des genres
            genre_words = Counter(extract_significant_words(movie['genres']))
            
            # Préparer les données pour l'insertion
            keywords_data = []
            
            # Ajouter les mots du titre (avec un poids plus important)
            for word, count in title_words.items():
                keywords_data.append((movie['rowid'], word, count * 3, 'title'))
            
            # Ajouter les mots de la description
            for word, count in overview_words.items():
                keywords_data.append((movie['rowid'], word, count, 'overview'))
            
            # Ajouter les mots des genres (avec un poids plus important)
            for word, count in genre_words.items():
                keywords_data.append((movie['rowid'], word, count * 2, 'genre'))
            
            # Insérer les mots-clés
            movie_db.cursor.executemany("""
                INSERT OR REPLACE INTO movie_keywords (movie_id, word, count, source)
                VALUES (?, ?, ?, ?)
            """, keywords_data)
        
        movie_db.cursor.connection.commit()
        logger.info("Extraction des mots-clés terminée")
        
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction des mots-clés : {e}")
        movie_db.cursor.connection.rollback()

def extract_year(text):
    """Extrait l'année d'une requête."""
    year_patterns = [
        r'de (\d{4})',
        r'en (\d{4})',
        r'année (\d{4})',
        r'(\d{4})',
    ]
    current_year = datetime.now().year
    
    for pattern in year_patterns:
        match = re.search(pattern, text)
        if match:
            year = int(match.group(1))
            if 1900 <= year <= current_year:
                return year
    return None

async def search_movies_optimized(movie_db, filters):
    """Recherche optimisée utilisant les mots-clés extraits."""
    try:
        # Extraire les mots significatifs de la requête
        query_words = extract_significant_words(' '.join(filters['keywords']))
        logger.info(f"Mots-clés extraits : {query_words}")
        
        conditions = []
        params = []
        
        # Gestion des genres
        if filters['genres']:
            genre_conditions = []
            for genre in filters['genres']:
                genre_conditions.append("LOWER(genres) LIKE ?")
                params.append(f"%{genre.lower()}%")
            if genre_conditions:
                conditions.append(f"({' OR '.join(genre_conditions)})")
        
        # Gestion des thèmes
        if filters['themes']:
            theme_conditions = []
            for theme in filters['themes']:
                theme_words = THEME_MAPPING.get(theme, [])
                for word in theme_words:
                    theme_conditions.append("(LOWER(overview) LIKE ? OR LOWER(title) LIKE ?)")
                    params.extend([f"%{word.lower()}%", f"%{word.lower()}%"])
            if theme_conditions:
                conditions.append(f"({' OR '.join(theme_conditions)})")
        
        # Gestion de l'année
        if filters['year']:
            conditions.append("release_year = ?")
            params.append(filters['year'])
        elif filters['period'] == 'recent':
            conditions.append("release_year >= ?")
            params.append(datetime.now().year - 2)
        elif filters['period'] == 'classique':
            conditions.append("release_year <= ?")
            params.append(datetime.now().year - 20)
        
        # Gestion de la note minimum
        if filters['rating_min']:
            conditions.append("vote_average >= ?")
            params.append(filters['rating_min'])
        
        # Construction de la clause WHERE
        where_clause = " AND ".join(conditions) if conditions else "1=1"
        
        # Requête finale
        sql = f"""
        SELECT *,
               (vote_average * (CAST(vote_count AS FLOAT) / 1000.0) + popularity / 100.0) as weighted_score
        FROM movies
        WHERE {where_clause}
        ORDER BY 
            CASE 
                WHEN ? = 'popularity' THEN popularity
                WHEN ? = 'rating' THEN vote_average
                ELSE weighted_score
            END DESC
        LIMIT 5
        """
        
        # Exécution de la requête
        movie_db.cursor.execute(sql, params + [filters['sort_by'], filters['sort_by']])
        movies = movie_db.cursor.fetchall()
        logger.info(f"Nombre de films trouvés : {len(movies)}")
        
        if movies:
            return [format_movie_result(movie) for movie in movies]
        
        return []
        
    except Exception as e:
        logger.error(f"Erreur lors de la recherche : {e}")
        logger.error(f"Détails de l'erreur : {str(e)}")
        return []

def format_movie_result(movie):
    """Formate un résultat de film."""
    try:
        return {
            'titre': movie['title'],
            'année': movie['release_year'],
            'genre': movie['genres'],
            'note': movie['vote_average'],
            'vote_count': movie['vote_count'],
            'popularité': movie.get('popularity', 0),
            'description': movie['overview'],
            'weighted_score': movie.get('weighted_score', movie['vote_average'])
        }
    except Exception as e:
        logger.error(f"Erreur lors du formatage du film : {e}")
        logger.error(f"Données du film : {movie}")
        return None

async def generate_response(movies_info, filters):
    """Génère une réponse basée sur les filtres et les résultats."""
    if not movies_info:
        return "Désolé, je n'ai pas trouvé de films correspondant à vos critères."

    # Construction de l'introduction
    intro = "Voici les films que j'ai trouvés "
    if filters['genres']:
        intro += f"dans le genre {', '.join(filters['genres'])} "
    if filters['mood']:
        intro += f"avec une ambiance {filters['mood']} "
    if filters['period']:
        intro += f"de période {filters['period']} "
    intro += ":\n\n"

    # Formatage des résultats
    response = intro
    for movie in movies_info:
        response += f"🎬 {movie['titre']} ({movie['année']})\n"
        response += f"📝 Genre : {movie['genre']}\n"
        response += f"⭐ Note : {movie['note']}/10 ({movie['vote_count']} votes)\n"
        response += f"📊 Score ajusté : {movie['weighted_score']:.1f}/10\n"
        response += f"📈 Popularité : {movie['popularité']}\n"
        
        # Limiter la description à 200 caractères
        description = movie['description']
        if len(description) > 200:
            description = description[:197] + "..."
        response += f"📖 {description}\n"
        response += "─" * 50 + "\n"

    return response

async def chat_with_bot(movie_db, prompt):
    """Interaction avec le chatbot."""
    start_time = datetime.now()
    logger.info(f"Nouvelle requête reçue : {prompt}")
    
    # Analyse de la requête
    analysis_start = datetime.now()
    filters = analyze_request(movie_db, prompt)
    logger.info(f"Filtres extraits : {filters}")
    logger.info(f"Analyse effectuée en {(datetime.now() - analysis_start).total_seconds():.2f} secondes")
    
    # Recherche des films
    search_start = datetime.now()
    movies_info = await search_movies_optimized(movie_db, filters)
    logger.info(f"Recherche effectuée en {(datetime.now() - search_start).total_seconds():.2f} secondes")
    
    # Génération de la réponse
    response_start = datetime.now()
    response = await generate_response(movies_info, filters)
    logger.info(f"Réponse générée en {(datetime.now() - response_start).total_seconds():.2f} secondes")
    
    logger.info(f"Temps total de traitement : {(datetime.now() - start_time).total_seconds():.2f} secondes")
    return response

def cleanup_gpt4all():
    """Supprime les fichiers du modèle GPT4All qui ne sont plus utilisés."""
    try:
        # Chemin du cache GPT4All
        cache_path = os.path.expanduser("~/.cache/gpt4all")
        if os.path.exists(cache_path):
            logger.info("Suppression des fichiers GPT4All...")
            shutil.rmtree(cache_path)
            logger.info("Fichiers GPT4All supprimés avec succès")
        else:
            logger.info("Aucun fichier GPT4All trouvé")
    except Exception as e:
        logger.error(f"Erreur lors de la suppression des fichiers GPT4All : {e}")

async def list_all_movies(movie_db, page=1, per_page=10):
    """Liste tous les films de la base de données avec pagination."""
    try:
        # Récupérer le nombre total de films
        movie_db.cursor.execute("SELECT COUNT(*) FROM movies")
        total_movies = movie_db.cursor.fetchone()[0]
        total_pages = (total_movies + per_page - 1) // per_page
        
        # Vérifier que la page demandée est valide
        page = max(1, min(page, total_pages))
        offset = (page - 1) * per_page
        
        # Récupérer les films de la page demandée
        sql = """
        SELECT title, release_year, vote_average, vote_count
        FROM movies
        ORDER BY title
        LIMIT ? OFFSET ?
        """
        movie_db.cursor.execute(sql, (per_page, offset))
        movies = movie_db.cursor.fetchall()
        
        # Formater la réponse
        response = f"Liste des films (page {page}/{total_pages}):\n\n"
        for movie in movies:
            response += f"🎬 {movie['title']} ({movie['release_year']}) "
            response += f"- ⭐ {movie['vote_average']}/10 ({movie['vote_count']} votes)\n"
        
        response += f"\n--- Page {page}/{total_pages} ---"
        if total_pages > 1:
            response += "\nUtilisez 'list page X' pour voir d'autres pages"
        
        return response
        
    except Exception as e:
        logger.error(f"Erreur lors de la récupération de la liste des films : {e}")
        return "Désolé, une erreur est survenue lors de la récupération de la liste des films."

async def main():
    logger.info("Démarrage de RecoBot")
    print("╔════════════════════════════════════╗")
    print("║         Bienvenue sur RecoBot      ║")
    print("║  Votre conseiller cinéma personnel ║")
    print("╚════════════════════════════════════╝")
    print("\nInitialisation du chatbot...")
    
    # Nettoyage des fichiers inutilisés
    cleanup_gpt4all()
    
    movie_db = initialize_db()
    
    print("\nRecoBot est prêt ! Voici quelques exemples de questions :")
    print("- 'Je cherche un film d'action récent avec des explosions'")
    print("- 'Un film drôle et léger pour toute la famille'")
    print("- 'Un thriller intense avec du suspense'")
    print("- 'Un film acclamé par la critique mais pas trop connu'")
    print("\nCommandes spéciales :")
    print("- 'list' : Affiche la liste des films (10 par page)")
    print("- 'list page X' : Affiche la page X de la liste des films")
    print("- 'add word category subcategory' : Ajoute un nouveau mot significatif")
    print("- 'add stop word' : Ajoute un nouveau stop word")
    print("- 'quit' : Quitter le programme")
    
    while True:
        user_input = input("\nVous: ")
        user_input_lower = user_input.lower()
        
        if user_input_lower == 'quit':
            logger.info("Arrêt de RecoBot")
            break
        elif user_input_lower == 'list':
            response = await list_all_movies(movie_db)
            print("\nRecoBot:", response)
        elif user_input_lower.startswith('list page '):
            try:
                page = int(user_input_lower.split('page ')[1])
                response = await list_all_movies(movie_db, page=page)
                print("\nRecoBot:", response)
            except ValueError:
                print("\nRecoBot: Veuillez spécifier un numéro de page valide (ex: 'list page 2')")
        elif user_input_lower.startswith('add word '):
            try:
                _, _, word, category, subcategory = user_input_lower.split(maxsplit=4)
                movie_db.cursor.execute("""
                INSERT OR REPLACE INTO significant_words (word, category, subcategory, weight)
                VALUES (?, ?, ?, 1)
                """, (word, category, subcategory))
                movie_db.cursor.connection.commit()
                print(f"\nRecoBot: Mot '{word}' ajouté avec succès dans la catégorie '{category}/{subcategory}'")
            except ValueError:
                print("\nRecoBot: Format incorrect. Utilisez: 'add word [mot] [catégorie] [sous-catégorie]'")
        elif user_input_lower.startswith('add stop '):
            try:
                _, _, word = user_input_lower.split()
                movie_db.cursor.execute("INSERT OR REPLACE INTO stop_words (word) VALUES (?)", (word,))
                movie_db.cursor.connection.commit()
                print(f"\nRecoBot: Stop word '{word}' ajouté avec succès")
            except ValueError:
                print("\nRecoBot: Format incorrect. Utilisez: 'add stop [mot]'")
        else:
            response = await chat_with_bot(movie_db, user_input)
            print("\nRecoBot:", response)

if __name__ == "__main__":
    asyncio.run(main()) 