# CLI notes

The app is a window on top of Proton's official `proton-drive` command-line
client. This page lists what the CLI can and can't do, and what that means for
the app. The CLI changes between releases, so re-check these notes after you
update it.

Sources: the [CLI's own README](https://github.com/ProtonDriveApps/sdk/blob/main/cli/README.md)
and the output of `proton-drive --help` and `--help` for each command.

## JSON output and the parser

The CLI supports a `--json` flag, but Proton hasn't published one documented
schema for its output. `gui/cli.py` reads the fields it needs and tolerates a
few variants of field names. Parsing is done in
`ProtonDriveCLI._normalize_item()`, which is the one place that should need
changing if the output shape changes.

If items show up with missing names or sizes after a CLI update, compare the raw
output with the parser:

```bash
proton-drive filesystem list /my-files --json
```

Pull requests that fix this for real-world output are welcome.

## Used by the app

- `filesystem list`, `info`, `size`, `create-folder`, `upload`, `download`,
  `rename`, `copy`, `move`, `trash`, `restore`, `delete`, `empty-trash`
- `photo timeline -d`, `photo download`
- `auth login`, `auth logout`, `--version`

## Confirmed possible but not in the app

- **Sharing**: `sharing status`, `invite`, `leave`, `remove`, `set-url`,
  `remove-url`, and `invitation list / accept / reject`. The GUI can only browse
  Shared by me and Shared with me. The Share menu entry is a placeholder until
  the role values and output formats are confirmed.
- **Albums**: `album list / create / update / delete / photos / add-photo /
  remove-photo`. They're separate from the Photos timeline and not used yet.
- **Takeout**: `takeout run` exports content to a local folder. Not used yet.

## Not possible through this CLI (as of the last check)

- **Account storage quota.** No account, quota or usage command appears in the
  help. The account email is shown anyway, read from the owner field of file
  listings.
- **Folder sizes for every folder at once.** `filesystem size` works one folder
  at a time, so the app counts them in the background and caches the results.
- **Image thumbnails.** The CLI generates WebP thumbnails when a file is uploaded,
  for Proton's own apps. There is no command to fetch them back, only full-file
  `photo download`.
- **Creating an empty file.** Not a command. The app uploads an empty local file
  under the name you choose.
- **Setting a folder colour.** Not a command. Colours are kept locally (see
  [features](features.md#privacy-and-local-data)).

## Background from the CLI's own documentation

- The CLI is built with Bun and its own SDK. The documentation says the SDK is
  **not yet ready for third-party production use** and expects it to change.
  That's Proton's own statement, and it's one reason some parsing here is
  defensive rather than based on a stable contract.
- Proton has announced a cryptographic migration for Drive that could change
  output shapes again.
- Credentials are kept in the system secret store (libsecret on Linux) under the
  service name `ch.proton.drive/drive-sdk-cli`. The app doesn't read them.
- The CLI keeps its own cache and logs under `~/.cache/proton-drive-cli`,
  `~/.local/share/proton-drive-cli` and `~/.local/state/proton-drive-cli`, or
  under `$PROTON_DRIVE_CACHE_DIR` if that's set. Look there when troubleshooting
  a problem that is in the CLI rather than in the app.
