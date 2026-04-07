<div align="center">
  <img src="assets/FA_logo.png" alt="FA Logo" width="100"/>

# Fantage Archive Cache Tool

</div>

A desktop tool that scans your computer for Fantage-related cache files (Flash SharedObjects, browser caches, etc.) and extracts them into a zip folder, preserving the original directory structure.

Built for the [Fantage Archive](https://github.com/shersafi/Fantage-Archive) project.

## How to Use

1. Download the correct version for the computer that has the cache (see Downloads below)
2. Put it on a USB flash drive from **another** computer
3. Plug the flash drive into the computer with the cache
4. **Turn off the internet** on that computer (browsers auto-clear old caches when they connect)
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
| Windows                                          | `FantageArchiveCacheTool-Windows.exe`  |
| macOS (Intel, runs on Apple Silicon via Rosetta) | `FantageArchiveCacheTool-macOS.zip`    |
| Linux                                            | `FantageArchiveCacheTool-Linux.tar.gz` |

## Features

- **Browser scanning** - searches 30+ browsers including Chrome, Firefox, Edge, Brave, Opera, Vivaldi, Waterfox, Pale Moon, SeaMonkey, Maxthon, and more
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
README.md
requirements.txt
```

## License

Part of the Fantage Archive project.
