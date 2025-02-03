# 🎬 Movie Recommendations for Plex 🎯

This script analyzes your Plex viewing patterns and suggests movies you might enjoy, both from your existing unwatched library and from Trakt's recommendations.
It can then
* label unwatched recommended movies in Plex (to create a collection)
* add new recommendations to Radarr

Requires 
- [Plex](https://www.plex.tv/)
- [TMDB API Key](https://developer.themoviedb.org/docs/getting-started)

Optionally requires:
- [Trakt API key](https://trakt.docs.apiary.io/#) (for movie suggestions outside of your existing library)
- [Radarr](https://radarr.video/) (for adding new recommendations)

Also check out [TV Show Recommendations for Plex](https://github.com/netplexflix/TV-Show-Recommendations-for-Plex)

---

## ✨ Features
- 🧠 **Smart Recommendations**: Analyzes your watch history to understand your preferences
- 🏷️ **Label Management**: Labels recommended movies in Plex
- 🎯 **Radarr Integration**: Adds external recommendations to your Radarr wanted list
- ☑ **Selection**: Confirm recommendations to label and/or add to Radarr, or have it run unattended
- 🔍 **Genre Filtering**: Excludes unwanted genres from recommendations
- 🛠️ **Customizable**: Choose which parameters matter to you
- ☑️ **Trakt Integration**: Uploads your Plex watch history to Trakt if needed and gets personalized recommendations
- 🗃️ **Caching**: Keeps a cache of operations to speed up subsequent runs, limit API calls, and avoid duplicates while syncing
- 💾 **Path Mapping**: Supports different system configurations (NAS, Linux, Windows)
- 📒 **Logging**: Keep desired amount of run logs

---
## 🧙‍♂️ How are recommendations picked?

The script checks your Plex library for watched movies and notes its characteristics, such as genres, director, actors, rating,  language, TMDB keywords, ...
It keeps a frequency count of how often each of these characteristics were found to build a profile on what you like watching.

**For each unwatched Plex movie**, it calculates a similarity score based on how many of those familiar elements it shares with your watch profile, giving extra weight to those you watch more frequently.
It also factors in external ratings (e.g. IMDb), then randomly selects from the top matches to avoid repetitive lists.</br>

**For suggestions outside your existing library**, the script uses your watch history to query Trakt for its built-in movie recommendations algorithm.
It excludes any titles already in your Plex library or containing excluded genres and randomly samples from the top-rated portion of Trakt’s suggestions, ensuring variety across runs.

---

## 🛠️ Installation

### 1️⃣ Download the script
Clone the repository:
```sh
git clone https://github.com/netplexflix/Movie-Recommendations-for-Plex.git
cd Movie-Recommendations-for-Plex
```

![#c5f015](https://placehold.co/15x15/c5f015/c5f015.png) Or simply download by pressing the green 'Code' button above and then 'Download Zip'.

### 2️⃣ Install Dependencies
- Ensure you have [Python](https://www.python.org/downloads/) installed (`>=3.8` recommended)
- Open a Terminal in the script's directory
>[!TIP]
>Windows Users: <br/>
>Go to the script folder (where recommendations.py is).</br>
>Right mouse click on an empty space in the folder and click `Open in Windows Terminal`
- Install the required dependencies:
```sh
pip install -r requirements.txt
```

---

## ⚙️ Configuration
Rename `config.example.yml` to `config.yml` and set up your credentials and preferences:

### General
- **confirm_operations:** `true` will prompt you for extra confirmation for applying labels in plex (If `add_label` is `true`) or adding to radarr (If `add_to_radarr` is `true`)
- **plex_only:** Set to `true` if you only want recommendations among your unwatched Plex Movies. Set to `false` if you also want external recommendations (to optionally add to Radarr).
- **limit_plex_results:** Limit amount of recommended unwatched movies from within your Plex library.
- **limit_trakt_results:** Limit amount of recommended movies from outside your Plex library.
- **exclude_genre:** Genres to exclude. E.g. "animation, documentary".
- **show_summary:** `true` will show you a brief plot summary for each movie.
- **show_cast:** `true` will show top 3 cast members.
- **show_director:** `true` will show the director.
- **show_language:** `true` will show main movie language.
- **show_imdb_rating:** `true` will show IMDb ratings
- **show_imdb_link:** `true` will show an imdb link for each recommended movie.
- **keep_logs:** The amount of logs to keep of your runs. set to `0` to disable logging.

### Paths
- Can be used to path maps across systems.
- Examples:
```yaml
paths:
  # Windows to Windows (local)
  platform: windows
  path_mappings: null

  # Windows to Linux/NAS
  platform: linux
  path_mappings:
    'P:\Movies': '/volume1/Movies'
    'D:\Media': '/volume2/Media'

  # Linux to Windows
  platform: windows
  path_mappings:
    '/mnt/media': 'Z:'
    '/volume1/movies': 'P:\Movies'

  # Linux to Linux/NAS
  platform: linux
  path_mappings:
    '/mnt/local': '/volume1/remote'
    '/home/user/media': '/shared/media'
```

### Plex
- **url:** Edit if needed.
- **token:** [Finding your Plex Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
- **library_title:** The title of your Movie Library
- **add_label:** Adds label to the recommended Movies in your Plex library if set to `true`
- **label_name:** The label to be used
- **remove_previous_recommendations:** If set to `true` removes the label from previously recommendation runs. If set to `false' simply appends the new recommendations.

### Radarr
- **url:** Change if needed
- **api_key:** Can be found in Radarr under Settings => General => Security
- **root_folder:** Change to your Movies root folder
- **add_to_radarr:** Set to `true` if you want to add Trakt recommendations to Radarr. (Requires `plex_only:` `false`)
- **monitor:** `true` will add movies as monitored and trigger a search. `false` will add them unmonitored without searching.
- **quality_profile:** Name of the quality profile to be used when adding movies
- **radarr_tag:** Add a Radarr tag to added movies
 
### Trakt
- Your Trakt API credentials can be found in Trakt under settings => [Your Trakt Apps](https://trakt.tv/oauth/applications) [More info here](https://trakt.docs.apiary.io/#)
- **sync_watch_history:** Can be set to `false` if you already build your Trakt watch history another way (e.g.: through Trakt's Plex Scrobbler).

### TMDB Settings
- **use_TMDB_keywords:** `true` uses TMDB (plot)keywords for matching (Recommended). In this case an api_key is required.
- **api_key:** [How to get a TMDB API Key](https://developer.themoviedb.org/docs/getting-started)

### Weights
Here you can change the 'weight' or 'importance' some parameters have.</br>
Make sure the sum of the weights adds up to 1.</br>
Plex User Ratings, if you use them, automatically apply soft multipliers to scores.

---

## 🚀 Usage

Run the script with:
```sh
python MRFP.py
```

> [!TIP]
> Windows users can create a batch file for quick launching:
> ```batch
> "C:\Path\To\Python\python.exe" "Path\To\Script\MRFP.py"
> pause
> ```

---

## 🍿 Plex collection
Adding labels instead of directly creating a collection gives you more freedom to create a smart collection in Plex.
- Go to your movie library
- Click on All => Advanced filters
- Filter on your chosen 'label' and set any other criteria
- For example; you could append the recommendations to a longer list, then 'limit to' 5 for example, and 'sort by' randomly.
- Click on the arrow next to 'Save as' and click on 'Save as Smart Collection'
- Give the collection a name like 'What should I watch?' and pin it to your home to get 5 random recommendations every time you refresh your home
 ![Image](https://github.com/user-attachments/assets/aabff022-3624-47c9-b9c7-6253f238dcc6)
 ![Image](https://github.com/user-attachments/assets/b5f60a00-32d7-4aad-af2e-fca01d6cc60e)

---

### ⚠️ Need Help or have Feedback?
- Open an [Issue](https://github.com/netplexflix/Movie-Recommendations-for-Plex/issues) on GitHub
- Join our [Discord](https://discord.gg/VBNUJd7tx3)

---

### ❤️ Support the Project
If you find this project useful, please ⭐ star the repository and share it!

<br/>

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/neekokeen)
