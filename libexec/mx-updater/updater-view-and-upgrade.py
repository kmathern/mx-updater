#!/usr/bin/python3

from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton,
    QHBoxLayout, QVBoxLayout, QGridLayout,
    QTextEdit, QGroupBox, QSpinBox, QDialog,
    QCheckBox, QDialogButtonBox, QStyle, QProgressDialog
)
from PyQt6.QtGui import (
    QFont, QIcon, QPixmap, QKeyEvent, QGuiApplication,
    QPalette, QAction, QColor
    )

from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtCore import Qt, QPoint, QSize
from PyQt6.QtCore import QSettings

import os, sys, time
import gettext
import subprocess
import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import logging

# Set up the translation
locale_dir = "/usr/share/locale"
gettext.bindtextdomain('mx-updater', locale_dir)
gettext.textdomain('mx-updater')
_ = gettext.gettext


logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

#----------
# Constants
#----------

# dbus
SETTINGS_OBJECT_NAME  = "org.mxlinux.UpdaterSettings"
SETTINGS_OBJECT_PATH  = "/org/mxlinux/UpdaterSettings"
SETTINGS_OBJECT_IFACE = "org.mxlinux.UpdaterSettings"

VIEW_AND_UPGRADE_OBJECT_NAME  = "org.mxlinux.UpdaterViewAndUpgrade"
VIEW_AND_UPGRADE_OBJECT_PATH  = "/org/mxlinux/UpdaterViewAndUpgrade"
VIEW_AND_UPGRADE_OBJECT_IFACE = "org.mxlinux.UpdaterViewAndUpgrade"

AUTO_CLOSE_TIMEOUT_MIN =  1  # in seconds
AUTO_CLOSE_TIMEOUT_MAX = 60  # in seconds


class LogUpdateThread(QThread):
    log_ready = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        try:
            command = [ "/usr/lib/mx-updater/bin/updater_list" ]
            result = subprocess.run(command, 
                                    capture_output=True, 
                                    text=True, 
                                    timeout=30)
            log_text = result.stdout
            self.log_ready.emit(log_text)
        except Exception as e:
            self.log_ready.emit(f"Error: {str(e)}")



class ViewAndUpgradeService(dbus.service.Object):
    """
    D-Bus service that provides a simple interface to get and set a value.
    """

    def __init__(self, bus_name, object_path):
        super().__init__(bus_name, object_path)
        #self._settings = QSettings("MX-Linux", "mx-updater")
        # QObject wrapper for emitting Qt signals
        class _Emitter(QObject):
            value_changed_qt = pyqtSignal(str, str)
        self._emitter = _Emitter()

    # Expose the Qt signal for others to connect to
    @property
    def value_changed_qt(self):
        return self._emitter.value_changed_qt

    @dbus.service.method(VIEW_AND_UPGRADE_OBJECT_IFACE, in_signature='ss', out_signature='')
    def SetValue(self, key, value):
        if not key.strip():
            return
        # write to qsettings
        # self._settings.setValue(f"Settings/{key}", str(value))
        # force immediate write to disk
        # self._settings.sync()
        # emit PyQt signal
        self._emitter.value_changed_qt.emit(key, value)

    @dbus.service.signal(VIEW_AND_UPGRADE_OBJECT_IFACE, signature="")
    def Quit(self): pass


