#!/usr/bin/python3

import sys
import os

# remove the directory of the current script
if '' in sys.path:
    sys.path.remove('')

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)


MX_UPDATER_PATH = "/usr/libexec/mx-updater"

if MX_UPDATER_PATH not in sys.path:
    sys.path.insert(0, MX_UPDATER_PATH)
#print(f"sys.path: {sys.path}")

from updater_translator import Translator


from PyQt6.QtWidgets import (QApplication, QDialog, QTextEdit, QVBoxLayout,
                             QDialogButtonBox, QMessageBox)
from PyQt6.QtGui import QIcon, QFont, QGuiApplication
from PyQt6.QtCore import Qt, QRect, QTranslator, QLocale, QLibraryInfo

# localization
LOCALE_DOMAIN = 'mx-updater'
LOCALE_DIR = '/usr/share/locale'

#print("translator = Translator(textdomain='mx-updater')")
translator = Translator(textdomain='mx-updater')
_ = translator.translate


'''
import gettext
LOCALE_DOMAIN = 'mx-updater'
LOCALE_DIR = '/usr/share/locale'
# bind the domain
gettext.bindtextdomain(LOCALE_DOMAIN, LOCALE_DIR)
gettext.textdomain(LOCALE_DOMAIN)
_ = gettext.gettext

'''

class LogViewer(QDialog):
    def __init__(self, file_path=None, view_cmd=None, icon_path=None,
                 window_class=None, window_title="Log Viewer",
                 default_width=960, default_height=600):
        """
        Initialize the LogViewer dialog with smart screen sizing.
        """
        super().__init__()

        self.setWindowTitle(window_title)

        if window_class:
            self.setProperty('class', window_class)

        if icon_path:
            if os.path.isfile(icon_path):
                self.setWindowIcon(QIcon(icon_path))
            else:
                # try icon from theme
                self.setWindowIcon(QIcon.fromTheme(icon_path))

        # VBox layout
        layout = QVBoxLayout()

        # text area
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)

        #self.text_area.setFont(QFont('monospace', 10))
        #self.text_area.setFont(QFont('Liberation Mono Regular', 11))
        self.text_area.setFont(QFont('Liberation Sans Regular', 11))
        #self.text_area.setFont(QFont('Courier New', 11))

        # standard button box with Close
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)  # Close and Esc

        # widgets to layout
        layout.addWidget(self.text_area)
        layout.addWidget(button_box)

        self.setLayout(layout)

        # load file if it exists
        if file_path:
            self.load_file(file_path, view_cmd)
        else:
            # If no file is provided, show a default message
            self.text_area.setPlainText("No file specified. Please provide a file path.")

        # Set initial size and center with smart scaling
        self.resize_and_center(default_width, default_height)

    def load_file(self, file_path, view_cmd=None):
        """
        Load file content into the text area.

        :param file_path: Path to the file to be viewed
        :param view_cmd: Command to view the file (optional)
        """
        try:
            # check file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            # with view_cmd given, read the file
            if view_cmd:
                import subprocess
                content = subprocess.check_output([view_cmd, file_path],
                                                  universal_newlines=True)
            else:
                # Otherwise, try to read the file directly
                with open(file_path, 'r') as f:
                    content = f.read()

            # Ensure some content
            if not content:
                content = "File is empty."

            self.text_area.setPlainText(content)
        except Exception as e:
            # show error in text area
            error_msg = f"Error loading file: {str(e)}"
            self.text_area.setPlainText(error_msg)
            # message box for the error - not used
            #QMessageBox.warning(self, "File Load Error", error_msg)

    def resize_and_center(self, default_width, default_height):
        """
        Resize and center the window with scaling.

        :param default_width: Desired window width
        :param default_height: Desired window height
        """
        #print(f"Original size: {default_width}x{default_height}")

        # Get the primary screen
        screen = QGuiApplication.primaryScreen()

        # Get available screen geometry (accounting for panels)
        available_geometry = screen.availableGeometry()
        #print(f"Screen available: {available_geometry.width()}x{available_geometry.height()}")

        # Calculate maximum allowed size while preserving aspect ratio
        max_width = int(available_geometry.width() * 0.9)  # 90% of available width
        max_height = int(available_geometry.height() * 0.9)  # 90% of available height
        #print(f"max_width x max_height: {max_width} x {max_height}")

        # Calculate scaling factors
        width_scale = max_width / default_width
        height_scale = max_height / default_height

        # Use the smaller scale to maintain aspect ratio, but not scale up
        scale = min(1.0, min(width_scale, height_scale))

        # Calculate final dimensions
        final_width = int(default_width * scale)
        final_height = int(default_height * scale)

        # Resize the window to exact calculated dimensions
        self.resize(final_width, final_height)

        # Calculate center position
        center_point = available_geometry.center()
        frame_geometry = self.frameGeometry()
        frame_geometry.moveCenter(center_point)

        # Ensure the window is within available screen space
        adjusted_pos = frame_geometry.topLeft()
        adjusted_pos.setX(max(available_geometry.left(),
                               min(adjusted_pos.x(),
                                   available_geometry.right() - frame_geometry.width())))
        adjusted_pos.setY(max(available_geometry.top(),
                               min(adjusted_pos.y(),
                                   available_geometry.bottom() - frame_geometry.height())))

        # Move the window
        self.move(adjusted_pos)

        #print(f"Final size: {final_width}x{final_height}")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("mx-updater")

    # QTranslator instance
    qtranslator = QTranslator()
    locale = QLocale.system().name()  # system locale

    # get path to Qt's translations directory
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    translation_file_path = f"{translations_path}/qt_{locale}.qm"

    # load translation file
    if qtranslator.load(translation_file_path):
        #print(f"Translation file for locale {locale} found: {translation_file_path}")
        app.installTranslator(qtranslator)
    else:
        # ignore if not found
        pass

    default_width  = 600
    default_height = 500
    window_title_updater = _("MX Updater")
    window_title_changelog = _('Changelog')
    window_title = f"[ {window_title_updater} ] -- {window_title_changelog}"

    viewer = LogViewer(
        file_path='/usr/share/doc/mx-updater/changelog.gz',
        view_cmd='/usr/bin/zcat',
        #icon_path_png='/usr/share/icons/updater.png',
        icon_path='/usr/share/icons/hicolor/scalable/mx-updater.svg',
        window_class='mx-updater',
        window_title=window_title,
        default_width=default_width,
        default_height=default_height
    )
    viewer.exec()


if __name__ == '__main__':
    main()
