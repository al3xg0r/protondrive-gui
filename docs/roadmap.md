# Roadmap

## Planned

- **Sharing management**: invite people, see who has access, remove access,
  create or remove share links, and accept or reject invitations. Waiting on the
  role values and output formats from `proton-drive sharing invite --help` and
  `sharing status --help`. Sharing someone else's content also needs different
  actions (leave, unshare), and a wrong guess could change someone else's files.
- **Search**. Possible by building a local index of names. The index would need
  refreshing, and changes made elsewhere would only show up after that.
- **Shared sections**: rename, delete and restore there are deliberately not
  enabled yet. They need confirming against real shared content first. Report
  anything odd you see when browsing them.
- **Albums** in the Photos section, using the CLI's album commands.
- **Local folder sync**. The CLI has no watch or sync mode, so any sync would be
  built on top of it. Two-way sync is deliberately postponed, because conflicts
  and deletions can lose data if rushed.
- **Follow the system theme** automatically, as an alternative to the manual
  switch.

## Not planned, or blocked by the CLI

- **Account storage quota**: no CLI command for it (see [CLI notes](cli.md)).
- **Image thumbnails in Photos**: the CLI can't return them. Fetching full files
  just to draw a grid would be slow and use a lot of data, so the app doesn't
  do it silently.
- **Flatpak and Snap**: not offered. The app ships as an AppImage and a `.deb`.

## Done

- Browsing, uploading, downloading, moving, copying, renaming and trashing in
  My files, with a progress bar for transfers.
- Photos with real names and sizes.
- Trash: restore, permanent delete, empty trash, each with confirmation.
- Expandable folder tree under My files.
- Folder sizes, folder colours, copy/cut/paste, a right-click menu for empty
  space, and new file.
- Local caches for listings and folder sizes, cleared as described in
  [features](features.md#privacy-and-local-data).
- Light and dark themes, remembered view and window settings.
- Account email in the toolbar.
- Sorting by name or date, with saved choices.
- About with version checks for the app and the CLI.
- Packaging: AppImage, `.deb` and an install script.
