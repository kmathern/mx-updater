#!/usr/bin/python3

import os
import re
import subprocess
import sys
from pprint import pprint
import dbus
from PyQt6.QtCore import QObject, pyqtSignal
import logging

print(f"sys.path: {sys.path}")

# import gettext

BUILD_VERSION='%%VERSION%%'
MX_UPDATER_PATH = "/usr/libexec/mx-updater"

'''
#----------
# Check MX_UPDATER_PATH
#----------
try:
    MX_UPDATER_PATH = os.environ["MX_UPDATER_PATH"]
except KeyError:
    print("MX_UPDATER_PATH missing from environment, exiting")
    #logger.error("MX_UPDATER_PATH missing from environment, exiting")
    sys.exit(1)
'''

sys.path.insert(0, MX_UPDATER_PATH)

if '' in sys.path:
    sys.path.remove('')

# remove the directory of the current script
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir in sys.path:
    sys.path.remove(script_dir)

if MX_UPDATER_PATH not in sys.path:
    sys.path.insert(0, MX_UPDATER_PATH)

import updater_config
from updater_config import UpdaterSettingsManager
from updater_translator import Translator

# suppress some warnings
os.environ["QT_LOGGING_RULES"] = "*.debug=false;*.warning=false"
#os.environ["QT_QPA_EGLFS_INTEGRATION"] = "none"
#os.environ["LIBGL_DEBUG"] = "0"
os.environ["EGL_LOG_LEVEL"] = "fatal"


# create a Translator instance
translator = Translator(textdomain='apt-notifier')
_ = translator.translate  # Use the translator function


from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QFrame,
    QRadioButton, QCheckBox, QLabel, QPushButton, QWidget, QGroupBox,
    QButtonGroup, QGridLayout, QSizePolicy, QDialog, QDialogButtonBox,
    QMessageBox, QSpinBox, QToolTip
)
from PyQt6.QtGui import QPixmap, QIcon, QKeyEvent, QGuiApplication, QFont, QPalette
from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtCore import QTranslator, QLocale, QLibraryInfo

from PyQt6.QtGui import (
    QFont, QIcon, QPixmap, QKeyEvent, QGuiApplication,
    QPalette, QColor
    )

from pydbus import SessionBus



logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# constants
# dbus
SETTINGS_OBJECT_NAME  = "org.mxlinux.UpdaterSettings"
SETTINGS_OBJECT_PATH  = "/org/mxlinux/UpdaterSettings"
SETTINGS_OBJECT_IFACE = "org.mxlinux.UpdaterSettings"

TRAYICON_OBJECT_NAME  = "org.mxlinux.UpdaterSystemTrayIcon"
TRAYICON_OBJECT_PATH  = "/org/mxlinux/UpdaterSystemTrayIcon"
TRAYICON_OBJECT_IFACE = "org.mxlinux.UpdaterSystemTrayIcon"

VIEW_AND_UPGRADE_OBJECT_NAME  = "org.mxlinux.UpdaterViewAndUpgrade"
VIEW_AND_UPGRADE_OBJECT_PATH  = "/org/mxlinux/UpdaterViewAndUpgrade"
VIEW_AND_UPGRADE_OBJECT_IFACE = "org.mxlinux.UpdaterViewAndUpgrade"

#
AUTO_CLOSE_TIMEOUT_MIN =  1  # in seconds
AUTO_CLOSE_TIMEOUT_MAX = 60  # in seconds

class SettingsService:
    """
    <node>
     <interface name="org.mxlinux.UpdaterSettings">
        <method name="Close">
        </method>
        <method name="Minimize">
        </method>
        <method name="Restore">
        </method>
        <method name="SetValue">
          <arg direction="in"  type="s" name="key" />
          <arg direction="in"  type="s" name="value" />
        </method>
    </interface>
    </node>
    """

    def __init__(self, dialog):
        self.dialog = dialog
        #self._value = ""
        #self._settings = {}
        #self._settings_store = {}
        #self._settings = QSettings("MX-Linux", "mx-updater")
        # QObject wrapper for emitting Qt signals
        class _Emitter(QObject):
            value_changed_qt = pyqtSignal(str, str)
        self._emitter = _Emitter()

    # expose Qt signal to others
    @property
    def value_changed_qt(self):
        return self._emitter.value_changed_qt

    def SetValue(self, key, value):
        if not key.strip():
            return

        # write QSettings - nope will be done in update_setting_dialog
        #self._settings.setValue(key, value)
        #force write to disk
        #self._settings.sync()

        # emit PyQt signal value_changed_qt
        self._emitter.value_changed_qt.emit(key, value)
        # emit dbus signal for external listener
        #self.ValueChanged(key, value)


    def Close(self):
        self.dialog.close()

    def Minimize(self):
        self.dialog.minimize()

    def Restore(self):
        self.dialog.restore()

    # dbus signal not used - as we use directrly PyQt signal
    #def ValueChanged(self):
    #    pass

