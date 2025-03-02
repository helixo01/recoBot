from tmdbv3api import TMDb, Movie, Search, Discover, Genre
from dotenv import load_dotenv
import os
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import colorlog
import sqlite3

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
    
    logger = colorlog.getLogger('MovieDB')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

logger = setup_logger()

class MovieDatabase:
    def __init__(self):
        logger.info("Initialisation de la base de données de films...")
        load_dotenv()
        self.tmdb = TMDb()
        self.tmdb.api_key = os.getenv('TMDB_API_KEY')
        self.tmdb.language = 'fr'  # Résultats en français
        self.movie = Movie()
        self.search = Search()
        self.discover = Discover()
        self.genres = self._get_genres()
        logger.info("Base de données initialisée avec succès")

    def _get_genres(self):
        """Récupère la liste des genres disponibles."""
        try:
            logger.debug("Récupération de la liste des genres...")
            genre = Genre()
            genres = {g.name.lower(): g.id for g in genre.movie_list()}
            logger.debug(f"Genres récupérés : {list(genres.keys())}")
            return genres
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des genres : {e}")
            return {}

    def calculate_movie_score(self, movie):
        """Calcule un score global pour un film basé sur plusieurs critères."""
        try:
            # Récupération des valeurs de base
            vote_average = float(getattr(movie, 'vote_average', 0))
            vote_count = int(getattr(movie, 'vote_count', 0))
            popularity = float(getattr(movie, 'popularity', 0))
            release_date = getattr(movie, 'release_date', '')
            
            # Score de base (note moyenne)
            base_score = vote_average
            
            # Bonus/Malus selon différents critères
            # 1. Nombre de votes (confiance dans la note)
            vote_multiplier = min(vote_count/500, 1)  # Normalisé à 500 votes
            
            # 2. Bonus pour les films récents
            year_bonus = 0
            if release_date:
                try:
                    year = int(release_date[:4])
                    current_year = datetime.now().year
                    if year == current_year:
                        year_bonus = 1
                    elif year >= current_year - 5:
                        year_bonus = 0.5
                except ValueError:
                    year_bonus = 0
            
            # 3. Popularité (normalisée)
            popularity_bonus = min(popularity/100, 1)
            
            # Calcul du score final
            final_score = (
                base_score * 0.5 +                # 50% note de base
                (base_score * vote_multiplier * 0.25) +  # 25% note pondérée par les votes
                (year_bonus * 1.5) +              # Bonus films récents
                (popularity_bonus * 1.0)          # Bonus popularité
            )
            
            return final_score
            
        except Exception as e:
            print(f"Erreur lors du calcul du score : {e}")
            return 0

    async def calculate_movie_score_async(self, movie):
        """Version asynchrone du calcul de score."""
        return self.calculate_movie_score(movie)

    async def search_movie(self, query, year=None, genre=None):
        """Recherche un film par titre avec filtres optionnels de manière asynchrone."""
        try:
            logger.info(f"Début de la recherche pour : '{query}' (année: {year}, genre: {genre})")
            
            # Récupération initiale des films (opération synchrone)
            if genre and genre.lower() in self.genres:
                logger.debug(f"Recherche avec genre : {genre}")
                movies = self.discover.discover_movies({
                    'with_genres': self.genres[genre.lower()],
                    'query': query,
                    'year': year if year else None,
                    'sort_by': 'vote_average.desc',
                    'vote_count.gte': 20
                })
            else:
                logger.debug("Recherche standard sans genre")
                movies = self.search.movies(query)

            # Préparation des films à traiter (limité à 10)
            movies_to_process = []
            for movie in movies:
                if len(movies_to_process) >= 10:
                    break
                if year and hasattr(movie, 'release_date') and movie.release_date:
                    movie_year = movie.release_date[:4]
                    if movie_year != str(year):
                        continue
                movies_to_process.append(movie)
            
            logger.info(f"Nombre de films à traiter : {len(movies_to_process)}")

            # Calcul parallèle des scores
            logger.debug("Début du calcul parallèle des scores")
            async with ThreadPoolExecutor(max_workers=min(len(movies_to_process), 5)) as executor:
                tasks = []
                for movie in movies_to_process:
                    task = asyncio.create_task(self.calculate_movie_score_async(movie))
                    tasks.append((movie, task))
                
                # Attendre tous les résultats
                movies_list = []
                for i, (movie, task) in enumerate(tasks, 1):
                    score = await task
                    logger.debug(f"Score calculé ({i}/{len(tasks)}) : {getattr(movie, 'title', 'Unknown')} = {score:.2f}")
                    movies_list.append((movie, score))

            # Trier et retourner les 5 meilleurs résultats
            sorted_movies = sorted(movies_list, key=lambda x: x[1], reverse=True)
            top_movies = [movie for movie, score in sorted_movies[:5]]
            
            logger.info(f"Recherche terminée. {len(top_movies)} films trouvés.")
            for i, movie in enumerate(top_movies, 1):
                logger.debug(f"Top {i}: {getattr(movie, 'title', 'Unknown')}")
            
            return top_movies

        except Exception as e:
            logger.error(f"Erreur lors de la recherche : {e}")
            return []

    def get_similar_movies(self, movie_title):
        """Trouve des films similaires à partir d'un titre."""
        try:
            search_results = self.search_movie(movie_title)
            if not search_results:
                return []
            
            reference_movie = search_results[0]
            similar_movies = self.movie.similar(reference_movie.id)
            
            # Filtrer et trier par qualité
            similar_list = []
            for movie in similar_movies:
                if len(similar_list) >= 5:
                    break
                
                vote_average = float(getattr(movie, 'vote_average', 0))
                vote_count = int(getattr(movie, 'vote_count', 0))
                
                if vote_count >= 100 and vote_average >= 6.0:
                    quality_score = vote_average * min(vote_count/500, 1)
                    similar_list.append((movie, quality_score))
            
            # Trier par score de qualité
            sorted_movies = sorted(similar_list, key=lambda x: x[1], reverse=True)
            return [movie for movie, _ in sorted_movies]
            
        except Exception as e:
            print(f"Erreur lors de la recherche de films similaires : {e}")
            return []

    def search_by_genre(self, genre, year=None):
        """Recherche des films par genre."""
        try:
            if genre.lower() in self.genres:
                params = {
                    'with_genres': self.genres[genre.lower()],
                    'sort_by': 'popularity.desc',
                    'vote_count.gte': 100  # Au moins 100 votes
                }
                if year:
                    params['year'] = year
                
                movies = self.discover.discover_movies(params)
                return list(movies)[:5]
            return []
        except Exception as e:
            print(f"Erreur lors de la recherche par genre : {e}")
            return []

    def get_popular_movies(self, genre=None):
        """Obtient les films populaires avec filtre de genre optionnel."""
        try:
            params = {
                'sort_by': 'popularity.desc',
                'vote_count.gte': 200,  # Augmenté pour plus de fiabilité
                'vote_average.gte': 6.5,  # Note minimale plus élevée
                'primary_release_year': datetime.now().year  # Films de l'année en cours
            }
            if genre and genre.lower() in self.genres:
                params['with_genres'] = self.genres[genre.lower()]
            
            movies = self.discover.discover_movies(params)
            return list(movies)[:5]
        except Exception as e:
            print(f"Erreur lors de la récupération des films populaires : {e}")
            return []

    def get_movie_details(self, movie_id):
        """Obtient les détails d'un film par son ID."""
        try:
            return self.movie.details(movie_id)
        except Exception as e:
            print(f"Erreur lors de la récupération des détails : {e}")
            return None

    def get_recommendations(self, movie_id):
        """Obtient des recommandations basées sur un film."""
        try:
            recommendations = self.movie.recommendations(movie_id)
            return list(recommendations)[:5]
        except Exception as e:
            print(f"Erreur lors de la récupération des recommandations : {e}")
            return []

    async def format_movie_info_async(self, movie):
        """Version asynchrone du formatage des informations d'un film."""
        try:
            # Si movie est une chaîne de caractères, on ne peut pas l'utiliser
            if isinstance(movie, str):
                return {
                    "titre": "Titre non disponible",
                    "année": "N/A",
                    "genre": "Information non disponible",
                    "description": "Information non disponible",
                    "note": "N/A",
                    "popularité": "N/A",
                    "score_ajusté": "N/A"
                }

            # Vérification que movie a un ID
            if not hasattr(movie, 'id'):
                return {
                    "titre": str(getattr(movie, 'title', 'Titre non disponible')),
                    "année": "N/A",
                    "genre": "Information non disponible",
                    "description": "Information non disponible",
                    "note": "N/A",
                    "popularité": "N/A",
                    "score_ajusté": "N/A"
                }

            # Utiliser ThreadPoolExecutor pour l'appel API
            loop = asyncio.get_event_loop()
            details = await loop.run_in_executor(None, self.get_movie_details, movie.id)
            
            # Si on ne peut pas obtenir les détails, on utilise les informations de base
            if not details:
                return {
                    "titre": str(getattr(movie, 'title', 'Titre non disponible')),
                    "année": str(getattr(movie, 'release_date', 'N/A'))[:4] if hasattr(movie, 'release_date') and movie.release_date else "N/A",
                    "genre": "Genre non spécifié",
                    "description": str(getattr(movie, 'overview', 'Pas de description disponible.')),
                    "note": f"{float(getattr(movie, 'vote_average', 0)):.1f}/10 ({int(getattr(movie, 'vote_count', 0))} votes)",
                    "popularité": f"{float(getattr(movie, 'popularity', 0)):.1f}",
                    "score_ajusté": "N/A"
                }
            
            # Si on a les détails, on les utilise
            genres = ", ".join([genre.name for genre in details.genres]) if details.genres else "Genre non spécifié"
            
            # Récupération sécurisée des valeurs
            vote_average = float(getattr(movie, 'vote_average', 0))
            vote_count = int(getattr(movie, 'vote_count', 0))
            popularity = float(getattr(movie, 'popularity', 0))
            
            # Score personnalisé qui prend en compte les votes et la popularité
            if vote_count > 0:
                adjusted_score = (vote_average * min(vote_count/100, 1) + (popularity/100)) / 2
            else:
                adjusted_score = popularity/100
            
            return {
                "titre": str(getattr(movie, 'title', 'Titre non disponible')),
                "année": str(getattr(movie, 'release_date', 'N/A'))[:4] if hasattr(movie, 'release_date') and movie.release_date else "N/A",
                "genre": genres,
                "description": str(getattr(movie, 'overview', 'Pas de description disponible.')),
                "note": f"{vote_average:.1f}/10 ({vote_count} votes)",
                "popularité": f"{popularity:.1f}",
                "score_ajusté": f"{adjusted_score:.1f}/10"
            }
        except Exception as e:
            logger.error(f"Erreur lors du formatage des informations : {e}")
            return {
                "titre": "Titre non disponible",
                "année": "N/A",
                "genre": "Information non disponible",
                "description": "Information non disponible",
                "note": "N/A",
                "popularité": "N/A",
                "score_ajusté": "N/A"
            }

    def format_movie_info(self, movie):
        """Formate les informations d'un film pour l'affichage."""
        try:
            # Si movie est une chaîne de caractères, on ne peut pas l'utiliser
            if isinstance(movie, str):
                return {
                    "titre": "Titre non disponible",
                    "année": "N/A",
                    "genre": "Information non disponible",
                    "description": "Information non disponible",
                    "note": "N/A",
                    "popularité": "N/A",
                    "score_ajusté": "N/A"
                }

            # Vérification que movie a un ID
            if not hasattr(movie, 'id'):
                return {
                    "titre": str(getattr(movie, 'title', 'Titre non disponible')),
                    "année": "N/A",
                    "genre": "Information non disponible",
                    "description": "Information non disponible",
                    "note": "N/A",
                    "popularité": "N/A",
                    "score_ajusté": "N/A"
                }

            details = self.get_movie_details(movie.id)
            
            # Si on ne peut pas obtenir les détails, on utilise les informations de base
            if not details:
                return {
                    "titre": str(getattr(movie, 'title', 'Titre non disponible')),
                    "année": str(getattr(movie, 'release_date', 'N/A'))[:4] if hasattr(movie, 'release_date') and movie.release_date else "N/A",
                    "genre": "Genre non spécifié",
                    "description": str(getattr(movie, 'overview', 'Pas de description disponible.')),
                    "note": f"{float(getattr(movie, 'vote_average', 0)):.1f}/10 ({int(getattr(movie, 'vote_count', 0))} votes)",
                    "popularité": f"{float(getattr(movie, 'popularity', 0)):.1f}",
                    "score_ajusté": "N/A"
                }
            
            # Si on a les détails, on les utilise
            genres = ", ".join([genre.name for genre in details.genres]) if details.genres else "Genre non spécifié"
            
            # Récupération sécurisée des valeurs
            vote_average = float(getattr(movie, 'vote_average', 0))
            vote_count = int(getattr(movie, 'vote_count', 0))
            popularity = float(getattr(movie, 'popularity', 0))
            
            # Score personnalisé qui prend en compte les votes et la popularité
            if vote_count > 0:
                adjusted_score = (vote_average * min(vote_count/100, 1) + (popularity/100)) / 2
            else:
                adjusted_score = popularity/100
            
            return {
                "titre": str(getattr(movie, 'title', 'Titre non disponible')),
                "année": str(getattr(movie, 'release_date', 'N/A'))[:4] if hasattr(movie, 'release_date') and movie.release_date else "N/A",
                "genre": genres,
                "description": str(getattr(movie, 'overview', 'Pas de description disponible.')),
                "note": f"{vote_average:.1f}/10 ({vote_count} votes)",
                "popularité": f"{popularity:.1f}",
                "score_ajusté": f"{adjusted_score:.1f}/10"
            }
        except Exception as e:
            print(f"Erreur lors du formatage des informations : {e}")
            # Format minimal en cas d'erreur
            return {
                "titre": "Titre non disponible",
                "année": "N/A",
                "genre": "Information non disponible",
                "description": "Information non disponible",
                "note": "N/A",
                "popularité": "N/A",
                "score_ajusté": "N/A"
            }

