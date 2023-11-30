import os
import sys
import threading
import json
import clipboard
import keyboard
import re
from PyQt5.QtWidgets import *
from pytube import YouTube
from moviepy.editor import AudioFileClip
from PyQt5.QtCore import *
from PyQt5.QtGui import *

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class DownloadWorker(QObject):
    finished = pyqtSignal()

    def __init__(self, youtube_link, format_choice, output_folder):
        super().__init__()
        self.youtube_link = youtube_link
        self.format_choice = format_choice
        self.output_folder = output_folder

    def run(self):
        try:
            yt = YouTube(self.youtube_link)
            stream = yt.streams.get_highest_resolution() if self.format_choice == 'mp4' else yt.streams.get_audio_only()
            sanitized_title = ''.join(c if c != '/' else '-' for c in yt.title)
            stream.download(self.output_folder, filename=sanitized_title + '.' + self.format_choice)

            if self.format_choice == 'mp3':
                output_path = os.path.join(self.output_folder, f"{sanitized_title}.mp4")
                audio = AudioFileClip(output_path)
                audio.write_audiofile(output_path.replace('.mp4', '.mp3'))
                os.remove(output_path)

        except Exception as e:
            print(f"Error: {str(e)}")

        self.finished.emit()

class HotkeyConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Configure Hotkey')
        self.setMinimumWidth(300)

        self.hotkey_edit = QKeySequenceEdit(keyboard.read_hotkey() or QKeySequence('Ctrl+Shift+D'))

        layout = QFormLayout()
        layout.addRow('Current Hotkey:', QLabel(keyboard.read_hotkey()))
        layout.addRow('New Hotkey:', self.hotkey_edit)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        layout.addWidget(button_box)
        self.setLayout(layout)

        self.show()  # Show the dialog immediately

    def accept(self):
        new_hotkey = self.hotkey_edit.keySequence().toString()
        keyboard.remove_hotkey('ctrl+shift+d')
        keyboard.add_hotkey(new_hotkey, self.parent().download_from_clipboard)
        super().accept()

