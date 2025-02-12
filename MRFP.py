import os
import plexapi.server
from plexapi.server import PlexServer
from plexapi.myplex import MyPlexAccount
import yaml
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
from datetime import datetime, timezone, timedelta

__version__ = "3.0b05"
REPO_URL = "https://github.com/netplexflix/Movie-Recommendations-for-Plex"
API_VERSION_URL = f"https://api.github.com/repos/netplexflix/Movie-Recommendations-for-Plex/releases/latest"

# ANSI Color Codes
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

def get_full_language_name(lang_code: str) -> str:
    LANGUAGE_CODES = {
        'en': 'English',
        'es': 'Spanish',
        'fr': 'French',
        'de': 'German',
        'it': 'Italian',
        'zh': 'Chinese',
        'ja': 'Japanese',
        'ko': 'Korean',
        'pt': 'Portuguese',
        'ru': 'Russian',
        'ar': 'Arabic',
        'hi': 'Hindi',
        'bn': 'Bengali',
        'pa': 'Punjabi',
        'jv': 'Javanese',
        'vi': 'Vietnamese',
        'tr': 'Turkish',
        'nl': 'Dutch',
        'da': 'Danish',
        'sv': 'Swedish',
        'no': 'Norwegian',
        'fi': 'Finnish',
        'pl': 'Polish',
        'cs': 'Czech',
        'hu': 'Hungarian',
        'el': 'Greek',
        'he': 'Hebrew',
        'id': 'Indonesian',
        'ms': 'Malay',
        'th': 'Thai',
        'tl': 'Tagalog',
        # Add more as needed
    }
    return LANGUAGE_CODES.get(lang_code.lower(), lang_code.capitalize())
	
RATING_MULTIPLIERS = {
    0: 0.1,   # Strong dislike
    1: 0.2,   # Very poor
    2: 0.4,   # Poor
    3: 0.6,   # Below average
    4: 0.8,   # Slightly below average
    5: 1.0,   # Neutral/baseline
    6: 1.2,   # Slightly above average
    7: 1.4,   # Good
    8: 1.6,   # Very good
    9: 1.8,   # Excellent
    10: 2.0   # Outstanding
    }
	
