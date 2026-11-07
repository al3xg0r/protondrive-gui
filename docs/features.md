# Features

What the app does today. Anything not listed here is on the
[roadmap](roadmap.md).

## Browsing

- **Sidebar**: New folder, My files, Photos, Trash, Shared by me, Shared with
  me. The current section is highlighted. Log in / out, the theme switch and
  About sit at the bottom. In a narrow window it shows icons only.
- **Folder tree under My files**: click the arrow next to My files to show your
  folders. Expand any folder to load its subfolders. An arrow appears only on
  folders that have subfolders. A scrollbar appears while the pointer is over the
  tree.
- **Breadcrumbs** with Back and Refresh, plus **Go to path…** for typing a path
  directly.
- **Sorting** by name, size or date modified. Click a column heading, or use
  the sort button above the list; a second click reverses the order. Folders
  stay in front in My files. Photos has its own sort, newest first by default.
  Choices are remembered.
- **List and grid views**, remembered across launches. Folders are amber
  unless you give them a colour; photos, videos, spreadsheets, archives, audio
  and other files each have their own icon colour, the same in every section.
- **Remembers** the last section and folder you were in, and the window size
  and position.
- **Folder listings are cached** on this computer, so a folder you've opened
  before appears at once while the live listing loads. See
  [Privacy and local data](#privacy-and-local-data).
- **Photos**: real file names and sizes, with separate icons for photos and
  videos. There are no image thumbnails (see [CLI notes](cli.md)).
- **Trash**: browse, restore, delete permanently, or empty the trash. Deleting
  and emptying ask first.
- **Shared by me / Shared with me**: browse only. Actions there are not enabled
  yet.

## Files and folders

- **Upload**: the Upload button, or drag files onto the window. In My files you
  can also drag whole folders. Photos accepts files only.
- **Download** a selection to a folder you choose, with a progress bar. The
  progress bar reads the CLI's live output, which isn't a documented format, so
  it can stop working after a CLI update.
- **Proton's own documents and sheets** (created inside Proton Drive, not
  uploaded) can't be downloaded through the CLI. The app skips them and says so.
- **New folder** and **New file**. A new file is an empty file uploaded under
  the name you choose, because the CLI has no create-file command.
- **Rename**, **Move to folder** (with a folder picker), **Make a copy**.
- **Copy, Cut and Paste** from the right-click menu or with Ctrl+C, Ctrl+X and
  Ctrl+V. The clipboard is internal to the app, not the system clipboard. A
  pasted copy that clashes with an existing name gets " (copy)" added. A folder
  can't be pasted into itself.
- **Move to Trash** with the Delete key or from the menu. It asks first.
- **Information…** shows name, type, size, modified date, sharing status and
  path. For folders it also shows the total size and the number of items inside.
- **Folder sizes** in the Size column are counted in the background, one folder
  at a time, and remembered. They're recounted after an hour, or straight after
  a change made in the app.
- **Folder colours**: right-click a folder in My files → Folder colour. There
  are eight colours and Default. Colours are stored on this computer only (see
  [Privacy and local data](#privacy-and-local-data)).
- **Right-click on empty space** in My files gives New folder, New file and
  Paste.

## Look and behaviour

- Light and dark themes, switched from the sidebar. The choice is remembered.
  The app doesn't follow the system theme automatically.
- Context menus and dialogs are styled to match the app.
- **About** shows the app version and the installed CLI version, and says
  whether a newer version of either is out. Each has a link to download it. It
  also shows what's new in the current version, from the changelog.

## Privacy and local data

The app keeps a few things on this computer. Nothing is sent anywhere except
through the official CLI, with one exception described below.

| What | Where | Removed when |
| --- | --- | --- |
| Folder listings (names, sizes, dates) | `~/.cache/protondrive-gui/listings.json` | You log out, or you delete the file. My files entries are also dropped after any change made in the app. |
| Folder colours (keyed by folder id) | `~/.config/protondrive-gui/folder_colors.json` | You set a folder back to Default, or delete the file. |
| Folder size counts | in the settings file | Refreshed after an hour, or after a change made in the app. |
| Window, section and view settings | Qt settings for `protondrive-gui` | You delete them. |

The cache and colour files are readable only by you. They hold file and folder
names, so delete them if you don't want those kept on disk.

**The one network request outside the CLI**: when you open About, the app asks
GitHub for the latest release of this app, and for the latest CLI version it
relies on what the CLI itself reports. Nothing is sent except that request.