class LocalMovieDatabase:
    def __init__(self):
        logger.info("Initialisation de la base de données locale...")
        self.conn = sqlite3.connect('movies.db')
        self.conn.row_factory = sqlite3.Row  # Pour accéder aux colonnes par nom
        self.cursor = self.conn.cursor()
        self.genres = {
            'action': 28,
            'aventure': 12,
            'animation': 16,
            'comédie': 35,
            'crime': 80,
            'documentaire': 99,
            'drame': 18,
            'familial': 10751,
            'fantastique': 14,
            'histoire': 36,
            'horreur': 27,
            'musique': 10402,
            'mystère': 9648,
            'romance': 10749,
            'science-fiction': 878,
            'téléfilm': 10770,
            'thriller': 53,
            'guerre': 10752,
            'western': 37
        }
        
        # Créer la table si elle n'existe pas
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS movies (
            title TEXT,
            overview TEXT,
            release_year INTEGER,
            genres TEXT,
            vote_average REAL,
            vote_count INTEGER,
            popularity REAL
        )
        """)
        self.conn.commit()
        logger.info("Base de données locale initialisée")
    
    def import_movies_from_tmdb(self):
        """Importe des films depuis TMDB dans la base locale."""
        try:
            logger.info("Importation des films depuis TMDB...")
            tmdb = MovieDatabase()
            
            # Récupérer des films populaires pour chaque genre
            for genre in self.genres.keys():
                logger.info(f"Importation des films du genre : {genre}")
                movies = tmdb.search_by_genre(genre)
                
                for movie in movies:
                    # Extraire les informations du film
                    title = getattr(movie, 'title', '')
                    overview = getattr(movie, 'overview', '')
                    release_date = getattr(movie, 'release_date', '')
                    release_year = int(release_date[:4]) if release_date else None
                    vote_average = float(getattr(movie, 'vote_average', 0))
                    vote_count = int(getattr(movie, 'vote_count', 0))
                    popularity = float(getattr(movie, 'popularity', 0))
                    
                    # Récupérer les genres
                    movie_genres = []
                    if hasattr(movie, 'genre_ids'):
                        for genre_id in movie.genre_ids:
                            for name, id in self.genres.items():
                                if id == genre_id:
                                    movie_genres.append(name)
                    genres_str = ', '.join(movie_genres)
                    
                    # Insérer dans la base de données
                    self.cursor.execute("""
                    INSERT OR REPLACE INTO movies 
                    (title, overview, release_year, genres, vote_average, vote_count, popularity)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (title, overview, release_year, genres_str, vote_average, vote_count, popularity))
                
                self.conn.commit()
                logger.info(f"Films du genre {genre} importés avec succès")
            
            # Vérifier le nombre total de films importés
            self.cursor.execute("SELECT COUNT(*) FROM movies")
            count = self.cursor.fetchone()[0]
            logger.info(f"Importation terminée. Nombre total de films : {count}")
            
        except Exception as e:
            logger.error(f"Erreur lors de l'importation des films : {e}")
            self.conn.rollback()

    def search_movies(self, query=None, year=None, genre=None, limit=5):
        """Recherche des films dans la base locale."""
        try:
            conditions = []
            params = []
            
            if query:
                conditions.append("(title LIKE ? OR overview LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])
            
            if year:
                conditions.append("release_year = ?")
                params.append(year)
            
            if genre:
                conditions.append("genres LIKE ?")
                params.append(f"%{genre}%")
            
            where_clause = " AND ".join(conditions) if conditions else "1"
            
            sql = f"""
            SELECT * FROM movies 
            WHERE {where_clause}
            ORDER BY vote_average DESC, vote_count DESC
            LIMIT ?
            """
            params.append(limit)
            
            self.cursor.execute(sql, params)
            movies = self.cursor.fetchall()
            
            return [self.format_movie_info(movie) for movie in movies]
        except Exception as e:
            logger.error(f"Erreur lors de la recherche locale : {e}")
            return []

    def get_popular_movies(self, genre=None, limit=5):
        """Récupère les films populaires de la base locale."""
        try:
            if genre:
                sql = """
                SELECT * FROM movies 
                WHERE genres LIKE ? 
                ORDER BY popularity DESC, vote_average DESC 
                LIMIT ?
                """
                self.cursor.execute(sql, (f"%{genre}%", limit))
            else:
                sql = """
                SELECT * FROM movies 
                ORDER BY popularity DESC, vote_average DESC 
                LIMIT ?
                """
                self.cursor.execute(sql, (limit,))
            
            movies = self.cursor.fetchall()
            return [self.format_movie_info(movie) for movie in movies]
        except Exception as e:
            logger.error(f"Erreur lors de la récupération des films populaires : {e}")
            return []

    def get_similar_movies(self, movie_title, limit=5):
        """Trouve des films similaires basés sur le genre."""
        try:
            # D'abord, trouvons les genres du film de référence
            self.cursor.execute(
                "SELECT genres FROM movies WHERE title LIKE ? LIMIT 1",
                (f"%{movie_title}%",)
            )
            reference = self.cursor.fetchone()
            
            if not reference:
                return []
            
            reference_genres = reference['genres'].split(',')
            
            # Construire une condition pour trouver des films avec des genres similaires
            genre_conditions = " OR ".join(["genres LIKE ?" for _ in reference_genres])
            params = [f"%{genre}%" for genre in reference_genres]
            params.append(movie_title)  # Pour exclure le film lui-même
            
            sql = f"""
            SELECT *, 
                   (vote_average * (vote_count / 1000.0)) as score
            FROM movies 
            WHERE ({genre_conditions})
            AND title != ?
            ORDER BY score DESC
            LIMIT ?
            """
            params.append(limit)
            
            self.cursor.execute(sql, params)
            movies = self.cursor.fetchall()
            return [self.format_movie_info(movie) for movie in movies]
        except Exception as e:
            logger.error(f"Erreur lors de la recherche de films similaires : {e}")
            return []

    def search_by_genre(self, genre, year=None, limit=5):
        """Recherche des films par genre."""
        try:
            if year:
                sql = """
                SELECT * FROM movies 
                WHERE genres LIKE ? 
                AND release_year = ?
                ORDER BY vote_average DESC, popularity DESC
                LIMIT ?
                """
                self.cursor.execute(sql, (f"%{genre}%", year, limit))
            else:
                sql = """
                SELECT * FROM movies 
                WHERE genres LIKE ?
                ORDER BY vote_average DESC, popularity DESC
                LIMIT ?
                """
                self.cursor.execute(sql, (f"%{genre}%", limit))
            
            movies = self.cursor.fetchall()
            return [self.format_movie_info(movie) for movie in movies]
        except Exception as e:
            logger.error(f"Erreur lors de la recherche par genre : {e}")
            return []

    def format_movie_info(self, movie):
        """Formate les informations d'un film depuis la base de données."""
        try:
            return {
                "titre": movie['title'],
                "année": str(movie['release_year']),
                "genre": movie['genres'],
                "description": movie['overview'],
                "note": f"{float(movie['vote_average']):.1f}/10 ({int(movie['vote_count'])} votes)",
                "popularité": f"{float(movie['popularity']):.1f}",
                "score_ajusté": f"{(float(movie['vote_average']) * min(int(movie['vote_count'])/500, 1)):.1f}/10"
            }
        except Exception as e:
            logger.error(f"Erreur lors du formatage des informations : {e}")
            return {
                "titre": "Titre non disponible",
                "année": "N/A",
                "genre": "Information non disponible",
                "description": "Information non disponible",
                "note": "N/A",
                "popularité": "N/A",
                "score_ajusté": "N/A"
            }

    def __del__(self):
        """Ferme la connexion à la base de données."""
        self.conn.close() 