# Build Instructions

To compile this application for your specific platform (Windows or macOS), follow these steps.

## Prerequisites

1.  **Install Python**: Download and install Python (3.8+) from [python.org](https://www.python.org/downloads/).
2.  **Install Dependencies**: Open your terminal or command prompt and run:
    ```bash
    pip install pyinstaller tkinter
    ```
    _(Note: Tkinter is usually included with Python on Windows. On macOS, you might need to install `python-tk` via Homebrew if it's missing, but the official installer includes it.)_

## Compiling the App

1.  Open your terminal/command prompt.
2.  Navigate to the project folder:
    ```bash
    cd path/to/Fantage-Cache-Extractor
    ```
3.  Run the build command:
    ```bash
    pyinstaller FantageCacheExtractor.spec
    ```

## Finding the App

- After the build completes, look in the `dist/FantageCacheExtractor` folder.
- **Windows**: You will see `FantageCacheExtractor.exe`.
- **Mac**: You will see a Unix executable named `FantageCacheExtractor`.

## Troubleshooting

- If the image doesn't load, ensure `thatsonecrazymonkey.gif` is in the same folder as `main.py` when you run the build command.
- If you get permission errors on Mac, you may need to go to System Settings > Privacy & Security to allow the app to run.