def check_version():
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
        self.config = self._load_config(config_path)
        self.library_title = self.config['plex'].get('movie_library_title', 'Movies')
        self.cached_watched_count = 0
        self.cached_unwatched_count = 0
        self.cached_library_movie_count = 0
        self.watched_data_counters = {}
        self.cached_unwatched_movies = []
        self.plex_tmdb_cache = {}
        self.tmdb_keywords_cache = {}
        self.users = self._get_configured_users()

        print("Initializing recommendation system...")
        if self.config.get('tautulli', {}).get('users'):
            if not self.config['tautulli'].get('url') or not self.config['tautulli'].get('api_key'):
                raise ValueError("Tautulli configuration requires both url and api_key when users are specified")        
        print("Connecting to Plex server...")
        self.plex = self._init_plex()
        print(f"Connected to Plex successfully!\n")
        print(f"{YELLOW}Checking Cache...{RESET}")
        
        general_config = self.config.get('general', {})
        self.confirm_operations = general_config.get('confirm_operations', False)
        self.limit_plex_results = general_config.get('limit_plex_results', 10)
        self.limit_trakt_results = general_config.get('limit_trakt_results', 10)
        self.show_summary = general_config.get('show_summary', False)
        self.plex_only = general_config.get('plex_only', False)
        self.show_cast = general_config.get('show_cast', False)
        self.show_director = general_config.get('show_director', False)
        self.show_language = general_config.get('show_language', False)
        self.show_rating = general_config.get('show_rating', False)
        self.show_imdb_link = general_config.get('show_imdb_link', False)
        
        exclude_genre_str = general_config.get('exclude_genre', '')
        self.exclude_genres = [g.strip().lower() for g in exclude_genre_str.split(',') if g.strip()] if exclude_genre_str else []

        weights_config = self.config.get('weights', {})
        self.weights = {
            'genre_weight': float(weights_config.get('genre_weight', 0.25)),
            'director_weight': float(weights_config.get('director_weight', 0.20)),
            'actor_weight': float(weights_config.get('actor_weight', 0.20)),
            'language_weight': float(weights_config.get('language_weight', 0.10)),
            'keyword_weight': float(weights_config.get('keyword_weight', 0.25))
        }

        total_weight = sum(self.weights.values())
        if not abs(total_weight - 1.0) < 1e-6:
            print(f"{YELLOW}Warning: Weights sum to {total_weight}, expected 1.0.{RESET}")
			
        trakt_config = self.config.get('trakt', {})
        self.sync_watch_history = trakt_config.get('sync_watch_history', False)
        self.trakt_headers = {
            'Content-Type': 'application/json',
            'trakt-api-version': '2',
            'trakt-api-key': trakt_config['client_id']
        }
        if 'access_token' in trakt_config:
            self.trakt_headers['Authorization'] = f"Bearer {trakt_config['access_token']}"
        else:
            self._authenticate_trakt()

        # Verify Tautulli/Plex user mapping
        if self.users['tautulli_users']:
            print(f"Validating Tautulli users: {self.users['tautulli_users']}")
            
            # Skip validation completely if 'All' is specified
            if any(u.lower() == 'all' for u in self.users['tautulli_users']):
                print(f"{YELLOW}Using watch history for all Tautulli users{RESET}")
            else:
                # Only validate specific users
                test_params = {'apikey': self.config['tautulli']['api_key'], 'cmd': 'get_users'}
                users_response = requests.get(f"{self.config['tautulli']['url']}/api/v2", params=test_params)
                if users_response.status_code == 200:
                    tautulli_users = [u['username'] for u in users_response.json()['response']['data']]
                    missing = [u for u in self.users['tautulli_users'] if u not in tautulli_users]
                    if missing:
                        raise ValueError(f"Tautulli users not found: {missing}")

        # Verify library exists
        if not self.plex.library.section(self.library_title):
            raise ValueError(f"Movie library '{self.library_title}' not found in Plex")
        
        tmdb_config = self.config.get('TMDB', {})
        self.use_tmdb_keywords = tmdb_config.get('use_TMDB_keywords', False)
        self.tmdb_api_key = tmdb_config.get('api_key', None)

        self.radarr_config = self.config.get('radarr', {})

        self.cache_dir = os.path.join(os.path.dirname(__file__), "cache")
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Get user context for cache files
        if self.users['tautulli_users']:
            user_ctx = 'tautulli_' + '_'.join(self.users['tautulli_users'])
        else:
            user_ctx = 'plex_' + '_'.join(self.users['managed_users'])
        safe_ctx = re.sub(r'\W+', '', user_ctx)
        
        # Update cache paths to be user-specific
        self.watched_cache_path = os.path.join(self.cache_dir, f"watched_cache_{safe_ctx}.json")
        self.unwatched_cache_path = os.path.join(self.cache_dir, f"unwatched_cache_{safe_ctx}.json")
        self.trakt_cache_path = os.path.join(self.cache_dir, f"trakt_sync_cache_{safe_ctx}.json")
        
        # Load watched cache
        if os.path.exists(self.watched_cache_path):
            try:
                with open(self.watched_cache_path, 'r', encoding='utf-8') as f:
                    watched_cache = json.load(f)
                    self.cached_watched_count = watched_cache.get('watched_count', 0)
                    self.watched_data_counters = watched_cache.get('watched_data_counters', {})
                    self.plex_tmdb_cache = watched_cache.get('plex_tmdb_cache', {})
                    self.tmdb_keywords_cache = watched_cache.get('tmdb_keywords_cache', {})
            except Exception as e:
                print(f"{YELLOW}Error loading watched cache: {e}{RESET}")
    
        # Load unwatched cache
        if os.path.exists(self.unwatched_cache_path):
            try:
                with open(self.unwatched_cache_path, 'r', encoding='utf-8') as f:
                    unwatched_cache = json.load(f)
                    self.cached_library_movie_count = unwatched_cache.get('library_movie_count', 0)
                    self.cached_unwatched_count = unwatched_cache.get('unwatched_count', 0)
                    self.cached_unwatched_movies = unwatched_cache.get('unwatched_movie_details', [])
            except Exception as e:
                print(f"{YELLOW}Error loading unwatched cache: {e}{RESET}") 
				
        if self.plex_tmdb_cache is None:
            self.plex_tmdb_cache = {}
        if self.tmdb_keywords_cache is None:
            self.tmdb_keywords_cache = {}
        if not hasattr(self, 'synced_trakt_history'):
            self.synced_trakt_history = {}

        current_watched_count = self._get_watched_count()
        cache_exists = os.path.exists(self.watched_cache_path)
        
        if (not cache_exists) or (current_watched_count != self.cached_watched_count):
            print("Watched count changed or no cache found; gathering watched data now. This may take a while...\n")
            if self.users['tautulli_users']:
                print("Using Tautulli users for watch history")
                self.watched_data = self._get_tautulli_watched_movies_data()
            else:
                print("Using managed users for watch history")
                self.watched_data = self._get_managed_users_watched_data()
            self.watched_data_counters = self.watched_data
            self.cached_watched_count = current_watched_count
            self._save_watched_cache()
        else:
            print("Watched count unchanged. Using cached data for faster performance.\n")
            self.watched_data = self.watched_data_counters

        print("Fetching library metadata (for existing movie checks)...")
        self.library_movies = self._get_library_movies_set()
        self.library_imdb_ids = self._get_library_imdb_ids()


    # ------------------------------------------------------------------------
    # CONFIG / SETUP
    # ------------------------------------------------------------------------
    def _load_config(self, config_path: str) -> Dict:
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
                print(f"Successfully loaded configuration from {config_path}")
                return config
        except Exception as e:
            print(f"{RED}Error loading config from {config_path}: {e}{RESET}")
            raise

    def _init_plex(self) -> plexapi.server.PlexServer:
        try:
            return plexapi.server.PlexServer(
                self.config['plex']['url'],
                self.config['plex']['token']
            )
        except Exception as e:
            print(f"{RED}Error connecting to Plex server: {e}{RESET}")
            raise

    def _authenticate_trakt(self):
        try:
            response = requests.post(
                'https://api.trakt.tv/oauth/device/code',
                headers={'Content-Type': 'application/json'},
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
                        headers={'Content-Type': 'application/json'},
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
    # USERS
    # ------------------------------------------------------------------------ 
    def _get_configured_users(self):
        # Get raw managed users list from config
        raw_managed = self.config['plex'].get('managed_users', '')
        managed_users = [u.strip() for u in raw_managed.split(',') if u.strip()]
        
        # Get Tautulli users
        tautulli_users = []
        tautulli_config = self.config.get('tautulli', {})
        if isinstance(tautulli_config.get('users'), list):
            tautulli_users = tautulli_config['users']
        elif isinstance(tautulli_config.get('users'), str):
            tautulli_users = [u.strip() for u in tautulli_config['users'].split(',') if u.strip()]
        
        # Resolve admin account
        account = MyPlexAccount(token=self.config['plex']['token'])
        admin_user = account.username
        
        # Replace admin aliases with actual username
        processed_managed = []
        for user in managed_users:
            if user.lower() in ['admin', 'administrator']:
                processed_managed.append(admin_user)
            else:
                processed_managed.append(user)
        
        # Remove duplicates while preserving order
        seen = set()
        managed_users = [u for u in processed_managed if not (u in seen or seen.add(u))]
        
        # Handle "none" case for Tautulli
        if tautulli_users and tautulli_users[0].lower() == 'none':
            tautulli_users = []
        
        return {
            'managed_users': managed_users,
            'tautulli_users': tautulli_users,
            'admin_user': admin_user
        }

    def _get_current_users(self) -> str:
        if self.users['tautulli_users']:
            return f"Tautulli users: {', '.join(self.users['tautulli_users'])}"
        return f"Managed users: {', '.join(self.users['managed_users'])}"

    def _get_user_specific_connection(self):
        if self.users['tautulli_users']:
            return self.plex
        try:
            account = MyPlexAccount(token=self.config['plex']['token'])
            user = account.user(self.users['managed_users'][0])
            return self.plex.switchUser(user)
        except:
            return self.plex

    def _get_watched_count(self) -> int:
        if self.users['tautulli_users']:
            params = {
                'apikey': self.config['tautulli']['api_key'],
                'cmd': 'get_history',
                'media_type': 'movie',
                'length': 10000
            }
            
            if not any(u.lower() == 'all' for u in self.users['tautulli_users']):
                params['user'] = ','.join(self.users['tautulli_users'])
            
            try:
                response = requests.get(
                    f"{self.config['tautulli']['url']}/api/v2",
                    params=params
                )
                if response.status_code == 200:
                    data = response.json().get('response', {})
                    history_items = data.get('data', [])
                    
                    if isinstance(history_items, dict):
                        history_items = history_items.get('data', [])
                    
                    rating_keys = {str(item.get('rating_key')) for item in history_items if item.get('rating_key')}
                    return len(rating_keys)
            except Exception as e:
                print(f"{YELLOW}Error fetching Tautulli history: {e}{RESET}")
                return 0
        else:
            # For managed users, sum up all unique watched movies
            try:
                total_watched = set()  # Using set to avoid counting duplicates
                movies_section = self.plex.library.section(self.library_title)
                account = MyPlexAccount(token=self.config['plex']['token'])
                
                users_to_process = self.users['managed_users'] or [self.users['admin_user']]
                
                for username in users_to_process:
                    try:
                        if username.lower() == self.users['admin_user'].lower():
                            user_plex = self.plex
                        else:
                            user = account.user(username)
                            user_plex = self.plex.switchUser(user)
                        
                        watched_movies = user_plex.library.section(self.library_title).search(unwatched=False)
                        total_watched.update(movie.ratingKey for movie in watched_movies)
                        
                    except Exception as e:
                        print(f"{YELLOW}Error getting watch count for user {username}: {e}{RESET}")
                        continue
                        
                return len(total_watched)
                
            except Exception as e:
                print(f"{YELLOW}Error getting watch count: {e}{RESET}")
                return 0
				
    def _get_tautulli_watched_movies_data(self) -> Dict:
        movies_section = self.plex.library.section(self.library_title)
        
        counters = {
            'genres': Counter(),
            'directors': Counter(),
            'actors': Counter(),
            'languages': Counter(),
            'tmdb_keywords': Counter()
        }
		
        not_found_count = 0
		
        users = self.users.get('tautulli_users', [])
        if not users:
            return self._normalize_all_counters(counters)
        
        try:
            params = {
                'apikey': self.config['tautulli']['api_key'],
                'cmd': 'get_history',
                'media_type': 'movie',
                'length': 10000
            }
            
            if not any(u.lower() == 'all' for u in users):
                params['user'] = ','.join(users)
            
            response = requests.get(
                f"{self.config['tautulli']['url']}/api/v2",
                params=params
            )
            response.raise_for_status()
            
            response_data = response.json()
            if 'response' not in response_data:
                raise ValueError("Invalid Tautulli API response format")
                
            history_data = response_data['response'].get('data', {})
            if isinstance(history_data, dict):
                # Paginated format (v2.6+)
                history_items = history_data.get('data', [])
                total = history_data.get('recordsFiltered', 0)
            else:
                # Legacy format
                history_items = history_data
                total = len(history_items)
    
            if not isinstance(history_items, list):
                raise ValueError("Invalid history data format from Tautulli")
            
            rating_keys = {str(item.get('rating_key')) for item in history_items if item.get('rating_key')}
            
            movie_titles = {
                str(item.get('rating_key')): item.get('title', 'Unknown Title') 
                for item in history_items if item.get('rating_key')
            }
            
            print(f"\nFound {len(rating_keys)} watched movies for {', '.join(users)}")
            
            # Create mapping of rating keys to movie details from Tautulli
            movie_details = {
                str(item.get('rating_key')): {
                    'title': item.get('title', 'Unknown Title'),
                    'year': item.get('year'),
                    'last_watched': item.get('started')
                }
                for item in history_items if item.get('rating_key')
            }
            
            total_movies = len(movie_details)
            print(f"\nProcessing {total_movies} watched movies from Tautulli history:")
            
            for i, (rating_key, details) in enumerate(movie_details.items(), 1):
                try:
                    self._show_progress("Processing", i, total_movies)
                    
                    movie = None
                    
                    # Trying by rating key
                    try:
                        movie = movies_section.fetchItem(int(rating_key))
                    except:
                        pass
                    
                    # Trying by title and year
                    if not movie and details['title'] and details['year']:
                        matches = movies_section.search(title=details['title'])
                        movie = next(
                            (m for m in matches if m.year == details['year']), 
                            None
                        )
                    
                    if movie:
                        movie.reload()
                        self._process_movie_counters(movie, counters)
                    else:
                        not_found_count += 1
                        
                except Exception as e:
                    not_found_count += 1
                    continue
                    
#            print(f"{YELLOW}DEBUG: {not_found_count} watched movies were no longer found in your library{RESET}\n")
                
        except Exception as e:
            print(f"{RED}Error getting Tautulli watch history: {e}{RESET}")
            
        return self._normalize_all_counters(counters)
    
    def _is_valid_movie_entry(self, entry: dict) -> bool:
        return (
            isinstance(entry, dict) and 
            entry.get('media_type') == 'movie' and
            isinstance(entry.get('metadata'), dict) and
            entry['metadata'].get('title')
        )
    
    def _get_managed_users_watched_data(self):
        movies_section = self.plex.library.section(self.library_title)
        if not movies_section:
            raise ValueError(f"Library section '{self.library_title}' not found")

        counters = {
            'genres': Counter(),
            'directors': Counter(),
            'actors': Counter(),
            'languages': Counter(),
            'tmdb_keywords': Counter()
        }
        
        account = MyPlexAccount(token=self.config['plex']['token'])
        admin_user = self.users['admin_user']
        
        users_to_process = self.users['managed_users'] or [admin_user]
        
        for username in users_to_process:
            try:
                if username.lower() == self.users['admin_user'].lower():
                    user_plex = self.plex
                else:
                    user = account.user(username)
                    user_plex = self.plex.switchUser(user)
                
                movies = user_plex.library.section(self.library_title).search(unwatched=False)
                total = len(movies)
                print(f"\nScanning watched movies for {username}:")

                for i, movie in enumerate(movies, 1):
                    self._show_progress(f"Processing {username}'s watched", i, total)
                    self._process_movie_counters(movie, counters)
                    
            except Exception as e:
                print(f"{RED}Error processing user {username}: {e}{RESET}")
                continue
        
        return self._normalize_all_counters(counters)

    # ------------------------------------------------------------------------
    # CACHING LOGIC
    # ------------------------------------------------------------------------ 
    def _save_watched_cache(self):
        try:
            cache_data = {
                'watched_count': self.cached_watched_count,
                'watched_data_counters': self.watched_data_counters,
                'plex_tmdb_cache': self.plex_tmdb_cache,
                'tmdb_keywords_cache': self.tmdb_keywords_cache,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.watched_cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=4, ensure_ascii=False)
                
        except Exception as e:
            print(f"{YELLOW}Error saving watched cache: {e}{RESET}")
    
    def _save_unwatched_cache(self):
        try:
            cache_data = {
                'library_movie_count': self.cached_library_movie_count,
                'unwatched_count': self.cached_unwatched_count,
                'unwatched_movie_details': self.cached_unwatched_movies,
                'last_updated': datetime.now().isoformat()
            }
            with open(self.unwatched_cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=4, ensure_ascii=False)
                
        except Exception as e:
            print(f"{YELLOW}Error saving unwatched cache: {e}{RESET}")
    
    def _save_cache(self):
        self._save_watched_cache()
        self._save_unwatched_cache()

    # ------------------------------------------------------------------------
    # PATH HANDLING
    # ------------------------------------------------------------------------
    def _map_path(self, path: str) -> str:
        try:
            if not self.config.get('paths'):
                return path
                
            mappings = self.config['paths'].get('path_mappings')
            if not mappings:
                return path
                
            platform = self.config['paths'].get('platform', '').lower()
            if platform == 'windows':
                path = path.replace('/', '\\')
            else:
                path = path.replace('\\', '/')
                
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
        try:
            movies = self.plex.library.section(self.library_title)
            return {(movie.title.lower(), getattr(movie, 'year', None)) for movie in movies.all()}
        except Exception as e:
            print(f"{RED}Error getting library movies: {e}{RESET}")
            return set()

    def _get_library_imdb_ids(self) -> Set[str]:
        imdb_ids = set()
        try:
            movies = self.plex.library.section(self.library_title).all()
            for movie in movies:
                if hasattr(movie, 'guids'):
                    for guid in movie.guids:
                        if guid.id.startswith('imdb://'):
                            imdb_ids.add(guid.id.replace('imdb://', ''))
                            break
        except Exception as e:
            print(f"{YELLOW}Error retrieving IMDb IDs from library: {e}{RESET}")
        return imdb_ids

    def _is_movie_in_library(self, title: str, year: Optional[int], imdb_id: Optional[str] = None) -> bool:
        if (title.lower(), year) in self.library_movies:
            return True
        if imdb_id and imdb_id in self.library_imdb_ids:
            return True
    
        return False

    def _get_movie_language(self, movie) -> str:
        try:
            if hasattr(movie, 'media') and movie.media:
                media = movie.media[0]
                if hasattr(media, 'parts') and media.parts:
                    part = media.parts[0]
                    languages = set()
                    for stream in part.audioStreams():
                        lang_code = (
                            getattr(stream, 'languageTag', None) or
                            getattr(stream, 'languageCode', None) or
                            getattr(stream, 'language', None)
                        )
                        if lang_code:
                            full_name = get_full_language_name(lang_code)
                            if full_name != lang_code:
                                languages.add(full_name)
                    if languages:
                        return list(languages)[0]
        except Exception as e:
            print(f"{YELLOW}Error getting language for {movie.title}: {e}{RESET}")
        return 'N/A'

    def _extract_genres(self, movie) -> List[str]:
        try:
            if hasattr(movie, 'genres') and movie.genres:
                return [g.tag.lower() for g in movie.genres]
        except Exception as e:
            print(f"{YELLOW}Error extracting genres for {movie.title}: {e}{RESET}")
        return []

    def get_movie_details(self, movie) -> Dict:
        try:
            movie.reload()
            
            # Get IMDb ID and TMDB keywords
            imdb_id = None
            tmdb_keywords = []
            
            if hasattr(movie, 'guids'):
                for guid in movie.guids:
                    if 'imdb://' in guid.id:
                        imdb_id = guid.id.replace('imdb://', '')
                        break
                        
            # Get TMDB keywords if enabled
            if self.use_tmdb_keywords and self.tmdb_api_key:
                tmdb_id = self._get_plex_movie_tmdb_id(movie)
                if tmdb_id:
                    tmdb_keywords = list(self._get_tmdb_keywords_for_id(tmdb_id))
            
            # Get cast and director
            cast_list = []
            director_name = None
            if hasattr(movie, 'roles'):
                cast_list = [r.tag for r in movie.roles[:3]]
            if hasattr(movie, 'directors') and movie.directors:
                director_name = movie.directors[0].tag
                
            # Get all audio languages
            language = self._get_movie_language(movie)
            
            # Get ratings
            ratings = {}
            if hasattr(movie, 'audienceRating'):
                ratings['Rating'] = round(float(movie.audienceRating), 1) if movie.audienceRating else 0
                
            return {
                'title': movie.title,
                'year': getattr(movie, 'year', None),
                'genres': [g.tag.lower() for g in movie.genres] if hasattr(movie, 'genres') else [],
                'summary': getattr(movie, 'summary', ''),
                'imdb_id': imdb_id,
                'tmdb_keywords': tmdb_keywords,
                'cast': cast_list,
                'director': director_name,
                'language': language,
                'ratings': ratings
            }
                
        except Exception as e:
            print(f"{YELLOW}Error getting movie details for {movie.title}: {e}{RESET}")
            return {}

    def _process_movie_counters(self, movie, counters):
        movie_details = self.get_movie_details(movie)
        
        try:
            rating = float(getattr(movie, 'userRating', 0))
        except (TypeError, ValueError):
            try:
                rating = float(getattr(movie, 'audienceRating', 5.0))
            except (TypeError, ValueError):
                rating = 5.0
    
        # Clamp rating to 0-10 scale and convert to integer
        rating = max(0, min(10, int(round(rating))))
        multiplier = RATING_MULTIPLIERS.get(rating, 1.0)
    
        # Process genres with multiplier
        for genre in movie_details.get('genres', []):
            counters['genres'][genre] += multiplier
            
        # Process director
        if director := movie_details.get('director'):
            counters['directors'][director] += multiplier
            
        # Process actors (top 3 only)
        for actor in movie_details.get('cast', [])[:3]:
            counters['actors'][actor] += multiplier
            
        # Process language
        if language := movie_details.get('language'):
            counters['languages'][language] += multiplier
            
        # Process TMDB keywords
        for keyword in movie_details.get('tmdb_keywords', []):
            counters['tmdb_keywords'][keyword] += multiplier

    def _normalize_counter(self, counter: Counter) -> Dict[str, float]:
        if not counter:
            return {}
        
        max_value = max(counter.values()) if counter else 1
        return {k: v/max_value for k, v in counter.items()}

    def _normalize_all_counters(self, counters):
        return {
            'genres': self._normalize_counter(counters['genres']),
            'directors': self._normalize_counter(counters['directors']),
            'actors': self._normalize_counter(counters['actors']),
            'languages': self._normalize_counter(counters['languages']),
            'tmdb_keywords': self._normalize_counter(counters['tmdb_keywords'])
        }

    def get_unwatched_library_movies(self) -> List[Dict]:
        print(f"\n{YELLOW}Fetching unwatched movies from Plex library...{RESET}")
        
        user_plex = self._get_user_specific_connection()
        movies_section = user_plex.library.section(self.library_title)
        
        current_all = movies_section.all()
        current_all_count = len(current_all)
        current_unwatched = movies_section.search(unwatched=True)
        current_unwatched_count = len(current_unwatched)
    
        if (current_all_count == self.cached_library_movie_count and
            current_unwatched_count == self.cached_unwatched_count):
            print(f"Unwatched count unchanged. Using cached data for {self._get_current_users()}.")
            return self.cached_unwatched_movies
    
        unwatched_details = []
        for i, movie in enumerate(current_unwatched, start=1):
            self._show_progress("Scanning unwatched", i, current_unwatched_count)
            info = self.get_movie_details(movie)
            
            unwatched_details.append(info)
        print()
    
        print(f"Found {len(unwatched_details)} unwatched movies matching your criteria.\n")
    
        self.cached_library_movie_count = current_all_count
        self.cached_unwatched_count = current_unwatched_count
        self.cached_unwatched_movies = unwatched_details
        self._save_unwatched_cache()
        return unwatched_details
    # ------------------------------------------------------------------------
    # TMDB HELPER METHODS
    # ------------------------------------------------------------------------
    def _get_plex_movie_tmdb_id(self, plex_movie) -> Optional[int]:
        if not self.use_tmdb_keywords or not self.tmdb_api_key:
            return None

        if plex_movie.ratingKey in self.plex_tmdb_cache:
            return self.plex_tmdb_cache[plex_movie.ratingKey]

        tmdb_id = None
        if hasattr(plex_movie, 'guids'):
            for guid in plex_movie.guids:
                if 'themoviedb://' in guid.id:
                    try:
                        tmdb_id = int(guid.id.split('themoviedb://')[1])
                        break
                    except:
                        pass

        if not tmdb_id:
            title = plex_movie.title
            year = getattr(plex_movie, 'year', None)
            if not title:
                self.plex_tmdb_cache[plex_movie.ratingKey] = None
                return None
            try:
                base_url = "https://api.themoviedb.org/3/search/movie"
                params = {'api_key': self.tmdb_api_key, 'query': title}
                if year:
                    params['year'] = year

                resp = requests.get(base_url, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    results = data.get('results', [])
                    if results:
                        if year:
                            for r in results:
                                if r.get('release_date', '').startswith(str(year)):
                                    tmdb_id = r['id']
                                    break
                        if not tmdb_id:
                            tmdb_id = results[0]['id']
            except Exception as e:
                print(f"{YELLOW}Could not fetch TMDB ID for '{title}': {e}{RESET}")

        self.plex_tmdb_cache[plex_movie.ratingKey] = tmdb_id
        return tmdb_id

    def _get_plex_movie_imdb_id(self, plex_movie) -> Optional[str]:
        if not plex_movie.guids:
            return None
        for guid in plex_movie.guids:
            if guid.id.startswith('imdb://'):
                return guid.id.split('imdb://')[1]
        
        tmdb_id = self._get_plex_movie_tmdb_id(plex_movie)
        if not tmdb_id:
            return None
        try:
            url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
            params = {'api_key': self.tmdb_api_key}
            resp = requests.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get('imdb_id')
            else:
                print(f"{YELLOW}Failed to fetch IMDb ID from TMDB for movie '{plex_movie.title}'. Status Code: {resp.status_code}{RESET}")
        except Exception as e:
            print(f"{YELLOW}Error fetching IMDb ID for TMDB ID {tmdb_id}: {e}{RESET}")
        return None

    def _get_tmdb_keywords_for_id(self, tmdb_id: int) -> Set[str]:
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

    def _show_progress(self, prefix: str, current: int, total: int):
        pct = int((current / total) * 100)
        msg = f"\r{prefix}: {current}/{total} ({pct}%)"
        sys.stdout.write(msg)
        sys.stdout.flush()
        if current == total:
            sys.stdout.write("\n")

    def _get_imdb_id_from_tmdb(self, tmdb_id: int) -> Optional[str]:
        try:
            url = f"https://api.themoviedb.org/3/movie/{tmdb_id}"
            params = {'api_key': self.tmdb_api_key}
            response = requests.get(url, params=params)
            if response.status_code == 200:
                return response.json().get('imdb_id')
        except Exception as e:
            print(f"{YELLOW}TMDB API Error: {e}{RESET}")
        return None
    # ------------------------------------------------------------------------
    # TRAKT SYNC
    # ------------------------------------------------------------------------
    def _get_tautulli_watched_for_sync(self) -> List[dict]:
        params = {
            'apikey': self.config['tautulli']['api_key'],
            'cmd': 'get_history',
            'media_type': 'movie',
            'length': 10000
        }
        
        # Add user filter if specific users are configured
        if not any(u.lower() == 'all' for u in self.users['tautulli_users']):
            params['user'] = ','.join(self.users['tautulli_users'])
        
        try:
            print("DEBUG: Fetching Tautulli watch history")
            response = requests.get(
                f"{self.config['tautulli']['url']}/api/v2",
                params=params
            )
            response.raise_for_status()
            
            json_data = response.json()
            print(f"DEBUG: Raw Tautulli response: {json_data.keys()}")
            
            history_data = json_data.get('response', {}).get('data', [])
            if isinstance(history_data, dict):
                history_items = history_data.get('data', [])
            else:
                history_items = history_data
                
            # Create dictionary to track latest watch time for each movie
            movie_watches = {}
            for item in history_items:
                if not isinstance(item, dict):
                    continue
                    
                rating_key = str(item.get('rating_key'))
                if not rating_key:
                    continue
                    
                # Convert timestamp to ISO format
                watched_at = datetime.fromtimestamp(
                    int(item.get('started', 0)), 
                    tz=timezone.utc
                ).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                
                # Update if this is the most recent watch
                if rating_key not in movie_watches or watched_at > movie_watches[rating_key]['last_watched']:
                    movie_watches[rating_key] = {
                        'rating_key': rating_key,
                        'last_watched': watched_at
                    }
            
            watched_items = list(movie_watches.values())
            print(f"DEBUG: Found {len(watched_items)} unique watched movies")
            return watched_items
                
        except Exception as e:
            print(f"{RED}Error fetching Tautulli history: {e}{RESET}")
            import traceback
            print(traceback.format_exc())
            return []

    def _get_plex_managed_users_watched_for_sync(self) -> List[dict]:
        watched_items = []
        account = MyPlexAccount(token=self.config['plex']['token'])
        
        users_to_process = self.users['managed_users'] or [self.users['admin_user']]
        
        for username in users_to_process:
            try:
                user = account.user(username)
                user_plex = self.plex.switchUser(user)
                movies = user_plex.library.section(self.library_title).search(unwatched=False)
                
                for movie in movies:
                    if movie.lastViewedAt:
                        watched_items.append({
                            'rating_key': movie.ratingKey,
                            'last_watched': movie.lastViewedAt.astimezone(timezone.utc).isoformat()
                        })
                    else:
                        print(f"{YELLOW}Missing watch date for {movie.title} ({movie.ratingKey}){RESET}")
                        
            except Exception as e:
                print(f"{RED}Error processing user {username}: {e}{RESET}")
        
        return watched_items

    def _clear_trakt_watch_history(self):
        print(f"{YELLOW}Clearing Trakt watch history...{RESET}")
        trakt_ids = []
        page = 1
        per_page = 100  # Max allowed by Trakt API
        
        try:
            while True:
                response = requests.get(
                    "https://api.trakt.tv/sync/history/movies",
                    headers=self.trakt_headers,
                    params={'page': page, 'limit': per_page}
                )
                if response.status_code != 200:
                    print(f"{RED}Error fetching history: {response.status_code}{RESET}")
                    break
                
                data = response.json()
                if not data:
                    break
                
                for item in data:
                    if 'movie' in item and 'ids' in item['movie']:
                        trakt_id = item['movie']['ids'].get('trakt')
                        if trakt_id:
                            trakt_ids.append(trakt_id)
                
                page += 1
    
            if trakt_ids:
                remove_payload = {
                    "movies": [
                        {"ids": {"trakt": tid}} for tid in trakt_ids
                    ]
                }
                
                remove_response = requests.post(
                    "https://api.trakt.tv/sync/history/remove",
                    headers=self.trakt_headers,
                    json=remove_payload
                )
                
                if remove_response.status_code == 200:
                    deleted = remove_response.json().get('deleted', {}).get('movies', 0)
                    print(f"{GREEN}Removed {deleted} movies from Trakt history.{RESET}")
                else:
                    print(f"{RED}Failed to remove history: {remove_response.status_code}{RESET}")
                    print(f"Response: {remove_response.text}")
            else:
                print(f"{YELLOW}No Trakt movie history to clear.{RESET}")
                
        except Exception as e:
            print(f"{RED}Error clearing Trakt history: {e}{RESET}")

    def _sync_plex_watched_to_trakt(self):
        if not self.sync_watch_history:
            return
        
        print(f"{YELLOW}Checking Trakt sync status...{RESET}")
        
        # Debug cache paths
        print(f"DEBUG: Using cache path: {self.trakt_cache_path}")
        print(f"DEBUG: Cache exists: {os.path.exists(self.trakt_cache_path)}")
        
        # Get watched movies based on configuration
        if self.users['tautulli_users']:
            print("DEBUG: Getting Tautulli watch history")
            watched_items = self._get_tautulli_watched_for_sync()
        else:
            print("DEBUG: Getting Plex managed users watch history")
            watched_items = self._get_plex_managed_users_watched_for_sync()
        
        print(f"DEBUG: Found {len(watched_items)} watched items")
        
        synced_movie_ids = set()
        if (not self.config['trakt'].get('clear_watch_history', False) and 
            os.path.exists(self.trakt_cache_path)):
            try:
                with open(self.trakt_cache_path, 'r') as f:
                    cache_data = json.load(f)
                    synced_movie_ids = set(cache_data.get('synced_movie_ids', []))
            except Exception as e:
                print(f"{YELLOW}Error loading Trakt cache: {e}{RESET}")
        
        movies_to_sync = []
        movies_section = self.plex.library.section(self.library_title)
        
        for item in watched_items:
            try:
                rating_key = str(item.get('rating_key'))
                if not rating_key:
                    continue
                    
                if rating_key in synced_movie_ids:
                    print(f"DEBUG: Skipping already synced movie: {rating_key}")
                    continue
                    
                movie = movies_section.fetchItem(int(rating_key))
                movies_to_sync.append({
                    'movie': movie,
                    'watched_at': item['last_watched']
                })
                print(f"DEBUG: Adding to sync: {movie.title} ({rating_key})")
                    
            except Exception as e:
                print(f"{YELLOW}Error processing {rating_key}: {str(e)}{RESET}")
                continue
        
        if not movies_to_sync:
            print(f"{GREEN}No new movies to sync to Trakt.{RESET}")
            return
    
        print(f"Found {len(movies_to_sync)} new watched movies to sync...")
        
        chunk_size = 100
        for i in range(0, len(movies_to_sync), chunk_size):
            chunk = movies_to_sync[i:i + chunk_size]
            chunk_data = {"movies": []}
            
            for item in chunk:
                movie = item['movie']
                imdb_id = None
                if hasattr(movie, 'guids'):
                    for guid in movie.guids:
                        if 'imdb://' in guid.id:
                            imdb_id = guid.id.replace('imdb://', '')
                            break
                
                if imdb_id:
                    chunk_data["movies"].append({
                        "ids": {
                            "imdb": imdb_id
                        },
                        "watched_at": item['watched_at']
                    })
            
            if chunk_data["movies"]:
                try:
                    response = requests.post(
                        "https://api.trakt.tv/sync/history",
                        headers=self.trakt_headers,
                        json=chunk_data
                    )
                    response.raise_for_status()
                    print(f"Successfully synced chunk of {len(chunk)} movies")
                    
                    for item in chunk:
                        synced_movie_ids.add(str(item['movie'].ratingKey))
                        
                    with open(self.trakt_cache_path, 'w', encoding='utf-8') as f:
                        json.dump({
                            'synced_movie_ids': list(synced_movie_ids),
                            'last_sync': datetime.now().isoformat()
                        }, f, indent=4)
                        
                except Exception as e:
                    print(f"{RED}Error syncing chunk to Trakt: {e}{RESET}")
                    continue
    
        print(f"Trakt sync complete.")

    # ------------------------------------------------------------------------
    # CALCULATE SCORES
    # ------------------------------------------------------------------------
    def calculate_movie_score(self, movie) -> float:
        user_genres = Counter(self.watched_data['genres'])
        user_dirs = Counter(self.watched_data['directors'])
        user_acts = Counter(self.watched_data['actors'])
        user_kws  = Counter(self.watched_data['tmdb_keywords'])
        user_langs = Counter(self.watched_data.get('languages', {}))  # Use .get to avoid KeyError

        weights = self.weights

        max_genre_count = max(user_genres.values(), default=1)
        max_director_count = max(user_dirs.values(), default=1)
        max_actor_count = max(user_acts.values(), default=1)
        max_keyword_count = max(user_kws.values(), default=1)
        max_language_count = max(user_langs.values(), default=1)

        score = 0.0
        if hasattr(movie, 'genres') and movie.genres:
            movie_genres = {g.tag.lower() for g in movie.genres}
            genre_scores = [user_genres.get(g, 0) for g in movie_genres]
            
            if genre_scores:
                max_genre = max(genre_scores)
                
                genre_contribution = (max_genre ** 2)
                
                base_genre_weight = weights.get('genre_weight', 0.25)
                adjusted_weight = base_genre_weight * (1 + (max_genre / 10))
                
                score += genre_contribution * adjusted_weight

        if hasattr(movie, 'directors') and movie.directors:
            dscore = 0.0
            matched_dirs = 0
            for d in movie.directors:
                if d.tag in user_dirs:
                    matched_dirs += 1
                    dscore += (user_dirs[d.tag] / max_director_count)
            if matched_dirs > 0:
                dscore /= matched_dirs
            score += dscore * weights.get('director_weight', 0.20)

        if hasattr(movie, 'roles') and movie.roles:
            ascore = 0.0
            matched_actors = 0
            for a in movie.roles:
                if a.tag in user_acts:
                    matched_actors += 1
                    ascore += (user_acts[a.tag] / max_actor_count)
            if matched_actors > 3:
                ascore *= (3 / matched_actors)
            if matched_actors > 0:
                ascore /= matched_actors
            score += ascore * weights.get('actor_weight', 0.20)

        if hasattr(movie, 'media') and self.show_language:
            try:
                media = movie.media[0]
                part = media.parts[0]
                audio_streams = part.audioStreams()
                if audio_streams:
                    primary_audio = audio_streams[0]
                    lang_code = (
                        getattr(primary_audio, 'languageTag', None) or
                        getattr(primary_audio, 'languageCode', None) or
                        getattr(primary_audio, 'language', None)
                    )
                    if lang_code:
                        language = get_full_language_name(lang_code).lower()
                        lcount = user_langs.get(language, 0)
                        lscore = (lcount / max_language_count) if max_language_count else 0
                        score += lscore * weights.get('language_weight', 0.10)
            except:
                pass

        if self.use_tmdb_keywords and self.tmdb_api_key:
            tmdb_id = self._get_plex_movie_tmdb_id(movie)
            if tmdb_id:
                keywords = self._get_tmdb_keywords_for_id(tmdb_id)
                kwscore = 0.0
                matched_kw = 0
                for kw in keywords:
                    count = user_kws.get(kw, 0)
                    if count > 0:
                        matched_kw += 1
                        kwscore += (count / max_keyword_count)
                if matched_kw > 0:
                    kwscore /= matched_kw
                score += kwscore * weights.get('keyword_weight', 0.25)

        return score

    # ------------------------------------------------------------------------
    # GET RECOMMENDATIONS
    # ------------------------------------------------------------------------
    def get_recommendations(self) -> Dict[str, List[Dict]]:
        # Handle clear history first (independent of sync_watch_history)
        if self.config['trakt'].get('clear_watch_history', False):
            self._clear_trakt_watch_history()
            # Clear the sync cache after history removal
            if os.path.exists(self.trakt_cache_path):
                try:
                    os.remove(self.trakt_cache_path)
                    print(f"{GREEN}Cleared Trakt sync cache{RESET}")
                except Exception as e:
                    print(f"{RED}Error clearing cache: {e}{RESET}")
    
        # Then handle sync if enabled
        if self.sync_watch_history:
            self._sync_plex_watched_to_trakt()
            self._save_cache()
    
        plex_recs = self.get_unwatched_library_movies()
        if plex_recs:
            excluded_recs = [m for m in plex_recs if any(g in self.exclude_genres for g in m['genres'])]
            included_recs = [m for m in plex_recs if not any(g in self.exclude_genres for g in m['genres'])]
    
            print(f"Excluded {len(excluded_recs)} movies based on excluded genres.")
    
            if not included_recs:
                print(f"{YELLOW}No unwatched movies left after applying genre exclusions.{RESET}")
                plex_recs = []
            else:
                plex_recs = included_recs
                plex_recs.sort(
                    key=lambda x: (
                        x.get('ratings', {}).get('rating', 0),
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

    def get_trakt_recommendations(self) -> List[Dict]:
        print(f"{YELLOW}Fetching recommendations from Trakt...{RESET}")
        try:
            url = "https://api.trakt.tv/recommendations/movies"
            collected_recs = []
            page = 1
            per_page = 100  # Trakt's maximum allowed per page

            while len(collected_recs) < self.limit_trakt_results:
                response = requests.get(
                    url,
                    headers=self.trakt_headers,
                    params={
                        'limit': per_page,
                        'page': page,
                        'extended': 'full'
                    }
                )

                if response.status_code == 200:
                    movies = response.json()
                    if not movies:
                        break

                    for m in movies:
                        if len(collected_recs) >= self.limit_trakt_results:
                            break

                        base_rating = float(m.get('rating', 0.0))
                        m['_randomized_rating'] = base_rating + random.uniform(0, 0.5)

                    movies.sort(key=lambda x: x['_randomized_rating'], reverse=True)

                    for movie in movies:
                        if len(collected_recs) >= self.limit_trakt_results:
                            break

                        imdb_id = movie.get('ids', {}).get('imdb')
                        if self._is_movie_in_library(movie['title'], movie.get('year'), imdb_id=imdb_id):
                            continue

                        ratings = {
                            'rating': round(float(movie.get('rating', 0)), 1),
                            'votes': movie.get('votes', 0)
                        }
                        md = {
                            'title': movie['title'],
                            'year': movie['year'],
                            'ratings': ratings,
                            'summary': movie.get('overview', ''),
                            'genres': [g.lower() for g in movie.get('genres', [])],
                            'cast': [],
                            'director': "N/A",
                            'language': "N/A",
                            'imdb_id': movie['ids'].get('imdb') if 'ids' in movie else None
                        }

                        if any(g in self.exclude_genres for g in md['genres']):
                            continue

                        tmdb_id = None
                        if 'ids' in movie and isinstance(movie['ids'], dict):
                            tmdb_id = movie['ids'].get('tmdb')

                        if tmdb_id and self.tmdb_api_key:
                            if self.show_language:
                                try:
                                    resp_lang = requests.get(
                                        f"https://api.themoviedb.org/3/movie/{tmdb_id}",
                                        params={'api_key': self.tmdb_api_key}
                                    )
                                    resp_lang.raise_for_status()
                                    d = resp_lang.json()
                                    if 'original_language' in d:
                                        md['language'] = get_full_language_name(d['original_language'])
                                except:
                                    pass

                            if self.show_cast or self.show_director:
                                try:
                                    resp_credits = requests.get(
                                        f"https://api.themoviedb.org/3/movie/{tmdb_id}/credits",
                                        params={'api_key': self.tmdb_api_key}
                                    )
                                    resp_credits.raise_for_status()
                                    c_data = resp_credits.json()

                                    if self.show_cast and 'cast' in c_data:
                                        c_sorted = c_data['cast'][:3]
                                        md['cast'] = [c['name'] for c in c_sorted]

                                    if self.show_director and 'crew' in c_data:
                                        directors = [p for p in c_data['crew'] if p.get('job') == 'Director']
                                        if directors:
                                            md['director'] = directors[0]['name']
                                except:
                                    pass

                        collected_recs.append(md)

                    if len(movies) < per_page:
                        break

                    page += 1
                else:
                    print(f"{RED}Error getting Trakt recommendations: {response.status_code}{RESET}")
                    if response.status_code == 401:
                        print(f"{YELLOW}Try re-authenticating with Trakt{RESET}")
                        self._authenticate_trakt()
                    break

            collected_recs.sort(key=lambda x: x.get('ratings', {}).get('rating', 0), reverse=True)
            random.shuffle(collected_recs)
            final_recs = collected_recs[:self.limit_trakt_results]
            print(f"Collected {len(final_recs)} Trakt recommendations after exclusions.")
            return final_recs

        except Exception as e:
            print(f"{RED}Error getting Trakt recommendations: {e}{RESET}")
            return []

    def _user_select_recommendations(self, recommended_movies: List[Dict], operation_label: str) -> List[Dict]:
        prompt = (
            f"\nWhich recommendations would you like to {operation_label}?\n"
            "Enter 'all' or 'y' to select ALL,\n"
            "Enter 'none' or 'n' to skip them,\n"
            "Or enter a comma-separated list of numbers (e.g. 1,3,5). "
            "\nYour choice: "
        )
        choice = input(prompt).strip().lower()

        if choice in ("n", "no", "none", ""):
            print(f"{YELLOW}Skipping {operation_label} as per user choice.{RESET}")
            return []
        if choice in ("y", "yes", "all"):
            return recommended_movies

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

        subset = []
        for c in chosen:
            subset.append(recommended_movies[c - 1])
        return subset

    def manage_plex_labels(self, recommended_movies: List[Dict]) -> None:
        if not recommended_movies:
            print(f"{YELLOW}No movies to add labels to.{RESET}")
            return
    
        if not self.config['plex'].get('add_label'):
            return
    
        if self.confirm_operations:
            selected_movies = self._user_select_recommendations(recommended_movies, "label in Plex")
            if not selected_movies:
                return
        else:
            selected_movies = recommended_movies
    
        try:
            movies_section = self.plex.library.section(self.library_title)
            label_name = self.config['plex'].get('label_name', 'Recommended')
    
            # Append usernames to label if configured
            if self.config['plex'].get('append_usernames', False):
                users = []
                if self.users['tautulli_users']:
                    users = self.users['tautulli_users']
                else:
                    users = self.users['managed_users']
                
                if users:
                    # Sanitize usernames and join with underscores
                    sanitized_users = [re.sub(r'\W+', '_', user.strip()) for user in users]
                    user_suffix = '_'.join(sanitized_users)
                    label_name = f"{label_name}_{user_suffix}"
    
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
    
            if self.config['plex'].get('remove_previous_recommendations', False):
                print(f"{YELLOW}Finding movies with existing label: {label_name}{RESET}")
                labeled_movies = set(movies_section.search(label=label_name))
                movies_to_unlabel = labeled_movies - set(movies_to_update)
                for movie in movies_to_unlabel:
                    current_labels = [label.tag for label in movie.labels]
                    if label_name in current_labels:
                        movie.removeLabel(label_name)
                        print(f"{YELLOW}Removed label from: {movie.title}{RESET}")
    
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

    def add_to_radarr(self, recommended_movies: List[Dict]) -> None:
        if not recommended_movies:
            print(f"{YELLOW}No movies to add to Radarr.{RESET}")
            return

        if not self.radarr_config.get('add_to_radarr'):
            return

        if self.confirm_operations:
            selected_movies = self._user_select_recommendations(recommended_movies, "add to Radarr")
            if not selected_movies:
                return
        else:
            selected_movies = recommended_movies

        try:
            if 'radarr' not in self.config:
                raise ValueError("Radarr configuration missing from config file")

            required_fields = ['url', 'api_key', 'root_folder', 'quality_profile']
            missing_fields = [f for f in required_fields if f not in self.radarr_config]
            if missing_fields:
                raise ValueError(f"Missing required Radarr config fields: {', '.join(missing_fields)}")

            radarr_url = self.radarr_config['url'].rstrip('/')
            if '/api/' not in radarr_url:
                radarr_url += '/api/v3'

            headers = {
                'X-Api-Key': self.radarr_config['api_key'],
                'Content-Type': 'application/json'
            }
            trakt_headers = self.trakt_headers

            try:
                test_response = requests.get(f"{radarr_url}/system/status", headers=headers)
                test_response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise ValueError(f"Failed to connect to Radarr: {str(e)}")

            tag_id = None
            if self.radarr_config.get('radarr_tag'):
                tags_response = requests.get(f"{radarr_url}/tag", headers=headers)
                tags_response.raise_for_status()
                tags = tags_response.json()
                tag = next((t for t in tags if t['label'].lower() == self.radarr_config['radarr_tag'].lower()), None)
                if tag:
                    tag_id = tag['id']
                else:
                    tag_response = requests.post(
                        f"{radarr_url}/tag",
                        headers=headers,
                        json={'label': self.radarr_config['radarr_tag']}
                    )
                    tag_response.raise_for_status()
                    tag_id = tag_response.json()['id']
                    print(f"{GREEN}Created new Radarr tag: {self.radarr_config['radarr_tag']} (ID: {tag_id}){RESET}")

            profiles_response = requests.get(f"{radarr_url}/qualityprofile", headers=headers)
            profiles_response.raise_for_status()
            quality_profiles = profiles_response.json()
            desired_profile = next(
                (p for p in quality_profiles
                 if p['name'].lower() == self.radarr_config['quality_profile'].lower()),
                None
            )
            if not desired_profile:
                available = [p['name'] for p in quality_profiles]
                raise ValueError(
                    f"Quality profile '{self.radarr_config['quality_profile']}' not found. "
                    f"Available: {', '.join(available)}"
                )
            quality_profile_id = desired_profile['id']

            existing_response = requests.get(f"{radarr_url}/movie", headers=headers)
            existing_response.raise_for_status()
            existing_movies = existing_response.json()
            existing_tmdb_ids = {m['tmdbId'] for m in existing_movies}

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

                    trakt_movie = next(
                        (r for r in trakt_results
                         if r['movie']['title'].lower() == movie['title'].lower()
                         and r['movie'].get('year') == movie.get('year')),
                        trakt_results[0]
                    )
                    tmdb_id = trakt_movie['movie']['ids'].get('tmdb')
                    if not tmdb_id:
                        print(f"{YELLOW}No TMDB ID found for {movie['title']}{RESET}")
                        continue

                    if tmdb_id in existing_tmdb_ids:
                        print(f"{YELLOW}Already in Radarr: {movie['title']}{RESET}")
                        continue

                    root_folder = self._map_path(self.radarr_config['root_folder'].rstrip('/\\'))
                    should_monitor = self.radarr_config.get('monitor', False)

                    movie_data = {
                        'tmdbId': tmdb_id,
                        'monitored': should_monitor,
                        'qualityProfileId': quality_profile_id,
                        'minimumAvailability': 'released',
                        'addOptions': {'searchForMovie': should_monitor},
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
def format_movie_output(movie: Dict,
                       show_summary: bool = False,
                       index: Optional[int] = None,
                       show_cast: bool = False,
                       show_director: bool = False,
                       show_language: bool = False,
                       show_imdb_link: bool = False,
                       show_rating: bool = False) -> str:
    bullet = f"{index}. " if index is not None else "- "
    output = f"{bullet}{CYAN}{movie['title']}{RESET} ({movie.get('year', 'N/A')})"
    
    if movie.get('genres'):
        output += f"\n  {YELLOW}Genres:{RESET} {', '.join(movie['genres'])}"

    if show_summary and movie.get('summary'):
        output += f"\n  {YELLOW}Summary:{RESET} {movie['summary']}"

    if show_cast and 'cast' in movie and movie['cast']:
        cast_str = ', '.join(movie['cast'])
        output += f"\n  {YELLOW}Cast:{RESET} {cast_str}"

    if show_director and 'director' in movie and movie['director'] != "N/A":
        output += f"\n  {YELLOW}Director:{RESET} {movie['director']}"

    if show_language and 'language' in movie and movie['language'] != "N/A":
        output += f"\n  {YELLOW}Language:{RESET} {movie['language']}"

    if show_rating and 'ratings' in movie:
        rating = movie['ratings'].get('Rating') or movie['ratings'].get('rating')
        if rating:
            votes_str = ""
            if 'votes' in movie['ratings']:
                votes_str = f" ({movie['ratings']['votes']} votes)"
            output += f"\n  {YELLOW}Rating:{RESET} {rating}/10{votes_str}"

    if show_imdb_link and 'imdb_id' in movie and movie['imdb_id']:
        imdb_link = f"https://www.imdb.com/title/{movie['imdb_id']}/"
        output += f"\n  {YELLOW}IMDb Link:{RESET} {imdb_link}"

    return output

# ------------------------------------------------------------------------
# LOGGING / MAIN
# ------------------------------------------------------------------------
ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*m')

class TeeLogger:
    """
    A simple 'tee' class that writes to both console and a file,
    stripping ANSI color codes for the file.
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
    if keep_logs <= 0:
        return

    all_files = sorted(
        (f for f in os.listdir(log_dir) if f.endswith('.log')),
        key=lambda x: os.path.getmtime(os.path.join(log_dir, x))
    )
    if len(all_files) > keep_logs:
        to_remove = all_files[:len(all_files) - keep_logs]
        for f in to_remove:
            try:
                os.remove(os.path.join(log_dir, f))
            except Exception as e:
                print(f"{YELLOW}Failed to remove old log {f}: {e}{RESET}")

def main():
    start_time = datetime.now()
    print(f"{CYAN}Movie Recommendations for Plex{RESET}")
    print("-" * 50)
    check_version()
    print("-" * 50)
    
    config_path = os.path.join(os.path.dirname(__file__), 'config.yml')
    
    try:
        with open(config_path, 'r') as f:
            base_config = yaml.safe_load(f)
    except Exception as e:
        print(f"{RED}Could not load config.yml: {e}{RESET}")
        sys.exit(1)

    general = base_config.get('general', {})
    keep_logs = general.get('keep_logs', 0)

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

    try:
        recommender = PlexMovieRecommender(config_path)
        recommendations = recommender.get_recommendations()
        
        print(f"\n{GREEN}=== Recommended Unwatched Movies in Your Library ==={RESET}")
        plex_recs = recommendations.get('plex_recommendations', [])
        if plex_recs:
            for i, movie in enumerate(plex_recs, start=1):
                print(format_movie_output(
                    movie,
                    show_summary=recommender.show_summary,
                    index=i,
                    show_cast=recommender.show_cast,
                    show_director=recommender.show_director,
                    show_language=recommender.show_language,
                    show_rating=recommender.show_rating,
                    show_imdb_link=recommender.show_imdb_link
                ))
                print()
            recommender.manage_plex_labels(plex_recs)
        else:
            print(f"{YELLOW}No recommendations found in your Plex library matching your criteria.{RESET}")
     
        if not recommender.plex_only:
            print(f"\n{GREEN}=== Recommended Movies to Add to Your Library ==={RESET}")
            trakt_recs = recommendations.get('trakt_recommendations', [])
            if trakt_recs:
                for i, movie in enumerate(trakt_recs, start=1):
                    print(format_movie_output(
                        movie,
                        show_summary=recommender.show_summary,
                        index=i,
                        show_cast=recommender.show_cast,
                        show_director=recommender.show_director,
                        show_language=recommender.show_language,
                        show_rating=recommender.show_rating,
                        show_imdb_link=recommender.show_imdb_link
                    ))
                    print()
                recommender.add_to_radarr(trakt_recs)
            else:
                print(f"{YELLOW}No Trakt recommendations found matching your criteria.{RESET}")

        recommender._save_cache()

    except Exception as e:
        print(f"\n{RED}An error occurred: {e}{RESET}")
        import traceback
        print(traceback.format_exc())

    finally:
        print(f"\n{GREEN}Process completed!{RESET}")
        runtime = datetime.now() - start_time
        hours = runtime.seconds // 3600
        minutes = (runtime.seconds % 3600) // 60
        seconds = runtime.seconds % 60
        print(f"Total runtime: {hours:02d}:{minutes:02d}:{seconds:02d}")

    if keep_logs > 0 and sys.stdout is not original_stdout:
        try:
            sys.stdout.logfile.close()
            sys.stdout = original_stdout
        except Exception as e:
            print(f"{YELLOW}Error closing log file: {e}{RESET}")

if __name__ == "__main__":
    main()