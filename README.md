<div align="center">
  <img src="assets/FA_logo.png" alt="FA Logo" width="100"/>

# Fantage Archive Cache Tool

</div>

A desktop tool that scans your computer for Fantage-related cache files (Flash SharedObjects, browser caches, etc.) and extracts them into a zip folder, preserving the original directory structure.

Built for the [Fantage Archive](https://fantagearchive.com/) project.

## How to Use

1. Download the correct version for the computer that has the cache (see Download below)
2. Put it on a USB flash drive from **another** computer
3. Plug the flash drive into the computer with the cache
4. **Turn off the internet** on that computer (browsers auto clear old caches when they connect)
5. **Close all browsers** (they can lock or overwrite cache files while running)
6. **Do NOT clear your browser history or caches**
7. Run the tool directly from the flash drive
8. Enter your Discord or Fantage username when prompted
9. Click **Start Extraction** and wait for it to finish
10. Send the generated `.zip` file to the Fantage Archive / Rewritten team

## Download

Grab the latest release for your platform from the [Releases](../../releases) page:

| Platform                                         | File                                   |
| ------------------------------------------------ | -------------------------------------- |
| Windows Vista SP2 or newer, 32 bit and 64 bit    | `FantageArchiveCacheTool-Windows.exe`  |
| macOS (Intel, runs on Apple Silicon via Rosetta) | `FantageArchiveCacheTool-macOS.zip`    |
| Linux                                            | `FantageArchiveCacheTool-Linux.tar.gz` |

### Windows Vista and 32 bit systems

The Windows release is a 32 bit x86 Win32 executable. It works on both 32 bit and 64 bit Windows through the built in WOW64 compatibility layer. This includes 64 bit Windows Vista and modern 64 bit Windows. It is built with Python 3.7.9 because the Python 3.7 Windows runtime supports Windows Vista, while newer Python versions require newer Windows releases.

Windows Vista must have Service Pack 2. The release includes the Vista compatible x86 Universal C Runtime. If Windows still reports a missing `api-ms-win-crt` DLL, install Microsoft update KB2999226.

If you downloaded an older x64 Windows `.exe` and saw `is not a valid Win32 application`, download the newest `FantageArchiveCacheTool-Windows.exe` from Releases.

## Features

- **Browser scanning** - searches 30+ browsers including Chrome, Firefox, Edge, Brave, Opera, Vivaldi, Waterfox, Pale Moon, SeaMonkey, Maxthon, and more
- **Decoded browser cache exports** - rebuilds URL-based Fantage folders from Windows/IE, old Chromium disk cache, Firefox cache files, and Chrome Simple Cache metadata where possible
- **SWF recovery fallback** - saves real SWF binaries found in raw browser cache files when URL metadata is missing
- **Flash cache discovery** - targets Macromedia Flash Player SharedObjects, Adobe Flash standalone, PepperFlash (per-browser), and Shockwave Player
- **Folder structure preserved** - extracted files maintain their original path hierarchy so you can see exactly where they came from
- **Cross-platform** - works on Windows, macOS, and Linux
- **Partial extraction** - stop anytime and still get a zip of everything found so far

## Running from Source

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run from the project root
python3 -m src.main
```

## Project Structure

```
src/
  __init__.py
  main.py              # GUI
  extractor.py         # Scanning and extraction logic
  scanner_utils.py     # Keyword matching helper
assets/
  FA_logo.png
  thatsonecrazymonkey.gif
.github/workflows/build.yml  # CI: cross platform builds
FantageArchiveCacheTool.spec  # PyInstaller build spec
requirements-windows-vista.txt  # Fixed Vista x86 release dependencies
README.md
requirements.txt
```

## License

Part of the Fantage Archive project.
