#!/usr/bin/python3

import sys
import os
import subprocess
import re
import gettext


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

# localization
translator = Translator(textdomain='mx-updater')
_ = translator.translate

"""
import gettext
LOCALE_DOMAIN = 'mx-updater'
LOCALE_DIR = '/usr/share/locale'
# bind the domain
gettext.bindtextdomain(LOCALE_DOMAIN, LOCALE_DIR)
gettext.textdomain(LOCALE_DOMAIN)
_ = gettext.gettext

"""

from PyQt6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QPlainTextEdit, QPushButton, 
    QHBoxLayout, QLineEdit, QStyle, QMessageBox
)
from PyQt6.QtGui import QFont, QIcon, QPixmap, QKeyEvent, QGuiApplication, QPalette, QAction, QColor

from PyQt6.QtCore import QTranslator, QLocale, QLibraryInfo, QSettings

from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtCore import QSettings



def is_dark_palette(pal: QPalette) -> bool:
    """
    Returns True if the base color is dark.
    """
    base = pal.color(QPalette.ColorRole.Base)
    return base.lightnessF() < 0.5


class FilterWithAction(QLineEdit):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # placeholder text 
        placeholder_text = _("Filter by")
        #print(f'placeholder_text = _("Filter by") : {placeholder_text}')
        self.setPlaceholderText(f"{placeholder_text}...")
        self.setClearButtonEnabled(False)

        # QAction with a clear/x icon
        clear_icon = QIcon.fromTheme("edit-clear")
        if clear_icon.isNull():
            # fallback: to own .png/.svg icon
            clear_icon = QIcon(":/icons/clear.png")

        self.clear_action = QAction(clear_icon, "Clear text", self)
        tooltip = _("Clear")
        self.clear_action.setToolTip(f"  {tooltip}  ")
        self.clear_action.triggered.connect(self.clear)

        # put clear_action to the right of line‐edit
        self.addAction(self.clear_action, QLineEdit.ActionPosition.TrailingPosition)

        # only show whith text entered
        self.clear_action.setVisible(False)
        self.textChanged.connect(lambda txt: self.clear_action.setVisible(bool(txt)))

        # set placeholde text for dark mode to "#888888"
        # for lightmode it stays as default ( something like #555 or #777) 
        if is_dark_palette(self.palette()):
            pal = self.palette()
            pal.setColor(QPalette.ColorRole.PlaceholderText, QColor("#888888"))
            self.setPalette(pal)
    
        # adjust padding 
        self.setTextMargins(0, 0, 4, 0)

