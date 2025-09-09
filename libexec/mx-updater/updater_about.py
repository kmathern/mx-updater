#! /usr/bin/python3
# -*- coding: utf-8 -*-

import os
import sys
import subprocess
from subprocess import Popen, check_call, run
from subprocess import DEVNULL, PIPE, CalledProcessError

from PyQt6 import QtWidgets, QtGui, QtCore
from PyQt6.QtWidgets import QApplication, QPushButton, QMessageBox
from PyQt6 import QtGui
from PyQt6.QtGui import (
    QFont, QIcon, QPixmap, QKeyEvent, QGuiApplication,
    QPalette, QColor
    )

BUILD_VERSION='%VERSION%'

# localization
import gettext
LOCALE_DOMAIN = 'mx-updater'
LOCALE_DIR = '/usr/share/locale'
gettext.bindtextdomain(LOCALE_DOMAIN, LOCALE_DIR)
gettext.textdomain(LOCALE_DOMAIN)
_ = gettext.gettext 


class AptnotifierAbout():

    def __init__(self):
        os.environ["QT_LOGGING_RULES"] = "qt.qpa.xcb.warning=false"

        self.__about_viewer = self.about_viewer

    @property
    def about_viewer(self):

        # list of viewers to check
        viewer_list = ['mx-viewer', 'antix-viewer']

        # xfce-handling
        if os.getenv('XDG_CURRENT_DESKTOP') == 'XFCE':
            viewer_list += ['exo-open']

        # set use xdg-open last to avoid html opens with tools like html-editor
        viewer_list += ['x-www-browser', 'gnome-www-browser', 'xdg-open']

        # take first found
        from shutil import which
        self.__about_viewer = list(filter( lambda x: which(x), viewer_list))[0]
        return self.__about_viewer


    def About(self, aboutBox):
        self.aboutBox = aboutBox


        updater_name         = _("MX Updater")
        about_updater        =  _("Tray applet to notify of system and application updates")
        about_updater_title  = _("About MX Updater")
        about_copyright      = 'Copyright (c) MX Linux'
        about_window_icon    = '/usr/share/icons/hicolor/scalable/mx-updater.svg'

        about_box_icon       = '/usr/share/icons/hicolor/96x96/apps/mx-updater.png'
        about_box_url        = 'https://mxlinux.org'
        about_copyright      = 'Copyright (c) MX Linux'
        about_window_icon    = '/usr/share/icons/hicolor/scalable/mx-updater.svg'
        changelog_file       = '/usr/share/doc/mx-updater/changelog.gz'
        license_file         = '/usr/share/doc/mx-updater/license.html'
        
        Close                = _("Close")
        License              = _("License")
        Changelog            = _("Changelog")
    
        license_title =  updater_name + ' - ' + License
        changelog_title = updater_name + ' - ' + Changelog
        license_title        = updater_name + ' - ' + License

        Changelog_Button = Changelog
        Close_Button     = Close
        License_Button   = License

        cmd = "dpkg-query -f ${Version} -W mx-updater".split()
        pkg_version = run(cmd, capture_output=True, text=True).stdout.strip()
        updater_version = pkg_version if pkg_version else BUILD_VERSION

        # link colors for dark:
        # link_color = "#58a6ff"  # soft blue
        # link_color = "#4CAF50"  # muted green-blue
        # link_color = "#64B5F6"  # light blue

        # link colors for dark:
        # link_color = "#58a6ff"  # soft blue
        # link_color = "#4CAF50"  # muted green-blue
        # link_color = "#64B5F6"  # light blue

        
        theme_link_colors = {
            #'light': '#1E88E5',  # deep blue for light theme
            'light': '#0d47a1',   # deeper navy blue for light theme
            'dark': '#58a6ff',    # soft blue for dark theme
            #'dark': '#4CAF50',    # muted green-blue
        }
    
        link_color = theme_link_colors['dark'] if self.is_dark_theme() else theme_link_colors['light']

        if self.is_dark_theme():
            link_style = f' style="color: {link_color};"'
            #print(f"Link color for dark theme is {link_color}")
        else:
            link_style = "" # use system defaults
            #print(f"Link color for light theme is {link_color}")
            
        
        aboutText = f"""
        <p align=center><b><h2>{updater_name}</h2></b></p>
        <p align=center>Version: {updater_version}</p>
        <p align=center><h3>{about_updater}</h3></p>
        <p align=center><a href="{about_box_url}" {link_style}>{about_box_url}</a>
        <br></p><p align=center>{about_copyright}<br /><br/></p>
        """
        #print(f"aboutText:'{aboutText}'")

        icon_pixmap = QtGui.QPixmap(about_box_icon)
        aboutBox.setIconPixmap(icon_pixmap)

        aboutBox.setWindowTitle(about_updater_title)
        aboutBox.setWindowIcon(QtGui.QIcon(about_window_icon))
        aboutBox.setText(aboutText)
        """
        class ButtonRole(enum.Enum)
        
         |  AcceptRole = <ButtonRole.AcceptRole: 0>
         |  
         |  ActionRole = <ButtonRole.ActionRole: 3>
         |  
         |  ApplyRole = <ButtonRole.ApplyRole: 8>
         |  
         |  DestructiveRole = <ButtonRole.DestructiveRole: 2>
         |  
         |  HelpRole = <ButtonRole.HelpRole: 4>
         |  
         |  InvalidRole = <ButtonRole.InvalidRole: -1>
         |  
         |  NoRole = <ButtonRole.NoRole: 6>
         |  
         |  RejectRole = <ButtonRole.RejectRole: 1>
         |  
         |  ResetRole = <ButtonRole.ResetRole: 7>
         |  
         |  YesRole = <ButtonRole.YesRole: 5>
        
        """
        changelogButton = aboutBox.addButton( (Changelog_Button), QMessageBox.ButtonRole.ActionRole)
        licenseButton   = aboutBox.addButton( (License_Button)  , QMessageBox.ButtonRole.ActionRole)
        closeButton     = aboutBox.addButton( (Close_Button)    , QMessageBox.ButtonRole.RejectRole)
        aboutBox.setDefaultButton(closeButton)
        aboutBox.setEscapeButton(closeButton)
        class_name = "mx-updater"

        while True:
            reply = aboutBox.exec()
            if aboutBox.clickedButton() == closeButton:
                sys.exit(reply)

            if aboutBox.clickedButton() == licenseButton:
                about_viewer = self.about_viewer
                if about_viewer in ['mx-viewer', 'antix-viewer' ]:
                    cmd = [about_viewer, license_file, license_title]
                    clx_filler = {
                        'about_viewer': about_viewer,
                        'license_title': license_title,
                        'class_name': class_name,
                    }
                    clx = """
                        xdotool sleep 0.3 
                        search --onlyvisible --class {about_viewer} 
                        search --classname {about_viewer}
                        search --name {license_title} 
                        set_window --classname {class_name} --class {class_name}
                        """

                    y = [ x.strip() for x in clx.strip().split('\n') ]
                    clx = [ x.format(**clx_filler) for x in ' '.join(y).split() ]
                    debug_p(clx)               
                    r = Popen(clx)
                    
                elif about_viewer == 'exo-open':
                    cmd = ['exo-open', '--launch', 'WebBrowser', license_file ]
                else:
                    cmd = [about_viewer, license_file ]
                #r = run(cmd, capture_output=True, text=True)
                Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                sys.exit(0)
            
            if aboutBox.clickedButton() == changelogButton:
                cmd = ['/usr/bin/python3', '/usr/libexec/mx-updater/updater-changelog.py']
                r = run(cmd, capture_output=True, text=True)
                #Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                #aboutBox.done()
                #sys.exit(0)

    def displayAbout(self):
        app = QApplication(sys.argv)
        app.setApplicationName("mx-updater")

        if is_dark_theme():
            IS_DARK_THEME = True
            #print(f"dark theme")
        else:
            IS_DARK_THEME = False
            #print(f"light theme")
        
        aboutBox = QMessageBox()
        about = AptnotifierAbout()
        about.About(aboutBox)
        aboutBox.show()
        sys.exit(app.exec())

    def is_dark_theme(self):
        return QApplication.palette().color(QtGui.QPalette.ColorRole.Window).lightness() < 128


def is_dark_theme():
    return QApplication.palette().color(QtGui.QPalette.ColorRole.Window).lightness() < 128


def debugging():
    """
    simple debugging helper
    """
    import os
    global debug_apt_notifier
    try:
        debug_apt_notifier
    except:
        try:
            debug_apt_notifier = os.getenv('MX_UPDATER_DEBUG')
        except:
            debug_apt_notifier = False

    return debug_apt_notifier

def debug_p(text=''):
    """
    simple debug print helper -  msg get printed to stderr
    """
    if debugging():
        print("Debug: " + text, file = sys.stderr)

def main():

    app = QApplication(sys.argv)
    app.setApplicationName("mx-updater")
    about = AptnotifierAbout()

    
    if about.is_dark_theme():
        IS_DARK_THEME = True
        #print(f"dark theme")
    else:
        IS_DARK_THEME = False
        #print(f"light theme")
        
    aboutBox = QMessageBox()
    about.About(aboutBox)
    aboutBox.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
