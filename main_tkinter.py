import sys
import os
import subprocess
import shutil
import threading
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


def find_yt_dlp():
    path = shutil.which("yt-dlp")
    return path if path else "yt-dlp"


def find_deno():
    path = shutil.which("deno")
    if path:
        return path
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for p in winget.glob("DenoLand.Deno_*"):
        exe = p / "deno.exe"
        if exe.exists():
            return str(exe)
    return None


def clean_url(url):
    from urllib.parse import urlparse, parse_qs, urlunparse
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    qs.pop('list', None)
    qs.pop('si', None)
    qs.pop('pp', None)
    qs.pop('t', None)
    new_query = '&'.join(f"{k}={v[0]}" for k, v in qs.items())
    return urlunparse(parsed._replace(query=new_query))


COLORS = {
    "bg_dark": "#1a1a2e",
    "bg_mid": "#16213e",
    "bg_card": "#0f3460",
    "accent": "#e94560",
    "accent_hover": "#ff6b81",
    "green": "#00b894",
    "green_dark": "#009974",
    "yellow": "#fdcb6e",
    "red": "#d63031",
    "text": "#ffffff",
    "text_dim": "#a0a0b0",
    "text_muted": "#6c6c80",
    "progress_bg": "#2d2d44",
    "progress_fill": "#e94560",
    "input_bg": "#1e1e3a",
    "input_border": "#3d3d5c",
    "input_focus": "#e94560",
}


class YTDownloaderApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("YouTube Downloader")
        self.root.geometry("920x680")
        self.root.minsize(800, 550)
        self.root.configure(bg=COLORS["bg_dark"])

        self.deno_path = find_deno()
        self.yt_dlp_path = find_yt_dlp()
        self.cookie_file = None

        self.setup_styles()
        self.build_ui()
        self.downloads = []

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("TFrame", background=COLORS["bg_dark"])
        style.configure("Card.TFrame", background=COLORS["bg_mid"])
        style.configure("TLabel", background=COLORS["bg_dark"], foreground=COLORS["text"],
                         font=("Segoe UI", 10))
        style.configure("Title.TLabel", background=COLORS["bg_dark"], foreground=COLORS["accent"],
                         font=("Segoe UI", 22, "bold"))
        style.configure("Subtitle.TLabel", background=COLORS["bg_dark"], foreground=COLORS["text_dim"],
                         font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=COLORS["bg_mid"], foreground=COLORS["text"],
                         font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", background=COLORS["bg_dark"], foreground=COLORS["green"],
                         font=("Consolas", 9))
        style.configure("Dim.TLabel", background=COLORS["bg_mid"], foreground=COLORS["text_muted"],
                         font=("Segoe UI", 9))

        style.configure("Accent.TButton", background=COLORS["accent"], foreground=COLORS["text"],
                         font=("Segoe UI", 11, "bold"), borderwidth=0, padding=(0, 12))
        style.map("Accent.TButton",
                   background=[("active", COLORS["accent_hover"]), ("pressed", "#c0392b")])

        style.configure("Secondary.TButton", background=COLORS["bg_card"], foreground=COLORS["text"],
                         font=("Segoe UI", 9), borderwidth=0, padding=(0, 8))
        style.map("Secondary.TButton",
                   background=[("active", "#1a4a7a")])

        style.configure("Danger.TButton", background=COLORS["red"], foreground=COLORS["text"],
                         font=("Segoe UI", 9), borderwidth=0, padding=(0, 8))
        style.map("Danger.TButton",
                   background=[("active", "#e74c3c")])

        style.configure("Custom.TCombobox", fieldbackground=COLORS["input_bg"],
                         background=COLORS["input_bg"], foreground=COLORS["text"],
                         selectbackground=COLORS["accent"], selectforeground=COLORS["text"],
                         borderwidth=0, padding=8)
        style.map("Custom.TCombobox",
                   fieldbackground=[("readonly", COLORS["input_bg"])])

        style.configure("Custom.Horizontal.TProgressbar",
                         troughcolor=COLORS["progress_bg"],
                         background=COLORS["accent"],
                         thickness=20, borderwidth=0)

        style.configure("Green.Horizontal.TProgressbar",
                         troughcolor=COLORS["progress_bg"],
                         background=COLORS["green"],
                         thickness=20, borderwidth=0)

        style.configure("Red.Horizontal.TProgressbar",
                         troughcolor=COLORS["progress_bg"],
                         background=COLORS["red"],
                         thickness=20, borderwidth=0)

    def build_ui(self):
        container = ttk.Frame(self.root)
        container.pack(fill="both", expand=True, padx=20, pady=15)

        ttk.Label(container, text="YouTube Downloader", style="Title.TLabel").pack(anchor="w")
        ttk.Label(container, text="Paste a URL and download instantly", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 15))

        url_frame = ttk.Frame(container)
        url_frame.pack(fill="x", pady=(0, 12))

        self.url_var = tk.StringVar()
        self.url_entry = tk.Entry(url_frame, textvariable=self.url_var,
                                   bg=COLORS["input_bg"], fg=COLORS["text"],
                                   insertbackground=COLORS["text"],
                                   font=("Segoe UI", 12),
                                   relief="flat", bd=0,
                                   highlightthickness=2,
                                   highlightbackground=COLORS["input_border"],
                                   highlightcolor=COLORS["accent"])
        self.url_entry.pack(fill="x", ipady=10)
        self.url_entry.bind("<Return>", lambda e: self.start_download())
        self.url_entry.focus()

        opts_frame = ttk.Frame(container)
        opts_frame.pack(fill="x", pady=(0, 12))

        ttk.Label(opts_frame, text="Type:", style="Section.TLabel").grid(row=0, column=0, padx=(0, 8))
        self.type_var = tk.StringVar(value="Video")
        type_menu = ttk.Combobox(opts_frame, textvariable=self.type_var,
                                  values=["Video", "Audio"], state="readonly",
                                  style="Custom.TCombobox", width=10)
        type_menu.grid(row=0, column=1, padx=(0, 20))
        type_menu.bind("<<ComboboxSelected>>", self.on_type_change)

        ttk.Label(opts_frame, text="Quality:", style="Section.TLabel").grid(row=0, column=2, padx=(0, 8))
        self.quality_var = tk.StringVar(value="Highest")
        self.quality_menu = ttk.Combobox(opts_frame, textvariable=self.quality_var,
                                          values=["Highest", "720p", "480p", "360p", "240p", "144p", "Lowest"],
                                          state="readonly",
                                          style="Custom.TCombobox", width=12)
        self.quality_menu.grid(row=0, column=3, padx=(0, 20))

        ttk.Label(opts_frame, text="Save to:", style="Section.TLabel").grid(row=0, column=4, padx=(0, 8))
        downloads_path = Path.home() / "Downloads" / "YouTubeDownloader"
        downloads_path.mkdir(parents=True, exist_ok=True)
        self.dir_var = tk.StringVar(value=str(downloads_path))
        self.dir_entry = tk.Entry(opts_frame, textvariable=self.dir_var,
                                   bg=COLORS["input_bg"], fg=COLORS["text"],
                                   font=("Segoe UI", 9), relief="flat", bd=0,
                                   highlightthickness=1,
                                   highlightbackground=COLORS["input_border"],
                                   highlightcolor=COLORS["accent"], width=22)
        self.dir_entry.grid(row=0, column=5, padx=(0, 6), ipady=4)

        browse_btn = ttk.Button(opts_frame, text="...", style="Secondary.TButton",
                                 command=self.browse_dir, width=4)
        browse_btn.grid(row=0, column=6)

        btn_frame = ttk.Frame(container)
        btn_frame.pack(fill="x", pady=(0, 12))

        self.dl_btn = ttk.Button(btn_frame, text="Download", style="Accent.TButton",
                                  command=self.start_download)
        self.dl_btn.pack(fill="x", ipady=4)

        auth_frame = tk.Frame(container, bg=COLORS["bg_mid"], highlightbackground=COLORS["input_border"],
                               highlightthickness=1)
        auth_frame.pack(fill="x", pady=(0, 12))

        inner_auth = ttk.Frame(auth_frame)
        inner_auth.configure(style="Card.TFrame")
        inner_auth.pack(fill="x", padx=15, pady=10)

        auth_row = ttk.Frame(inner_auth)
        auth_row.configure(style="Card.TFrame")
        auth_row.pack(fill="x")

        ttk.Label(auth_row, text="Browser:", style="Section.TLabel").pack(side="left", padx=(0, 8))
        self.browser_var = tk.StringVar(value="None")
        browser_menu = ttk.Combobox(auth_row, textvariable=self.browser_var,
                                      values=["None", "chrome", "edge", "firefox", "brave", "opera"],
                                      state="readonly", style="Custom.TCombobox", width=10)
        browser_menu.pack(side="left", padx=(0, 12))

        ttk.Button(auth_row, text="Browse cookies.txt", style="Secondary.TButton",
                    command=self.browse_cookies).pack(side="left", padx=(0, 12))

        self.cookies_label = tk.Label(auth_row, text="No cookies file selected",
                                       bg=COLORS["bg_mid"], fg=COLORS["text_muted"],
                                       font=("Segoe UI", 9))
        self.cookies_label.pack(side="left")

        deno_status = "OK" if self.deno_path else "NOT FOUND"
        deno_color = COLORS["green"] if self.deno_path else COLORS["red"]
        status_frame = ttk.Frame(inner_auth)
        status_frame.configure(style="Card.TFrame")
        status_frame.pack(fill="x", pady=(6, 0))
        tk.Label(status_frame, text=f"yt-dlp: OK  |  deno: {deno_status}",
                  bg=COLORS["bg_mid"], fg=deno_color, font=("Consolas", 9)).pack(side="left")

        hint = tk.Label(inner_auth, text="If downloads fail: close browser, select it above, or export cookies.txt",
                         bg=COLORS["bg_mid"], fg=COLORS["yellow"], font=("Segoe UI", 8), wraplength=700)
        hint.pack(anchor="w", pady=(4, 0))

        dl_label_frame = ttk.Frame(container)
        dl_label_frame.pack(fill="x", pady=(0, 6))
        ttk.Label(dl_label_frame, text="Active Downloads", style="Section.TLabel").pack(side="left")

        list_frame = tk.Frame(container, bg=COLORS["bg_dark"], highlightbackground=COLORS["input_border"],
                               highlightthickness=1)
        list_frame.pack(fill="both", expand=True, pady=(0, 8))

        self.download_canvas = tk.Canvas(list_frame, bg=COLORS["bg_dark"],
                                          highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical",
                                   command=self.download_canvas.yview)
        self.download_inner = ttk.Frame(self.download_canvas)
        self.download_inner.configure(style="TFrame")

        self.download_inner.bind("<Configure>",
                                  lambda e: self.download_canvas.configure(
                                      scrollregion=self.download_canvas.bbox("all")))

        self.canvas_window = self.download_canvas.create_window((0, 0), window=self.download_inner,
                                                                  anchor="nw")
        self.download_canvas.configure(yscrollcommand=scrollbar.set)

        self.download_canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.download_canvas.bind("<Configure>", self._on_canvas_configure)
        self.download_inner.bind("<Configure>", self._on_inner_configure)

        self._bind_mousewheel(self.download_canvas)

    def _on_canvas_configure(self, event):
        self.download_canvas.itemconfig(self.canvas_window, width=event.width)

    def _on_inner_configure(self, event):
        self.download_canvas.configure(scrollregion=self.download_canvas.bbox("all"))

    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", self._on_mousewheel)
        widget.bind("<Button-5>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        if event.num == 4:
            self.download_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.download_canvas.yview_scroll(1, "units")
        else:
            self.download_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_type_change(self, event=None):
        if self.type_var.get() == "Audio":
            self.quality_menu.configure(values=["Highest", "128kbps", "64kbps"])
            self.quality_var.set("Highest")
        else:
            self.quality_menu.configure(values=["Highest", "720p", "480p", "360p", "240p", "144p", "Lowest"])
            self.quality_var.set("Highest")

    def browse_dir(self):
        d = filedialog.askdirectory(title="Select Download Directory")
        if d:
            self.dir_var.set(d)

    def browse_cookies(self):
        f = filedialog.askopenfilename(title="Select cookies.txt",
                                        filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if f:
            self.cookie_file = f
            self.browser_var.set("None")
            self.cookies_label.configure(text=f"Using: {Path(f).name}", fg=COLORS["text"])

    def start_download(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showwarning("Error", "Please enter a YouTube URL")
            return
        if not url.startswith(('http://', 'https://')):
            messagebox.showwarning("Error", "Please enter a valid URL")
            return

        browser = self.browser_var.get()
        cookie_browser = browser if browser != "None" else None
        cookie_file = self.cookie_file if not cookie_browser else None

        dl = DownloadCard(self.download_inner, url,
                          self.quality_var.get(),
                          self.type_var.get(),
                          self.dir_var.get(),
                          cookie_browser, cookie_file)
        dl.pack(fill="x", padx=5, pady=4)
        self.downloads.append(dl)
        dl.start()

        self.url_var.set("")
        self.url_entry.focus()

    def run(self):
        self.root.mainloop()


class DownloadCard(tk.Frame):
    def __init__(self, parent, url, quality, dl_type, output_path,
                 cookie_browser, cookie_file):
        super().__init__(parent, bg=COLORS["bg_mid"], highlightbackground=COLORS["input_border"],
                          highlightthickness=1)
        self.url = url
        self.quality = quality
        self.dl_type = dl_type
        self.output_path = output_path
        self.cookie_browser = cookie_browser
        self.cookie_file = cookie_file
        self.title = "Loading..."
        self.progress = 0
        self.status = "Starting"
        self.status_color = COLORS["text_dim"]

        self.configure(padx=15, pady=10)

        top = tk.Frame(self, bg=COLORS["bg_mid"])
        top.pack(fill="x")

        self.title_label = tk.Label(top, text=f"Loading... ({clean_url(url)})",
                                     bg=COLORS["bg_mid"], fg=COLORS["text"],
                                     font=("Segoe UI", 11, "bold"), anchor="w",
                                     wraplength=650, justify="left")
        self.title_label.pack(side="left", fill="x", expand=True)

        self.status_label = tk.Label(top, text="Starting",
                                      bg=COLORS["bg_mid"], fg=COLORS["text_dim"],
                                      font=("Segoe UI", 9), anchor="e")
        self.status_label.pack(side="right")

        mid = tk.Frame(self, bg=COLORS["bg_mid"])
        mid.pack(fill="x", pady=(4, 0))
        tk.Label(mid, text=f"{dl_type} - {quality}", bg=COLORS["bg_mid"],
                  fg=COLORS["text_muted"], font=("Segoe UI", 9)).pack(side="left")

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(mid, variable=self.progress_var,
                                             maximum=100, mode="determinate",
                                             style="Custom.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", side="left", expand=True, padx=(10, 0))

        self.pct_label = tk.Label(mid, text="0%", bg=COLORS["bg_mid"],
                                   fg=COLORS["text_dim"], font=("Consolas", 9), width=5)
        self.pct_label.pack(side="right")

    def start(self):
        thread = threading.Thread(target=self._run_download, daemon=True)
        thread.start()

    def _run_download(self):
        url = clean_url(self.url)

        try:
            self._update_status("Fetching video info...", COLORS["text_dim"])

            info_cmd = [
                self._find_yt_dlp(), '--no-warnings', '--print', 'title',
                '--no-download', url,
            ]
            self._add_cookie_args(info_cmd)

            info_result = subprocess.run(info_cmd, capture_output=True, text=True,
                                          timeout=60, encoding='utf-8', errors='replace')

            if info_result.returncode != 0:
                error = info_result.stderr.strip()
                if "Sign in" in error or "bot" in error.lower():
                    self._update_status("Bot detection! Use cookies.", COLORS["red"])
                else:
                    self._update_status(f"Error: {error[:80]}", COLORS["red"])
                return

            self.title = info_result.stdout.strip().split('\n')[0] or "Unknown Video"
            self._update_status(f"Found: {self.title}", COLORS["green"])

            if self.dl_type == "Audio":
                fmt = 'bestaudio/best'
            elif self.quality == "Highest":
                fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            elif self.quality == "Lowest":
                fmt = "worst[ext=mp4]/worst"
            else:
                h = self.quality.replace('p', '')
                fmt = (f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]"
                       f"/best[height<={h}][ext=mp4]/best[ext=mp4]/best")

            self._update_status(f"Downloading ({self.quality})...", COLORS["text_dim"])

            dl_cmd = [
                self._find_yt_dlp(), '--no-warnings', '--newline',
                '-f', fmt,
                '-o', os.path.join(self.output_path, '%(title)s.%(ext)s'),
                '--progress', url,
            ]

            if self.dl_type == "Audio":
                dl_cmd.insert(1, '--extract-audio')
                dl_cmd.insert(2, '--audio-format')
                dl_cmd.insert(3, 'mp3')
                dl_cmd.insert(4, '--audio-quality')
                dl_cmd.insert(5, '192')
            else:
                dl_cmd.insert(1, '--merge-output-format')
                dl_cmd.insert(2, 'mp4')

            self._add_cookie_args(dl_cmd)

            process = subprocess.Popen(
                dl_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding='utf-8', errors='replace',
                bufsize=1, universal_newlines=True
            )

            for line in process.stdout:
                line = line.strip()
                if '[download]' in line and '%' in line:
                    try:
                        pct_str = line.split()[-2].replace('%', '')
                        pct = float(pct_str)
                        self._update_progress(pct)
                    except (ValueError, IndexError):
                        pass
                elif '[download] Destination:' in line:
                    fname = line.split('Destination:')[-1].strip()
                    if fname:
                        self.title = Path(fname).stem
                        self._update_title()
                elif '[ExtractAudio]' in line:
                    self._update_status("Converting to MP3...", COLORS["yellow"])

            process.wait()

            if process.returncode == 0:
                self._update_progress(100)
                self._update_status("Completed", COLORS["green"])
                self.title_label.configure(fg=COLORS["green"])
                self.progress_bar.configure(style="Green.Horizontal.TProgressbar")
            else:
                self._update_status("Download failed", COLORS["red"])
                self.progress_bar.configure(style="Red.Horizontal.TProgressbar")

        except Exception as e:
            self._update_status(f"Error: {str(e)[:80]}", COLORS["red"])

    def _find_yt_dlp(self):
        path = shutil.which("yt-dlp")
        return path if path else "yt-dlp"

    def _add_cookie_args(self, cmd):
        if self.cookie_browser and self.cookie_browser != "None":
            idx = 1
            cmd.insert(idx, '--cookies-from-browser')
            cmd.insert(idx + 1, self.cookie_browser)
        elif self.cookie_file:
            idx = 1
            cmd.insert(idx, '--cookies')
            cmd.insert(idx + 1, self.cookie_file)

    def _update_title(self):
        display = self.title if len(self.title) < 60 else self.title[:57] + "..."
        self.title_label.configure(text=display)

    def _update_status(self, text, color):
        def _set():
            self.status = text
            self.status_label.configure(text=text, fg=color)
        self.after(0, _set)

    def _update_progress(self, pct):
        def _set():
            self.progress = pct
            self.progress_var.set(pct)
            self.pct_label.configure(text=f"{int(pct)}%")
        self.after(0, _set)


def main():
    app = YTDownloaderApp()
    app.run()


if __name__ == "__main__":
    main()