class SettingsEditorDialog(QDialog):

    value_changed_signal = pyqtSignal(str, str)

    def __init__(self):
        super().__init__()

        self.bus = SessionBus()
        self.service = SettingsService(self)
        self.bus.publish(SETTINGS_OBJECT_NAME, self.service)
        self.dbus_call_back = True

        self._init_done = False

        self._auto_upgrade_state_is_updating = False

        self.is_detect_plasma = self.detect_plasma()
        self.disable_hide_until = (self.is_detect_plasma,)
        #self.is_detect_fluxbox = self.detect_fluxbox()
        #self.disable_hide_until = (self.is_detect_fluxbox, self.is_detect_plasma)

        # Connect to the service's Qt signal (avoids DBus loopback)
        self.service.value_changed_qt.connect(self.on_value_changed)
        # Connect the PyQt signal to the update_tray_icon method
        self.value_changed_signal.connect(self.update_setting_dialog)

        self.initUI()


    def unattended_upgrade_current_state(self):
        """
        Check and set current unattended upgrade state
        """
        me = "unattended_upgrade_current_state@Settings"
        try:
            # Use the method from previous example to check current state
            current_state = self.is_unattended_upgrade_enabled()

            # Set checkbox to match current state
            self.auto_upgrade_checkbox.setChecked(current_state)

        except Exception as e:
            logger.error("[%s] Checking unattended upgrade state failed: %s", me, str(e))

    def is_unattended_upgrade_enabled(self):
        """
        Check if unattended upgrade is enabled

        Returns:
            bool: True if unattended upgrade is enabled
        """
        me = "is_unattended_upgrade_enabled@Settings"
        try:
            cmd = ['apt-config', 'shell', 'opt', 'APT::Periodic::Unattended-Upgrade/b']
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            # match the single-quoted apt-config shell output
            output = result.stdout.strip()
            return output == "opt='true'"

        except subprocess.CalledProcessError:
            return False


    def on_value_changed(self, key, value):
        # Called when SetValue writes QSettings and emits the Qt signal
        self.value_changed_signal.emit(key, value)

    def update_setting_dialog(self, key, value):
        # update_setting_dialog key,value pair
        # logger.debug(f"Settings dialog updated with key=value: {key}={value}")
        me = "update_setting_dialog@Settings"
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
                # convert string to integer
                new_value = int(value)
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
                self.settings[key] = new_value
                self.auto_close_checkbox.setChecked(new_value)

            case 'auto_close_timeout':
                self.settings[key] = new_value
                self.auto_close_timeout.setValue(new_value)

            case 'hide_until_upgrades_available':
                self.settings['hide_until_upgrades_available'] = new_value
                self.hide_until_upgrades_available_checkbox.setChecked(new_value)

            case 'use_dbus_notifications':
                self.settings[key] = new_value
                self.use_dbus_notifications_checkbox.setChecked(new_value)

            case 'use_nala':
                self.settings[key] = new_value
                self.use_nala_checkbox.setChecked(new_value)

            case 'upgrade_assume_yes':
                self.settings[key] = new_value
                self.upgrade_assume_yes_checkbox.setChecked(new_value)

            case 'wireframe_transparent':
                self.settings[key] = new_value
                self.wireframe_transparent_checkbox.setChecked(new_value)

            case _:
                # default if any
                pass


    def minimize(self):
        self.showMinimized()

    def restore(self):
        self.showNormal()
        self.activateWindow()
        QApplication.setActiveWindow(self)

        # check if wmctrl exists and is executable
        wmctrl_path = '/usr/bin/wmctrl'
        if os.path.exists(wmctrl_path) and os.access(wmctrl_path, os.X_OK):
            # check if WAYLAND_DISPLAY is not set
            if 'WAYLAND_DISPLAY' not in os.environ:
                window_title = self.windowTitle()
                command = [wmctrl_path, '-r', window_title, '-u', '-F', '-b', 'remove,hidden,shaded']
                try:
                    subprocess.run(command, check=True)
                except Exception:
                    pass

    def close(self):
        QApplication.quit()

    def initUI(self):

        self.ok_clicked = False
        self.selected_icons = {}
        self.settings = {}
        self.saved_settings = {}

        # Initialize settings manager
        self.settings_manager = UpdaterSettingsManager()
        self.qsettings = self.settings_manager.qsettings

        # Load settings
        self.settings = self.settings_manager.load_all_settings()
        self.icon_set = self.settings_manager.get_icon_set_config()
        self.icon_order = self.settings_manager.get_icon_order()
        self.save_setting = self.settings_manager.save_setting
        self.load_setting = self.settings_manager.load_setting
        self.dialog = self.create_dialog()

        # center window on the screen
        self.center()

        # flag to check if window has been shown
        self.first_resize = True
        self._init_done = True


    def style_margins(self):
        # set framk margins
        gtk_frame_margins = (0, 10, 0, 0)
        breeze_frame_margins = (8, 0, 5, 5)
        other_frame_margins = (8, 3, 5, 3)
        other_frame_margins = (8, 10, 5, 3)
        # Get the current style
        current_style = QApplication.style().objectName()
        print(f"QApplication.style = {current_style}")
        if "gtk" in current_style:
            frame_margins = gtk_frame_margins
        elif "breeze" in current_style:
            frame_margins = breeze_frame_margins
        else:
            frame_margins = other_frame_margins

        return frame_margins

    def create_dialog(self):
        self.setWindowTitle(_('MX Updater preferences'))

        #self.setWindowIcon(QIcon("mx-updater-settings.svg"))
        self.setWindowIcon(QIcon("/usr/share/icons/hicolor/scalable/apps/mx-updater-settings.svg"))
        self.setGeometry(100, 100, 400, 400)  # X, Y,  Width, Height

        # margins for main layout (left, top, right, bottom)
        overall_margins = (8, 5, 8, 5)
        # frame margins (left, top, right, bottom)
        frame_margins = (0, 8, 0, 0)
        frame_margins = (0, 0, 0, 0)
        frame_margins = (0, 5, 0, 0)
        frame_margins = self.style_margins()

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.setContentsMargins(*overall_margins)

        #---------------------------------------------------------------
        # upgrade_frame: Upgrade mode
        #---------------------------------------------------------------
        upgrade_frame = QGroupBox(_("Upgrade mode"))
        upgrade_frame.setStyleSheet("QGroupBox { font-weight: bold; }")

        upgrade_layout = QVBoxLayout()
        upgrade_layout.setSpacing(1)  # smaller spacing between options
        # layout margins (left, top, right, bottom)
        upgrade_layout.setContentsMargins(*frame_margins)

        self.upgrade_button_group = QButtonGroup(self)
        self.full_upgrade_radio = QRadioButton(self.squeeze_spaces(
                _("full upgrade   (recommended)"))
                )
        self.full_upgrade_radio.setToolTip(
        _(
        """Upgrades all packages to their latest versions,
which may include adding or removing packages
to keep the system up-to-date and consistent."""))
        self.basic_upgrade_radio = QRadioButton(_("basic upgrade"))
        self.basic_upgrade_radio.setToolTip(
        _("""Upgrades existing packages to their latest versions
without installing new dependencies or removing existing packages."""))

        self.upgrade_button_map = {
            self.full_upgrade_radio: "full-upgrade",
            self.basic_upgrade_radio: "basic-upgrade",
        }

        # radio buttons to button group
        self.upgrade_button_group.addButton(self.full_upgrade_radio)
        self.upgrade_button_group.addButton(self.basic_upgrade_radio)

        try:
            if self.settings["upgrade_type"] in ("dist-upgrade", "full-upgrade"):
                self.full_upgrade_radio.setChecked(True)
            else:
                self.basic_upgrade_radio.setChecked(True)
        except:
            self.full_upgrade_radio.setChecked(True)

        # use_nala_checkbox with tooltip
        self.use_nala_checkbox = QCheckBox(_("use nala"))
        self.use_nala_checkbox.setToolTip(_("Select this to use nala package manager instead of apt."))

        if self.settings["use_nala"]:
            self.use_nala_checkbox.setChecked(True)

        # Does /usr/bin/nala exists and is executable
        if os.path.isfile('/usr/bin/nala') and os.access('/usr/bin/nala', os.X_OK):
            # horizontal layout for full upgrade radio button and use_nala checkbox
            upgrade_h_layout = QHBoxLayout()
            upgrade_h_layout.addWidget(self.full_upgrade_radio)

            # stretch space to pushuse_nala_checkbox right
            upgrade_h_layout.addStretch()  # This will take up all available space

            # use_nala_checkbox with a small fixed spacing
            upgrade_h_layout.addWidget(self.use_nala_checkbox)
            upgrade_h_layout.addSpacing(20)  # fixed 20 pixels
        else:
            self.use_nala_checkbox.setChecked(False)
            # no nala, add radio button only
            upgrade_h_layout = QHBoxLayout()
            upgrade_h_layout.addWidget(self.full_upgrade_radio)

         # Add horizontal layout and other widgets to upgrade layout
        upgrade_layout.addLayout(upgrade_h_layout)
        upgrade_layout.addWidget(self.basic_upgrade_radio)

        #---------------------------------------------------------------
        # upgrade_frame connections
        #---------------------------------------------------------------

        # Connect button group signal to slot
        self.upgrade_button_group.buttonClicked.connect(self.on_upgrade_button_clicked)

        # Connect checkbox signals to slot
        self.use_nala_checkbox.toggled.connect(
            lambda checked: self.on_use_nala_checkbox_toggled(checked))

        #---------------------------------------------------------------
        # auto_upgrade
        #---------------------------------------------------------------

        # Allow to select only automatic upgrade

        self.auto_upgrade_checkbox = QCheckBox(
            self.squeeze_spaces(
              #_("update automatically")))
              _("upgrade automatically")))
        self.auto_upgrade_checkbox.setToolTip(
        _("""Automatically check for package updates once a day and install them.
Only updates existing packages without changing your system configuration.
The updater icon shows the total number of updates, including automatic updates,
when additional updates are available."""))


        self.auto_cache_update_checkbox = QCheckBox(
            self.squeeze_spaces(
              _("update automatically")))
              #_("upgrade automatically")))
        self.auto_cache_update_checkbox.setToolTip(
        _("""Automatically update package cache with "apt update".
          """))

        # Allow to select automatic upgrade and pkg cache update
        if True:
            # Only allow to select automatic upgrade
            upgrade_layout.addWidget(self.auto_upgrade_checkbox)
        else:
            # Allow to select automatic upgrade and pkg cache update
            # horizontal layout for auto-upgrade and cache-updater
            auto_upgrade_h_layout = QHBoxLayout()
            auto_upgrade_h_layout.addWidget(self.auto_upgrade_checkbox)

            # stretch space to pushuse_nala_checkbox right
            # auto_upgrade_h_layout.addStretch()  # This will take up all available space

            # use_nala_checkbox with a small fixed spacing
            auto_upgrade_h_layout.addWidget(self.auto_cache_update_checkbox)
            auto_upgrade_h_layout.addSpacing(20)  # fixed 20 pixels

            upgrade_layout.addLayout(auto_upgrade_h_layout)

        #---------------------------------------------------------------
        # auto_upgrade checkbox set initilal state
        #---------------------------------------------------------------

        # initial auto_upgrade_checkbox state
        try:
            initial_state = self.is_unattended_upgrade_enabled()
            self.auto_upgrade_checkbox.setChecked(initial_state)
        except Exception as e:
            logging.error("Initial state of auto upgrade failed: %s", str(e))

        #---------------------------------------------------------------
        # auto_upgrade connections
        #---------------------------------------------------------------
        #self.auto_upgrade_checkbox.toggled.connect(
        #    lambda checked: self.on_auto_upgrade_checkbox_toggled(checked))
        self.auto_upgrade_checkbox.toggled.connect(self.on_auto_upgrade_checkbox_toggled)

        upgrade_frame.setLayout(upgrade_layout)
        layout.addWidget(upgrade_frame)

        #---------------------------------------------------------------
        # left_click_frame: Left-click behaviour
        #---------------------------------------------------------------

        left_click_frame = QGroupBox(_("Left-click behaviour   (when updates are available)"))
        left_click_frame.setStyleSheet("QGroupBox { font-weight: bold; }")
        left_click_layout = QVBoxLayout()
        left_click_layout.setSpacing(1)  # smaller spacing between options
        # layout margins (left, top, right, bottom)
        #left_click_layout.setContentsMargins(0, 10, 0, 0)  # adjust margins
        left_click_layout.setContentsMargins(*frame_margins)  # adjust margins

        # Check if /usr/bin/synaptic-pkexec exists and is executable
        self.opens_synaptic_radio = QRadioButton(_("opens Synaptic"))
        self.opens_view_and_upgrade_radio = QRadioButton(_("opens MX Updater 'View and Upgrade' window"))


        # Add the radio buttons to button group
        self.left_click_button_group = QButtonGroup(self)
        self.left_click_button_group.addButton(self.opens_synaptic_radio)
        self.left_click_button_group.addButton(self.opens_view_and_upgrade_radio)

        self.left_click_button_map = {
            self.opens_synaptic_radio: "package_manager",
            self.opens_view_and_upgrade_radio: "view_and_upgrade",
        }

        if self.settings.get("left_click") in 'package_manager':
            self.opens_synaptic_radio.setChecked(True)
        else:
            self.opens_view_and_upgrade_radio.setChecked(True)

        #---------------------------------------------------------------
        # left_click_frame connections
        #---------------------------------------------------------------
        # set connection

        # Connect button group signal to slot
        self.left_click_button_group.buttonClicked.connect(self.on_left_click_button_clicked)

        if (os.path.isfile('/usr/bin/synaptic-pkexec') and
            os.access('/usr/bin/synaptic-pkexec', os.X_OK)
            ):
            left_click_layout.addWidget(self.opens_synaptic_radio)
            left_click_layout.addWidget(self.opens_view_and_upgrade_radio)
            left_click_frame.setLayout(left_click_layout)
            layout.addWidget(left_click_frame)
        else:
            self.opens_view_and_upgrade_radio.setChecked(True)

        #---------------------------------------------------------------
        # icons_frame: Icons
        #---------------------------------------------------------------
        icons_frame = QGroupBox(_("Icons"))
        icons_frame.setStyleSheet("QGroupBox { font-weight: bold; }")
        icons_layout = QVBoxLayout()

        # layout margins (left, top, right, bottom)
        icons_layout.setContentsMargins(*frame_margins)  # Remove margins if needed

        self.icon_radio_buttons = {}  # name -> icon radio button
        self.wireframe_transparent_checkbox = QCheckBox(_("use transparent interior for no-updates wireframe"))
        self.wireframe_transparent_checkbox.setToolTip(
            _("""Display transparent wireframe icons without color fill
when no updates are available."""))

        for icon_name in self.icon_order:
            print(f"Icon_Look(name)={icon_name}")
            icon = self.icon_set.get(icon_name)
            icon_label = _(icon.get('label'))
            icon_some = icon.get('icon_some')
            icon_none = icon.get('icon_none')

            row_layout = QHBoxLayout()
            row_layout.setSpacing(20)  # smaller spacing between icons
            icon_radio_button = QRadioButton(icon_label)
            icon_radio_button.toggled.connect(
                lambda checked, label=icon_label, name=icon_name:
                self.on_icon_radio_button_toggled(checked, label, name))
            print(f"Icon_Look(icon_name={icon_name}")
            icon_look= self.settings.get('icon_look')
            print(f"self.settings.get('icon_look')={icon_look}")

            if icon_name == icon_look:
                icon_radio_button.setChecked(True)

            row_layout.addWidget(icon_radio_button)
            row_layout.addSpacing(10)  # spacing of 10 pixels
            row_layout.addWidget(self.create_icon_label(icon_some))
            row_layout.addSpacing(100)  # spacing of 100 pixels between icons
            row_layout.addWidget(self.create_icon_label(icon_none))
            row_layout.addSpacing(60)  # spacing of 60 pixels

            icons_layout.addLayout(row_layout)
            self.icon_radio_buttons[icon_name] = icon_radio_button  # Store the radio button

        # set connection
        self.wireframe_transparent_checkbox.toggled.connect(
            lambda checked:
            self.on_wireframe_transparent_checkbox_toggled(checked))

        if self.settings["wireframe_transparent"]:
            self.wireframe_transparent_checkbox.setChecked(True)

        icons_layout.addWidget(self.wireframe_transparent_checkbox)
        icons_frame.setLayout(icons_layout)
        layout.addWidget(icons_frame)

        #---------------------------------------------------------------
        # Frame: Other options
        #---------------------------------------------------------------
        other_options_frame = QGroupBox(_("Other options"))
        other_options_frame.setStyleSheet("QGroupBox { font-weight: bold; }")
        other_options_layout = QVBoxLayout()
        other_options_layout.setSpacing(1)  # small spacing between options

        other_options_layout.setContentsMargins(*frame_margins)  # with frame margins

        #---------------------------------------------------------------
        # upgrade_assume_yes_checkbox
        #---------------------------------------------------------------

        checkbox_label = _("automatically confirm all package upgrades")
        checkbox_tooltip = _(
            "Automatically answers 'yes' to package management prompts during upgrades.\n"
            "Some system configuration changes may still require manual confirmation."
            )

        self.upgrade_assume_yes_checkbox = QCheckBox(checkbox_label)
        self.upgrade_assume_yes_checkbox.setToolTip(checkbox_tooltip)


        # set connection
        self.upgrade_assume_yes_checkbox.toggled.connect(
            lambda checked:
            self.on_upgrade_assume_yes_checkbox_toggled(checked))
        if self.settings.get("upgrade_assume_yes"):
            self.upgrade_assume_yes_checkbox.setChecked(True)

        #---------------------------------------------------------------
         #---------------------------------------------------------------
        #---------------------------------------------------------------
        # start_8_login_checkbox

        # TRANSLATORS: The label of the checkbox where user can select
        #to start 'MX Updater' systray icon automatically at login
        #after a delay of seconds.
        checkbox_label = _('start "MX Updater" at login after delay')

        # TRANSLATORS: Explains the start of MX Updater automatically
        # after a delay of seconds. The user can select the number of seconds.
        checkbox_tooltip = _("""Select this to launch "MX Updater" automatically
at login after the specified delay in seconds.""")

        self.start_8_login_checkbox = QCheckBox(checkbox_label)
        self.start_8_login_checkbox.setToolTip(checkbox_tooltip)
        settings_key = "Settings/start_at_login"
        #---------------------------------------------------------------
        # start_8_login_delay spinbox
        self.start_8_login_delay_spinbox = QSpinBox()

        self.start_8_login_delay_spinbox.setRange(1, 60)

        # Load value from settings, or set default
        default_value = 5
        value = self.qsettings.value(f"{settings_key}_delay", default_value, type=int)
        value = default_value if value < 0 else min(value, 60)
        self.start_8_login_delay_spinbox.setValue(value)

        # TRANSLATORS: This is the abriavated string for 'seconds' shown within
        # the "start at login" selection field. Please use the most appropriate trnslated
        # string for the singular or plural form.
        seconds_suffix = _("sec")
        self.start_8_login_delay_spinbox.setSuffix(f" {seconds_suffix}")

        # Connect spinbox value change to save method
        #self.start_8_login_delay_spinbox.valueChanged.connect(self.save_start_8_login_delay)

        self.start_8_login_delay_spinbox.valueChanged.connect(
            lambda value: self.qsettings.setValue(f"{settings_key}_delay", value)
            )

        # Initial state setup
        start_8_login = self.qsettings.value(settings_key, "true")
        start_8_login = start_8_login.lower() in ["true","on", "1"]
        self.start_8_login_checkbox.setChecked(start_8_login)
        self.start_8_login_delay_spinbox.setEnabled(start_8_login)

        self.start_8_login_checkbox.toggled.connect(
            lambda checked: self.start_8_login_delay_spinbox.setEnabled(checked))
        self.start_8_login_checkbox.toggled.connect(
            lambda checked: self.qsettings.setValue(settings_key, checked))

       # horizontal layout for checkbox and spinbox
        start_8_login_layout = QHBoxLayout()
        start_8_login_layout.addWidget(self.start_8_login_checkbox)
        start_8_login_layout.addWidget(self.start_8_login_delay_spinbox)
        start_8_login_layout.addStretch()
        #---------------------------------------------------------------
        #---------------------------------------------------------------
        #---------------------------------------------------------------
        #---------------------------------------------------------------
        # auto_close_checkbox

        # TRANSLATORS: After the idle time in seconds has elapsed,
        # the terminal window is closed once the system update is complete.
        checkbox_label = _("close terminal window after idle time")

        # TRANSLATORS: Explains the auto-close behavior of terminal window
        # after system updates with a configurable idle time
        checkbox_tooltip = _("Automatically closes the terminal window after the specified\n"
                             "number of seconds of inactivity following system updates.")

        self.auto_close_checkbox = QCheckBox(checkbox_label)
        self.auto_close_checkbox.setToolTip(checkbox_tooltip)

        #---------------------------------------------------------------

        # auto_close_timeout spinbox
        self.auto_close_timeout = QSpinBox()

        self.auto_close_timeout.setRange(AUTO_CLOSE_TIMEOUT_MIN, AUTO_CLOSE_TIMEOUT_MAX)

        # Load value from settings, or set default
        #auto_close_timeout = self.qsettings.value("Settings/auto_close_timeout", 10, type=int)
        auto_close_timeout = self.load_setting("auto_close_timeout")
        self.auto_close_timeout.setValue(auto_close_timeout)

        # TRANSLATORS: This is the abriavated string for 'seconds' shown within
        # the timeout selection field. Please use the most appropriate trnslated
        # string for the singular or plural form. Only one form is shown.
        seconds_suffix = _("sec")
        self.auto_close_timeout.setSuffix(f" {seconds_suffix}")

        # Connect spinbox value change to save method
        self.auto_close_timeout.valueChanged.connect(self.save_auto_close_timeout)

        # Initial state setup
        #self.toggle_auto_close_timeout_spinbox(self.auto_close_checkbox.checkState())

        # Connect checkbox state change to enable/disable spinbox
        #self.auto_close_checkbox.stateChanged.connect(self.toggle_auto_close_timeout_spinbox)

        #---------------------------------------------------------------
        # set inital state
        if self.settings.get("auto_close"):
            self.auto_close_checkbox.setChecked(True)
            self.auto_close_timeout.setEnabled(True)
        else:
            self.auto_close_timeout.setEnabled(False)
            self.auto_close_checkbox.setChecked(False)

        #---------------------------------------------------------------
        # set connection
        self.auto_close_checkbox.toggled.connect(
            lambda checked:
            self.on_auto_close_checkbox_toggled(checked)
            )

       # horizontal layout to place checkbox and spinbox together
        timeout_layout = QHBoxLayout()
        timeout_layout.addWidget(self.auto_close_checkbox)
        timeout_layout.addWidget(self.auto_close_timeout)
        timeout_layout.addStretch()  # Pushes items to the left

        #---------------------------------------------------------------
        # use_dbus_notifications_checkbox
        self.use_dbus_notifications_checkbox = QCheckBox(_("use desktop notifications"))
        self.use_dbus_notifications_checkbox.setToolTip(
        _("""In addition to change of the tray icon,
pop-up messages will be shown when
system updates are available."""))

       # set connection
        self.use_dbus_notifications_checkbox.toggled.connect(
            lambda checked:
            self.on_use_dbus_notifications_checkbox_toggled(checked))

        if self.settings.get("use_dbus_notifications"):
            self.use_dbus_notifications_checkbox.setChecked(True)

        #---------------------------------------------------------------
        # hide_until_upgrades_available_checkbox
        self.hide_until_upgrades_available_checkbox = QCheckBox(_("hide until updates available"))
        self.hide_until_upgrades_available_checkbox.setToolTip(
        _("""Hide the system update icon when no updates are available.
Untick this box or run "MX Updater" from the menu to make the icon visible again."""))

        # set inital state
        if self.settings.get("hide_until_upgrades_available"):
            self.hide_until_upgrades_available_checkbox.setChecked(True)
        else:
            self.hide_until_upgrades_available_checkbox.setChecked(False)

        # set connection
        self.hide_until_upgrades_available_checkbox.toggled.connect(
            lambda checked:
            self.on_hide_until_upgrades_available_checkbox_toggled(checked))


        if self.settings.get("hide_until_upgrades_available"):
            self.hide_until_upgrades_available_checkbox.setChecked(True)

        #---------------------------------------------------------------
        other_options_layout.addWidget(self.upgrade_assume_yes_checkbox)
        #other_options_layout.addWidget(self.auto_close_checkbox)
        other_options_layout.addLayout(timeout_layout)
        other_options_layout.addWidget(self.use_dbus_notifications_checkbox)
        other_options_layout.addLayout(start_8_login_layout)
        if not any(self.disable_hide_until):
            other_options_layout.addWidget(self.hide_until_upgrades_available_checkbox)

        other_options_frame.setLayout(other_options_layout)
        layout.addWidget(other_options_frame)

        #---------------------------------------------------------------
        # Create a QDialogButtonBox
        """
        self.button_box = QDialogButtonBox(self)
        self.button_box.setStandardButtons(
             QDialogButtonBox.StandardButton.Help
            #|QDialogButtonBox.StandardButton.Cancel
            |QDialogButtonBox.StandardButton.Close
            #|QDialogButtonBox.StandardButton.Ok,
            )

        # Get the Close button
        self.close_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Close
        )

        # Get the Help button
        self.help_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Help
        )
        """
        self.button_box = QDialogButtonBox(self)

        #---------------------------------------------------------------
        # Close button
        self.close_button = self.button_box.addButton(QDialogButtonBox.StandardButton.Close)

        close_text_untranslated = "&Close"
        close_button_text = self.close_button.text()
        # translate close button label
        if  close_button_text == close_text_untranslated:
            #try gettext translation
            close_text = _(close_text_untranslated)

            if  close_text != close_text_untranslated:
                # Set translated text
                self.close_button.setText(close_text)

        # slots
        self.close_button.clicked.connect(self.on_close)

        """
        # TODO:  when we have an actual help content
        #---------------------------------------------------------------
        # Help button
        self.help_button = self.button_box.addButton(QDialogButtonBox.StandardButton.Help)

        help_button_text = self.help_button.text()
        print(f'help_button_text:  = {help_button_text}')

        # translate help button label
        if not '&' in help_button_text:
            # translate help button text
            help_text = _("&Help")
            print(f'help_text: _("&Help") = {help_text}')
            self.help_button.setText(help_text)

        # slot
        self.help_button.clicked.connect(self.on_close)
        #---------------------------------------------------------------
        """

        # button box to layout
        layout.addWidget(self.button_box)
        self.close_button.setFocus()


    #---------------------------------------------------------------
    def on_left_click_radio_toggled(self, checked, left_click):
        if checked:
            # store upgrade type in dictonry
            self.settings["left_click"] = left_click

    def on_left_click_button_clicked(self):
        # get selected button
        radio_button = self.left_click_button_group.checkedButton()
        if radio_button:
            left_click = self.left_click_button_map[radio_button]
            print(f"toggled left_click: {left_click}")
        else:
            left_click = "view_and_upgrade"
            print(f"set default left_click: {left_click}")

        #self.qsettings.setValue(f"Settings/left_click", left_click)
        self.settings['left_click'] = left_click
        self.save_setting("left_click", left_click)

        # Attempt to update the running apt-systray icon via D-Bus
        self.update_systray_icon('left_click', left_click)


    #---------------------------------------------------------------
    def on_upgrade_button_clicked(self):
        # get selected button
        radio_button = self.upgrade_button_group.checkedButton()
        if radio_button:
            upgrade_type = self.upgrade_button_map[radio_button]
            print(f"toggled upgrade_type: {upgrade_type}")
        else:
            upgrade_type = "full-upgrade"

        if  upgrade_type != "full-upgrade":
            upgrade_type = "upgrade"

        self.settings['upgrade_type'] = upgrade_type
        self.qsettings.setValue(f"Settings/upgrade_type", upgrade_type)
        self.qsettings.sync()

        # Attempt to update the running apt-systray icon via D-Bus
        self.update_systray_icon('upgrade_type', upgrade_type)

        # check states of checkboxes
        #self.settings['use_nala'] =  True if self.use_nala_checkbox.isChecked() else False
        #print(f"use_nala: {self.settings.get('use_nala')}")

        #self.settings['auto_update'] =  True if self.auto_upgrade_checkbox.isChecked() else False
        #print(f"auto_update: {self.settings.get('auto_update')}")

    #---------------------------------------------------------------
    def update_systray_icon(self, key, value):
        me = "update_systray_icon"

        if not self._init_done:
            return

        if not self.dbus_call_back:
            self.dbus_call_back = True
            print(f"No dbus callback for: {key} = {value}")
            return

        logger.debug("[%s] Try to update systray icon via dbus with: %s=%s", me, key, value)
        try:
            # Connect to the session bus
            bus = dbus.SessionBus()

            try:
                # dbus proxy object
                proxy = bus.get_object(TRAYICON_OBJECT_NAME, TRAYICON_OBJECT_PATH)

                # dbus interface
                interface = dbus.Interface(proxy, TRAYICON_OBJECT_IFACE)

                # method call to update systray icon settings with  key/value
                interface.SetValue(str(key), str(value))

            except dbus.exceptions.DBusException as e:
                # handle systray icon is not running
                #print(f"Systray icon not running: {e}")
                logger.debug("[%s] Systray icon not running or dbus error.", me)
                pass

        except Exception as e:
            #print(f"Unexpected D-Bus error: {e}")
            logger.debug("[%s] Unexpected D-Bus error: %s", me. e)


    #---------------------------------------------------------------
    def update_view_and_upgrade(self, key, value):

        me = "update_view_and_upgrade@UpdaterSettings"
        logger.debug("[%s] About to update view_and_upgrade dialog via dbus: %s = %s", me, key, value)
        logger.debug("[%s] dbus_call_back is %s", me, self.dbus_call_back)

        if not self.dbus_call_back:
            logger.debug("[%s] No callback to update view_and_upgrade dialog via dbus: %s = %s", me, key, value)
            logger.debug("[%s] reset dbus_call_back to %s", me, not self.dbus_call_back)
            self.dbus_call_back = True

            return


        prefix = 'no-dbus-callback@'

        print(f"Try update_view_and_upgrade via dbus: {key} = {value}")

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

        logger.debug("[%s] Try update view_and_upgrade dialog via dbus: %s = %s", me, key, value)
        logger.debug("[%s] dbus-call %s %s %s.SetValue %s %s", me,
                    VIEW_AND_UPGRADE_OBJECT_NAME,
                    VIEW_AND_UPGRADE_OBJECT_PATH,
                    VIEW_AND_UPGRADE_OBJECT_IFACE,
                    key,
                    value,
                    )

        try:
            # Connect to the session bus
            bus = dbus.SessionBus()

            try:
                # dbus proxy object
                proxy = bus.get_object(
                        VIEW_AND_UPGRADE_OBJECT_NAME,
                        VIEW_AND_UPGRADE_OBJECT_PATH
                    )

                # dbus interface
                interface = dbus.Interface(proxy, VIEW_AND_UPGRADE_OBJECT_IFACE)

                # method call to update settings with key/value
                interface.SetValue(str(key), str(value))

            except dbus.exceptions.DBusException as service_error:
                logger.debug("[%s] view_and_upgrade dialog does not appear to be active.", me)
                pass

        except Exception as e:
            logger.error("[%s] Unexpected D-Bus error: %r", me, e)
            pass

    #---------------------------------------------------------------
    def on_use_nala_checkbox_toggled(self, checked):
        # store use_nala selection into settings
        self.settings["use_nala"] = checked
        self.qsettings.setValue(f"Settings/use_nala", checked)
        self.qsettings.sync()
        self.update_view_and_upgrade("use_nala", checked)
        print(f"toggled use_nala: {checked}")

    def on_auto_upgrade_checkbox_toggledXXX(self, checked):
        # store auto_update selection into settings
        #self.settings["auto_update"] = checked
        #self.qsettings.setValue(f"Settings/auto_update", checked)
        logger.debug("toggled auto_update: %s", checked)
        self.apply_auto_upgrade_checkbox_toggled(checked)

    def on_auto_upgrade_checkbox_toggled(self, checked):
        # Prevent recursive calls
        if self._auto_upgrade_state_is_updating:
            return

        logger.debug("toggled auto_upgrade: %s", checked)
        try:
            # prevent recursion
            self._auto_upgrade_state_is_updating = True

            # current system state
            current_state = self.is_unattended_upgrade_enabled()
            logger.debug("current auto_upgrade state is: %s", current_state)
            logger.debug("toggle auto_upgrade state is: %s", checked)
            # state already set
            if current_state == checked:
                logging.info("Auto-upgrade already set to %r.", checked)
                message = _("Auto-upgrade setting is already in the desired state. No changes made.")
                self.show_message("Info", message, QMessageBox.Icon.Information)
                return

            # try to apply new state
            logger.debug("apply_auto_upgrade_checkbox_toggled: %s", checked)
            success = self.apply_auto_upgrade_checkbox_toggled(checked)
            logger.debug("apply_auto_upgrade_checkbox success: %s", success)

            if success:
                # state changed
                success = _("Success")
                message = _("Auto-upgrade setting updated successfully.")
                self.show_message(success, message, QMessageBox.Icon.Information)
                self.update_systray_icon("auto_upgrade", str(success).lower())
            else:
                # revert to previous state
                self.auto_upgrade_checkbox.setChecked(current_state)
                failure = _("Failure")
                message = _("Failed to update auto-upgrade setting.")
                self.show_message(failure, message, QMessageBox.Icon.Warning)

        except Exception as e:
            logging.error("Toggle error: %r", e)
            # Revert to previous known good state
            current_state = self.is_unattended_upgrade_enabled()
            self.auto_upgrade_checkbox.setChecked(current_state)

            # Show error message to user
            error = _("Error")
            message = _("An unexpected error occurred:")
            self.show_message(error, f"{message} {e}", QMessageBox.Icon.Critical)

        finally:
            # reset state_is_updating flag
            self._auto_upgrade_state_is_updating = False

    def show_message(self, title, message, icon):
        """
        Display a message box with given parameters

        :param title: Message box title
        :param message: Message content
        :param icon: QMessageBox icon type
        """
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(icon)
        msg_box.exec()



    def apply_auto_upgrade_checkbox_toggled(self, checked):
        """
        Apply the selected configuration
        """
        logging.debug("[apply_auto_upgrade_checkbox] clicked")
        try:
            # Check if Polkit is available
            #if not self.check_and_confirm_polkit():
            #    return

            # Select appropriate command based on desired state
            if checked:
                cmd = ['/usr/bin/pkexec', '/usr/lib/mx-updater/actions/auto-update-enable']
            else:
                cmd = ['/usr/bin/pkexec', '/usr/lib/mx-updater/actions/auto-update-disable']

            # Run the command
            result = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )

            success = checked == self.is_unattended_upgrade_enabled()
            return success

        except subprocess.CalledProcessError as e:
            # Show error popup
            title = _("Unattended Upgrades Configuration Failed")
            message=_("Could not change automatic upgrades configuration")
            command_failed= _("Command failed")
            details=f"{command_failed} [{e.returncode}]: {str(e.stderr)} "

            self.show_error_popup(
                title=title,
                message=message,
                details=details
            )

    def show_error_popup(self, title, message, details=None):
        """
        Display an error popup
        """
        from PyQt6.QtWidgets import QMessageBox

        error_dialog = QMessageBox(self)
        error_dialog.setIcon(QMessageBox.Icon.Critical)
        error_dialog.setWindowTitle(title)
        error_dialog.setText(message)

        if details:
            error_dialog.setDetailedText(details)

        error_dialog.exec()

    def on_wireframe_transparent_checkbox_toggled(self, checked):
        me = "on_wireframe_transparent_checkbox_toggled"
        logger.debug("[%s] toggled: %s", me, str(checked).lower())
        # store transparent icon selection into settings
        self.settings["wireframe_transparent"] = checked
        self.qsettings.setValue(f"Settings/wireframe_transparent", checked)
        self.qsettings.sync()
        name = self.settings.get("icon_look")
        if name.startswith("wireframe"):
            if checked:
                self.update_systray_icon("icon_look", f"{name}:transparent")
            else:
                self.update_systray_icon("icon_look", f"{name}:non-transparent")


    def on_icon_radio_button_toggled(self, checked, label, name):
        me = "on_icon_radio_button_toggled"
        if checked:
            logger.debug("[%s] toggled %s: %s", me, name, str(checked).lower())
            self.selected_icons["icon_selected"] = name
            self.settings["icon_look"] = name
            self.qsettings.setValue(f"Settings/icon_look", name)
            self.qsettings.sync()

            if name.startswith("wireframe"):
                self.wireframe_transparent_checkbox.setEnabled(True)
                # Attempt to update the running UpdaterSystemTray icon via D-Bus
                if self.settings.get("wireframe_transparent"):
                    self.update_systray_icon("icon_look", f"{name}:transparent")
                else:
                    self.update_systray_icon("icon_look", f"{name}:non-transparent")
            else:
                self.wireframe_transparent_checkbox.setEnabled(False)
                # Attempt to update the running UpdaterSystemTray icon via D-Bus
                self.update_systray_icon("icon_look", name)

    def on_upgrade_assume_yes_checkbox_toggled(self, checked):
        self.settings["upgrade_assume_yes"] = checked
        self.qsettings.setValue(f"Settings/upgrade_assume_yes", checked)
        self.qsettings.sync()
        self.update_view_and_upgrade("upgrade_assume_yes", checked)
        print(f"toggled upgrade_assume_yes: {checked}")

    def on_auto_close_checkbox_toggled(self, checked):
        self.auto_close_timeout.setEnabled(checked)
        self.settings["auto_close"] = checked
        self.qsettings.setValue(f"Settings/auto_close", checked)
        self.qsettings.sync()
        self.update_view_and_upgrade("auto_close", checked)
        print(f"toggled auto_close: {checked}")

    def on_use_dbus_notifications_checkbox_toggled(self, checked):
        # save use_dbus_notifications selection into settings dict
        self.settings["use_dbus_notifications"] = checked
        self.qsettings.setValue(f"Settings/use_dbus_notifications", checked)
        self.qsettings.sync()
        print(f"toggled use_dbus_notifications: {checked}")
        self.update_systray_icon("use_dbus_notifications", checked)


    def on_hide_until_upgrades_available_checkbox_toggled(self, checked):
        # save hide_until_upgrades_available selection into settings dict
        self.settings["hide_until_upgrades_available"] = checked
        self.qsettings.setValue("Settings/hide_until_upgrades_available", checked)
        self.qsettings.sync()
        print(f"toggled hide_until_upgrades_available: {checked}")
        self.update_systray_icon("hide_until_upgrades_available", checked)

    def save_auto_close_timeout(self, value):
        # save auto_close_timeout value to settings
        self.settings["auto_close_timeout"] = value
        self.qsettings.setValue("Settings/auto_close_timeout", value)
        self.qsettings.sync()
        self.update_view_and_upgrade("auto_close_timeout", value)

    def toggle_auto_close_timeout_spinbox(self, state):
        # Enable/disable spinbox based on checkbox state
        is_checked = state == Qt.CheckState.Checked
        self.auto_close_timeout.setEnabled(is_checked)


    #---------------------------------------------------------------
    #---------------------------------------------------------------
    def on_close_clicked(self):
        print("Close button clicked - on_close_clicked")
        self.close()

    def on_close(self):
        print("Close button clicked - on_close")
        self.close()

    #---------------------------------------------------------------

    def closeEvent(self, event):
        if self.ok_clicked:
            QApplication.exit(0)  # Exit with code 0 for OK
        else:
            QApplication.exit(1)  # Exit with code 1 for Cancel
        event.accept()  # Accept the event to close the dialog

    """
    def keyPressEvent(self, event: QKeyEvent):
        print(f"event.key()= {event.key()}")
        if event.key() in [Qt.Key.Key_Escape, Qt.Key.Key_Enter, Qt.Key.Key_Return] :  # Use Qt constant for Esc, Enter, and Return key
            self.on_close_clicked()  # Call the close method
        else:
            super().keyPressEvent(event)  # Call the base class method for other keys
    """

    def squeeze_spaces(self, text):
        return re.sub(r'\s+', ' ', text.strip())

    def create_icon_label(self, icon_path):
        label = QLabel()
        pixmap = QPixmap(icon_path)
        label.setPixmap(pixmap)
        label.setFixedSize(32, 32)  # Set a fixed size for the icon
        label.setScaledContents(True)  # Scale the pixmap to fit the label
        return label

    def name(self):
        return _("Preferences")

    def center(self):
        # Get the screen geometry using QMainWindow
        screen_geometry = self.screen().geometry()
        print("Screen Geometry (from QMainWindow):", screen_geometry)

        # Get the available geometry using QDesktopWidget
        #desktop = QDesktopWidget()
        desktop = QGuiApplication.primaryScreen()
        available_geometry = desktop.availableGeometry()
        print("Available Geometry (from primaryScreen()):", available_geometry)

        # Get the window geometry
        window_geometry = self.geometry()

        # Calculate the center position
        x = available_geometry.x() + (available_geometry.width() - self.width()) // 2
        y = available_geometry.y() + (available_geometry.height() - self.height()) // 2

        # Move the window to the center
        self.move(x, y)

    def resizeEventXXX(self, event):
        #return
        # Call the base class implementation
        super().resizeEvent(event)
        # Center the window after resizing
        self.center()

    def resizeEvent(self, event):
        # Call the base class implementation
        super().resizeEvent(event)

        # Center the window only after the first resize
        if self.first_resize:
            self.first_resize = False  # Set the flag to False after the first resize
            self.center()

    def print_existing_settings(self):
        # Create the QSettings object
        settings = QSettings("MX-Linux", "mx-updater")

        # Step 1: Read existing settings into a nested dictionary
        existing_settings = {}
        for key in settings.allKeys():
            parts = key.split('/')  # Assuming '/' is used as a separator for sub-keys
            current_level = existing_settings
            for part in parts[:-1]:
                current_level = current_level.setdefault(part, {})
            current_level[parts[-1]] = settings.value(key)

        # Step 2: Print the existing settings using pprint
        pprint(existing_settings)

    def update_settings(self, new_settings):

        # Step 1: Read existing settings
        existing_keys = self.qsettings.allKeys()

        # Step 2: Identify keys to remove
        keys_to_remove = [key for key in existing_keys
                            if key not in new_settings]

        # Step 3: Remove outdated keys
        for key in keys_to_remove:
            self.qsettings.remove(key)

        print("#", "-" * 40)
        print(f"Save selected settings:")
        # Step 4: Update existing keys and add new ones
        for key, value in new_settings.items():
            print(f"{key}={value}")
            self.qsettings.setValue(f"Settings/{key}", value)
        print("#", "-" * 10, " update_settings ", "-" * 30 )

    def print_window_title(self):
        # Get and print the current window title
        title = self.windowTitle()
        print(f"Current SettingsEditorDialog Title: {title}")


    def detect_plasma(self):
        # kde/plasma detection
        plasma_indicators = [
            os.environ.get('DESKTOP_SESSION', '').lower() == 'plasma',
            os.environ.get('XDG_CURRENT_DESKTOP', '').lower() == 'kde',
            os.environ.get('KDE_FULL_SESSION', '').lower() == 'true'
        ]

        if any(plasma_indicators):
            return any(plasma_indicators)

        # additional with process check
        try:
            plasma_shell_process = subprocess.run(
                ['pgrep', '-x', 'plasmashell'],
                capture_output=True,
                text=True
            )
            plasma_indicators.append(plasma_shell_process.returncode == 0)
        except Exception:
            try:
                plasma_shell_process = subprocess.run(
                    ['pidof', '-q', 'plasmashell'],
                    capture_output=True,
                    text=True
                )
                plasma_indicators.append(plasma_shell_process.returncode == 0)
            except Exception:
                pass

        return any(plasma_indicators)


    def detect_fluxbox(self):
        # fluxbox detection
        fluxbox_indicators = [
            os.environ.get('DESKTOP_SESSION', '').lower() == 'fluxbox',
            os.environ.get('XDG_SESSION_DESKTOP', '').lower() == 'fluxbox',
            os.environ.get('GDMSESSION', '').lower() == 'fluxbox'
        ]

        if any(fluxbox_indicators):
            return any(fluxbox_indicators)

        # additional with process check
        try:
            fluxbox_process = subprocess.run(
                ['pgrep', '-x', 'fluxbox'],
                capture_output=True,
                text=True
            )
            fluxbox_indicators.append(fluxbox_process.returncode == 0)
        except Exception:
            try:
                fluxbox_process = subprocess.run(
                    ['pidof', '-q', 'fluxbox'],
                    capture_output=True,
                    text=True
                )
                fluxbox_indicators.append(fluxbox_process.returncode == 0)
            except Exception:
                pass

        return any(fluxbox_indicators)


