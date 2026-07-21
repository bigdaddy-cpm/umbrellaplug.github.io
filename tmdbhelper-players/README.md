# Umbrella players for TMDbHelper

Copy `umbrella.select.json` and `umbrella.autoplay.json` to:

`special://profile/addon_data/plugin.video.themoviedb.helper/players/`

On CoreELEC this is normally:

`/storage/.kodi/userdata/addon_data/plugin.video.themoviedb.helper/players/`

If matching files exist in `reconfigured_players`, remove or reset those copies because TMDbHelper gives them priority over files in `players`.

- Source Select passes `select=0` to Umbrella.
- Autoplay passes `select=1` to Umbrella.
- Both use `is_resolvable=false` because Umbrella manages playback through its own source workflow.
