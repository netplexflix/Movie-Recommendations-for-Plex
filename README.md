# 🎬 Movie Recommendations for Plex 🎯

This script analyzes your viewing patterns and suggests movies you might enjoy, both from your existing unwatched library and from Trakt's recommendations.
It can then
* label unwatched recommended movies in Plex (to create a collection)
* add new recommendations to Radarr

Requires [Plex](https://www.plex.tv/), [Trakt API](https://trakt.docs.apiary.io/#) and [Radarr](https://radarr.video/) (optional)

---

## ✨ Features
- 🧠 **Smart Recommendations**: Analyzes your watch history to understand your preferences
- 🏷️ **Label Management**: Automatically labels recommended movies in Plex
- 🎯 **Radarr Integration**: Adds external recommendations to your Radarr wanted list
- ☑ **Selection**: Select which recommendations you wish to label and/or add to Radarr
- 🔍 **Genre Filtering**: Excludes unwanted genres from recommendations
- 📊 **Rating-Based**: Uses IMDb ratings to ensure quality recommendations
- 🌟 **Trakt Integration**: Gets personalized recommendations from Trakt
- 💾 **Path Mapping**: Supports different system configurations (NAS, Linux, Windows)

---
## 🧙‍♂️ How are recommendations picked?

The script checks your Plex library for watched movies and notes its characteristics, such as genre, director, actors, rating,  optionally fetches TMDB keywords (if enabled), ...
It keeps a frequency count of how often each of these characteristics were found to build a profile on what you like watching.

**For each unwatched Plex movie**, it calculates a similarity score based on how many of those familiar elements it shares with your watch history, giving extra weight to those you watch more frequently.
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

### General Settings
- **exclude_genre:** Genres to exclude. E.g. "animation, documentary".
- **limit_plex_results:** Limit amount of recommended unwatched movies from within your Plex library.
- **limit_trakt_results:** Limit amount of recommended movies from outside your Plex library.
- **plex_only:** Set to `true` if you only want recommendations among your unwatched Plex Movies. Set to `false` if you also want external recommendations (to optionally add to Radarr).
- **show_summary:** `true` will show you a brief plot summary for each movie.
- **keep_logs:** The amount of logs to keep of your runs. set to `0` to disable logging
- **confirm_operations:** `true` will prompt you for extra confirmation for applying labels in plex (If `add_label` is `true`) or adding to radarr (If `add_to_radarr` is `true`)

### Path Mappings
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

### Plex Settings
- **add_label:** Adds label to the recommended Movies in your Plex library if set to `true`
- **label_name:** The label to be used
- **library_title:** The title of your TV Show Library
- **remove_previous_recommendations:** If set to `true` removes the label from previously recommendation runs. If set to `false' simply appends the new recommendations.
- **token:** [Finding your Plex Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
- **url:** Edit if needed.

### Radarr Settings
- **add_to_radarr:** Set to `true` if you want to add Trakt recommendations to Radarr. (Requires `plex_only:` `false`)
- **api_key:** Can be found in Radarr under Settings => General => Security
- **monitor:** `true` will add movies as monitored and trigger a search. `false` will add them unmonitored without searching.
- **quality_profile:** Name of the quality profile to be used when adding movies
- **radarr_tag:** Add a Radarr tag to added movies
- **root_folder:** Change to your Movies root folder
- **url:** Change if needed
 
### Trakt Settings
Your Trakt API credentials can be found in Trakt under settings => [Your Trakt Apps](https://trakt.tv/oauth/applications) </br>
[More info here](https://trakt.docs.apiary.io/#)

### TMDB Settings
- **use_TMDB_keywords:** `true` uses TMDB (plot)keywords for matching (Recommended!). In this case an api_key is required.
- **api_key:** [How to get a TMDB API Key](https://developer.themoviedb.org/docs/getting-started)

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
- Give the collection a name like 'Recommended Movies' and pin it to your home to get 5 random recommendations every time you refresh your home
 ![Image](https://github.com/user-attachments/assets/aabff022-3624-47c9-b9c7-6253f238dcc6)


---

### ⚠️ Need Help or have Feedback?
- Open an [Issue](https://github.com/netplexflix/Movie-Recommendations-for-Plex/issues) on GitHub
- Join our [Discord](https://github.com/netplexflix/Missing-Trailer-Downloader-for-Plex/issues)

---

### ❤️ Support the Project
If you find this project useful, please ⭐ star the repository and share it!

<br/>

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/neekokeen)
