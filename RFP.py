import os
import plexapi.server
from trakt import Trakt
import yaml
from datetime import datetime
import sys
import requests
from typing import Dict, List, Set, Optional, Tuple
from collections import Counter, defaultdict
import time
from statistics import mean
import webbrowser
from urllib.parse import urlencode, quote
import random

__version__ = "1.0"
REPO_URL = "https://github.com/netplexflix/Recommendations-for-Plex"
API_VERSION_URL = f"https://api.github.com/repos/netplexflix/Recommendations-for-Plex/releases/latest"

def check_version():
    """Check if there's a newer version available on GitHub"""
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

# ANSI Color Codes
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
CYAN = '\033[96m'
RESET = '\033[0m'

class PlexMovieRecommender:
    def __init__(self, config_path: str):
        print("Initializing recommender system...")
        self.config = self._load_config(config_path)
        print("Connecting to Plex server...")
        self.plex = self._init_plex()
        print("Connected to Plex successfully!")
        
        # Load general settings
        general_config = self.config.get('general', {})
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
        
        # Add OAuth token if we have it
        if 'access_token' in self.config.get('trakt', {}):
            self.trakt_headers['Authorization'] = f"Bearer {self.config['trakt']['access_token']}"
        else:
            self._authenticate_trakt()

        # Get watched movies data for recommendations
        self.watched_data = self._get_watched_movies_data()
        
        # Get set of all movies in Plex library
        self.library_movies = self._get_library_movies_set()

    def _map_path(self, path: str) -> str:
        """
        Map paths between different systems using the path_mappings configuration.
        
        Args:
            path (str): The original path to map
            
        Returns:
            str: The mapped path according to configuration
        """
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

    def _get_library_movies_set(self) -> Set[Tuple[str, Optional[int]]]:
        """Get a set of tuples (title, year) for all movies in the Plex library"""
        try:
            movies = self.plex.library.section('Movies')
            return {(movie.title.lower(), getattr(movie, 'year', None)) for movie in movies.all()}
        except Exception as e:
            print(f"{RED}Error getting library movies: {e}{RESET}")
            return set()

    def _is_movie_in_library(self, title: str, year: Optional[int]) -> bool:
        """Check if a movie is already in the Plex library"""
        return (title.lower(), year) in self.library_movies

    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from YAML file"""
        try:
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)
                print(f"Successfully loaded configuration from {config_path}")
                return config
        except Exception as e:
            print(f"{RED}Error loading config from {config_path}: {e}{RESET}")
            raise

    def _init_plex(self) -> plexapi.server.PlexServer:
        """Initialize Plex server connection"""
        try:
            return plexapi.server.PlexServer(
                self.config['plex']['url'],
                self.config['plex']['token']
            )
        except Exception as e:
            print(f"{RED}Error connecting to Plex server: {e}{RESET}")
            raise
    def _get_watched_movies_data(self) -> Dict:
        """Get data about watched movies for recommendation calculations"""
        try:
            movies = self.plex.library.section('Movies')
            watched_movies = movies.search(unwatched=False)
            
            genres = set()
            directors = set()
            actors = set()
            
            for movie in watched_movies:
                if hasattr(movie, 'genres'):
                    genres.update(g.tag.lower() for g in movie.genres)
                if hasattr(movie, 'directors'):
                    directors.update(d.tag for d in movie.directors)
                if hasattr(movie, 'roles'):  # roles contains actors
                    actors.update(a.tag for a in movie.roles)
            
            return {
                'genres': genres,
                'directors': directors,
                'actors': actors
            }
        except Exception as e:
            print(f"{RED}Error getting watched movies data: {e}{RESET}")
            return {'genres': set(), 'directors': set(), 'actors': set()}

    def calculate_movie_score(self, movie) -> float:
        """Calculate a weighted score for a movie based on multiple factors"""
        score = 0.0
        weights = {
            'genre_match': 0.5,    # Increased weight for genres
            'director_match': 0.3,  # Medium weight for directors
            'actor_match': 0.2      # Lower weight for actors
        }
        
        # Genre matching
        if self.watched_data['genres'] and hasattr(movie, 'genres'):
            movie_genres = {g.tag.lower() for g in movie.genres}
            genre_matches = len(movie_genres & self.watched_data['genres'])
            genre_score = genre_matches / len(movie_genres) if movie_genres else 0
            score += genre_score * weights['genre_match']
        
        # Director matching
        if hasattr(movie, 'directors') and self.watched_data['directors']:
            director_matches = len({d.tag for d in movie.directors} & self.watched_data['directors'])
            director_score = 1.0 if director_matches > 0 else 0
            score += director_score * weights['director_match']
        
        # Actor matching
        if hasattr(movie, 'roles') and self.watched_data['actors']:
            actor_matches = len({a.tag for a in movie.roles} & self.watched_data['actors'])
            actor_score = min(1.0, actor_matches / 3)  # Cap at 3 matching actors
            score += actor_score * weights['actor_match']
        
        return score

    def _authenticate_trakt(self):
        """Handle Trakt OAuth authentication"""
        try:
            # Step 1: Get device code
            response = requests.post(
                'https://api.trakt.tv/oauth/device/code',
                headers=self.trakt_headers,
                json={
                    'client_id': self.config['trakt']['client_id']
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                device_code = data['device_code']
                user_code = data['user_code']
                verification_url = data['verification_url']
                
                print(f"\n{GREEN}Please visit {verification_url} and enter code: {CYAN}{user_code}{RESET}")
                print("Waiting for authentication...")
                
                # Open browser for user
                webbrowser.open(verification_url)
                
                # Step 2: Poll for access token
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
                        # Save token to config
                        self.config['trakt']['access_token'] = token_data['access_token']
                        self.trakt_headers['Authorization'] = f"Bearer {token_data['access_token']}"
                        
                        # Save updated config
                        with open(os.path.join(os.path.dirname(__file__), 'config.yml'), 'w') as f:
                            yaml.dump(self.config, f)
                            
                        print(f"{GREEN}Successfully authenticated with Trakt!{RESET}")
                        return
                    
                    elif token_response.status_code != 400:  # 400 means token not ready
                        print(f"{RED}Error getting token: {token_response.status_code}{RESET}")
                        return
                
                print(f"{RED}Authentication timed out{RESET}")
            else:
                print(f"{RED}Error getting device code: {response.status_code}{RESET}")
                
        except Exception as e:
            print(f"{RED}Error during Trakt authentication: {e}{RESET}")
    def get_movie_details(self, movie) -> Dict:
        """Extract detailed information about a movie including ratings from Plex"""
        sys.stdout.write(f"\rProcessing movie: {movie.title:<50}")
        sys.stdout.flush()
        
        # Get ratings directly from Plex
        ratings = {}
        if hasattr(movie, 'rating'):  # IMDb rating
            ratings['imdb_rating'] = round(float(movie.rating), 1) if movie.rating else 0
        if hasattr(movie, 'audienceRating'):  # Rotten Tomatoes audience rating
            ratings['audience_rating'] = round(float(movie.audienceRating), 1) if movie.audienceRating else 0
        if hasattr(movie, 'ratingCount'):
            ratings['votes'] = movie.ratingCount
        
        # Calculate similarity score
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
        """Get all unwatched movies from Plex library"""
        try:
            print(f"\n{YELLOW}Fetching unwatched movies from Plex library...{RESET}")
            movies = self.plex.library.section('Movies')
            unwatched = []
            total_movies = len(movies.search(unwatched=True))
            processed = 0
            
            for movie in movies.search(unwatched=True):
                processed += 1
                sys.stdout.write(f"\rProcessing movie {processed}/{total_movies}: {CYAN}{movie.title:<50}{RESET}")
                sys.stdout.flush()        
                       
                movie_details = self.get_movie_details(movie)
                
                # Skip movies with excluded genres
                if any(genre in self.exclude_genres for genre in movie_details['genres']):
                    continue
                
                unwatched.append(movie_details)
            
            print(f"\n{GREEN}Processed {total_movies} movies, found {len(unwatched)} matching your criteria.{RESET}")
            return unwatched
            
        except Exception as e:
            print(f"\n{RED}Error getting unwatched movies: {e}{RESET}")
            return []

    def get_trakt_recommendations(self) -> List[Dict]:
        """Get personalized movie recommendations from Trakt"""
        print(f"\n{YELLOW}Fetching recommendations from Trakt...{RESET}")
        try:
            url = "https://api.trakt.tv/recommendations/movies"
            response = requests.get(
                url,
                headers=self.trakt_headers,
                params={
                    'limit': self.limit_trakt_results * 4,  # Get more to increase variety
                    'extended': 'full'
                }
            )
            
            if response.status_code == 200:
                recommendations = []
                movies = response.json()
                random.shuffle(movies)
                total_movies = len(movies)
                processed = 0
                
                for movie in movies:
                    processed += 1
                    sys.stdout.write(f"\rProcessing Trakt recommendation {processed}/{total_movies}: {CYAN}{movie['title']:<50}{RESET}")
                    sys.stdout.flush()
                    
                    # Skip if movie is already in library
                    if self._is_movie_in_library(movie['title'], movie.get('year')):
                        continue
                    
                    # Get ratings from the movie data
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
                    
                    # Check excluded genres
                    if any(genre.lower() in self.exclude_genres for genre in movie_details['genres']):
                        continue
                        
                    recommendations.append(movie_details)
                
                print(f"\n{GREEN}Processed {total_movies} Trakt recommendations, found {len(recommendations)} matching your criteria.{RESET}")
                return recommendations
            else:
                print(f"\n{RED}Error getting Trakt recommendations: {response.status_code}{RESET}")
                if response.status_code == 401:
                    print(f"{YELLOW}Try re-authenticating with Trakt{RESET}")
                    self._authenticate_trakt()
                return []
                
        except Exception as e:
            print(f"\n{RED}Error getting Trakt recommendations: {e}{RESET}")
            return []
    def get_recommendations(self) -> Dict[str, List[Dict]]:
        """Get both internal and external recommendations"""
        print(f"\n{YELLOW}Starting recommendation process...{RESET}")
        
        # Get unwatched library movies
        print(f"\n{YELLOW}Step 1: Processing your Plex library...{RESET}")
        plex_recommendations = self.get_unwatched_library_movies()
        
        if plex_recommendations:
            # Sort by both similarity score and rating
            print(f"{YELLOW}Sorting and selecting Plex recommendations...{RESET}")
            
            # First sort by IMDb rating to get quality content
            plex_recommendations.sort(
                key=lambda x: (
                    x.get('ratings', {}).get('imdb_rating', 0),
                    x.get('similarity_score', 0)
                ),
                reverse=True
            )
            
            # Take top 50% of rated movies to ensure quality
            top_count = max(int(len(plex_recommendations) * 0.5), self.limit_plex_results)
            top_movies = plex_recommendations[:top_count]
            
            # Then sort these by similarity score
            top_movies.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
            
            # Take top 30% of those based on similarity
            final_count = max(int(len(top_movies) * 0.3), self.limit_plex_results)
            final_pool = top_movies[:final_count]
            
            # Randomly select from final pool
            plex_recommendations = random.sample(
                final_pool, 
                min(self.limit_plex_results, len(final_pool))
            ) if final_pool else []
        
        # Get Trakt recommendations if not plex_only
        trakt_recommendations = []
        if not self.plex_only:
            print(f"\n{YELLOW}Step 2: Getting Trakt recommendations...{RESET}")
            trakt_recommendations = self.get_trakt_recommendations()
            
            # Sort by rating and randomly select
            if trakt_recommendations:
                # Sort by rating
                trakt_recommendations.sort(
                    key=lambda x: x.get('ratings', {}).get('imdb_rating', 0),
                    reverse=True
                )
                
                # Take top 50% to ensure quality
                top_trakt_count = max(int(len(trakt_recommendations) * 0.5), self.limit_trakt_results)
                top_trakt = trakt_recommendations[:top_trakt_count]
                
                # Randomly select from top rated
                trakt_recommendations = random.sample(
                    top_trakt, 
                    min(self.limit_trakt_results, len(top_trakt))
                )
    
        print(f"\n{GREEN}Recommendation process completed!{RESET}")
        return {
            'plex_recommendations': plex_recommendations,
            'trakt_recommendations': trakt_recommendations
        }

    def manage_plex_labels(self, recommended_movies: List[Dict]) -> None:
        """Manage Plex labels based on configuration settings"""
        if not recommended_movies:
            print(f"{YELLOW}No movies to add labels to.{RESET}")
            return
    
        if not self.config['plex'].get('add_label'):
            return
    
        try:
            movies_section = self.plex.library.section('Movies')
            label_name = self.config['plex'].get('label_name', 'Recommended')
            
            # Get movies to add first
            movies_to_update = []
            for rec in recommended_movies:
                # Find the movie in Plex
                plex_movie = next((m for m in movies_section.search(title=rec['title']) 
                                 if m.year == rec.get('year')), None)
                if plex_movie:
                    # Reload to get full details including labels
                    plex_movie.reload()
                    movies_to_update.append(plex_movie)
    
            if not movies_to_update:
                print(f"{YELLOW}No matching movies found in Plex to add labels to.{RESET}")
                return
    
            # Get all movies with the recommendation label if we need to remove old ones
            if self.config['plex'].get('remove_previous_recommendations', False):
                print(f"{YELLOW}Finding movies with existing label: {label_name}{RESET}")
                labeled_movies = set(movies_section.search(label=label_name))
                movies_to_unlabel = labeled_movies - set(movies_to_update)
                
                # Remove label from movies not in current recommendations
                for movie in movies_to_unlabel:
                    current_labels = [label.tag for label in movie.labels]
                    if label_name in current_labels:
                        movie.removeLabel(label_name)
                        print(f"{YELLOW}Removed label from: {movie.title}{RESET}")
    
            # Add label to new recommendations
            print(f"{YELLOW}Adding label to recommended movies...{RESET}")
            for movie in movies_to_update:
                current_labels = [label.tag for label in movie.labels]
                if label_name not in current_labels:
                    movie.addLabel(label_name)
                    print(f"{GREEN}Added label to: {movie.title}{RESET}")
                else:
                    print(f"{YELLOW}Label already exists on: {movie.title}{RESET}")
    
            print(f"{GREEN}Successfully updated labels for all recommended movies{RESET}")
    
        except Exception as e:
            print(f"{RED}Error managing Plex labels: {e}{RESET}")
            import traceback
            print(traceback.format_exc())

    def add_to_radarr(self, recommended_movies: List[Dict]) -> None:
        """Add recommended movies to Radarr"""
        if not recommended_movies:
            print(f"{YELLOW}No movies to add to Radarr.{RESET}")
            return
    
        if not self.config['radarr'].get('add_to_radarr'):
            return
    
        try:
            # Verify Radarr configuration
            if 'radarr' not in self.config:
                raise ValueError("Radarr configuration missing from config file")
            
            required_fields = ['url', 'api_key', 'root_folder', 'quality_profile']
            missing_fields = [field for field in required_fields if field not in self.config['radarr']]
            if missing_fields:
                raise ValueError(f"Missing required Radarr configuration fields: {', '.join(missing_fields)}")
    
            radarr_url = self.config['radarr']['url'].rstrip('/')
            if not radarr_url.endswith('/api/v3'):
                radarr_url = f"{radarr_url}/api/v3"
                
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
    
            # Get or create tag
            tag_id = None
            if self.config['radarr'].get('radarr_tag'):
                # Get existing tags
                tags_response = requests.get(f"{radarr_url}/tag", headers=headers)
                tags_response.raise_for_status()
                tags = tags_response.json()
                
                # Look for existing tag
                tag = next((t for t in tags if t['label'].lower() == self.config['radarr']['radarr_tag'].lower()), None)
                
                if tag:
                    tag_id = tag['id']
                else:
                    # Create new tag
                    tag_response = requests.post(
                        f"{radarr_url}/tag",
                        headers=headers,
                        json={'label': self.config['radarr']['radarr_tag']}
                    )
                    tag_response.raise_for_status()
                    tag_id = tag_response.json()['id']
                    print(f"{GREEN}Created new tag: {self.config['radarr']['radarr_tag']} (ID: {tag_id}){RESET}")
    
            # Get quality profiles from Radarr
            try:
                profiles_response = requests.get(f"{radarr_url}/qualityprofile", headers=headers)
                profiles_response.raise_for_status()
                quality_profiles = profiles_response.json()
                
                quality_profile = next(
                    (profile for profile in quality_profiles 
                     if profile['name'].lower() == self.config['radarr']['quality_profile'].lower()),
                    None
                )
                
                if not quality_profile:
                    available_profiles = [profile['name'] for profile in quality_profiles]
                    raise ValueError(
                        f"Quality profile '{self.config['radarr']['quality_profile']}' not found. "
                        f"Available profiles: {', '.join(available_profiles)}"
                    )
                
                quality_profile_id = quality_profile['id']
                
            except Exception as e:
                raise ValueError(f"Error getting quality profiles: {str(e)}")
    
            # Get existing movies from Radarr
            existing_response = requests.get(f"{radarr_url}/movie", headers=headers)
            existing_response.raise_for_status()
            existing_movies = existing_response.json()
            existing_tmdb_ids = {movie['tmdbId'] for movie in existing_movies}
    
            # Process each recommended movie
            for movie in recommended_movies:
                try:
    
                    # Get TMDB ID from Trakt
                    trakt_search_url = f"https://api.trakt.tv/search/movie?query={quote(movie['title'])}"
                    if movie.get('year'):
                        trakt_search_url += f"&years={movie['year']}"
                    
                    trakt_response = requests.get(trakt_search_url, headers=trakt_headers)
                    trakt_response.raise_for_status()
                    trakt_results = trakt_response.json()
    
                    if not trakt_results:
                        print(f"{YELLOW}Movie not found on Trakt: {movie['title']}{RESET}")
                        continue
    
                    # Find exact match
                    trakt_movie = next(
                        (result for result in trakt_results 
                         if result['movie']['title'].lower() == movie['title'].lower() 
                         and result['movie'].get('year') == movie.get('year')),
                        trakt_results[0]
                    )
    
                    tmdb_id = trakt_movie['movie']['ids']['tmdb']
                    if not tmdb_id:
                        print(f"{YELLOW}No TMDB ID found for movie: {movie['title']}{RESET}")
                        continue
    
                    # Skip if movie is already in Radarr
                    if tmdb_id in existing_tmdb_ids:
                        print(f"{YELLOW}Movie already in Radarr: {movie['title']}{RESET}")
                        continue
    
                    # Apply path mapping and format according to platform
                    root_folder = self._map_path(self.config['radarr']['root_folder'].rstrip('/\\'))
                    
                    # Get monitor setting from config, default to False if not specified
                    should_monitor = self.config['radarr'].get('monitor', False)
    
                    # Prepare movie data for Radarr using minimal required fields
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
    
                    # Add tags only if we have them
                    if tag_id is not None:
                        movie_data['tags'] = [tag_id]
    
                    try:
                        add_response = requests.post(
                            f"{radarr_url}/movie",
                            headers=headers,
                            json=movie_data
                        )
                        add_response.raise_for_status()
    
                        # Only trigger search if monitoring is enabled
                        if should_monitor:
                            movie_id = add_response.json()['id']
                            search_command = {
                                'name': 'MoviesSearch',
                                'movieIds': [movie_id]
                            }
                            search_response = requests.post(
                                f"{radarr_url}/command",
                                headers=headers,
                                json=search_command
                            )
                            search_response.raise_for_status()
                            print(f"{GREEN}Triggered download search for: {movie['title']}{RESET}")
                        else:
                            print(f"{YELLOW}Movie added but not monitored: {movie['title']}{RESET}")
    
                    except requests.exceptions.RequestException as e:
                        print(f"{RED}Error adding movie to Radarr: {str(e)}{RESET}")
                        if hasattr(e.response, 'text'):
                            print(f"{RED}Radarr error response: {e.response.text}{RESET}")
                        continue
    
                except requests.exceptions.RequestException as e:
                    print(f"{RED}Error processing movie {movie['title']}: {str(e)}{RESET}")
                    continue
    
        except Exception as e:
            print(f"{RED}Error adding movies to Radarr: {e}{RESET}")
            import traceback
            print(traceback.format_exc())
    
        print(f"\n{GREEN}Radarr processing completed at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC{RESET}")

def format_movie_output(movie: Dict, show_summary: bool = False) -> str:
    """Format movie information for display"""
    output = f"- {CYAN}{movie['title']}{RESET} ({movie.get('year', 'N/A')})"

    if movie.get('genres'):
        output += f"\n  {YELLOW}Genres:{RESET} {', '.join(movie['genres'])}"

    if movie.get('ratings'):
        if 'imdb_rating' in movie['ratings'] and movie['ratings']['imdb_rating'] > 0:
            votes_str = f" ({movie['ratings'].get('votes', 'N/A')} votes)" if 'votes' in movie['ratings'] else ""
            output += f"\n  {YELLOW}IMDb Rating:{RESET} {movie['ratings']['imdb_rating']}/10{votes_str}"

    if show_summary and movie.get('summary'):
        output += f"\n  {YELLOW}Summary:{RESET} {movie['summary']}"

    return output

def main():
    print(f"{CYAN}Recommendations for Plex v{__version__}{RESET}")
    print(f"{CYAN}Starting recommendation generation at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC{RESET}")
    print(f"{CYAN}User: netplexflix{RESET}")
    print("-" * 50)
    
    # Check for updates
    check_version()
    print("-" * 50)
    
    config_path = os.path.join(os.path.dirname(__file__), 'config.yml')
    
    try:
        recommender = PlexMovieRecommender(config_path)
        recommendations = recommender.get_recommendations()
        
        print(f"\n{GREEN}=== Recommended Unwatched Movies in Your Library ==={RESET}")
        plex_recs = recommendations.get('plex_recommendations', [])
        if plex_recs:
            for movie in plex_recs:
                if isinstance(movie, dict):
                    print(format_movie_output(movie, recommender.show_summary))
                    print()
            # Manage Plex labels
            recommender.manage_plex_labels(plex_recs)
        else:
            print(f"{YELLOW}No recommendations found in your Plex library matching your criteria.{RESET}")
     
        if not recommender.plex_only:
            print(f"\n{GREEN}=== Recommended Movies to Add to Your Library ==={RESET}")
            trakt_recs = recommendations.get('trakt_recommendations', [])
            if trakt_recs:
                for movie in trakt_recs:
                    if isinstance(movie, dict):
                        print(format_movie_output(movie, recommender.show_summary))
                        print()
                # Add to Radarr
                recommender.add_to_radarr(trakt_recs)
            else:
                print(f"{YELLOW}No Trakt recommendations found matching your criteria.{RESET}")
            
    except Exception as e:
        print(f"\n{RED}An error occurred: {e}{RESET}")
        import traceback
        print(traceback.format_exc())
    
    print(f"\n{GREEN}Process completed!{RESET}")

if __name__ == "__main__":
    main()