class YouTubeDownloaderGUI(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowIcon(QIcon(resource_path('yta.ico')))

        self.initUI()
        self.load_preferences()
        self.setSystemStyleAndPalette()  # Call the method to set system style and palette

    def initUI(self):
        self.setWindowTitle('YTAssistant')
        self.setFixedSize(400, 250)  # Make the window non-resizable

        main_layout = QVBoxLayout()  # Use a QVBoxLayout for vertical arrangement

        self.central_widget = QWidget(self)
        self.setCentralWidget(self.central_widget)
        self.central_widget.setLayout(main_layout)  # Set the main layout for the central widget

        self.label_link = QLabel('Enter YouTube link:')
        self.link_input = QLineEdit()
        self.label_format = QLabel('Choose format:')
        self.mp4_radio = QRadioButton('mp4')
        self.mp3_radio = QRadioButton('mp3')

        # Set 'mp4' as the default format choice
        self.mp4_radio.setChecked(True)

        self.download_button = QPushButton('Download')
        self.set_path_button = QPushButton('Set Download Path')
        self.config_hotkey_button = QPushButton('Configure Hotkey')

        main_layout.addWidget(self.label_link)
        main_layout.addWidget(self.link_input)
        main_layout.addWidget(self.label_format)
        main_layout.addWidget(self.mp4_radio)
        main_layout.addWidget(self.mp3_radio)

        # Create a QVBoxLayout for the buttons
        button_layout = QVBoxLayout()

        # Add the "Download" button and set its size policy to take more vertical space
        self.download_button.setMinimumHeight(40)
        self.download_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        button_layout.addWidget(self.download_button)

        # Create a QHBoxLayout for the "Set Download Path" and "Configure Hotkey" buttons
        sub_button_layout = QHBoxLayout()

        # Add the "Set Download Path" button and set its size policy to take less vertical space
        self.set_path_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sub_button_layout.addWidget(self.set_path_button)

        # Add the "Configure Hotkey" button and set its size policy to take less vertical space
        self.config_hotkey_button.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sub_button_layout.addWidget(self.config_hotkey_button)

        button_layout.addLayout(sub_button_layout)

        main_layout.addLayout(button_layout)
        
        # Create a QHBoxLayout for the entire bottom row
        bottom_layout = QHBoxLayout()
    
        # Create a QHBoxLayout for the theme toggle, align it left
        theme_layout = QHBoxLayout()
        self.theme_toggle = QCheckBox('Dark Theme', self)
        self.theme_toggle.stateChanged.connect(self.toggleTheme)
        theme_layout.addWidget(self.theme_toggle)
        theme_layout.addStretch(1)  # This will push the checkbox to the left
    
        # Add the theme layout to the bottom layout
        bottom_layout.addLayout(theme_layout)
    
        # Add a stretch item to push the status label to the right
        bottom_layout.addStretch(1)
    
        # Set up the status label, align it right
        self.status_label = QLabel('Ready')
        self.status_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom_layout.addWidget(self.status_label)

        bottom_layout.setContentsMargins(0, 0, 3, 0)

        # Set the bottom_layout to the bottom of the main layout
        main_layout.addLayout(bottom_layout)
    
        # Set the initial status message
        self.show_status_message('Ready')
        
        self.download_button.clicked.connect(self.start_download_thread)
        self.set_path_button.clicked.connect(self.set_default_download_path)
        self.config_hotkey_button.clicked.connect(self.configure_hotkey)

        self.download_worker = None
        self.hotkey = 'ctrl+shift+d'  # Default hotkey

        self.load_hotkey()

    def toggleTheme(self, state):
        # Toggle between dark and light themes based on the checkbox state
        self.dark_theme_enabled = state == Qt.Checked
        self.setSystemStyleAndPalette()
        self.save_preferences()

    def setSystemStyleAndPalette(self):
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)

        # Set the application style to follow the system style
        app.setStyle("Fusion")

        # Get the system palette
        system_palette = app.palette()

        # Update the color roles based on the dark mode state
        if hasattr(self, 'dark_theme_enabled') and self.dark_theme_enabled:
            # Dark mode colors
            system_palette.setColor(QPalette.Window, QColor(53, 53, 53))
            system_palette.setColor(QPalette.WindowText, Qt.white)
            system_palette.setColor(QPalette.Base, QColor(25, 25, 25))
            system_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))

            # Customize text and button colors for dark mode
            system_palette.setColor(QPalette.ButtonText, Qt.white)
            system_palette.setColor(QPalette.Button, QColor(53, 53, 53))

            # Customize input text color for dark mode
            system_palette.setColor(QPalette.Text, Qt.white)
            # Customize radio button and checkmark color for dark mode
            system_palette.setColor(QPalette.Highlight, Qt.white)
        else:
            # Light mode colors
            system_palette.setColor(QPalette.Window, Qt.white)
            system_palette.setColor(QPalette.WindowText, Qt.black)
            system_palette.setColor(QPalette.Base, QColor(240, 240, 240))
            system_palette.setColor(QPalette.AlternateBase, Qt.white)

            # Customize text and button colors for light mode
            system_palette.setColor(QPalette.ButtonText, Qt.black)
            system_palette.setColor(QPalette.Button, Qt.white)

            # Customize input text color for light mode
            system_palette.setColor(QPalette.Text, Qt.black)
            # Customize radio button and checkmark color for light mode
            system_palette.setColor(QPalette.Highlight, QColor(240, 240, 240))

        # Apply the modified palette
        app.setPalette(system_palette)

    def load_preferences(self):
        # Check if preferences file exists
        if not os.path.isfile('preferences.json'):
            # Create a default preferences file with default values
            default_preferences = {
                'default_download_path': os.path.join(os.path.dirname(__file__), 'downloads'),
                'hotkey': 'ctrl+shift+d',
            }
            with open('preferences.json', 'w') as file:
                json.dump(default_preferences, file)

        # Load preferences from the JSON file
        with open('preferences.json', 'r') as file:
            preferences = json.load(file)
            self.output_folder = preferences['default_download_path']
            self.hotkey = preferences['hotkey']

            # Check if 'dark_theme_enabled' key exists in the preferences file
            if 'dark_theme_enabled' in preferences:
                self.dark_theme_enabled = preferences['dark_theme_enabled']
            else:
                self.dark_theme_enabled = False  # Set to False by default if not found

        os.makedirs(self.output_folder, exist_ok=True)

        # Set the checkbox state based on the 'dark_theme_enabled' attribute
        self.theme_toggle.setChecked(self.dark_theme_enabled)

    def save_preferences(self):
        # Save preferences, including dark theme preference, to the JSON file
        preferences = {
            'default_download_path': self.output_folder,
            'hotkey': self.hotkey,
            'dark_theme_enabled': self.dark_theme_enabled,
        }
        with open('preferences.json', 'w') as file:
            json.dump(preferences, file)

    def set_default_download_path(self):
        options = QFileDialog.Options()
        options |= QFileDialog.ReadOnly
        folder_path = QFileDialog.getExistingDirectory(self, 'Select Default Download Path', options=options)
        if folder_path:
            self.output_folder = folder_path
            self.save_preferences()
            self.show_status_message(f'Default download path set: {folder_path}')

    def start_download_thread(self):
        youtube_link = self.link_input.text()
        format_choice = 'mp4' if self.mp4_radio.isChecked() else 'mp3'

        if not youtube_link:
            return

        self.download_button.setEnabled(False)
        self.download_worker = DownloadWorker(youtube_link, format_choice, self.output_folder)
        self.download_worker.finished.connect(self.on_download_finished)
        self.download_thread = threading.Thread(target=self.download_worker.run)
        self.download_thread.start()

    def on_download_finished(self):
        self.download_button.setEnabled(True)
        self.show_status_message('Download complete!')

    def download_from_clipboard(self):
        clipboard_text = clipboard.paste()
        if re.match(r'(https?://)?(www\.)?(youtube\.com|youtu\.?be)/.+', clipboard_text):
            self.link_input.setText(clipboard_text)
            self.start_download_thread()

    def configure_hotkey(self):
        dialog = HotkeyConfigDialog(self)
        result = dialog.exec_()
        if result == QDialog.Accepted:
            # Save new hotkey to preferences
            self.hotkey = dialog.hotkey_edit.keySequence().toString()
            self.save_preferences()
            self.load_hotkey()
            self.show_status_message(f'Hotkey updated: {self.hotkey}')

    def load_hotkey(self):
        try:
            keyboard.remove_hotkey(self.hotkey)
        except Exception:
            pass  # Ignore if hotkey is not registered
        keyboard.add_hotkey(self.hotkey, self.download_from_clipboard)

    def show_status_message(self, message):
        self.status_label.setText(message)
        QApplication.processEvents()

def main():
    app = QApplication(sys.argv)
    window = YouTubeDownloaderGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()