class ViewAndUpgradeDialog(QDialog):
    # PyQt signals
    value_changed_signal = pyqtSignal(str, str)
 
    def __init__(self, service, session_bus,
                default_width=960, default_height=600):
        super().__init__()
        self.session_bus = session_bus
        self.service = service
        self.default_width  = default_width
        self.default_height = default_height

        self.qsettings = QSettings("MX-Linux", "mx-updater")
        self.qsettings_section = "Geometry_View_and_Upgrade"
        self.dbus_call_back = True       

        # Connect service's PyQt signal
        self.service.value_changed_qt.connect(self.on_value_changed)

        # Connect the value_changed_signal PyQt signal to the update_dialog method
        self.value_changed_signal.connect(self.update_dialog)

        self.init_ui()
        self.restore_dialog_geometry()

        # start background thread
        self.start_log_update()

    def on_value_changed(self, key, value):
        # Called when SetValue emits the 'value_changed_qt' PyQt signal
        self.value_changed_signal.emit(key, value)



    def update_dialog(self, key, value):
        # update view_and_upgrade dialog based key,value pair
        me = "update_dialog@ViewAndUpgrade"
        logger.debug("[%s] dialog updated with key=value: %s='%s' of type '%s'", me, key, value, type(value).__name__ )
        logger.debug("[%s] dbus_call_back is %s", me, self.dbus_call_back)

        prefix = 'no-dbus-callback@'
        if key.startswith(prefix):
            self.dbus_call_back = False
            logger.debug("[%s] dbus_call_back set to %s", me, self.dbus_call_back)
            key = key.removeprefix(prefix)

        bool_keys = (
            'auto_close',
            'hide_until_upgrades_available',
            'start_at_login',
            'use_dbus_notifications',
            'use_nala',
            'upgrade_assume_yes',
            'wireframe_transparent',
        )   

        if key in bool_keys:
            if isinstance(value, str):
                new_value = value.lower() in ("true", "yes", "on", "1")
            elif isinstance(value, bool):
                new_value = value
            elif isinstance(value, int):
                new_value = bool(value)
            else:
                return

        if key == 'auto_close_timeout':
            try:
                # try to convert string to integer
                new_value = int(value)
                # check value is in range, and set accordingly
                    
                if not (AUTO_CLOSE_TIMEOUT_MIN <= new_value <= AUTO_CLOSE_TIMEOUT_MAX):
                    logger.debug("[%s] value '%s' for auto_close_timeout, not within allowed range of (%s..%s)",
                                me, value,
                                AUTO_CLOSE_TIMEOUT_MIN, AUTO_CLOSE_TIMEOUT_MAX
                                )
                    if new_value < AUTO_CLOSE_TIMEOUT_MIN:
                        new_value = AUTO_CLOSE_TIMEOUT_MIN
                        
                    if new_value > AUTO_CLOSE_TIMEOUT_MAX:
                        new_value = AUTO_CLOSE_TIMEOUT_MAX
            except ValueError:
                print(f"Error: '{value}' is not a valid integer.")
                return  # ignored
            

        match key:

            case 'auto_close':
                self.auto_close_checkbox.setChecked(new_value)

            case 'auto_close_timeout':
                self.auto_close_timeout.setValue(new_value)

            case 'use_nala':
                logger.debug("[update_dialog@UpdaterViewAndUpgrade] use_nala_checkbox.setChecked to  %s", new_value)
            
                self.use_nala_checkbox.setChecked(new_value)

            case 'upgrade_assume_yes':
                self.upgrade_assume_yes_checkbox.setChecked(new_value)


            case _:
                # default handling if any 
                pass

    
    def update_settings_dialog(self, key, value):

        me = "update_settings_dialog@UpdaterViewAndUpgrade"

        logger.debug("[%s] About to update view_and_upgrade dialog via dbus: %s = %s", me, key, value)
        logger.debug("[%s] dbus_call_back is %s", me, self.dbus_call_back)

        if not self.dbus_call_back:
            logger.debug("[%s] No callback to update settings dialog via dbus: %s = %s", me, key, value)
            logger.debug("[%s] reset dbus_call_back to %s", me, not self.dbus_call_back)

            self.dbus_call_back = True
            return

        prefix = 'no-dbus-callback@'

        keys = ('auto_close',
                'auto_close_timeout',
                'upgrade_assume_yes',
                'use_nala',
                )
        if key not in keys:
            return

        bool_keys = (
            'auto_close',
            'use_nala',
            'upgrade_assume_yes',
        )   

        if key in bool_keys:
            if isinstance(value, str):
                value = value.lower() in ("true", "yes", "on", "1")
                value = str(value).lower()
            elif isinstance(value, bool):
                value = str(value).lower()
                pass
            elif isinstance(value, int):
                value = bool(value)
                value = str(value).lower()
            else:
                return


        key = f'{prefix}{key}'

        logger.debug("[%s] Try update settings dialog via dbus: %s = %s", me, key, value)
        logger.debug("[%s] dbus-call %s %s %s.SetValue %s %s", me,
                    SETTINGS_OBJECT_NAME,
                    SETTINGS_OBJECT_PATH,
                    SETTINGS_OBJECT_IFACE,
                    key,
                    value,
                    )
        try:
            # Connect to session bus
            bus = dbus.SessionBus()
            
            try:
                # dbus proxy object
                proxy = bus.get_object(SETTINGS_OBJECT_NAME, SETTINGS_OBJECT_PATH)
                
                # dbus interface
                interface = dbus.Interface(proxy, SETTINGS_OBJECT_IFACE)
                
                # dbus method call to update settings dialog with key/value
                interface.SetValue(str(key), str(value))
            
            except dbus.exceptions.DBusException as e:
                #print(f"UpdaterSettings dialog not running.: {e}")
                logger.debug("[%s] UpdaterSettings dialog does not appear to be active.", me)
                pass
        
        except Exception as e:
            #print(f"Unexpected D-Bus error: {e}")
            logger.error("[%s] Unexpected D-Bus error: %r", me, e)
            pass


    def start_log_update(self):
        # create and start background thread
        self.log_thread = LogUpdateThread()
        self.log_thread.log_ready.connect(self.update_log_text)
        self.log_thread.start()

    def update_log_text(self, log_text):
        # Update log text and enable close button
        self.log.setPlainText(log_text)
        self.close_button.setEnabled(True)

    def load_settings(self):
        self.qsettings.sync()
        try:
            assume_yes = self.qsettings.value("Settings/upgrade_assume_yes", False, type=bool)
            logger.debug("loaded settings 'upgrade_assume_yes' = %s", assume_yes)
        except:
            assume_yes = False
            logger.debug("default settings 'use_nala' = %s", assume_yes)
        self.upgrade_assume_yes_checkbox.setChecked(assume_yes)
        
        try:
            use_nala = self.qsettings.value("Settings/use_nala", False, type=bool)
            logger.debug("loaded settings 'use_nala' = %s", use_nala)
        except:
            use_nala = False
            logger.debug("default settings 'use_nala' = %s", use_nala)
        if hasattr(self, 'use_nala_checkbox'):
            if os.path.isfile('/usr/bin/nala') and os.access('/usr/bin/nala', os.X_OK):
                self.use_nala_checkbox.setChecked(use_nala)
                self.use_nala_checkbox.setVisible(True)
            else:
                self.use_nala_checkbox.setVisible(False)

        try:
            auto_close = self.qsettings.value("Settings/auto_close", True, type=bool)
            logger.debug("loaded settings 'auto_close' = %s", auto_close)
        except:
            auto_close = False
            logger.debug("default settings 'auto_close' = %s", auto_close)
        self.auto_close_checkbox.setChecked(auto_close)

        if auto_close:
            self.auto_close_timeout.setEnabled(True)
        else:
            self.auto_close_timeout.setEnabled(False)

        try:
            auto_close_timeout = self.qsettings.value("Settings/auto_close_timeout", 10, type=int)
            logger.debug("loaded settings 'auto_close_timeout' = %s", auto_close_timeout)
        except:
            auto_close_timeout = 10
            logger.debug("default settings 'auto_close_timeout' = %s", auto_close_timeout)
        self.auto_close_timeout.setValue(auto_close_timeout)
        
    def init_ui(self):

        window_title_updater = _("MX Updater")
        window_title_view_and_upgrade = _("View and Upgrade")
        window_title = f"[ {window_title_updater} ] -- {window_title_view_and_upgrade}"
        window_icon = "/usr/share/icons/hicolor/scalable/mx-updater.svg"

        self.setWindowTitle(window_title)
        self.setWindowIcon(QIcon(window_icon))
        
        self.log_text = ""
        self.log_cnt = 0
        #self.setlog_text()
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        #self.log.setPlainText(self.log_text)

        # Set initial placeholder text
        # ="...$(mygettext -d apt ' [Working]')..."
        working=' [Working]'
        self.log.setPlainText(f"...{working}...")

        # main outer vbox layout 
        outer = QVBoxLayout(self)
        # with stretch=1 to expand on vertical resize
        outer.addWidget(self.log, stretch=1)

        # 2 rows with 2 columns
        grid = QGridLayout()
        # row 0
        
        checkbox_label = _("automatically confirm all package upgrades")
        checkbox_tooltip = _("Automatically answers 'yes' to package management prompts during upgrades.\n"
                             "Some system configuration changes may still require manual confirmation.")
        self.upgrade_assume_yes_checkbox = QCheckBox(checkbox_label)
        self.upgrade_assume_yes_checkbox.setToolTip(checkbox_tooltip)
        grid.addWidget(self.upgrade_assume_yes_checkbox, 0, 0)

        # check if /usr/bin/nala exists and is executable
        if os.path.isfile('/usr/bin/nala') and os.access('/usr/bin/nala', os.X_OK):

            # TRANSLATORS: Select this to use nala package manager instead of apt.
            self.use_nala_checkbox = QCheckBox(_("use nala"))
            # TRANSLATORS: Explains upgrade can be done by using nala package manager instead of apt
            self.use_nala_checkbox.setToolTip(_("Select this to use nala package manager instead of apt."))
            grid.addWidget(self.use_nala_checkbox, 0, 1)
            self.use_nala_checkbox.toggled.connect(
                lambda checked: self.on_use_nala_checkbox_toggled(checked))



        # TRANSLATORS: After the idle time in seconds has elapsed,
        # the terminal window is closed once the system update is complete.
        auto_close_label = _("close terminal window automatically after idle time")

        # TRANSLATORS: Explains the auto-close behavior of terminal window
        # after system updates with a configurable idle time
        auto_close_tooltip = _("Automatically closes the terminal window after the specified\n"
                                "number of seconds of inactivity following system updates.")
        
        # row 1
        self.auto_close_checkbox = QCheckBox(auto_close_label)
        self.auto_close_checkbox.setToolTip(auto_close_tooltip)

        self.auto_close_timeout = QSpinBox()
        self.auto_close_timeout.setRange(1, 60)

        # TRANSLATORS: This is the abriavated string for 'seconds' shown within
        # the timeout selection field. Please use the most appropriate trnslated
        # string for the singular or plural form. Only one form is shown.
        seconds_suffix = _("sec.")
        self.auto_close_timeout.setSuffix(f" {seconds_suffix} ")
        self.auto_close_timeout.setEnabled(False)
        grid.addWidget(self.auto_close_checkbox,            1, 0)
        grid.addWidget(self.auto_close_timeout,                        1, 1)

        # 3rd empty, column 2 with stretch=1, so columns 0+1 stay close 
        grid.setColumnStretch(2, 1)
        
        # add grid into a group-box for the frame
        frame = QGroupBox()
        frame.setLayout(grid)
        frame.setContentsMargins(5, 0, 5, 0)  # margins
        outer.addWidget(frame, stretch=0)


        # horizontal layout for buttons
        reload_label = _("Reload")
        upgrade_label = _("upgrade")
        close_label = _("Close")

        # fix lower/upper spelling
        reload_label = reload_label[0].upper() + reload_label[1:]
        upgrade_label = upgrade_label[0].upper() + upgrade_label[1:]

        # if the very first character matches, insert '&' right after it in label1
        if reload_label[0] == upgrade_label[0]:
            reload_label = reload_label[0] + "&" + reload_label[1:]
        else:
            reload_label = "&" + reload_label
        upgrade_label = "&" + upgrade_label
        close_label = "&" + close_label

        
        button_layout = QHBoxLayout()
        self.reload_button = QPushButton(reload_label, self)
        self.upgrade_button = QPushButton(upgrade_label, self)
        self.close_button = QPushButton(close_label, self)

        self.reload_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)) 
        self.upgrade_button.setIcon(QIcon("/usr/share/icons/hicolor/48x48/apps/mx-updater.png"))  # Set Upgrade icon
        self.close_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCloseButton)) 
        
        # minimum width for buttons
        self.reload_button.setMinimumWidth(130)
        self.upgrade_button.setMinimumWidth(130)
        self.close_button.setMinimumWidth(130)

        # fixed height for buttons
        self.reload_button.setFixedHeight(50)
        self.upgrade_button.setFixedHeight(50)
        self.close_button.setFixedHeight(50)

        # icon size
        self.reload_button.setIconSize(QSize(16, 16))
        self.upgrade_button.setIconSize(QSize(32, 32))
        self.close_button.setIconSize(QSize(32, 32))
       
        # stretchable space to right-align the buttons
        button_layout.addStretch()
        button_layout.addWidget(self.reload_button)
        button_layout.addStretch()
        button_layout.addWidget(self.upgrade_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        button_layout.addStretch()

        # button layout goes into to the outer main layout
        outer.addLayout(button_layout)

        # checkbox connections
        self.auto_close_checkbox.toggled.connect(
            lambda checked:self.on_auto_close_checkbox_toggled(checked)
            )
        self.upgrade_assume_yes_checkbox.toggled.connect(
            lambda checked:
            self.on_upgrade_assume_yes_checkbox_toggled(checked)
            )

        self.auto_close_timeout.valueChanged.connect(
            self.on_auto_close_timeout
            )

        # button connections
        self.reload_button.clicked.connect(self.do_reload)
        self.upgrade_button.clicked.connect(self.do_upgrade)
        self.close_button.clicked.connect(self.reject)

    def on_auto_close_timeout(self, value):
        self.qsettings.setValue("Settings/auto_close_timeout", value)
        self.qsettings.sync()
        self.update_settings_dialog("auto_close_timeout", value)

    def on_upgrade_assume_yes_checkbox_toggled(self, checked):
        self.qsettings.setValue("Settings/upgrade_assume_yes", checked)
        self.qsettings.sync()
        self.update_settings_dialog("upgrade_assume_yes", checked)

    def on_use_nala_checkbox_toggled(self, checked):
        self.qsettings.setValue("Settings/use_nala", checked)
        self.qsettings.sync()
        self.update_settings_dialog("use_nala", checked)

    def on_auto_close_checkbox_toggled(self, checked):
        self.auto_close_timeout.setEnabled(checked)
        self.qsettings.setValue("Settings/auto_close", checked)
        self.qsettings.sync()
        self.update_settings_dialog("auto_close", checked)
        

    def do_reload(self):
        self.hide()
        self.state = "do_reload"
        self.updater_reload_run()
        self.log.setPlainText("... working, please wait")
        self.start_log_update()
        self.accept()

    def do_upgrade(self):
        self.hide()
        self.state = "do_upgrade"
        self.updater_upgrade_run()
        # self.accept()
        self.reject()


    def do_upgradeXXXXXX(self):
        self.hide()
        self.state = "do_upgrade"
        dlg = QProgressDialog(
            "Upgrading packages…", "", 0, 100, self
        )
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.show()
        for i in range(101):
            time.sleep(0.05)
            dlg.setValue(i)
        dlg.close()
        self.reject()

    def setlog_text(self):
        self.log_cnt +=1
        self.log_text = self.get_updater_list()
        
    def get_updater_list(self):
        #print("get_updater_list running ...")
        try:
            command = "/usr/lib/mx-updater/bin/updater_list"
            result = subprocess.run(
                command, 
                shell=False,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
   
            return f"get_updater_list counter : {self.log_cnt}\n" + result.stdout.strip()
        except Exception as e:
            return f"Error retrieving apt package lists: {str(e)}"
    
    def updater_reload_run(self):
        logger.info("updater_reload_run started ...")
        try:
            command = ["/usr/libexec/mx-updater/updater_action_run", "updater_reload"]
            result = subprocess.run(
                command, 
                shell=False,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
   
            return result.stdout.strip()
        except Exception as e:
            return f"Error updater_reload [apt/nala update] : {str(e)}"

    
    def updater_upgrade_run(self):
        logger.info("updater_upgrade_run started ...")
        try:
            command = ["/usr/libexec/mx-updater/updater_action_run", "updater_upgrade"]
            result = subprocess.run(
                command, 
                shell=False,
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                text=True
            )
   
            return result.stdout.strip()
        except Exception as e:
            return f"Error updater_upgrade [apt/nala update] : {str(e)}"

    
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
        saved_pos = self.qsettings.value(f'{section}/position', None)
        saved_size = self.qsettings.value(f'{section}/size', None)
        
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
    


    
def is_dark_theme():
    if QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128:
        logger.debug("Dark theme detected")
        return True
    else:
        logger.debug("Light theme detected")
        return False
            
 
def tooltip_stylesheet():
    if is_dark_theme():
        # Dark theme: slightly more saturated yellow
        return """
            QToolTip {
                color: black;
                background-color: #FFF0A0;  /* Goldish yellow */
                border: 1px solid #000000;
                padding: 5px;
                opacity: 230;  /* Slightly transparent */
            }
        """
    else:
        # Light theme: softer, lighter yellow
        return """
            QToolTip {
                color: black;
                background-color: #FFFFE0;  /* Light yellow */
                border: 1px solid #000000;
                padding: 5px;
                opacity: 230;  /* Slightly transparent */
            }
        """


if __name__ == "__main__":

    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    logger.info("MX Updater 'View and Upgrade' started.")
    try:
        # connect to session bus
        session_bus = dbus.SessionBus()
        logger.info("Connected to session bus.")
    except dbus.DBusException as e:
        logger.error("Unable to connect to session bus: %r", e)
        logger.error("%s exiting.", VIEW_AND_UPGRADE_OBJECT_NAME)
        logger.error("MX Updater 'View and Upgrade' exited.")
        sys.exit(1)


    # if already running, terminate - no double runs
    try:
        if session_bus.name_has_owner(VIEW_AND_UPGRADE_OBJECT_NAME):
            logger.info("%r is already running, exiting.", VIEW_AND_UPGRADE_OBJECT_NAME )
            sys.exit(0)
        else:
            logger.info("%r appears to be not running.", VIEW_AND_UPGRADE_OBJECT_NAME )

    except dbus.DBusException as e:
        logger.error("Error checking name ownership: %r", e)
        sys.exit(1)

    # request bus name
    try:
        request = session_bus.request_name(
            VIEW_AND_UPGRADE_OBJECT_NAME,
            dbus.bus.NAME_FLAG_DO_NOT_QUEUE
        )
    except dbus.DBusException as e:
        logger.error("Failed to request name %r: %r", VIEW_AND_UPGRADE_OBJECT_NAME, e)
        sys.exit(1)

    if request != dbus.bus.REQUEST_NAME_REPLY_PRIMARY_OWNER:
        logger.error("Could not become primary owner (got %r), exiting.", request)
        sys.exit(1)

    logger.debug("dbus object name : %s", VIEW_AND_UPGRADE_OBJECT_NAME)
    logger.debug("dbus object path : %s", VIEW_AND_UPGRADE_OBJECT_PATH)
    logger.debug("dbus object iface: %s", VIEW_AND_UPGRADE_OBJECT_IFACE)

    service = ViewAndUpgradeService(session_bus, VIEW_AND_UPGRADE_OBJECT_PATH)
    
    app = QApplication(sys.argv)
    app.setApplicationName("mx-updater")
    app.setStyleSheet(tooltip_stylesheet())

    default_width  = 900
    default_height = 600

    dlg = ViewAndUpgradeDialog(service, session_bus,
            default_width=default_width,
            default_height=default_height
            )

  
    #dlg.resize(900, 600)
    
    while True:
        dlg.load_settings()
        result = dlg.exec()
        if result == QDialog.DialogCode.Accepted:
            logger.info("Reload settings ...")
            pass
        else:
            break
    logger.info("MX Updater 'View and Upgrade' finished.")
    sys.exit(0)
