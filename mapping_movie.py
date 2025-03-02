from tmdbv3api import TMDb, Movie, Discover
from dotenv import load_dotenv
import sqlite3
import os
import time
from datetime import datetime
import logging
import colorlog

# Configuration du logger
def setup_logger():
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
    
    logger = colorlog.getLogger('MovieMapper')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

logger = setup_logger()

def init_db():
    """Initialise la base de données SQLite."""
    conn = sqlite3.connect('movies.db')
    cursor = conn.cursor()
    
    # Création de la table films
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS movies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tmdb_id INTEGER UNIQUE,
        title TEXT NOT NULL,
        release_year INTEGER,
        vote_average FLOAT,
        vote_count INTEGER,
        popularity FLOAT,
        overview TEXT,
        genres TEXT,
        last_updated DATETIME
    )
    ''')
    
    # Création des index
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_vote_average ON movies(vote_average)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_release_year ON movies(release_year)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_popularity ON movies(popularity)')
    
    conn.commit()
    return conn

def init_tmdb():
    """Initialise l'API TMDB."""
    load_dotenv()
    tmdb = TMDb()
    tmdb.api_key = os.getenv('TMDB_API_KEY')
    tmdb.language = 'fr'
    return tmdb

def fetch_movies():
    """Récupère les films depuis TMDB avec gestion des limites de taux."""
    tmdb = init_tmdb()
    discover = Discover()
    movie = Movie()
    conn = init_db()
    cursor = conn.cursor()
    
    current_page = 1
    requests_count = 0
    start_time = time.time()
    total_movies = 0
    
    try:
        while True:
            # Vérification des limites de taux
            if requests_count >= 35:  # Marge de sécurité par rapport à la limite de 40
                time_elapsed = time.time() - start_time
                if time_elapsed < 10:
                    sleep_time = 10 - time_elapsed
                    logger.info(f"Pause de {sleep_time:.2f} secondes pour respecter les limites de l'API")
                    time.sleep(sleep_time)
                requests_count = 0
                start_time = time.time()
            
            logger.info(f"Récupération de la page {current_page}")
            
            # Recherche des films avec les critères spécifiés
            movies = discover.discover_movies({
                'sort_by': 'vote_average.desc',
                'vote_average.gte': 8.2,  # Note minimale de 8
                'primary_release_date.gte': '2000-01-01',  # Films après 2015
                'page': current_page,
                'vote_count.gte': 100  # Pour éviter les films avec trop peu de votes
            })
            
            requests_count += 1
            
            if not movies:
                break
                
            for movie_data in movies:
                try:
                    # Récupération des détails du film
                    details = movie.details(movie_data.id)
                    requests_count += 1
                    
                    # Formatage des genres
                    genres = ','.join([genre.name for genre in details.genres]) if hasattr(details, 'genres') else ''
                    
                    # Insertion ou mise à jour dans la base
                    cursor.execute('''
                    INSERT OR REPLACE INTO movies 
                    (tmdb_id, title, release_year, vote_average, vote_count, popularity, overview, genres, last_updated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        details.id,
                        details.title,
                        int(details.release_date[:4]) if hasattr(details, 'release_date') else None,
                        details.vote_average,
                        details.vote_count,
                        details.popularity,
                        details.overview,
                        genres,
                        datetime.now().isoformat()
                    ))
                    
                    total_movies += 1
                    if total_movies % 10 == 0:
                        logger.info(f"Films traités : {total_movies}")
                        conn.commit()
                        
                except Exception as e:
                    logger.error(f"Erreur lors du traitement du film {movie_data.id}: {e}")
                    continue
            
            current_page += 1
            
    except Exception as e:
        logger.error(f"Erreur lors de la récupération des films : {e}")
    finally:
        conn.commit()
        logger.info(f"Nombre total de films ajoutés/mis à jour : {total_movies}")
        conn.close()

if __name__ == "__main__":
    logger.info("Début du mapping des films")
    fetch_movies()
    logger.info("Mapping terminé") 