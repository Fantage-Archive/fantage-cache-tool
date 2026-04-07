import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import os
import sys
from PIL import Image, ImageTk
# I put this here in case you want to run it from src
try:
    from extractor import FantageExtractor
except ImportError:
    from src.extractor import FantageExtractor

# ============================================================
#  Same Fantage Archive design language
# ============================================================
COLORS = {
    "pink_dark":  "#d1629b",
    "pink_mid":   "#f2a7c3",
    "pink_light": "#fce4ec",
    "pink_pale":  "#fff0f5",
    "pink_hot":   "#e91e8a",
    "lavender":   "#e8d5f5",
    "baby_blue":  "#c8e6f5",
    "text_dark":  "#5a2d42",
    "text_mid":   "#8b5e7a",
    "text_light": "#c48aaa",
    "border":     "#f0c6d8",
    "card_bg":    "#ffffff",
    "white":      "#ffffff",
    "green":      "#95CC9C",
}

FONT_MAIN     = ("Varela Round", 11)
FONT_HEADER   = ("Patrick Hand", 22, "bold")
FONT_DESC     = ("Varela Round", 10)
FONT_LABEL    = ("Varela Round", 9, "bold")
FONT_ENTRY    = ("Consolas", 10)
FONT_STATUS   = ("Consolas", 9)
FONT_BTN      = ("Varela Round", 11, "bold")
FONT_BTN_SM   = ("Varela Round", 10)

def resource_path(relative_path):
    """Get absolute path to resource (for PyInstaller and dev.)"""
    try:
        # PyInstaller bundles assets into a temp folder
        base_path = sys._MEIPASS
    except AttributeError:
        # In development, assets/ is one level up from src/
        base_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets')
    return os.path.join(base_path, relative_path)


