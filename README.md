# MarkUnfinished ([Deluge](https://www.deluge-torrent.org) plugin)

Appends a `.!incomplete` extension to all files in the torrent, then renames them back to original as each file finishes downloading.

### Benefits
* You can tell which files have finished downloading from within your file explorer, without having to open the Deluge UI
* Prevent your media organizer (Jellyfin, Plex, etc.) from indexing or trying to play incomplete files

### Limitations
* Only handles torrents that are added after the plugin is installed. Old torrents will be left alone.

### Installation
* Download the .egg file from [here](https://github.com/quantumfrost/deluge-markunfinished/releases)
* `Edit -> Preferences -> Plugins -> Install`
* More info [here](https://dev.deluge-torrent.org/wiki/Plugins#InstallingPluginEggs)
