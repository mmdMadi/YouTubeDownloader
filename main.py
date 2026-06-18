import sys
import os
import subprocess
import shutil
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTextEdit, QProgressBar, QComboBox, QFileDialog,
                               QMessageBox, QGroupBox, QGridLayout, QListWidget,
                               QListWidgetItem)
from PySide6.QtCore import QThread, Signal, Qt, QTimer
from PySide6.QtGui import QFont, QPalette, QColor
from multiprocessing import freeze_support


def find_yt_dlp():
    yt_dlp_path = shutil.which("yt-dlp")
    if yt_dlp_path:
        return yt_dlp_path
    for p in [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Links" / "yt-dlp.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "yt-dlp" / "yt-dlp.exe",
    ]:
        if p.exists():
            return str(p)
    return "yt-dlp"


def find_deno():
    deno_path = shutil.which("deno")
    if deno_path:
        return deno_path
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


YT_DLP_PATH = find_yt_dlp()
DENO_PATH = find_deno()

# Ensure deno is in PATH for yt-dlp
if DENO_PATH:
    deno_dir = str(Path(DENO_PATH).parent)
    os.environ["PATH"] = deno_dir + os.pathsep + os.environ.get("PATH", "")


class DownloadItem:
    def __init__(self, url, output_path, quality, download_type, title=""):
        self.url = url
        self.output_path = output_path
        self.quality = quality
        self.download_type = download_type
        self.title = title
        self.status = "pending"
        self.progress = 0
        self.error_message = ""


class DownloadThread(QThread):
    progress_signal = Signal(int)
    status_signal = Signal(str)
    finished_signal = Signal(bool, str)

    def __init__(self, download_item, cookie_browser=None, cookie_file=None):
        super().__init__()
        self.download_item = download_item
        self.cookie_browser = cookie_browser
        self.cookie_file = cookie_file

    def run(self):
        url = clean_url(self.download_item.url)

        try:
            self.status_signal.emit("Fetching video info...")

            info_cmd = [
                YT_DLP_PATH,
                '--no-warnings',
                '--print', 'title',
                '--no-download',
                url,
            ]
            if self.cookie_browser and self.cookie_browser != "None":
                info_cmd.insert(1, '--cookies-from-browser')
                info_cmd.insert(2, self.cookie_browser)
            elif self.cookie_file:
                info_cmd.insert(1, '--cookies')
                info_cmd.insert(2, self.cookie_file)

            info_result = subprocess.run(
                info_cmd, capture_output=True, text=True, timeout=60,
                encoding='utf-8', errors='replace'
            )

            if info_result.returncode != 0:
                error = info_result.stderr.strip()
                if "Sign in" in error or "bot" in error.lower():
                    self.finished_signal.emit(False,
                        "Bot detection! Close your browser and select it in settings, "
                        "or use a cookies.txt file with login session.")
                else:
                    self.finished_signal.emit(False, f"Failed: {error[:200]}")
                return

            video_title = info_result.stdout.strip().split('\n')[0] or "Unknown Video"
            self.download_item.title = video_title
            self.status_signal.emit(f"Found: {video_title}")

            if self.download_item.download_type == "Audio":
                fmt = 'bestaudio/best'
            else:
                if self.download_item.quality == "Highest":
                    fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
                elif self.download_item.quality == "Lowest":
                    fmt = "worst[ext=mp4]/worst"
                else:
                    h = self.download_item.quality.replace('p', '')
                    fmt = (f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]"
                           f"/best[height<={h}][ext=mp4]/best[ext=mp4]/best")

            self.status_signal.emit(f"Downloading ({self.download_item.quality})...")

            dl_cmd = [
                YT_DLP_PATH,
                '--no-warnings',
                '--newline',
                '-f', fmt,
                '-o', os.path.join(self.download_item.output_path, '%(title)s.%(ext)s'),
                '--progress',
                url,
            ]

            if self.download_item.download_type == "Audio":
                dl_cmd.insert(1, '--extract-audio')
                dl_cmd.insert(2, '--audio-format')
                dl_cmd.insert(3, 'mp3')
                dl_cmd.insert(4, '--audio-quality')
                dl_cmd.insert(5, '192')
            else:
                dl_cmd.insert(1, '--merge-output-format')
                dl_cmd.insert(2, 'mp4')

            if self.cookie_browser and self.cookie_browser != "None":
                dl_cmd.insert(1, '--cookies-from-browser')
                dl_cmd.insert(2, self.cookie_browser)
            elif self.cookie_file:
                dl_cmd.insert(1, '--cookies')
                dl_cmd.insert(2, self.cookie_file)

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
                        pct = int(float(pct_str))
                        self.progress_signal.emit(pct)
                    except (ValueError, IndexError):
                        pass
                elif '[download] Destination:' in line:
                    fname = line.split('Destination:')[-1].strip()
                    if fname:
                        self.download_item.title = Path(fname).stem
                elif '[ExtractAudio]' in line:
                    self.status_signal.emit("Converting to MP3...")

            process.wait()

            if process.returncode == 0:
                self.status_signal.emit("Done!")
                self.finished_signal.emit(True, f"Downloaded: {self.download_item.title}")
            else:
                self.finished_signal.emit(False, "Download failed")

        except subprocess.TimeoutExpired:
            self.finished_signal.emit(False, "Download timed out")
        except Exception as e:
            self.finished_signal.emit(False, f"Error: {str(e)}")


