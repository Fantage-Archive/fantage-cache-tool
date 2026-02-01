
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import sys
from extractor import FantageExtractor

def resource_path(relative_path):
    """ Get absolute path to resource, for PyInstaller"""
    try:
        # PyInstaller creates a temp folder
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Fantage Cache Extractor")
        self.root.geometry("500x450")
        
        # Style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Header Frame
        header_frame = ttk.Frame(root)
        header_frame.pack(pady=20)

        # Image
        self.gif_frames = []
        try:
            # Load frames
            i = 0
            while True:
                try:
                    img_path = resource_path("thatsonecrazymonkey.gif")
                    frame = tk.PhotoImage(file=img_path, format=f"gif -index {i}")
                    self.gif_frames.append(frame)
                    i += 1
                except tk.TclError:
                    break # End of frames
            
            if self.gif_frames:
                self.img_label = ttk.Label(header_frame, image=self.gif_frames[0])
                self.img_label.pack(side="left", padx=0)
                self.animate_gif(0)
            else:
                print("No frames loaded.")

        except Exception as e:
            print(f"Could not load image: {e}")

        # Header Text
        header = ttk.Label(header_frame, text="Fantage Cache Extractor", font=("Helvetica", 16, "bold"))
        header.pack(side="left")

        desc = ttk.Label(root, text="This tool scans your computer for Fantage-related files\nand extracts them to a zip folder.", justify="center")
        desc.pack(pady=5)

        # Directory Selection
        self.dir_frame = ttk.LabelFrame(root, text="Search Scope")
        self.dir_frame.pack(pady=10, padx=20, fill="x")
        
        self.selected_dir = tk.StringVar(value="All Drives (Default)")
        self.path_label = ttk.Label(self.dir_frame, textvariable=self.selected_dir, font=("Consolas", 8))
        self.path_label.pack(side="left", padx=5, expand=True, fill="x")
        
        self.browse_btn = ttk.Button(self.dir_frame, text="Browse...", command=self.browse_directory)
        self.browse_btn.pack(side="right", padx=5, pady=5)
        
        self.custom_path = None

        # Progress
        self.progress = ttk.Progressbar(root, orient="horizontal", length=400, mode="indeterminate")
        self.progress.pack(pady=20)
        
        # Status Label
        self.status_var = tk.StringVar(value="Ready to scan")
        self.status = ttk.Label(root, textvariable=self.status_var, font=("Consolas", 9))
        self.status.pack(pady=5)
        
        # Buttons
        self.btn_frame = ttk.Frame(root)
        self.btn_frame.pack(pady=10)
        
        self.start_btn = ttk.Button(self.btn_frame, text="Start Extraction", command=self.start_scan)
        self.start_btn.pack(side="left", padx=10)
        
        self.stop_btn = ttk.Button(self.btn_frame, text="Stop", command=self.stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=10)
        
        self.extractor = None
        self.thread = None

    def animate_gif(self, idx):
        frame = self.gif_frames[idx]
        self.img_label.configure(image=frame)
        next_idx = (idx + 1) % len(self.gif_frames)
        # Animation delay
        self.root.after(150, self.animate_gif, next_idx)

    def browse_directory(self):
        path = filedialog.askdirectory()
        if path:
            self.custom_path = path
            # Truncate if too long for display
            display_path = path if len(path) < 40 else "..." + path[-37:]
            self.selected_dir.set(display_path)
            self.status_var.set(f"Target: {display_path}")

    def start_scan(self):
        output_dir = os.getcwd() # Save to where the executable is being run
        self.extractor = FantageExtractor(output_dir, self.update_status, search_path=self.custom_path)
        
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.browse_btn.config(state="disabled") # Lock selection during scan
        self.progress.start(10)
        
        self.thread = threading.Thread(target=self.run_extractor)
        self.thread.daemon = True
        self.thread.start()
        
    def stop_scan(self):
        if self.extractor:
            self.extractor.stop_event.set()
            self.status_var.set("Stopping...")
            
    def run_extractor(self):
        self.extractor.run()
        # When done (or stopped)
        self.root.after(0, self.scan_finished)

    def update_status(self, message, progress_value=0):
        # Schedule GUI update on main thread
        self.root.after(0, lambda: self.status_var.set(message))
        
    def scan_finished(self):
        self.progress.stop()
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.status_var.set("Scan complete.")
        messagebox.showinfo("Done", "Extraction Complete! The folder has been opened.")

if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
