# Changelog

Notable changes per release. The full list is in the
[GitHub releases](https://github.com/al3xg0r/protondrive-gui/releases).

## 1.5.0

- Sort files by name or date modified: click the Name or Modified heading, or use
  the sort button above the list. Click again to reverse the order. Photos has its
  own sort, newest first by default. The choice is remembered.
- The `.deb` package now downloads the official CLI during installation and
  checks its SHA-512 checksum, the same way `install.sh` does. If anything
  fails, the app still installs and tells you where to get the CLI.
- About shows what's new in the current version.

## 1.4.0

- Folder colours, kept on this computer, shown in the list, grid and tree.
- Copy, Cut and Paste, with a right-click menu for empty space that adds
  New folder, New file and Paste.
- `.deb` packages for Debian, Ubuntu and Linux Mint, alongside the AppImages.
- Better error messages when the CLI skips an item it can't download.
- Menu and tree spacing fixes; the My files arrow sits inside its highlight.

## 1.3.0

- Expandable folder tree under My files in the sidebar.
- Local cache for folder listings, so folders open at once.
- Grid or list view is remembered across launches.
- Account email in the top toolbar.
- Fixes: sidebar width after a theme switch, icon colours at startup, tree
  overlap on short windows, selection highlight.

## 1.2.0

- Folder sizes in the Size column, counted in the background and remembered.
- Right-click menu matching the web app: Download, Move to folder, Make a copy,
  Rename, Information, Move to Trash.
- About shows the app and CLI versions and whether newer versions are out.
- Clicking empty space clears the selection and its focus outline.

## 1.1.0

- Remembers the last section, folder and window size.
- Account email shown in the toolbar.
- Grid spacing and empty-trash placement fixes.
- License changed to PolyForm Noncommercial 1.0.0: free for noncommercial use,
  no commercial use or resale.

## 1.0.1

- Light and dark theme switch, remembered between launches.
- AppImages for x86_64 and arm64 built automatically on each release.

## 1.0.0

- First release without the beta label. Browsing, upload, download, organising
  and trash in My files; Photos, Trash and Shared sections; list and grid views;
  AppImage packaging.
