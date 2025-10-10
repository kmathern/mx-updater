#!/usr/bin/python3

import sys
import os

BUILD_VERSION='%%VERSION%%'
MX_UPDATER_PATH = "/usr/libexec/mx-updater"

# remove directory of the current script
if '' in sys.path:
    sys.path.remove('')

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)

if MX_UPDATER_PATH not in sys.path:
    sys.path.insert(0, MX_UPDATER_PATH)


from updater_translator import Translator

from PyQt6.QtWidgets import (
    QApplication, QDialog, QTextEdit, QVBoxLayout, QHBoxLayout,
    QPushButton, QDialogButtonBox, QMessageBox, QStyle
)
from PyQt6.QtGui import QIcon, QFont, QGuiApplication
from PyQt6.QtCore import Qt, QRect, QTranslator, QLocale, QLibraryInfo

from PyQt6.QtCore import QSettings, QPoint, QSize
from PyQt6.QtGui import QGuiApplication


# localization
LOCALE_DOMAIN = 'mx-updater'
LOCALE_DIR = '/usr/share/locale'

translator = Translator(textdomain=LOCALE_DOMAIN)
_ = translator.translate  # Use the translator function


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

        # Initialize settings
        self.qsettings  = QSettings('MX-Linux', 'mx-updater')
        if "dpkg_log" in os.path.basename(os.path.abspath(__file__)):
            self.qsettings_section = "Geometry_AutoUpdate_Dpkg_LogViewer"
        else:
            self.qsettings_section = "Geometry_AutoUpdate_LogViewer"

        self.default_width  = default_width
        self.default_height = default_height


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

        #--------------------------------------------------------------
        # text area
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)

        #self.text_area.setFont(QFont('monospace', 10))
        #self.text_area.setFont(QFont('Liberation Mono Regular', 11))
        self.text_area.setFont(QFont('Liberation Sans Regular', 11))
        #self.text_area.setFont(QFont('Courier New', 11))

        layout.addWidget(self.text_area)

        #--------------------------------------------------------------
        # standard button box with Close
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.reject)  # Close and Esc

        # widgets to layout
        # layout.addWidget(button_box)

        #--------------------------------------------------------------
        # horizontal layout for buttons and search field
        button_layout = QHBoxLayout()

        # close button - using OK instead of Close
        close_text = get_standard_button_text(QMessageBox.StandardButton.Close)

        self.close_button = QPushButton(close_text, self)
        self.close_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton))

        locale = QLocale.system().name()  # system locale

        if not locale.startswith('en'):
            if close_text == "&Close":
                close_text = _("_Close")
                self.close_button.setText(close_text.replace('_','&'))

        # connect buttons to functions
        self.close_button.clicked.connect(self.close_and_exit)

        # stretch space before close button
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)

        # button layout to main layout
        layout.addLayout(button_layout)
        #--------------------------------------------------------------
        self.setLayout(layout)

        # load file if it exists
        if file_path and view_cmd:
            self.load_file(file_path=file_path, view_cmd=view_cmd)
        elif  not file_path and view_cmd:
            self.load_file(view_cmd=view_cmd)
        else:
            # If no file is provided, show a default message
            self.text_area.setPlainText("No file specified. Please provide a file path.")

        # Set initial size and center with scaling
        # self.resize_and_center(default_width, default_height)
        # Restore dialog geometry
        self.restore_dialog_geometry()

    def close_and_exit(self):
        self.accept()  # Close the dialog


    def load_file(self, file_path=None, view_cmd=None):
        """
        Load file content into the text area.

        :param file_path: Path to the file to be viewed
        :param view_cmd: Command to view the file (optional)
        """
        content = None
        try:
            # check file exists
            if file_path and not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            # with view_cmd given, read the file
            if file_path and view_cmd:
                import subprocess
                content = subprocess.check_output([view_cmd, file_path],
                                                  universal_newlines=True)
            elif not file_path and view_cmd:
                import subprocess
                #content = subprocess.check_output([view_cmd],
                content = subprocess.check_output(view_cmd,
                                                  universal_newlines=True)
            elif file_path and not view_cmd:
                # try to read the file directly
                with open(file_path, 'r') as f:
                    content = f.read()

            # Ensure some content
            if not content:
                content = _("Log file is empty.")

            self.text_area.setPlainText(content)
        except Exception as e:
            # show error in text area
            error_msg = f"Error loading file: {str(e)}"
            self.text_area.setPlainText(error_msg)
            # message box for the error - not used
            #QMessageBox.warning(self, "File Load Error", error_msg)

    #def resize_and_center(self, default_width, default_height):
    def resize_and_center(self):
        """
        Resize and center the window with scaling.

        :param default_width: Desired window width
        :param default_height: Desired window height
        """

        default_width  = self.default_width
        default_height = self.default_height

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

    def keyPressEventXXX(self, event):
        """
        Override key press event to close window when Esc is pressed.

        :param event: Key press event
        """
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)


    def done(self, result):
        # Save geometry when dialog is closed
        self.save_dialog_geometry()
        super().done(result)

    def save_dialog_geometry(self):
        """
        Save dialog position and size to QSettings
        """
        section = self.qsettings_section
        self.qsettings.setValue(f'{section}/position', self.pos())
        self.qsettings.setValue(f'{section}/size', self.size())

    def restore_dialog_geometry(self):
        """
        Restore dialog position and size, with fallback to resize_and_center
        """
        # Get the primary screen's available geometry
        screen = QGuiApplication.primaryScreen()
        available_geometry = screen.availableGeometry()

        # Check if valid geometry exists in settings
        section = self.qsettings_section
        saved_pos = self.qsettings .value(f'{section}/position', None)
        saved_size = self.qsettings .value(f'{section}/size', None)

        # Validate saved geometry
        if (saved_pos is not None and saved_size is not None and
            isinstance(saved_pos, QPoint) and isinstance(saved_size, QSize)):

            # Adjust size to fit within available geometry
            adjusted_size = self.adjust_size_to_screen(saved_size, available_geometry)

            # Adjust position to ensure dialog is within screen bounds
            adjusted_pos = self.adjust_position_to_screen(saved_pos, adjusted_size, available_geometry)

            # Set the dialog geometry
            self.resize(adjusted_size)
            self.move(adjusted_pos)

        else:
            # No valid saved geometry - use resize_and_center method
            self.resize_and_center()

    def adjust_size_to_screen(self, size, available_geometry):
        """
        Ensure dialog size does not exceed available screen geometry
        """
        max_width = min(size.width(), available_geometry.width())
        max_height = min(size.height(), available_geometry.height())

        return QSize(
            max(max_width, self.minimumWidth()),
            max(max_height, self.minimumHeight())
        )

    def adjust_position_to_screen(self, pos, size, available_geometry):
        """
        Ensure dialog position is within available screen geometry
        """
        # Adjust x-coordinate
        x = max(
            available_geometry.left(),
            min(pos.x(), available_geometry.right() - size.width())
        )

        # Adjust y-coordinate
        y = max(
            available_geometry.top(),
            min(pos.y(), available_geometry.bottom() - size.height())
        )

        return QPoint(x, y)

    def resize_and_centerXXX(self):
        """
        Resize and center the dialog
        """
        screen = QGuiApplication.primaryScreen().geometry()
        size = self.sizeHint()
        self.resize(size)

        # Center the dialog
        self.move(
            (screen.width() - self.width()) // 2,
            (screen.height() - self.height()) // 2
        )