class YouTubeDownloader(QMainWindow):
    def __init__(self):
        super().__init__()
        self.active_downloads = []
        self.download_threads = []
        self.cookie_file = None
        self.init_ui()
        self.apply_dark_theme()

        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.update_display)
        self.refresh_timer.start(500)

    def apply_dark_theme(self):
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.Text, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ColorRole.ButtonText, QColor(255, 255, 255))
        dark_palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 0, 0))
        dark_palette.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
        self.setPalette(dark_palette)

        self.setStyleSheet("""
            QMainWindow { background-color: #353535; }
            QGroupBox {
                font-weight: bold; border: 2px solid #555555;
                border-radius: 5px; margin-top: 1ex; padding-top: 10px;
                background-color: #2d2d2d;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px;
                padding: 0 5px 0 5px; color: #ffffff;
            }
            QLineEdit {
                background-color: #404040; border: 2px solid #555555;
                border-radius: 5px; padding: 8px; color: #ffffff; font-size: 12px;
            }
            QLineEdit:focus { border: 2px solid #4CAF50; }
            QComboBox {
                background-color: #404040; border: 2px solid #555555;
                border-radius: 5px; padding: 8px; color: #ffffff; font-size: 12px;
                min-width: 6em;
            }
            QComboBox:hover { border: 2px solid #4CAF50; }
            QComboBox::drop-down { border: none; width: 20px; }
            QComboBox::down-arrow {
                image: none; border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff; margin-right: 5px;
            }
            QComboBox::down-arrow:on { border-top: 5px solid #4CAF50; }
            QComboBox QAbstractItemView {
                background-color: #404040; border: 2px solid #555555;
                selection-background-color: #4CAF50; color: #ffffff;
            }
            QPushButton {
                background-color: #4CAF50; color: #ffffff; border: none;
                border-radius: 5px; padding: 10px; font-size: 14px; font-weight: bold;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:pressed { background-color: #3d8b40; }
            QPushButton:disabled { background-color: #666666; color: #999999; }
            QTextEdit {
                background-color: #2d2d2d; border: 2px solid #555555;
                border-radius: 5px; padding: 10px; color: #ffffff;
                font-family: 'Consolas', 'Monaco', monospace; font-size: 12px;
            }
            QProgressBar {
                border: 2px solid #555555; border-radius: 5px;
                text-align: center; background-color: #404040; color: #ffffff;
            }
            QProgressBar::chunk { background-color: #4CAF50; border-radius: 3px; }
            QLabel { color: #ffffff; }
            QListWidget {
                background-color: #2d2d2d; border: 2px solid #555555;
                border-radius: 5px; color: #ffffff; font-size: 12px;
            }
            QListWidget::item { padding: 12px; border-bottom: 1px solid #555555; min-height: 80px; }
            QListWidget::item:selected { background-color: #4CAF50; }
            QListWidget::item:hover { background-color: #404040; }
        """)

    def init_ui(self):
        self.setWindowTitle("YouTube Downloader")
        self.setGeometry(100, 100, 900, 650)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        title_label = QLabel("YouTube Downloader")
        title_label.setFont(QFont("Arial", 18, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("color: #4CAF50; margin-bottom: 5px;")
        main_layout.addWidget(title_label)

        input_group = QGroupBox("Download")
        input_layout = QGridLayout(input_group)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter YouTube URL...")
        self.url_input.setMinimumHeight(40)
        self.url_input.returnPressed.connect(self.start_download)
        input_layout.addWidget(self.url_input, 0, 0, 1, 3)

        type_label = QLabel("Type:")
        type_label.setStyleSheet("color: #ffffff; font-weight: bold;")
        input_layout.addWidget(type_label, 1, 0)
        self.type_combo = QComboBox()
        self.type_combo.addItems(["Video", "Audio"])
        self.type_combo.currentTextChanged.connect(self.on_type_changed)
        input_layout.addWidget(self.type_combo, 1, 1)

        quality_label = QLabel("Quality:")
        quality_label.setStyleSheet("color: #ffffff; font-weight: bold;")
        input_layout.addWidget(quality_label, 1, 2)
        self.quality_combo = QComboBox()
        self.quality_combo.addItems(["Highest", "720p", "480p", "360p", "240p", "144p", "Lowest"])
        input_layout.addWidget(self.quality_combo, 1, 3)

        dir_label = QLabel("Save to:")
        dir_label.setStyleSheet("color: #ffffff; font-weight: bold;")
        input_layout.addWidget(dir_label, 2, 0)
        self.dir_input = QLineEdit()
        downloads_path = Path.home() / "Downloads" / "YouTubeDownloader"
        downloads_path.mkdir(parents=True, exist_ok=True)
        self.dir_input.setText(str(downloads_path))
        self.dir_input.setReadOnly(True)
        input_layout.addWidget(self.dir_input, 2, 1, 1, 2)
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setMaximumWidth(80)
        self.browse_btn.clicked.connect(self.browse_directory)
        input_layout.addWidget(self.browse_btn, 2, 3)

        self.download_btn = QPushButton("Download")
        self.download_btn.setMinimumHeight(50)
        self.download_btn.clicked.connect(self.start_download)
        input_layout.addWidget(self.download_btn, 3, 0, 1, 4)

        main_layout.addWidget(input_group)

        auth_group = QGroupBox("Authentication (if downloads fail)")
        auth_layout = QGridLayout(auth_group)

        auth_layout.addWidget(QLabel("Browser:"), 0, 0)
        self.browser_combo = QComboBox()
        self.browser_combo.addItems(["None", "chrome", "edge", "firefox", "brave", "opera", "vivaldi"])
        self.browser_combo.currentTextChanged.connect(self.on_browser_changed)
        auth_layout.addWidget(self.browser_combo, 0, 1)

        self.cookies_btn = QPushButton("Browse cookies.txt")
        self.cookies_btn.setMaximumWidth(160)
        self.cookies_btn.clicked.connect(self.browse_cookies)
        auth_layout.addWidget(self.cookies_btn, 0, 2)

        self.cookies_label = QLabel("No cookies file selected")
        self.cookies_label.setStyleSheet("color: #999999; font-size: 11px;")
        auth_layout.addWidget(self.cookies_label, 1, 0, 1, 3)

        status_parts = []
        status_parts.append(f"yt-dlp: {'OK' if YT_DLP_PATH != 'yt-dlp' else 'needs install'}")
        status_parts.append(f"deno: {'OK' if DENO_PATH else 'not found'}")
        self.status_info = QLabel(" | ".join(status_parts))
        self.status_info.setStyleSheet("color: #4CAF50; font-size: 11px;")
        auth_layout.addWidget(self.status_info, 2, 0, 1, 3)

        info = QLabel("If downloads fail: close your browser, then select it above. "
                       "Or export cookies.txt from youtube.com using 'Get cookies.txt LOCALLY' extension.")
        info.setStyleSheet("color: #ff9800; font-size: 11px;")
        info.setWordWrap(True)
        auth_layout.addWidget(info, 3, 0, 1, 3)

        main_layout.addWidget(auth_group)

        self.download_list = QListWidget()
        main_layout.addWidget(self.download_list)

        self.status_display = QTextEdit()
        self.status_display.setMaximumHeight(100)
        self.status_display.setReadOnly(True)
        main_layout.addWidget(self.status_display)

    def on_browser_changed(self, text):
        if text != "None":
            self.cookie_file = None
            self.cookies_label.setText(f"Using {text} browser cookies (close browser first!)")

    def on_type_changed(self, download_type):
        self.quality_combo.clear()
        if download_type == "Audio":
            self.quality_combo.addItems(["Highest", "128kbps", "64kbps"])
        else:
            self.quality_combo.addItems(["Highest", "720p", "480p", "360p", "240p", "144p", "Lowest"])

    def browse_directory(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Download Directory")
        if directory:
            self.dir_input.setText(directory)

    def browse_cookies(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select cookies.txt", "",
            "Text Files (*.txt);;All Files (*)")
        if path:
            self.cookie_file = path
            self.browser_combo.setCurrentText("None")
            name = Path(path).name
            self.cookies_label.setText(f"Using: {name}")

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Error", "Please enter a YouTube URL")
            return
        if not url.startswith(('http://', 'https://')):
            QMessageBox.warning(self, "Error", "Please enter a valid URL")
            return

        quality = self.quality_combo.currentText()
        download_type = self.type_combo.currentText()
        output_path = self.dir_input.text()

        browser = self.browser_combo.currentText()
        cookie_browser = browser if browser != "None" else None
        cookie_file = self.cookie_file if not cookie_browser else None

        download_item = DownloadItem(url, output_path, quality, download_type, "Loading...")
        self.active_downloads.append(download_item)

        idx = len(self.active_downloads) - 1
        item = QListWidgetItem()
        widget = self.create_download_widget()
        item.setSizeHint(widget.sizeHint())
        self.download_list.addItem(item)
        self.download_list.setItemWidget(item, widget)

        thread = DownloadThread(download_item, cookie_browser, cookie_file)
        thread.progress_signal.connect(lambda p, i=idx: self.on_progress(i, p))
        thread.status_signal.connect(lambda s, i=idx: self.on_status(i, s))
        thread.finished_signal.connect(lambda ok, msg, i=idx: self.on_finished(i, ok, msg))
        self.download_threads.append(thread)
        thread.start()

        self.url_input.clear()
        self.status_display.append(f"[{self.get_timestamp()}] Started: {url}")

    def create_download_widget(self):
        widget = QWidget()
        widget.setFixedHeight(100)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(6)
        widget.setStyleSheet("background-color: #262a2e; border-radius: 12px;")

        info_layout = QHBoxLayout()
        title_label = QLabel("Loading...")
        title_label.setObjectName("title_label")
        title_label.setStyleSheet("font-weight: bold; color: #fff; font-size: 14px;")
        title_label.setWordWrap(True)
        info_layout.addWidget(title_label, 1)

        status_label = QLabel("Starting")
        status_label.setObjectName("status_label")
        status_label.setStyleSheet("color: #cccccc; font-size: 12px;")
        status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        info_layout.addWidget(status_label, 0)
        layout.addLayout(info_layout)

        progress_bar = QProgressBar()
        progress_bar.setObjectName("progress_bar")
        progress_bar.setFixedHeight(18)
        progress_bar.setValue(0)
        progress_bar.setStyleSheet("""
            QProgressBar { border: 1px solid #555555; border-radius: 5px;
                           background-color: #2d2d2d; color: #ffffff; text-align: center; }
            QProgressBar::chunk { background-color: #4CAF50; border-radius: 4px; }
        """)
        layout.addWidget(progress_bar)

        return widget

    def on_progress(self, index, progress):
        if index < len(self.active_downloads):
            self.active_downloads[index].progress = progress

    def on_status(self, index, status):
        if index < len(self.active_downloads):
            self.active_downloads[index].status = status

    def on_finished(self, index, success, message):
        if index < len(self.active_downloads):
            dl = self.active_downloads[index]
            if success:
                dl.status = "completed"
                dl.progress = 100
                self.status_display.append(f"[{self.get_timestamp()}] Done: {dl.title}")
            else:
                dl.status = "failed"
                dl.error_message = message
                self.status_display.append(f"[{self.get_timestamp()}] Failed: {message}")

    def update_display(self):
        for i, dl in enumerate(self.active_downloads):
            if i >= self.download_list.count():
                break
            item = self.download_list.item(i)
            if not item:
                continue
            widget = self.download_list.itemWidget(item)
            if not widget:
                continue

            title_label = widget.findChild(QLabel, "title_label")
            status_label = widget.findChild(QLabel, "status_label")
            progress_bar = widget.findChild(QProgressBar, "progress_bar")

            title_text = dl.title if dl.title else "Loading..."
            title_label.setText(f"{i+1}. {title_text}")

            if isinstance(dl.status, str) and dl.status not in ("pending", "completed", "failed"):
                status_text = f"{dl.status} ({dl.progress}%)"
            elif dl.status == "completed":
                status_text = "Completed"
            elif dl.status == "failed":
                status_text = f"Failed - {dl.error_message}"
            else:
                status_text = "Starting"
            status_label.setText(status_text)

            progress_bar.setValue(dl.progress)

            if dl.status == "completed":
                item.setBackground(QColor(76, 175, 80, 30))
                progress_bar.setStyleSheet("""
                    QProgressBar { border: 1px solid #4CAF50; border-radius: 5px;
                                   background-color: #2d2d2d; color: #ffffff; }
                    QProgressBar::chunk { background-color: #4CAF50; border-radius: 4px; }
                """)
            elif dl.status == "failed":
                item.setBackground(QColor(244, 67, 54, 30))
                progress_bar.setStyleSheet("""
                    QProgressBar { border: 1px solid #f44336; border-radius: 5px;
                                   background-color: #2d2d2d; color: #ffffff; }
                    QProgressBar::chunk { background-color: #f44336; border-radius: 4px; }
                """)
            else:
                item.setBackground(QColor(33, 150, 243, 30))
                progress_bar.setStyleSheet("""
                    QProgressBar { border: 1px solid #555555; border-radius: 5px;
                                   background-color: #2d2d2d; color: #ffffff; }
                    QProgressBar::chunk { background-color: #4CAF50; border-radius: 4px; }
                """)

    def get_timestamp(self):
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    window = YouTubeDownloader()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    freeze_support()
    main()
