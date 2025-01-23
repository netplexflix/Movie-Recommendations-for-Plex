# 🎬 Recommendations for Plex 🎯

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
- 🔍 **Genre Filtering**: Excludes unwanted genres from recommendations
- 📊 **Rating-Based**: Uses IMDb ratings to ensure quality recommendations
- 🌟 **Trakt Integration**: Gets personalized recommendations from Trakt
- 💾 **Path Mapping**: Supports different system configurations (NAS, Linux, Windows)

---

## 🛠️ Installation

### 1️⃣ Download the script
Clone the repository:
```sh
git clone https://github.com/netplexflix/Recommendations-for-Plex.git
cd Recommendations-for-Plex
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
- **plex_only:** Set to `true` if you only want recommendations among your unwatched Plex Movies. Set to `false` if you also want external recommendations (to optionally add to Radarr).
- **limit_plex_results:** Limit amount of recommended unwatched movies from within your Plex library.
- **limit_trakt_results:** Limit amount of recommended movies from outside your Plex library.
- **exclude_genre:** Genres to exclude. E.g. "animation, documentary".
- **show_summary:** `True` will show you a brief plot summary for each movie.

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
- **url:** Edit if needed.
- **token:** [Finding your Plex Token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
- **add_label:** Adds label to the recommended Movies in your Plex library if set to `true` 
- **label_name:** The label to be used
- **remove_previous_recommendations:** If set to `true` removes the label from previously recommendation runs. If set to `false' simply appends the new recommendations.

### Radarr Settings
- **url:** Change if needed
- **api_key:** Can be found in Radarr under Settings => General => Security
- **root_folder:** Change to your Movies root folder
- **add_to_radarr:** Set to `true` if you want to add Trakt recommendations to Radarr. (Requires `plex_only:` `false`)
- **quality_profile:** Name of the quality profile to be used when adding movies
- **radarr_tag:** Add a Radarr tag to added movies
- **monitor:** `true` will add movies as monitored and trigger a search. `false` will add them unmonitored without searching.




---

## 🚀 Usage

Run the script with:
```sh
python RFP.py
```

The script will:
1. Analyze your watch history
2. Generate recommendations from your library
3. Get external recommendations from Trakt
4. Label recommended movies in Plex
5. Add external recommendations to Radarr (if configured)

> [!TIP]
> Windows users can create a batch file for quick launching:
> ```batch
> "C:\Path\To\Python\python.exe" "Path\To\Script\RFP.py"
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
- Open an [Issue](https://github.com/netplexflix/Recommendations-for-Plex/issues) on GitHub
- Join our [Discord](https://github.com/netplexflix/Missing-Trailer-Downloader-for-Plex/issues)

---

### ❤️ Support the Project
If you find this project useful, please ⭐ star the repository and share it!

<br/>

[!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/neekokeen)
