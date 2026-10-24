# Umbrella - A Video Plugin for Kodi

Welcome to the umbrellaplug.github.io

Compatible with Kodi 19, 20, 21, and 22.

## Current Versions:
Umbrella - 6.7.98 (custom; upstream 6.7.97)
Umbrella Repo - 2.2.6

The October 23 custom release incorporates upstream through commit
`82e91dda01a72d51fe1988cbe61cef1c5d2d78a7`. It retains AIOStreams, source details,
anime episode-group mapping, and original-numbering retries. Custom setting
labels use IDs 40900–40907 in Kodi's `resource.language.en_gb` folder.
Settings backups include AIOStreams connection details only when that account
is explicitly selected for export; ordinary preference backups omit them.

## Installation Instructions:
From Kodi:
System > File Manager > Select Add Source

For "Enter the paths or browse for the media locations" select "None" and input:

**https://bigdaddy-cpm.github.io/**

Then Select Done. For "Enter a name for this media source" input "Umbrella" or whatever you would like to name the source.
Click Ok.

From the Kodi Homescreen select "Add-ons".
At the top on the left hand side select the box icon under "Add-ons" (Add-on Browser).

Install the custom repository by clicking on Install from Zip File then "Umbrella" then repository.bigdaddy-cpm-1.0.1.zip and waiting for the repository installed notification.

Select "Install From Repository" then bigdaddy-cpm Repository then Video Add-ons then Umbrella. Click on Install and wait for the Add-on Enabled Notification.

## Setup Instructions

From the main menu, navigate to Tools > Settings > Trakt
Follow the onscreen instructions and authorize Trakt.

Next add any debrid services you use and follow the on-screen instructions.
Currently Supported Debrid Providers:
- All Debrid
- Real Debrid
- Premiumize
- TorBox
- OffCloud

Currently Supported Other Providers:
- Easynews
- Plex
- Google Drive
- AIOStreams (resolved HTTP/debrid streams)

### AIOStreams Setup

Configure and save your user in the AIOStreams web interface. In Umbrella, open **Settings > Providers > AIOStreams**, enable it, select the instance, and enter your AIOStreams UUID and password. **MidnightIgnite Stable** uses `https://aiostreamsfortheweebsstable.midnightignite.me`; select **Custom** to enter a different self-hosted or private instance URL.

Umbrella uses AIOStreams' authenticated Search API to request movie and episode results by IMDb ID. Results containing resolved HTTP(S) URLs are added to Umbrella's normal source list; P2P-only `infoHash`, YouTube, and external-page results are ignored.

**The plugin will not work without at least 1 of these types of accounts**

## Issues
Please do not mention any other addons in issues.

## Logs
Enable Logs: Go to Umbrella settings and select Debugging on the left hand side.
Set your settings like this:
![Screen Sho](https://user-images.githubusercontent.com/107957815/177895894-eb3f68cb-cd83-4d05-b033-6588579f2ce5.png)

## FAQ

**Q:** After setting up, I'm getting "No Sources Found"

**A:** Umbrella only searches your cloud from Providers you have entered. For additional sources, external providers can be installed. Umbrella does not offer support for any external providers.


**Q:** Do you take feature requests?

**A:** Some yes. Open an issue and use the feature request template.


[Setup Instructions](https://github.com/umbrellaplug/umbrellaplug.github.io/wiki#setup-instructions)
