import sqlite3
from tmdbv3api import TMDb, Movie, Person, Collection, Company
from datetime import datetime
import logging
import os
from dotenv import load_dotenv
import time
import json
import requests
from requests.exceptions import ConnectionError, Timeout, RequestException
import backoff  # Ajoutez cette dépendance avec: pip install backoff

# Configuration du logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration des paramètres de retry
MAX_RETRIES = 5
INITIAL_WAIT = 1  # secondes
MAX_WAIT = 30  # secondes

@backoff.on_exception(
    backoff.expo,
    (ConnectionError, Timeout, RequestException),
    max_tries=MAX_RETRIES,
    max_time=300  # 5 minutes maximum de tentatives
)
def make_api_request(func, *args, **kwargs):
    """Wrapper pour les appels API avec retry."""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        logger.error(f"Erreur lors de l'appel API: {str(e)}")
        raise

def initialize_db():
    """Initialise ou met à jour la structure de la base de données."""
    for attempt in range(MAX_RETRIES):
        try:
            conn = sqlite3.connect('movies.db', timeout=60)
            cursor = conn.cursor()
            
            # Création de la table movies avec les nouveaux champs
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS movies (
                id INTEGER PRIMARY KEY,
                tmdb_id INTEGER UNIQUE,
                title TEXT,
                release_year INTEGER,
                vote_average REAL,
                vote_count INTEGER,
                popularity REAL,
                overview TEXT,
                runtime INTEGER,
                status TEXT,
                genres TEXT,
                cast TEXT,
                crew TEXT,
                keywords TEXT,
                collection_id INTEGER,
                collection_name TEXT,
                production_companies TEXT,
                production_countries TEXT,
                last_updated TIMESTAMP,
                is_complete BOOLEAN DEFAULT 0
            )
            ''')
            
            conn.commit()
            return conn, cursor
        except sqlite3.OperationalError as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait_time = min(INITIAL_WAIT * (2 ** attempt), MAX_WAIT)
            logger.warning(f"Erreur de connexion à la base de données, nouvelle tentative dans {wait_time} secondes...")
            time.sleep(wait_time)

def initialize_tmdb():
    """Initialise l'API TMDB avec retry."""
    for attempt in range(MAX_RETRIES):
        try:
            load_dotenv()
            tmdb = TMDb()
            tmdb.api_key = os.getenv('TMDB_API_KEY')
            tmdb.language = 'fr'
            return tmdb, Movie()
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                raise
            wait_time = min(INITIAL_WAIT * (2 ** attempt), MAX_WAIT)
            logger.warning(f"Erreur d'initialisation TMDB, nouvelle tentative dans {wait_time} secondes...")
            time.sleep(wait_time)

def get_movie_complete_info(movie_api, movie_id):
    """Récupère toutes les informations détaillées d'un film avec retry."""
    try:
        # Récupération des détails avec retry
        movie_details = make_api_request(movie_api.details, movie_id)
        credits = make_api_request(movie_api.credits, movie_id)
        keywords = make_api_request(movie_api.keywords, movie_id)
        
        # Formatage des données
        movie_info = {
            'tmdb_id': movie_id,
            'title': movie_details.title,
            'release_year': int(movie_details.release_date[:4]) if movie_details.release_date else None,
            'vote_average': movie_details.vote_average,
            'vote_count': movie_details.vote_count,
            'popularity': movie_details.popularity,
            'overview': movie_details.overview,
            'runtime': movie_details.runtime,
            'status': movie_details.status,
            'genres': json.dumps([genre.name for genre in movie_details.genres]),
            'cast': json.dumps([{
                'id': cast.id,
                'name': cast.name,
                'character': cast.character,
                'order': cast.order
            } for cast in credits.cast[:10]]),  # Top 10 acteurs
            'crew': json.dumps([{
                'id': crew.id,
                'name': crew.name,
                'job': crew.job,
                'department': crew.department
            } for crew in credits.crew if crew.job in ['Director', 'Writer', 'Producer']]),
            'keywords': json.dumps([keyword.name for keyword in keywords.keywords]),
            'collection_id': movie_details.belongs_to_collection.id if movie_details.belongs_to_collection else None,
            'collection_name': movie_details.belongs_to_collection.name if movie_details.belongs_to_collection else None,
            'production_companies': json.dumps([{
                'id': company.id,
                'name': company.name
            } for company in movie_details.production_companies]),
            'production_countries': json.dumps([country.name for country in movie_details.production_countries]),
            'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'is_complete': 1
        }
        
        return movie_info
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des informations pour le film {movie_id}: {str(e)}")
        return None

def update_movie_if_needed(cursor, movie_info):
    """Met à jour un film si nécessaire avec retry."""
    for attempt in range(MAX_RETRIES):
        try:
            # Vérifier si le film existe et s'il est complet
            cursor.execute('''
            SELECT tmdb_id, last_updated, is_complete 
            FROM movies 
            WHERE tmdb_id = ?
            ''', (movie_info['tmdb_id'],))
            
            existing_movie = cursor.fetchone()
            
            if not existing_movie:
                # Nouveau film
                placeholders = ', '.join(['?' for _ in movie_info])
                columns = ', '.join(movie_info.keys())
                cursor.execute(f'''
                INSERT INTO movies ({columns})
                VALUES ({placeholders})
                ''', list(movie_info.values()))
                logger.info(f"Nouveau film ajouté: {movie_info['title']}")
                return True
                
            elif existing_movie[2] == 0:  # Film incomplet
                # Mise à jour complète
                set_clause = ', '.join([f'{k} = ?' for k in movie_info.keys()])
                cursor.execute(f'''
                UPDATE movies 
                SET {set_clause}
                WHERE tmdb_id = ?
                ''', list(movie_info.values()) + [movie_info['tmdb_id']])
                logger.info(f"Film incomplet mis à jour: {movie_info['title']}")
                return True
                
            else:
                # Vérifier si une mise à jour est nécessaire (plus de 7 jours)
                last_updated = datetime.strptime(existing_movie[1], '%Y-%m-%d %H:%M:%S')
                days_since_update = (datetime.now() - last_updated).days
                
                if days_since_update >= 7:
                    set_clause = ', '.join([f'{k} = ?' for k in movie_info.keys()])
                    cursor.execute(f'''
                    UPDATE movies 
                    SET {set_clause}
                    WHERE tmdb_id = ?
                    ''', list(movie_info.values()) + [movie_info['tmdb_id']])
                    logger.info(f"Film mis à jour après {days_since_update} jours: {movie_info['title']}")
                    return True
                    
            return False
            
        except sqlite3.OperationalError as e:
            if attempt == MAX_RETRIES - 1:
                logger.error(f"Erreur lors de la mise à jour du film {movie_info['title']}: {str(e)}")
                return False
            wait_time = min(INITIAL_WAIT * (2 ** attempt), MAX_WAIT)
            logger.warning(f"Erreur de base de données, nouvelle tentative dans {wait_time} secondes...")
            time.sleep(wait_time)

def update_database():
    """Met à jour la base de données avec gestion des erreurs de connexion."""
    conn = None
    cursor = None
    
    try:
        conn, cursor = initialize_db()
        tmdb, movie_api = initialize_tmdb()
        
        # Récupérer tous les films de la base
        cursor.execute('SELECT tmdb_id FROM movies')
        existing_movies = cursor.fetchall()
        
        updates_count = 0
        errors_count = 0
        
        for movie_id in existing_movies:
            try:
                # Respecter les limites de l'API (40 requêtes/10 secondes)
                if updates_count > 0 and updates_count % 35 == 0:
                    logger.info("Pause pour respecter les limites de l'API...")
                    time.sleep(10)
                
                movie_info = get_movie_complete_info(movie_api, movie_id[0])
                if movie_info:
                    if update_movie_if_needed(cursor, movie_info):
                        updates_count += 1
                    conn.commit()
                
            except Exception as e:
                errors_count += 1
                logger.error(f"Erreur lors du traitement du film {movie_id[0]}: {str(e)}")
                if errors_count >= 5:  # Arrêt après 5 erreurs consécutives
                    logger.error("Trop d'erreurs consécutives, arrêt du processus")
                    break
                continue
        
        logger.info(f"Mise à jour terminée. {updates_count} films mis à jour, {errors_count} erreurs rencontrées.")
        
    except Exception as e:
        logger.error(f"Erreur lors de la mise à jour de la base de données: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    update_database() 