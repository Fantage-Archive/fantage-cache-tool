# Build Instructions

## Prerequisites

1.  **Install Python**: Download and install Python (3.8+) from [python.org](https://www.python.org/downloads/).
2.  **Install Dependencies**: Open your command prompt and run:
    ```bash
    pip install pyinstaller tkinter
    ```

## Compiling the App

1.  Open command prompt.
2.  Go to the project folder:
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