def get_standard_button_text(button):
    # a temporary message box to access the button text
    msg_box = QMessageBox()
    msg_box.setStandardButtons(button)
    text = msg_box.button(button).text()
    return text


def main():

    window_class='mx-updater'

    app = QApplication(sys.argv)

    app.setApplicationName(window_class)

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


    window_title_updater = _("MX Updater")


    if "dpkg_log" in os.path.basename(os.path.abspath(__file__)):

        default_width  = 800
        default_height = 500
        log_view_title = _('Auto-update dpkg log(s)')
        window_title = f"[ {window_title_updater} ] -- {log_view_title}"

        view_cmd = [
            '/usr/bin/pkexec',
            '/usr/libexec/mx-updater/updater_auto_upgrades_dpkg_log_view'
            ]

    else:

        default_width  = 900
        default_height = 600
        log_view_title = _('Auto-update log(s)')
        window_title = f"[ {window_title_updater} ] -- {log_view_title}"
        view_cmd = [
            '/usr/bin/pkexec',
            '/usr/libexec/mx-updater/updater_auto_upgrades_log_view'
            ]

    viewer = LogViewer(
        view_cmd=view_cmd,
        icon_path='/usr/share/icons/hicolor/scalable/mx-updater.svg',
        window_class=window_class,
        window_title=window_title,
        default_width=default_width,
        default_height=default_height
    )
    viewer.exec()



if __name__ == '__main__':
    main()

'''

TODO if files check permssions and use pkexec for the view cmd
import os
import glob

def files_exist(filepath_glob):
    """
    Check if any files match the given glob pattern exist.

    Args:
        filepath_glob (str): A file path glob pattern (e.g., '*.txt', '/path/to/files/*.log')

    Returns:
        bool: True if at least one file matching the pattern exists, False otherwise
    """
    return len(glob.glob(filepath_glob)) > 0

def files_readable(filepath_glob):
    """
    Check if all files matching the given glob pattern are readable by the current user.

    Args:
        filepath_glob (str): A file path glob pattern (e.g., '*.txt', '/path/to/files/*.log')

    Returns:
        bool: True if all matching files are readable, False if any file is not readable
    """
    # Get all files matching the glob pattern
    matching_files = glob.glob(filepath_glob)

    # If no files match, return False
    if not matching_files:
        return False

    # Check readability for each file
    return all(os.access(file, os.R_OK) for file in matching_files)



'''





