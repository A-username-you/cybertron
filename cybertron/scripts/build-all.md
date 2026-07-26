# Producing installers for all three OSes

`electron-builder` can't cross-compile everything from one machine — this
is a real limitation, not something this scaffold papers over.

| Target | Can build on |
|---|---|
| Windows `.exe` (nsis) | Windows, or Linux/macOS with Wine installed |
| macOS `.dmg` | macOS only (Apple's tooling requirement) |
| Linux `.AppImage` / `.deb` | Linux, or macOS/Windows with extra setup |

**Practical path:** run a GitHub Actions matrix (`windows-latest`,
`macos-latest`, `ubuntu-latest`), each running:

```bash
npm install --workspaces
npm run build
npm run dist:win   # on windows-latest
npm run dist:mac   # on macos-latest
npm run dist:linux # on ubuntu-latest
```

and upload `electron/release/*` as artifacts from each job. That's the
standard, reliable way indie Electron apps ship on all three OSes — a
single local machine building all three reliably is the exception, not
the norm.

For macOS specifically: an unsigned `.dmg` will trigger Gatekeeper
warnings on other people's machines. Signing needs an Apple Developer
account ($99/yr) and `electron-builder`'s `mac.notarize` config — not
included here since it needs your credentials.
