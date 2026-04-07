# Fantage Archive Cache Tool

A desktop tool that scans your computer for Fantage related cache files (Flash SharedObjects, browser caches, etc.) and extracts them into a zip folder.

## Features

- **Browser scanning**: Searches 30+ browsers including Chrome, Firefox, Edge, Brave, Opera, Vivaldi, Waterfox, Pale Moon, SeaMonkey, Maxthon, and more.
- **Flash cache discovery**: Targets Macromedia Flash Player SharedObjects, Adobe Flash standalone, PepperFlash (per-browser), and Shockwave Player.
- **Folder structure preserved**: Extracted files maintain their original path hierarchy so you can see exactly where they came from.
- **Cross-platform**: Works on Windows, macOS, and Linux.

## Download

Grab the latest release for your platform from the [Releases](../../releases) page:

| Platform                      | File                                          |
| ----------------------------- | --------------------------------------------- |
| Windows                       | `FantageArchiveCacheTool-Windows.exe`         |
| macOS (Intel + Apple Silicon) | `FantageArchiveCacheTool-macOS-Universal.zip` |
| Linux                         | `FantageArchiveCacheTool-Linux.tar.gz`        |

## Running from Source

```bash
# Install dependencies
pip3 install -r requirements.txt

# Run from the project root
python3 -m src.main
```

## How It Works

1. Enter a search keyword (default: `fantage`)
2. Enter your username (it gets appended to the output folder/zip name)
3. Click **Start Extraction**
4. The tool scans all known browser and Flash cache locations on your system
5. Matching files and folders are copied to `Fantage_Extraction_YourName/` preserving directory structure
6. Everything is zipped into `Fantage_Cache_YourName.zip`
7. The output folder opens automatically

## Project Structure

```
├── src/
│   ├── __init__.py
│   ├── main.py              # GUI
│   ├── extractor.py         # Scanning and extraction logic
│   └── scanner_utils.py     # Keyword matching helper
├── assets/
│   ├── FA_logo.png         
│   └── thatsonecrazymonkey.gif  
├── .github/workflows/build.yml  # CI: cross platform builds
├── FantageArchiveCacheTool.spec  # PyInstaller build spec
├── BUILD_INSTRUCTIONS.md
├── README.md
└── requirements.txt
```

## License

Part of the Fantage Archive project.
