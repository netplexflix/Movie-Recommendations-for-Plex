import os
import plexapi.server
import yaml
from datetime import datetime
import sys
import requests
from typing import Dict, List, Set, Optional, Tuple
from collections import Counter
import time
import webbrowser
import random
import json
from urllib.parse import quote
import re

__version__ = "2.0"
REPO_URL = "https://github.com/netplexflix/Movie-Recommendations-for-Plex"
API_VERSION_URL = f"https://api.github.com/repos/netplexflix/Movie-Recommendations-for-Plex/releases/latest"

# ANSI Color Codes
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

def check_version():
    """Check if there's a newer version available on GitHub."""
    try:
        response = requests.get(API_VERSION_URL)
        if response.status_code == 200:
            latest_release = response.json()
            latest_version = latest_release['tag_name'].lstrip('v')
            if latest_version > __version__:
                print(f"{YELLOW}A new version is available: v{latest_version}")
                print(f"You are currently running: v{__version__}")
                print(f"Please visit {REPO_URL}/releases to download the latest version.{RESET}")
            else:
                print(f"{GREEN}You are running the latest version (v{__version__}){RESET}")
        else:
            print(f"{YELLOW}Unable to check for updates. Status code: {response.status_code}{RESET}")
    except Exception as e:
        print(f"{YELLOW}Unable to check for updates: {str(e)}{RESET}")