class LogDialog(QDialog):
    def __init__(self, log_text, default_width=960, default_height=600):
        super().__init__()

        self.default_width  = default_width
        self.default_height = default_height
        
        self.qsettings_section = "Geometry_Updater_History"
        self.qsettings = QSettings("MX-Linux", "mx-updater")
        window_title_history = _("History")
        window_title_updater = _("MX Updater")
        window_title = f"[ {window_title_updater} ] -- {window_title_history}"
        window_icon = "/usr/share/icons/hicolor/scalable/mx-updater.svg"
        self.setWindowIcon(QIcon(window_icon))
        self.setWindowTitle(window_title)

        available_geometry = QGuiApplication.primaryScreen().availableGeometry()
        x = available_geometry.width()
        y = available_geometry.height()
        margin_x = 60  # horizontal margin
        margin_y = 60   # vertical margin

        self.resize(min(1100, x - margin_x), min(600, y - margin_y))
        #print("width height : ", self.width(), self.height())
        self.move((x - self.width()) // 2, (y - self.height()) // 2)
        self.setMinimumSize(600, 400)  # Optional: Set minimum size
       
        # original log text
        self.original_log_text = log_text

        # layout
        layout = QVBoxLayout(self)


        # QPlainTextEdit for displaying log text
        self.log_text_edit = QPlainTextEdit(self)
        self.log_text_edit.setPlainText(self.original_log_text) 
        self.log_text_edit.setReadOnly(True)  # read-only

        # monospace font
        log_text_font = "Courier New"
        #log_text_font = "Liberation Mono Regular"
        #log_text_font = "Monospace"
        self.log_text_edit.setFont(QFont(log_text_font, 11))
        # disable line wrapping
        self.log_text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        # pixels for one space
        space_width = self.log_text_edit.fontMetrics().horizontalAdvance(' ')
        # for 4‐space tabs:
        self.log_text_edit.setTabStopDistance(space_width * 4)

        # "text edit" to the layout
        layout.addWidget(self.log_text_edit)

        #--------------------------------------------------------------
        # horizontal layout for buttons and search field
        button_layout = QHBoxLayout()

        # search field
        #self.search_field = QLineEdit(self)
        self.search_field = FilterWithAction(self)
        # placeholder text
        #placeholder_text = "Filter..."
        placeholder_text = _("Filter by")
        #print(f'placeholder_text = _("Filter by") : {placeholder_text}')

        self.search_field.setPlaceholderText(f"{placeholder_text}...")
        # fixed width for search field
        self.search_field.setFixedWidth(200)
        # connect to filter function
        self.search_field.textChanged.connect(self.filter_log_text) 

        """
        # clear button
        self.clear_button = QPushButton(self)
        self.clear_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogResetButton))
        self.clear_button.setFixedWidth(30)  # fixed width for clear button
        self.clear_button.clicked.connect(self.clear_search)  # connect to clear function
        """

        
        # copy and close button
        copy_text = _("_Copy")

        self.copy_button = QPushButton(copy_text.replace('_','&'), self)
        self.copy_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)) 

        # close button - using OK instead of Close
        OK_TEXT = get_standard_button_text(QMessageBox.StandardButton.Ok)
        
        self.close_button = QPushButton(OK_TEXT, self)
        self.close_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton)) 

        # connect buttons to functions
        self.close_button.clicked.connect(self.close_and_exit)
        self.copy_button.clicked.connect(self.copy_to_clipboard)

        # add search field
        button_layout.addWidget(self.search_field)
        # clear button - not used as we havea search/filter field
        #button_layout.addWidget(self.clear_button)  # Add the clear button to the layout
        # stretch space before copy and close buttons
        button_layout.addStretch()
        button_layout.addWidget(self.copy_button)
        button_layout.addWidget(self.close_button)

        # button layout to main layout
        layout.addLayout(button_layout)
        #--------------------------------------------------------------

        self.setLayout(layout)

        self.center()

        self.restore_dialog_geometry()

    def center(self):
        # set initial size
        # screen geometry
        screen_geometry = self.screen().geometry()
        #print("Screen Geometry (from QMainWindow):", screen_geometry)

        # available geometry
        desktop = QGuiApplication.primaryScreen()
        available_geometry = desktop.availableGeometry()
        #print("Available Geometry (from primaryScreen()):", available_geometry)

        # window geometry
        window_geometry = self.geometry()

        # center position
        x = available_geometry.x() + (available_geometry.width() - self.width()) // 2
        y = available_geometry.y() + (available_geometry.height() - self.height()) // 2

        # move to center
        self.move(x, y)


    def filter_log_text(self):
        search_text = self.search_field.text().lower()  # get search text

        # filter log text based on original log text
        if search_text:
            filtered_lines = []
            for line in self.original_log_text.splitlines():  # use original log text for filtering
                if search_text in line.lower():  # case insensitive search
                    filtered_lines.append(line)
            self.log_text_edit.setPlainText("\n".join(filtered_lines))  # update text edit with filtered lines
        else:
            self.log_text_edit.setPlainText(self.original_log_text)  # reset to original text if search field is empty

    def clear_search(self):
        self.search_field.clear()  # Clear the search field
        self.log_text_edit.setPlainText(self.original_log_text)  # Reset to original text

    def copy_to_clipboard(self):
        # copy text to the clipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(self.log_text_edit.toPlainText())

    def close_and_exit(self):
        self.save_dialog_geometry()
        self.accept()  # Close the dialog

   
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
        
        # calculate scaling factors
        width_scale = max_width / default_width
        height_scale = max_height / default_height
        
        # use the smaller scale to maintain aspect ratio, but not scale up
        scale = min(1.0, min(width_scale, height_scale))
        
        # calculate final dimensions
        final_width = int(default_width * scale)
        final_height = int(default_height * scale)
        
        # Resize the window to exact calculated dimensions
        self.resize(final_width, final_height)
        
        # calculate center position
        center_point = available_geometry.center()
        frame_geometry = self.frameGeometry()
        frame_geometry.moveCenter(center_point)
        
        # ensure window is within available screen space
        adjusted_pos = frame_geometry.topLeft()
        adjusted_pos.setX(max(available_geometry.left(), 
                               min(adjusted_pos.x(), 
                                   available_geometry.right() - frame_geometry.width())))
        adjusted_pos.setY(max(available_geometry.top(), 
                               min(adjusted_pos.y(), 
                                   available_geometry.bottom() - frame_geometry.height())))
        
        # move window
        self.move(adjusted_pos)
        
        print(f"Final size: {final_width}x{final_height}")

    def keyPressEvent_NotUsed(self, event):
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
        Restore dialog position and size, with fallback to 'resize_and_center' method
        """
        # get primary screen's available geometry
        screen = QGuiApplication.primaryScreen()
        available_geometry = screen.availableGeometry()
        
        # check if valid geometry exists in settings
        section = self.qsettings_section
        saved_pos = self.qsettings.value(f'{section}/position', None)
        saved_size = self.qsettings.value(f'{section}/size', None)
        
        # validate saved geometry
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

    
def get_apt_history():
    try:
        # Run apt-history command and capture the output
        command = ["/usr/bin/apt-history"]
        result = subprocess.run(
            command, 
            shell=False,  # Use shell=True to execute the command as a single string
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE, 
            text=True
        )

        # Process the output using Python
        if result.stdout.strip():
            # Replace the sed command with Python code
            processed_lines = []
            for line in result.stdout.splitlines():
                # Use regex to replace ":<lowercase letter>" with " <lowercase letter>"
                processed_line = re.sub(r':([a-z])', r' \1', line)
                processed_lines.append(processed_line)

            # Create a list of lists for column data
            column_data = [line.split() for line in processed_lines]

            # Calculate maximum width for each column
            max_widths = []
            for row in column_data:
                for i, item in enumerate(row):
                    if i >= len(max_widths):
                        max_widths.append(len(item))
                    else:
                        max_widths[i] = max(max_widths[i], len(item))

            # format output into columns
            formatted_lines = []
            for row in column_data:
                formatted_line = ""
                for i, item in enumerate(row):
                    formatted_line += f"{item:<{max_widths[i]}}  "  # Align left with padding
                formatted_lines.append(formatted_line.rstrip())

            # Join formatted lines into a single string with newlines
            return "\n".join(formatted_lines)
        else:
            return _("No apt-history data found!")
    except Exception as e:
        error=_("Error retrieving apt-history:")
        return f"{error} {str(e)}"

def get_standard_button_text(button):
    # temporary message box to access the button text
    msg_box = QMessageBox()
    msg_box.setStandardButtons(button)
    text = msg_box.button(button).text()
    return text


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName("mx-updater")

    # QTranslator instance
    qtranslator = QTranslator()
    locale = QLocale.system().name()  # Get the system locale

    # get path to  translations directory
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    translation_file_path = f"{translations_path}/qt_{locale}.qm"

    # load translation file
    if qtranslator.load(translation_file_path):
        #print(f"Translation file for locale {locale} found: {translation_file_path}")
        app.installTranslator(qtranslator)
    else:
        #print(f"Translation file not found: {translation_file_path}")
        pass


    CLOSE_TEXT = "&Close"
    CLOSE_TEXT = get_standard_button_text(QMessageBox.StandardButton.Close)

    # get apt-history log text
    log_text = get_apt_history()

    default_width  = 900
    default_height = 600

    dialog = LogDialog(log_text,
            default_width=default_width,
            default_height=default_height
            )

    dialog.exec()  # This will block until the dialog is closed

    sys.exit()  # Exit the application after the dialog is closed