def is_dark_theme():
    return QApplication.palette().color(QPalette.ColorRole.Window).lightness() < 128

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
    app = QApplication(sys.argv)  # QApplication instance
    app.setApplicationName("mx-updater")
    app.setStyleSheet(tooltip_stylesheet())

    bus = SessionBus()
    try:
        # Check if the app is already running
        if bus.get(SETTINGS_OBJECT_NAME):
            print("App is already running, restoring window...")
            bus.get(SETTINGS_OBJECT_NAME).Restore()
            sys.exit(0)
    except Exception as e:
        print("App is not running, starting new instance...")


    #----------------------------------------------------------------
    # Create a QTranslator instance
    qtranslator = QTranslator()
    locale = QLocale.system().name()  # Get the system locale

    # Get the path to the translations directory
    translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    translation_file_path = f"{translations_path}/qt_{locale}.qm"

    # Load the translation file
    if qtranslator.load(translation_file_path):
        print(f"Translation file found: {translation_file_path}")
        app.installTranslator(qtranslator)
    else:
        print(f"Translation file not found: {translation_file_path}")

    #----------------------------------------------------------------
    dialog = SettingsEditorDialog()

    print(f"SettingsEditorDialog title: {dialog.windowTitle()}")
    print(f"qdbus6 {SETTINGS_OBJECT_NAME}  {SETTINGS_OBJECT_PATH}  {SETTINGS_OBJECT_IFACE} ")
    print(f"/usr/lib/qt6/bin/qdbus {SETTINGS_OBJECT_NAME}  {SETTINGS_OBJECT_PATH}  {SETTINGS_OBJECT_IFACE} ")
    print(f"/usr/lib/qt6/bin/qdbus {SETTINGS_OBJECT_NAME}  {SETTINGS_OBJECT_PATH}  ")

    dialog.show()

    dialog.print_window_title()

    sys.exit(app.exec())

"""

    # Check the return code after the dialog is closed
    return_code = app.exec()

    if return_code == 0:
        print("Action completed.")
    else:
        print("Cancelled action.")

    sys.exit(return_code)



if __name__ == "__main__":
    MyApp()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = MyApp()
    ex.show()
    sys.exit(app.exec_())


"""