class PlexMovieRecommender:
    def __init__(self, config_path: str):
        print("Initializing recommendation system...")
        self.config = self._load_config(config_path)
        
        print("Connecting to Plex server...")
        self.plex = self._init_plex()
        print(f"Connected to Plex successfully!\n")
        
        # Load general settings
        general_config = self.config.get('general', {})
        self.confirm_operations = general_config.get('confirm_operations', False)
        self.limit_plex_results = general_config.get('limit_plex_results', 10)
        self.limit_trakt_results = general_config.get('limit_trakt_results', 10)
        self.show_summary = general_config.get('show_summary', False)
        self.plex_only = general_config.get('plex_only', False)
        
        exclude_genre_str = general_config.get('exclude_genre', '')
        self.exclude_genres = [g.strip().lower() for g in exclude_genre_str.split(',') if g.strip()] if exclude_genre_str else []
        
        # Initialize Trakt with OAuth
        self.trakt_headers = {
            'Content-Type': 'application/json',
            'trakt-api-version': '2',
            'trakt-api-key': self.config['trakt']['client_id']
        }
        if 'access_token' in self.config.get('trakt', {}):
            self.trakt_headers['Authorization'] = f"Bearer {self.config['trakt']['access_token']}"
        else:
            self._authenticate_trakt()

        # TMDB config
        tmdb_config = self.config.get('TMDB', {})
        self.use_tmdb_keywords = tmdb_config.get('use_TMDB_keywords', False)
        self.tmdb_api_key = tmdb_config.get('api_key', None)

        # Prepare a cache directory
        self.cache_dir = os.path.join(os.path.dirname(__file__), "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_path = os.path.join(self.cache_dir, "watched_data_cache.json")

        # Load existing cache if available
        (self.cached_watched_count,
         self.watched_data_counters,
         self.plex_tmdb_cache,
         self.tmdb_keywords_cache,
         self.cached_library_movie_count,
         self.cached_unwatched_count,
         self.cached_unwatched_movies) = self._load_cache()

        # If we didn't have caches for TMDB IDs or keywords, create empty
        if self.plex_tmdb_cache is None:
            self.plex_tmdb_cache = {}
        if self.tmdb_keywords_cache is None:
            self.tmdb_keywords_cache = {}

        # If the user has changed the watched count, re-scan
        current_watched_count = self._get_watched_count()
        if current_watched_count != self.cached_watched_count:
            print("Watched count changed or no cache found; gathering watched data now. This may take a while...\n")
            self.watched_data = self._get_watched_movies_data()
            self.watched_data_counters = self.watched_data
            self.cached_watched_count = current_watched_count
        else:
            print("Watched count unchanged. Using cached watched data for faster performance.\n")
            self.watched_data = self.watched_data_counters

        # Get all movies in Plex library
        print("Fetching library metadata (for existing movie checks)...")
        self.library_movies = self._get_library_movies_set()

    # ------------------------------------------------------------------------
    # CONFIG / PLEX SETUP
    # ------------------------------------------------------------------------
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file."""
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
                print(f"Successfully loaded configuration from {config_path}")
                return config
        except Exception as e:
            print(f"{RED}Error loading config from {config_path}: {e}{RESET}")
            raise

    def _init_plex(self) -> plexapi.server.PlexServer:
        """Initialize Plex server connection."""
        import plexapi.server
        try:
            return plexapi.server.PlexServer(
                self.config['plex']['url'],
                self.config['plex']['token']
            )
        except Exception as e:
            print(f"{RED}Error connecting to Plex server: {e}{RESET}")
            raise

    def _authenticate_trakt(self):
        """Handle Trakt OAuth authentication."""
        try:
            response = requests.post(
                'https://api.trakt.tv/oauth/device/code',
                headers=self.trakt_headers,
                json={'client_id': self.config['trakt']['client_id']}
            )
            
            if response.status_code == 200:
                data = response.json()
                device_code = data['device_code']
                user_code = data['user_code']
                verification_url = data['verification_url']
                
                print(f"\n{GREEN}Please visit {verification_url} and enter code: {CYAN}{user_code}{RESET}")
                print("Waiting for authentication...")
                webbrowser.open(verification_url)
                
                poll_interval = data['interval']
                expires_in = data['expires_in']
                start_time = time.time()
                
                while time.time() - start_time < expires_in:
                    time.sleep(poll_interval)
                    token_response = requests.post(
                        'https://api.trakt.tv/oauth/device/token',
                        headers=self.trakt_headers,
                        json={
                            'code': device_code,
                            'client_id': self.config['trakt']['client_id'],
                            'client_secret': self.config['trakt']['client_secret']
                        }
                    )
                    
                    if token_response.status_code == 200:
                        token_data = token_response.json()
                        self.config['trakt']['access_token'] = token_data['access_token']
                        self.trakt_headers['Authorization'] = f"Bearer {token_data['access_token']}"
                        
                        with open(os.path.join(os.path.dirname(__file__), 'config.yml'), 'w') as f:
                            yaml.dump(self.config, f)
                            
                        print(f"{GREEN}Successfully authenticated with Trakt!{RESET}")
                        return
                    elif token_response.status_code != 400:
                        print(f"{RED}Error getting token: {token_response.status_code}{RESET}")
                        return
                print(f"{RED}Authentication timed out{RESET}")
            else:
                print(f"{RED}Error getting device code: {response.status_code}{RESET}")
        except Exception as e:
            print(f"{RED}Error during Trakt authentication: {e}{RESET}")


    # ------------------------------------------------------------------------
    # CACHING LOGIC
    # ------------------------------------------------------------------------
    def _load_cache(self):
        if not os.path.exists(self.cache_path):
            return None, None, None, None, None, None, []
        with open(self.cache_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return (
            data.get('watched_count'),
            data.get('watched_data_counters'),
            data.get('plex_tmdb_cache'),
            data.get('tmdb_keywords_cache'),
            data.get('library_movie_count'),
            data.get('unwatched_count'),
            data.get('unwatched_movie_details', [])
        )
    
    def _save_cache(self):
        data = {
            'watched_count': self.cached_watched_count,
            'watched_data_counters': self.watched_data_counters,
            'plex_tmdb_cache': self.plex_tmdb_cache,
            'tmdb_keywords_cache': self.tmdb_keywords_cache,
            'library_movie_count': self.cached_library_movie_count,
            'unwatched_count': self.cached_unwatched_count,
            'unwatched_movie_details': self.cached_unwatched_movies,
        }
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(data, f)

    def _get_watched_count(self) -> int:
        """Return how many watched movies exist in Plex right now."""
        try:
            movies_section = self.plex.library.section('Movies')
            watched_movies = movies_section.search(unwatched=False)
            return len(watched_movies)
        except:
            return 0

    # ------------------------------------------------------------------------
    # PATH HANDLING
    # ------------------------------------------------------------------------
    def _map_path(self, path: str) -> str:
        """Map paths between different systems using the path_mappings config."""
        try:
            if not self.config.get('paths'):
                return path
                
            mappings = self.config['paths'].get('path_mappings')
            if not mappings:
                return path
                
            platform = self.config['paths'].get('platform', '').lower()
            
            # Convert path separators based on platform
            if platform == 'windows':
                path = path.replace('/', '\\')
            else:  # linux, mac, or others
                path = path.replace('\\', '/')
                
            # Apply path mappings
            for local_path, remote_path in mappings.items():
                if path.startswith(local_path):
                    mapped_path = path.replace(local_path, remote_path, 1)
                    print(f"{YELLOW}Mapped path: {path} -> {mapped_path}{RESET}")
                    return mapped_path
                    
            return path
            
        except Exception as e:
            print(f"{YELLOW}Warning: Path mapping failed: {e}. Using original path.{RESET}")
            return path

    # ------------------------------------------------------------------------
    # LIBRARY UTILITIES
    # ------------------------------------------------------------------------
    def _get_library_movies_set(self) -> Set[Tuple[str, Optional[int]]]:
        """Get a set of (title.lower(), year) for all movies in the Plex library."""
        try:
            movies = self.plex.library.section('Movies')
            return {(movie.title.lower(), getattr(movie, 'year', None)) for movie in movies.all()}
        except Exception as e:
            print(f"{RED}Error getting library movies: {e}{RESET}")
            return set()

    def _is_movie_in_library(self, title: str, year: Optional[int]) -> bool:
        return (title.lower(), year) in self.library_movies

    # ------------------------------------------------------------------------
    # TMDB HELPER METHODS WITH IN-MEMORY & PERSISTENT CACHES
    # ------------------------------------------------------------------------
    def _get_plex_movie_tmdb_id(self, plex_movie) -> Optional[int]:
        """Find a TMDB ID for a given Plex movie, with caching to avoid repeat lookups."""
        if not self.use_tmdb_keywords or not self.tmdb_api_key:
            return None

        if plex_movie.ratingKey in self.plex_tmdb_cache:
            return self.plex_tmdb_cache[plex_movie.ratingKey]

        tmdb_id = None
        # Attempt to parse from guid
        if hasattr(plex_movie, 'guids'):
            for guid in plex_movie.guids:
                if 'themoviedb://' in guid.id:
                    try:
                        tmdb_id = int(guid.id.split('themoviedb://')[1])
                        break
                    except:
                        pass

        # If no ID from guid, do a search
        if not tmdb_id:
            title = plex_movie.title
            year = getattr(plex_movie, 'year', None)
            if not title:
                self.plex_tmdb_cache[plex_movie.ratingKey] = None
                return None

            try:
                base_url = "https://api.themoviedb.org/3/search/movie"
                params = {
                    'api_key': self.tmdb_api_key,
                    'query': title
                }
                if year:
                    params['year'] = year

                resp = requests.get(base_url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get('results', [])
                    if results:
                        # Try exact match on release_date
                        if year:
                            for r in results:
                                if r.get('release_date', '').startswith(str(year)):
                                    tmdb_id = r['id']
                                    break
                        # fallback to first
                        if not tmdb_id:
                            tmdb_id = results[0]['id']
            except Exception as e:
                print(f"{YELLOW}Could not fetch TMDB ID for '{title}': {e}{RESET}")

        self.plex_tmdb_cache[plex_movie.ratingKey] = tmdb_id
        return tmdb_id

    def _get_tmdb_keywords_for_id(self, tmdb_id: int) -> Set[str]:
        """Fetch TMDB keywords for the given ID (cached)."""
        if not tmdb_id or not self.use_tmdb_keywords or not self.tmdb_api_key:
            return set()

        if tmdb_id in self.tmdb_keywords_cache:
            return set(self.tmdb_keywords_cache[tmdb_id])

        kw_set = set()
        try:
            url = f"https://api.themoviedb.org/3/movie/{tmdb_id}/keywords"
            params = {'api_key': self.tmdb_api_key}
            resp = requests.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                keywords = data.get('keywords', [])
                kw_set = {k['name'].lower() for k in keywords}
        except Exception as e:
            print(f"{YELLOW}Error fetching TMDB keywords for ID {tmdb_id}: {e}{RESET}")

        self.tmdb_keywords_cache[tmdb_id] = list(kw_set)
        return kw_set

    # ------------------------------------------------------------------------
    # GATHER WATCHED MOVIES DATA
    # ------------------------------------------------------------------------
    def _get_watched_movies_data(self) -> Dict:
        """Collect counters for how many times the user has watched each genre, director, actor, etc."""
        import plexapi
        genre_counter = Counter()
        director_counter = Counter()
        actor_counter = Counter()
        tmdb_keyword_counter = Counter()

        try:
            movies_section = self.plex.library.section('Movies')
            watched_movies = movies_section.search(unwatched=False)
            total_watched = len(watched_movies)

            print(f"Found {total_watched} watched movies. Building frequency data...")
            for i, movie in enumerate(watched_movies, start=1):
                self._show_progress("Analyzing watched movies", i, total_watched)

                # Count genres
                if hasattr(movie, 'genres') and movie.genres:
                    for g in movie.genres:
                        genre_counter[g.tag.lower()] += 1

                # Count directors
                if hasattr(movie, 'directors') and movie.directors:
                    for d in movie.directors:
                        director_counter[d.tag] += 1

                # Count actors
                if hasattr(movie, 'roles') and movie.roles:
                    for a in movie.roles:
                        actor_counter[a.tag] += 1

                # Optional TMDB keywords
                if self.use_tmdb_keywords and self.tmdb_api_key:
                    tmdb_id = self._get_plex_movie_tmdb_id(movie)
                    if tmdb_id:
                        keywords = self._get_tmdb_keywords_for_id(tmdb_id)
                        for kw in keywords:
                            tmdb_keyword_counter[kw] += 1

            print()  # new line after progress finishes

        except plexapi.exceptions.BadRequest as e:
            print(f"{RED}Error gathering watched movies data: {e}{RESET}")

        return {
            'genres': dict(genre_counter),
            'directors': dict(director_counter),
            'actors': dict(actor_counter),
            'tmdb_keywords': dict(tmdb_keyword_counter)
        }

    def _show_progress(self, prefix: str, current: int, total: int):
        """Update a single console line with progress info."""
        pct = int((current / total) * 100)
        msg = f"\r{prefix}: {current}/{total} ({pct}%)"
        sys.stdout.write(msg)
        sys.stdout.flush()
        if current == total:
            sys.stdout.write("\n")

    # ------------------------------------------------------------------------
    # SCORING FUNCTION
    # ------------------------------------------------------------------------
    def calculate_movie_score(self, movie) -> float:
        """Calculate a weighted score for a movie based on frequency-based matching."""
        from collections import Counter
        user_genres = Counter(self.watched_data['genres'])
        user_dirs = Counter(self.watched_data['directors'])
        user_acts = Counter(self.watched_data['actors'])
        user_kws  = Counter(self.watched_data['tmdb_keywords'])

        weights = {
            'genre_weight': 0.4,
            'director_weight': 0.3,
            'actor_weight': 0.2,
            'keyword_weight': 0.1
        }

        max_genre_count = max(user_genres.values(), default=1)
        max_director_count = max(user_dirs.values(), default=1)
        max_actor_count = max(user_acts.values(), default=1)
        max_keyword_count = max(user_kws.values(), default=1)

        score = 0.0

        # GENRES
        if hasattr(movie, 'genres') and movie.genres:
            movie_genres = {g.tag.lower() for g in movie.genres}
            gscore = 0.0
            for mg in movie_genres:
                if mg in user_genres:
                    gscore += (user_genres[mg] / max_genre_count)
            if len(movie_genres) > 0:
                gscore /= len(movie_genres)
            score += gscore * weights['genre_weight']

        # DIRECTORS
        if hasattr(movie, 'directors') and movie.directors:
            dscore = 0.0
            matched_dirs = 0
            for d in movie.directors:
                if d.tag in user_dirs:
                    matched_dirs += 1
                    dscore += (user_dirs[d.tag] / max_director_count)
            if matched_dirs > 0:
                dscore /= matched_dirs
            score += dscore * weights['director_weight']

        # ACTORS
        if hasattr(movie, 'roles') and movie.roles:
            ascore = 0.0
            matched_actors = 0
            for a in movie.roles:
                if a.tag in user_acts:
                    matched_actors += 1
                    ascore += (user_acts[a.tag] / max_actor_count)
            # cap at 3
            if matched_actors > 3:
                ascore *= (3 / matched_actors)
            if matched_actors > 0:
                ascore /= matched_actors
            score += ascore * weights['actor_weight']

        # TMDB KEYWORDS
        if self.use_tmdb_keywords and self.tmdb_api_key:
            tmdb_id = self._get_plex_movie_tmdb_id(movie)
            if tmdb_id:
                keywords = self._get_tmdb_keywords_for_id(tmdb_id)
                kwscore = 0.0
                matched_kw = 0
                for kw in keywords:
                    if kw in user_kws:
                        matched_kw += 1
                        kwscore += (user_kws[kw] / max_keyword_count)
                if matched_kw > 0:
                    kwscore /= matched_kw
                score += kwscore * weights['keyword_weight']

        return score

    # ------------------------------------------------------------------------
    # MOVIE EXTRACTION
    # ------------------------------------------------------------------------
    def get_movie_details(self, movie) -> Dict:
        """Extract basic details + our similarity score for a Plex movie."""
        ratings = {}
        if hasattr(movie, 'rating'):
            ratings['imdb_rating'] = round(float(movie.rating), 1) if movie.rating else 0
        if hasattr(movie, 'audienceRating'):
            ratings['audience_rating'] = round(float(movie.audienceRating), 1) if movie.audienceRating else 0
        if hasattr(movie, 'ratingCount'):
            ratings['votes'] = movie.ratingCount

        similarity_score = self.calculate_movie_score(movie)
        details = {
            'title': movie.title,
            'year': getattr(movie, 'year', None),
            'genres': [g.tag.lower() for g in movie.genres] if hasattr(movie, 'genres') else [],
            'summary': getattr(movie, 'summary', ''),
            'ratings': ratings,
            'similarity_score': similarity_score
        }
        return details

    def get_unwatched_library_movies(self) -> List[Dict]:
        print(f"\n{YELLOW}Fetching unwatched movies from Plex library...{RESET}")
        movies_section = self.plex.library.section('Movies')
        
        current_all = movies_section.all()
        current_all_count = len(current_all)
        current_unwatched = movies_section.search(unwatched=True)
        current_unwatched_count = len(current_unwatched)
    
        # Check if library/unwatched count changed
        if (current_all_count == self.cached_library_movie_count and
            current_unwatched_count == self.cached_unwatched_count):
            print(f"No change in Plex library or unwatched count. Using cached unwatched data.")
            return self.cached_unwatched_movies
    
        unwatched_details = []
        for i, movie in enumerate(current_unwatched, start=1):
            self._show_progress("Scanning unwatched", i, current_unwatched_count)
            movie_info = self.get_movie_details(movie)
            if any(g in self.exclude_genres for g in movie_info['genres']):
                continue
            unwatched_details.append(movie_info)
        print()
    
        print(f"Found {len(unwatched_details)} unwatched movies matching your criteria.\n")
    
        self.cached_library_movie_count = current_all_count
        self.cached_unwatched_count = current_unwatched_count
        self.cached_unwatched_movies = unwatched_details
        return unwatched_details

    def get_trakt_recommendations(self) -> List[Dict]:
        """Get personalized movie recommendations from Trakt."""
        print(f"{YELLOW}Fetching recommendations from Trakt...{RESET}")
        try:
            url = "https://api.trakt.tv/recommendations/movies"
            response = requests.get(
                url,
                headers=self.trakt_headers,
                params={
                    'limit': self.limit_trakt_results * 4,
                    'extended': 'full'
                }
            )
            
            if response.status_code == 200:
                movies = response.json()
                # We'll do a random offset to each rating so top item changes across runs
                for m in movies:
                    base_rating = float(m.get('rating', 0.0))
                    m['_randomized_rating'] = base_rating + random.uniform(0, 0.5)

                # Sort by the randomized rating, descending
                movies.sort(key=lambda x: x['_randomized_rating'], reverse=True)

                recs = []
                for movie in movies:
                    # Skip if already in library
                    if self._is_movie_in_library(movie['title'], movie.get('year')):
                        continue

                    ratings = {
                        'imdb_rating': round(float(movie.get('rating', 0)), 1),
                        'votes': movie.get('votes', 0)
                    }
                    movie_details = {
                        'title': movie['title'],
                        'year': movie['year'],
                        'ratings': ratings,
                        'summary': movie.get('overview', ''),
                        'genres': [g.lower() for g in movie.get('genres', [])]
                    }
                    # Exclude if it has excluded genres
                    if any(g in self.exclude_genres for g in movie_details['genres']):
                        continue
                    recs.append(movie_details)
                
                half_cut = max(int(len(recs) * 0.5), 1)
                top_half = recs[:half_cut]
                random.shuffle(top_half)
                final_recs = top_half[:min(self.limit_trakt_results, len(top_half))]
                return final_recs
            else:
                print(f"{RED}Error getting Trakt recommendations: {response.status_code}{RESET}")
                if response.status_code == 401:
                    print(f"{YELLOW}Try re-authenticating with Trakt{RESET}")
                    self._authenticate_trakt()
                return []
        except Exception as e:
            print(f"{RED}Error getting Trakt recommendations: {e}{RESET}")
            return []

    # ------------------------------------------------------------------------
    # BUILD FINAL RECOMMENDATIONS
    # ------------------------------------------------------------------------
    def get_recommendations(self) -> Dict[str, List[Dict]]:
        """Gather both unwatched library recs and Trakt recs (unless plex_only)."""       
        plex_recs = self.get_unwatched_library_movies()
        if plex_recs:
            # Sort by (IMDb rating, similarity)
            plex_recs.sort(
                key=lambda x: (
                    x.get('ratings', {}).get('imdb_rating', 0),
                    x.get('similarity_score', 0)
                ),
                reverse=True
            )
            top_count = max(int(len(plex_recs) * 0.5), self.limit_plex_results)
            top_by_rating = plex_recs[:top_count]

            top_by_rating.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
            final_count = max(int(len(top_by_rating) * 0.3), self.limit_plex_results)
            final_pool = top_by_rating[:final_count]

            if final_pool:
                plex_recs = random.sample(final_pool, min(self.limit_plex_results, len(final_pool)))
            else:
                plex_recs = []
        else:
            plex_recs = []

        trakt_recs = []
        if not self.plex_only:
            trakt_recs = self.get_trakt_recommendations()

        print(f"\nRecommendation process completed!")
        return {
            'plex_recommendations': plex_recs,
            'trakt_recommendations': trakt_recs
        }

    # ------------------------------------------------------------------------
    # SELECTION HELPER
    # ------------------------------------------------------------------------
    def _user_select_recommendations(self, recommended_movies: List[Dict], operation_label: str) -> List[Dict]:
        """
        Asks the user which recommendations to process.
          - 'y', 'yes', 'all' => all
          - 'n', 'no', 'none' => none
          - comma-separated numbers => only those indices
        Returns a subset list of recommended_movies based on user input.
        """
        # Show a message:
        prompt = (
            f"\nWhich recommendations would you like to {operation_label}?\n"
            "Enter 'all' or 'y' to select ALL,\n"
            "Enter 'none' or 'n' to skip them,\n"
            "Or enter a comma-separated list of numbers (e.g. 1,3,5). "
            "\nYour choice: "
        )
        choice = input(prompt).strip().lower()

        # If user chooses none
        if choice in ("n", "no", "none", ""):
            # treat empty as none
            print(f"{YELLOW}Skipping {operation_label} as per user choice.{RESET}")
            return []

        # If user chooses all
        if choice in ("y", "yes", "all"):
            return recommended_movies

        # Otherwise parse comma-separated indices
        indices_str = re.split(r'[,\s]+', choice)
        chosen = []
        for idx_str in indices_str:
            idx_str = idx_str.strip()
            if not idx_str.isdigit():
                print(f"{YELLOW}Skipping invalid index: {idx_str}{RESET}")
                continue
            idx = int(idx_str)
            if 1 <= idx <= len(recommended_movies):
                chosen.append(idx)
            else:
                print(f"{YELLOW}Skipping out-of-range index: {idx}{RESET}")

        if not chosen:
            print(f"{YELLOW}No valid indices selected, skipping {operation_label}.{RESET}")
            return []

        # Build the subset
        subset = []
        for c in chosen:
            subset.append(recommended_movies[c - 1])  # 1-based index => 0-based list
        return subset

    # ------------------------------------------------------------------------
    # PLEX LABEL MANAGEMENT
    # ------------------------------------------------------------------------
    def manage_plex_labels(self, recommended_movies: List[Dict]) -> None:
        if not recommended_movies:
            print(f"{YELLOW}No movies to add labels to.{RESET}")
            return
    
        if not self.config['plex'].get('add_label'):
            return
    
        if self.confirm_operations:
            # Let the user pick which to label
            selected_movies = self._user_select_recommendations(recommended_movies, "label in Plex")
            if not selected_movies:
                return
        else:
            selected_movies = recommended_movies

        try:
            movies_section = self.plex.library.section('Movies')
            label_name = self.config['plex'].get('label_name', 'Recommended')

            # Collect matching movies
            movies_to_update = []
            for rec in selected_movies:
                plex_movie = next(
                    (m for m in movies_section.search(title=rec['title'])
                     if m.year == rec.get('year')), 
                    None
                )
                if plex_movie:
                    plex_movie.reload()
                    movies_to_update.append(plex_movie)

            if not movies_to_update:
                print(f"{YELLOW}No matching movies found in Plex to add labels to.{RESET}")
                return

            # Possibly remove old label
            if self.config['plex'].get('remove_previous_recommendations', False):
                print(f"{YELLOW}Finding movies with existing label: {label_name}{RESET}")
                labeled_movies = set(movies_section.search(label=label_name))
                movies_to_unlabel = labeled_movies - set(movies_to_update)
                for movie in movies_to_unlabel:
                    current_labels = [label.tag for label in movie.labels]
                    if label_name in current_labels:
                        movie.removeLabel(label_name)
                        print(f"{YELLOW}Removed label from: {movie.title}{RESET}")

            # Add label
            print(f"{YELLOW}Adding label to recommended movies...{RESET}")
            for movie in movies_to_update:
                current_labels = [label.tag for label in movie.labels]
                if label_name not in current_labels:
                    movie.addLabel(label_name)
                    print(f"{GREEN}Added label to: {movie.title}{RESET}")
                else:
                    print(f"{YELLOW}Label already exists on: {movie.title}{RESET}")

            print(f"{GREEN}Successfully updated labels for recommended movies{RESET}")

        except Exception as e:
            print(f"{RED}Error managing Plex labels: {e}{RESET}")
            import traceback
            print(traceback.format_exc())

    # ------------------------------------------------------------------------
    # RADARR INTEGRATION
    # ------------------------------------------------------------------------
    def add_to_radarr(self, recommended_movies: List[Dict]) -> None:
        """Add recommended movies to Radarr, optionally confirming first."""
        if not recommended_movies:
            print(f"{YELLOW}No movies to add to Radarr.{RESET}")
            return
    
        if not self.config['radarr'].get('add_to_radarr'):
            return

        if self.confirm_operations:
            # Let user pick which to add
            selected_movies = self._user_select_recommendations(recommended_movies, "add to Radarr")
            if not selected_movies:
                return
        else:
            selected_movies = recommended_movies
    
        try:
            # Verify Radarr config
            if 'radarr' not in self.config:
                raise ValueError("Radarr configuration missing from config file")

            required_fields = ['url', 'api_key', 'root_folder', 'quality_profile']
            missing_fields = [field for field in required_fields if field not in self.config['radarr']]
            if missing_fields:
                raise ValueError(f"Missing required Radarr config fields: {', '.join(missing_fields)}")

            radarr_url = self.config['radarr']['url'].rstrip('/')
            if '/api/' not in radarr_url:
                if '/radarr' not in radarr_url:
                    radarr_url += '/radarr'
                radarr_url += '/api/v3'

            headers = {
                'X-Api-Key': self.config['radarr']['api_key'],
                'Content-Type': 'application/json'
            }

            trakt_headers = {
                'Content-Type': 'application/json',
                'trakt-api-version': '2',
                'trakt-api-key': self.config['trakt']['client_id'],
                'Authorization': f"Bearer {self.config['trakt']['access_token']}"
            }

            # Test Radarr connection
            try:
                test_response = requests.get(f"{radarr_url}/system/status", headers=headers)
                test_response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise ValueError(f"Failed to connect to Radarr: {str(e)}")

            # Create/find tag
            tag_id = None
            if self.config['radarr'].get('radarr_tag'):
                tags_response = requests.get(f"{radarr_url}/tag", headers=headers)
                tags_response.raise_for_status()
                tags = tags_response.json()
                tag = next(
                    (t for t in tags 
                     if t['label'].lower() == self.config['radarr']['radarr_tag'].lower()),
                    None
                )
                if tag:
                    tag_id = tag['id']
                else:
                    tag_response = requests.post(
                        f"{radarr_url}/tag",
                        headers=headers,
                        json={'label': self.config['radarr']['radarr_tag']}
                    )
                    tag_response.raise_for_status()
                    tag_id = tag_response.json()['id']
                    print(f"{GREEN}Created new Radarr tag: {self.config['radarr']['radarr_tag']} (ID: {tag_id}){RESET}")

            # Quality profile
            profiles_response = requests.get(f"{radarr_url}/qualityprofile", headers=headers)
            profiles_response.raise_for_status()
            quality_profiles = profiles_response.json()
            desired_profile = next(
                (p for p in quality_profiles
                 if p['name'].lower() == self.config['radarr']['quality_profile'].lower()),
                None
            )
            if not desired_profile:
                available = [p['name'] for p in quality_profiles]
                raise ValueError(
                    f"Quality profile '{self.config['radarr']['quality_profile']}' not found. "
                    f"Available: {', '.join(available)}"
                )
            quality_profile_id = desired_profile['id']

            # Check existing in Radarr
            existing_response = requests.get(f"{radarr_url}/movie", headers=headers)
            existing_response.raise_for_status()
            existing_movies = existing_response.json()
            existing_tmdb_ids = {m['tmdbId'] for m in existing_movies}

            # Process each selected
            for movie in selected_movies:
                try:
                    trakt_search_url = f"https://api.trakt.tv/search/movie?query={quote(movie['title'])}"
                    if movie.get('year'):
                        trakt_search_url += f"&years={movie['year']}"

                    trakt_response = requests.get(trakt_search_url, headers=trakt_headers)
                    trakt_response.raise_for_status()
                    trakt_results = trakt_response.json()

                    if not trakt_results:
                        print(f"{YELLOW}Movie not found on Trakt: {movie['title']}{RESET}")
                        continue

                    # find exact or fallback
                    trakt_movie = next(
                        (r for r in trakt_results
                         if r['movie']['title'].lower() == movie['title'].lower()
                         and r['movie'].get('year') == movie.get('year')),
                        trakt_results[0]
                    )
                    tmdb_id = trakt_movie['movie']['ids']['tmdb']
                    if not tmdb_id:
                        print(f"{YELLOW}No TMDB ID found for {movie['title']}{RESET}")
                        continue

                    # skip if in Radarr
                    if tmdb_id in existing_tmdb_ids:
                        print(f"{YELLOW}Already in Radarr: {movie['title']}{RESET}")
                        continue

                    root_folder = self._map_path(self.config['radarr']['root_folder'].rstrip('/\\'))
                    should_monitor = self.config['radarr'].get('monitor', False)

                    movie_data = {
                        'tmdbId': tmdb_id,
                        'monitored': should_monitor,
                        'qualityProfileId': quality_profile_id,
                        'minimumAvailability': 'released',
                        'addOptions': {
                            'searchForMovie': should_monitor
                        },
                        'rootFolderPath': root_folder,
                        'title': movie['title']
                    }
                    if tag_id is not None:
                        movie_data['tags'] = [tag_id]

                    add_resp = requests.post(f"{radarr_url}/movie", headers=headers, json=movie_data)
                    add_resp.raise_for_status()

                    if should_monitor:
                        new_id = add_resp.json()['id']
                        search_cmd = {'name': 'MoviesSearch', 'movieIds': [new_id]}
                        sr = requests.post(f"{radarr_url}/command", headers=headers, json=search_cmd)
                        sr.raise_for_status()
                        print(f"{GREEN}Triggered download search for: {movie['title']}{RESET}")
                    else:
                        print(f"{YELLOW}Movie added but not monitored: {movie['title']}{RESET}")

                except requests.exceptions.RequestException as e:
                    print(f"{RED}Error adding {movie['title']} to Radarr: {str(e)}{RESET}")
                    if hasattr(e, 'response') and e.response is not None:
                        raw_error = e.response.text
                        try:
                            corrected_error = raw_error.encode('utf-8').decode('unicode_escape')
                        except UnicodeDecodeError:
                            corrected_error = raw_error
                        print(f"{RED}Radarr error response: {corrected_error}{RESET}")
                    continue

        except Exception as e:
            print(f"{RED}Error adding movies to Radarr: {e}{RESET}")
            import traceback
            print(traceback.format_exc())


# ------------------------------------------------------------------------
# OUTPUT FORMATTING
# ------------------------------------------------------------------------
def format_movie_output(movie: Dict, show_summary: bool = False, index: Optional[int] = None) -> str:
    """
    Format movie info for display. If index is provided, include a numbered bullet.
    """
    bullet = f"{index}. " if index is not None else "- "
    output = f"{bullet}{CYAN}{movie['title']}{RESET} ({movie.get('year', 'N/A')})"
    
    if movie.get('genres'):
        output += f"\n  {YELLOW}Genres:{RESET} {', '.join(movie['genres'])}"

    if movie.get('ratings'):
        if 'imdb_rating' in movie['ratings'] and movie['ratings']['imdb_rating'] > 0:
            votes_str = f" ({movie['ratings'].get('votes', 'N/A')} votes)" if 'votes' in movie['ratings'] else ""
            output += f"\n  {YELLOW}IMDb Rating:{RESET} {movie['ratings']['imdb_rating']}/10{votes_str}"

    if 'similarity_score' in movie:
        output += f"\n  {YELLOW}Similarity Score:{RESET} {movie['similarity_score']:.2f}"

    if show_summary and movie.get('summary'):
        output += f"\n  {YELLOW}Summary:{RESET} {movie['summary']}"

    return output


# ------------------------------------------------------------------------
# LOGGING / MAIN
# ------------------------------------------------------------------------
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

class TeeLogger:
    """
    A simple 'tee' class that writes to both console (sys.__stdout__) and a file,
    but strips ANSI color codes for the file.
    """
    def __init__(self, logfile):
        self.logfile = logfile
    
    def write(self, text):
        sys.__stdout__.write(text)
        stripped = ANSI_PATTERN.sub('', text)
        self.logfile.write(stripped)

    def flush(self):
        sys.__stdout__.flush()
        self.logfile.flush()

def cleanup_old_logs(log_dir: str, keep_logs: int):
    """Keep only the most recent `keep_logs` log files, remove older ones."""
    if keep_logs <= 0:
        return

    all_files = sorted(
        (f for f in os.listdir(log_dir) if f.endswith('.log')),
        key=lambda x: os.path.getmtime(os.path.join(log_dir, x))
    )
    if len(all_files) > keep_logs:
        to_remove = all_files[:len(all_files) - keep_logs]
        for f in to_remove:
            os.remove(os.path.join(log_dir, f))

def main():
    print(f"{CYAN}Movie Recommendations for Plex{RESET}")
    print("-" * 50)
    check_version()
    print("-" * 50)
    
    config_path = os.path.join(os.path.dirname(__file__), 'config.yml')
    
    # Load config once here (so we can see keep_logs before building the Recommender)
    try:
        with open(config_path, 'r') as f:
            base_config = yaml.safe_load(f)
    except Exception as e:
        print(f"{RED}Could not load config.yml: {e}{RESET}")
        sys.exit(1)

    general = base_config.get('general', {})
    keep_logs = general.get('keep_logs', 0)

    # If keep_logs > 0, set up logging
    original_stdout = sys.stdout
    log_dir = os.path.join(os.path.dirname(__file__), 'Logs')
    if keep_logs > 0:
        try:
            os.makedirs(log_dir, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file_path = os.path.join(log_dir, f"recommendations_{timestamp}.log")
            lf = open(log_file_path, "w", encoding="utf-8")
            sys.stdout = TeeLogger(lf)

            cleanup_old_logs(log_dir, keep_logs)
        except Exception as e:
            print(f"{RED}Could not set up logging: {e}{RESET}")
            # fallback to normal console printing

    try:
        recommender = PlexMovieRecommender(config_path)
        recommendations = recommender.get_recommendations()
        
        print(f"\n{GREEN}=== Recommended Unwatched Movies in Your Library ==={RESET}")
        plex_recs = recommendations.get('plex_recommendations', [])
        if plex_recs:
            for i, movie in enumerate(plex_recs, start=1):
                print(format_movie_output(movie, recommender.show_summary, index=i))
                print()
            # Manage Plex labels if configured
            recommender.manage_plex_labels(plex_recs)
        else:
            print(f"{YELLOW}No recommendations found in your Plex library matching your criteria.{RESET}")
     
        if not recommender.plex_only:
            print(f"\n{GREEN}=== Recommended Movies to Add to Your Library ==={RESET}")
            trakt_recs = recommendations.get('trakt_recommendations', [])
            if trakt_recs:
                for i, movie in enumerate(trakt_recs, start=1):
                    print(format_movie_output(movie, recommender.show_summary, index=i))
                    print()
                # Add to Radarr
                recommender.add_to_radarr(trakt_recs)
            else:
                print(f"{YELLOW}No Trakt recommendations found matching your criteria.{RESET}")

        # Save updated caches
        recommender._save_cache()

    except Exception as e:
        print(f"\n{RED}An error occurred: {e}{RESET}")
        import traceback
        print(traceback.format_exc())

    if keep_logs > 0 and sys.stdout is not original_stdout:
        sys.stdout.logfile.close()
        sys.stdout = original_stdout

    print(f"\n{GREEN}Process completed!{RESET}")


if __name__ == "__main__":
    main()