class RoundedButton(tk.Canvas):
    """Tried to match it with the FA buttons."""

    def __init__(self, parent, text="", command=None,
                 bg="#e91e8a", fg="#ffffff", hover_bg="#d1629b",
                 width=160, height=38, radius=18, font=FONT_BTN, **kwargs):
        super().__init__(parent, width=width, height=height,
                         bg=parent["bg"], highlightthickness=0, **kwargs)
        self.command = command
        self.bg = bg
        self.fg = fg
        self.hover_bg = hover_bg
        self._current_bg = bg
        self.radius = radius
        self.text = text
        self.font = font
        self._disabled = False

        self._draw(bg)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        """Draw a rounded rectangle on the canvas."""
        points = [
            x1+r, y1,   x2-r, y1,   x2, y1,   x2, y1+r,
            x2, y2-r,   x2, y2,     x2-r, y2,  x1+r, y2,
            x1, y2,     x1, y2-r,   x1, y1+r,  x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _draw(self, fill_color):
        self.delete("all")
        w = int(self["width"])
        h = int(self["height"])
        # Shadow
        self._round_rect(2, 3, w-2, h, self.radius,
                         fill="#f0c6d8", outline="")
        # Body
        self._round_rect(1, 1, w-2, h-3, self.radius,
                         fill=fill_color, outline="")
        # Text
        self.create_text(w//2, (h-3)//2, text=self.text,
                         fill=self.fg, font=self.font)

    def _on_enter(self, e):
        if not self._disabled:
            self._draw(self.hover_bg)

    def _on_leave(self, e):
        if not self._disabled:
            self._draw(self.bg)

    def _on_press(self, e):
        if not self._disabled:
            self._draw(self.hover_bg)

    def _on_release(self, e):
        if not self._disabled and self.command:
            self._draw(self.bg)
            self.command()

    def set_disabled(self, disabled):
        self._disabled = disabled
        if disabled:
            self._draw("#e0ccd5")
            self.config(cursor="")
        else:
            self._draw(self.bg)
            self.config(cursor="hand2")


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Fantage Archive Cache Tool")
        self.root.geometry("520x600")
        self.root.configure(bg=COLORS["pink_pale"])
        self.root.resizable(False, False)

        # Window icon
        try:
            icon_path = resource_path("FA_logo.png")
            icon_img = Image.open(icon_path)
            icon_img = icon_img.resize((64, 64), Image.LANCZOS)
            self._icon = ImageTk.PhotoImage(icon_img)
            self.root.iconphoto(True, self._icon)
        except Exception as e:
            print(f"Could not set icon: {e}")

        # TTK styling
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Y2K.TFrame", background=COLORS["pink_pale"])
        style.configure("Card.TFrame", background=COLORS["card_bg"])
        style.configure("Y2K.TLabel",
                         background=COLORS["pink_pale"],
                         foreground=COLORS["text_dark"],
                         font=FONT_MAIN)
        style.configure("Header.TLabel",
                         background=COLORS["pink_pale"],
                         foreground=COLORS["pink_dark"],
                         font=FONT_HEADER)
        style.configure("Desc.TLabel",
                         background=COLORS["pink_pale"],
                         foreground=COLORS["text_mid"],
                         font=FONT_DESC)
        style.configure("Status.TLabel",
                         background=COLORS["pink_pale"],
                         foreground=COLORS["text_mid"],
                         font=FONT_STATUS)
        style.configure("CardLabel.TLabel",
                         background=COLORS["card_bg"],
                         foreground=COLORS["text_dark"],
                         font=FONT_LABEL)
        style.configure("CardDesc.TLabel",
                         background=COLORS["card_bg"],
                         foreground=COLORS["text_light"],
                         font=("Varela Round", 8))

        # Progress bar
        style.configure("Pink.Horizontal.TProgressbar",
                         troughcolor=COLORS["pink_light"],
                         background=COLORS["pink_hot"],
                         bordercolor=COLORS["border"],
                         lightcolor=COLORS["pink_mid"],
                         darkcolor=COLORS["pink_dark"],
                         thickness=14)

        style.configure("Y2K.TLabelframe",
                         background=COLORS["card_bg"],
                         foreground=COLORS["pink_dark"],
                         bordercolor=COLORS["border"],
                         relief="groove",
                         font=FONT_LABEL)
        style.configure("Y2K.TLabelframe.Label",
                         background=COLORS["card_bg"],
                         foreground=COLORS["pink_dark"],
                         font=FONT_LABEL)

        # ============================================================
        #  Layout
        # ============================================================

        # Main container
        main_frame = tk.Frame(root, bg=COLORS["pink_pale"])
        main_frame.pack(fill="both", expand=True, padx=24, pady=16)

        # Header Row (logo, title)
        header_frame = tk.Frame(main_frame, bg=COLORS["pink_pale"])
        header_frame.pack(pady=(0, 4))

        try:
            logo_path = resource_path("FA_logo.png")
            logo_img = Image.open(logo_path)
            logo_img = logo_img.resize((48, 48), Image.LANCZOS)
            self._logo = ImageTk.PhotoImage(logo_img)
            logo_label = tk.Label(header_frame, image=self._logo,
                                  bg=COLORS["pink_pale"])
            logo_label.pack(side="left", padx=(0, 10))
        except Exception as e:
            print(f"Could not load logo: {e}")

        title = ttk.Label(header_frame, text="Fantage Archive Cache Tool",
                          style="Header.TLabel")
        title.pack(side="left")

        # Dashed separator like it is in FA
        sep_canvas = tk.Canvas(main_frame, height=2, bg=COLORS["pink_pale"],
                               highlightthickness=0)
        sep_canvas.pack(fill="x", pady=(2, 6))
        sep_canvas.bind("<Configure>", lambda e: self._draw_dashed(sep_canvas))

        # Description
        desc = ttk.Label(main_frame,
                         text="Scans your computer for Fantage related cache files\nand extracts them into a zip folder.",
                         style="Desc.TLabel", justify="center")
        desc.pack(pady=(0, 12))

        # ============================================================
        #  Card: Search Scope
        # ============================================================
        scope_card = tk.Frame(main_frame, bg=COLORS["card_bg"],
                              highlightbackground=COLORS["border"],
                              highlightthickness=2, bd=0)
        scope_card.pack(fill="x", pady=(0, 10), ipady=10, ipadx=12)

        # Card header
        scope_header = tk.Frame(scope_card, bg=COLORS["card_bg"])
        scope_header.pack(fill="x", padx=12, pady=(8, 0))

        tk.Label(scope_header, text="SEARCH SCOPE",
                 bg=COLORS["card_bg"], fg=COLORS["pink_dark"],
                 font=FONT_LABEL).pack(side="left")

        # Path display
        self.selected_dir = tk.StringVar(value="Browser Caches Only (Default)")
        path_frame = tk.Frame(scope_card, bg=COLORS["card_bg"])
        path_frame.pack(fill="x", padx=12, pady=(6, 0))

        self.path_label = tk.Label(path_frame, textvariable=self.selected_dir,
                                   bg=COLORS["pink_light"], fg=COLORS["text_mid"],
                                   font=FONT_ENTRY, anchor="w",
                                   padx=10, pady=5,
                                   relief="flat",
                                   highlightbackground=COLORS["border"],
                                   highlightthickness=1)
        self.path_label.pack(side="left", fill="x", expand=True)

        # Browse button
        self.browse_btn_frame = tk.Frame(path_frame, bg=COLORS["card_bg"])
        self.browse_btn_frame.pack(side="right", padx=(8, 0))
        self.browse_btn = RoundedButton(
            self.browse_btn_frame, text="Browse…", command=self.browse_directory,
            bg=COLORS["pink_light"], fg=COLORS["pink_dark"],
            hover_bg=COLORS["pink_mid"], width=90, height=30,
            radius=14, font=FONT_BTN_SM
        )
        self.browse_btn.pack()

        self.custom_path = None

        # ============================================================
        #  Card: Keyword
        # ============================================================
        kw_card = tk.Frame(main_frame, bg=COLORS["card_bg"],
                           highlightbackground=COLORS["border"],
                           highlightthickness=2, bd=0)
        kw_card.pack(fill="x", pady=(0, 10), ipady=10, ipadx=12)

        kw_header = tk.Frame(kw_card, bg=COLORS["card_bg"])
        kw_header.pack(fill="x", padx=12, pady=(8, 0))

        tk.Label(kw_header, text="SEARCH KEYWORD",
                 bg=COLORS["card_bg"], fg=COLORS["pink_dark"],
                 font=FONT_LABEL).pack(side="left")

        kw_input_frame = tk.Frame(kw_card, bg=COLORS["card_bg"])
        kw_input_frame.pack(fill="x", padx=12, pady=(6, 0))

        self.keyword_var = tk.StringVar(value="fantage")
        self.keyword_entry = tk.Entry(
            kw_input_frame, textvariable=self.keyword_var,
            bg=COLORS["pink_light"], fg=COLORS["text_dark"],
            font=FONT_ENTRY, relief="flat",
            highlightbackground=COLORS["border"], highlightthickness=1,
            insertbackground=COLORS["pink_hot"],
            selectbackground=COLORS["pink_mid"],
            selectforeground=COLORS["white"]
        )
        self.keyword_entry.pack(fill="x", ipady=5)

        tk.Label(kw_input_frame,
                 text="Files and folders matching this keyword will be extracted",
                 bg=COLORS["card_bg"], fg=COLORS["text_light"],
                 font=("Varela Round", 8)).pack(anchor="w", pady=(3, 0))

        # ============================================================
        #  Card: Username
        # ============================================================
        user_card = tk.Frame(main_frame, bg=COLORS["card_bg"],
                             highlightbackground=COLORS["border"],
                             highlightthickness=2, bd=0)
        user_card.pack(fill="x", pady=(0, 10), ipady=10, ipadx=12)

        user_header = tk.Frame(user_card, bg=COLORS["card_bg"])
        user_header.pack(fill="x", padx=12, pady=(8, 0))

        tk.Label(user_header, text="YOUR NAME",
                 bg=COLORS["card_bg"], fg=COLORS["pink_dark"],
                 font=FONT_LABEL).pack(side="left")

        user_input_frame = tk.Frame(user_card, bg=COLORS["card_bg"])
        user_input_frame.pack(fill="x", padx=12, pady=(6, 0))

        self.username_var = tk.StringVar(value="")

        # 32 characters max for the username
        def _limit_username(*args):
            val = self.username_var.get()
            if len(val) > 32:
                self.username_var.set(val[:32])
        self.username_var.trace_add("write", _limit_username)

        self.username_entry = tk.Entry(
            user_input_frame, textvariable=self.username_var,
            bg=COLORS["pink_light"], fg=COLORS["text_dark"],
            font=FONT_ENTRY, relief="flat",
            highlightbackground=COLORS["border"], highlightthickness=1,
            insertbackground=COLORS["pink_hot"],
            selectbackground=COLORS["pink_mid"],
            selectforeground=COLORS["white"]
        )
        self.username_entry.pack(fill="x", ipady=5)

        tk.Label(user_input_frame,
                 text="Discord or Fantage username (max 32 chars), which is added to output folder name",
                 bg=COLORS["card_bg"], fg=COLORS["text_light"],
                 font=("Varela Round", 8)).pack(anchor="w", pady=(3, 0))

        # ============================================================
        #  Progress Bar
        # ============================================================
        progress_frame = tk.Frame(main_frame, bg=COLORS["pink_pale"])
        progress_frame.pack(fill="x", pady=(6, 4))

        self.progress = ttk.Progressbar(
            progress_frame, orient="horizontal",
            length=400, mode="indeterminate",
            style="Pink.Horizontal.TProgressbar"
        )
        self.progress.pack(fill="x")

        # ============================================================
        #  Status
        # ============================================================
        self.status_var = tk.StringVar(value="Ready to scan")
        self.status_label = ttk.Label(main_frame, textvariable=self.status_var,
                                       style="Status.TLabel")
        self.status_label.pack(pady=(2, 8))

        # ============================================================
        #  Action Buttons
        # ============================================================
        btn_frame = tk.Frame(main_frame, bg=COLORS["pink_pale"])
        btn_frame.pack(pady=(0, 4))

        self.start_btn = RoundedButton(
            btn_frame, text="Start Extraction",
            command=self.start_scan,
            bg=COLORS["pink_hot"], fg=COLORS["white"],
            hover_bg=COLORS["pink_dark"],
            width=180, height=40, radius=20, font=FONT_BTN
        )
        self.start_btn.pack(side="left", padx=8)

        self.stop_btn = RoundedButton(
            btn_frame, text="Stop",
            command=self.stop_scan,
            bg=COLORS["pink_light"], fg=COLORS["text_mid"],
            hover_bg=COLORS["pink_mid"],
            width=90, height=40, radius=20, font=FONT_BTN_SM
        )
        self.stop_btn.pack(side="left", padx=8)
        self.stop_btn.set_disabled(True)

        # GIF (that's one crazy monkey!) 
        self.gif_frames = []
        try:
            i = 0
            while True:
                try:
                    img_path = resource_path("thatsonecrazymonkey.gif")
                    frame = tk.PhotoImage(file=img_path, format=f"gif -index {i}")
                    self.gif_frames.append(frame)
                    i += 1
                except tk.TclError:
                    break

            if self.gif_frames:
                self.img_label = tk.Label(main_frame, image=self.gif_frames[0],
                                          bg=COLORS["pink_pale"])
                self.img_label.pack(pady=(6, 0))
                self.animate_gif(0)
        except Exception as e:
            print(f"Could not load gif: {e}")

        self.extractor = None
        self.thread = None

    def _draw_dashed(self, canvas):
        """Draw dashed separator line."""
        canvas.delete("all")
        w = canvas.winfo_width()
        x = 0
        while x < w:
            canvas.create_line(x, 1, min(x + 8, w), 1,
                             fill=COLORS["border"], width=2,
                             dash=(6, 4))
            x += 14

    def animate_gif(self, idx):
        frame = self.gif_frames[idx]
        self.img_label.configure(image=frame)
        next_idx = (idx + 1) % len(self.gif_frames)
        self.root.after(150, self.animate_gif, next_idx)

    def browse_directory(self):
        path = filedialog.askdirectory()
        if path:
            self.custom_path = path
            display_path = path if len(path) < 40 else "…" + path[-37:]
            self.selected_dir.set(display_path)
            self.status_var.set(f"Target: {display_path}")

    def start_scan(self):
        # Output goes next to the executable (PyInstaller) or project root (dev)
        if getattr(sys, 'frozen', False):
            output_dir = os.path.dirname(sys.executable)
        else:
            output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
        keyword = self.keyword_var.get().strip()
        if not keyword:
            messagebox.showerror("Error", "Please enter a search keyword.")
            return

        self.extractor = FantageExtractor(output_dir, self.update_status,
                                          search_path=self.custom_path,
                                          keyword=keyword,
                                          username=self.username_var.get().strip())

        self.start_btn.set_disabled(True)
        self.stop_btn.set_disabled(False)
        self.keyword_entry.config(state="disabled")
        self.username_entry.config(state="disabled")
        self.browse_btn.set_disabled(True)
        self.progress.start(10)

        self.thread = threading.Thread(target=self.run_extractor)
        self.thread.daemon = True
        self.thread.start()

    def stop_scan(self):
        if self.extractor:
            self.extractor.stop_event.set()
            self.status_var.set("Stopping…")

    def run_extractor(self):
        self.extractor.run()
        self.root.after(0, self.scan_finished)

    def update_status(self, message, progress_value=0):
        self.root.after(0, lambda: self.status_var.set(f"{message}"))

    def scan_finished(self):
        self.progress.stop()
        self.start_btn.set_disabled(False)
        self.stop_btn.set_disabled(True)
        self.browse_btn.set_disabled(False)
        self.keyword_entry.config(state="normal")
        self.username_entry.config(state="normal")

        # Show appropriate message based on what happened
        status = self.status_var.get()
        if "Stopped early" in status:
            self.status_var.set("Scan stopped... partial results saved.")
            messagebox.showinfo("Stopped", "Scan was stopped early.\nPartial results have been zipped and the folder has been opened.")
        elif "No files found" in status or "No cache" in status:
            self.status_var.set("No Fantage files found.")
            messagebox.showinfo("Done", "No matching files were found on this computer.")
        else:
            self.status_var.set("Scan complete!")
            messagebox.showinfo("Done", "Extraction complete! The folder has been opened.")

    def show_instructions(self):
        """Show a startup instructions dialog."""
        dialog = tk.Toplevel(self.root)
        dialog.title("Before You Start")
        dialog.geometry("460x420")
        dialog.configure(bg=COLORS["pink_pale"])
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        # Center on parent
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 460) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 420) // 2
        dialog.geometry(f"+{x}+{y}")

        # Header
        tk.Label(dialog, text="Important Instructions",
                 bg=COLORS["pink_pale"], fg=COLORS["pink_dark"],
                 font=("Patrick Hand", 18, "bold")).pack(pady=(16, 10))

        # Instructions card
        card = tk.Frame(dialog, bg=COLORS["card_bg"],
                        highlightbackground=COLORS["border"],
                        highlightthickness=2, bd=0)
        card.pack(fill="x", padx=20, pady=(0, 12), ipady=8)

        instructions = [
            ("1.", "Do NOT connect to the internet.\n    Browsers auto clear old caches when they sync."),
            ("2.", "Close ALL browsers before scanning.\n    Browsers may lock or overwrite cache files."),
            ("3.", "Do NOT clear your browser history or caches.\n    That's exactly what we're looking for!"),
            ("4.", "Enter your Discord or Fantage username\n    so we know who the cache belongs to."),
            ("5.", "After extraction, send the generated .zip file\n    to the Fantage Archive / Rewritten team."),
        ]

        for num, text in instructions:
            row = tk.Frame(card, bg=COLORS["card_bg"])
            row.pack(fill="x", padx=14, pady=(6, 0), anchor="w")

            tk.Label(row, text=num, bg=COLORS["card_bg"],
                     fg=COLORS["pink_hot"], font=("Varela Round", 10, "bold")
                     ).pack(side="left", anchor="n", padx=(0, 6))

            tk.Label(row, text=text, bg=COLORS["card_bg"],
                     fg=COLORS["text_dark"], font=("Varela Round", 9),
                     justify="left", anchor="w"
                     ).pack(side="left", anchor="w")

        # Got it button
        btn_frame = tk.Frame(dialog, bg=COLORS["pink_pale"])
        btn_frame.pack(pady=(4, 16))

        got_it = RoundedButton(
            btn_frame, text="Got it!",
            command=dialog.destroy,
            bg=COLORS["pink_hot"], fg=COLORS["white"],
            hover_bg=COLORS["pink_dark"],
            width=140, height=38, radius=18, font=FONT_BTN
        )
        got_it.pack()

        # Block until dismissed
        self.root.wait_window(dialog)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    app.show_instructions()
    root.mainloop()