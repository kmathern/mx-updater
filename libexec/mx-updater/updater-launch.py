#!/usr/bin/python3


import os
import sys
import time
import subprocess
from PyQt6.QtCore import QSettings
import logging
import argparse

# Check root early. And do't let MX Updater run as root
if os.getuid() == 0:
    print("MX Updater should not be run as root. Please run it in user mode.")
    sys.exit(1)

#----------
# Argparser
#----------
import argparse

help_text="""

MX Updater will sit with the system tray icon and notify about available package updates.

"""

parser = argparse.ArgumentParser(
        description='MX Updater System Tray Icon',
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=help_text
        )

parser.add_argument("-d", "--debug",
                    help="Print debugging information.",
                    action="store_true")

parser.add_argument("-a", "--autostart",
                    help="Exit if MX Updater preference 'start_at_login' is disabled.",
                    action="store_true")

parser.add_argument("-r", "--restart",
                    help="Restart MX Updater systray icon.",
                    action="store_true")

parser.add_argument("-q", "--quit",
                    help="Quit MX Updater systray icon.",
                    action="store_true")

parser.add_argument("-w", "--wait", type=int,
                    help='Startup delay in seconds when using --autostart (default: 5)')

# default autostart delay
default_delay = 5

args = parser.parse_args()

#----------
# Logger
#----------

class CustomFormatter(logging.Formatter):
    # override formatTime
    def formatTime(self, record, datefmt=None):
        # current time with milliseconds
        millis = int(record.created * 1000) % 1000
        # only include hours, minutes and seconds
        time_str = super().formatTime(record, datefmt="%H:%M:%S")
        # add milliseconds
        return f"{time_str},{millis:03d}"

    def format(self, record):
        # format with original method
        return super().format(record)


logger = logging.getLogger(__name__)

if args.debug:
    logger.setLevel(logging.DEBUG)
else:
    logger.setLevel(logging.INFO)

# log stream handler to stdout
log_handler = logging.StreamHandler(sys.stdout)
log_handler.setLevel(logging.DEBUG)
# custom formatter
mx_updater = "MX Updater Launcher"
#formatter = CustomFormatter('%(asctime)s %(levelname)-8s %(name)s: %(message)s')
formatter = CustomFormatter('%(asctime)s [mx_updater] %(levelname)s: %(message)s')

log_handler.setFormatter(formatter)

# add handler to logger
logger.addHandler(log_handler)

#----------
# Check MX_UPDATER_PATH
#----------

try:
    MX_UPDATER_PATH = os.environ["MX_UPDATER_PATH"]
except KeyError:
    print("MX_UPDATER_PATH missing from environment, exiting")
    logger.error("MX_UPDATER_PATH missing from environment, exiting")
    sys.exit(1)

sys.path.insert(0, MX_UPDATER_PATH)
updater_path = os.path.join(MX_UPDATER_PATH, "updater-systray.py")
launch_args = ["/usr/bin/python3",  updater_path]

#----------
# Quit
#----------
dbus_quit_cmd = ['dbus-send',
                '--session',
                '--dest=org.mxlinux.UpdaterSystemTrayIcon',
                '--type=signal',
                '/org/mxlinux/UpdaterSystemTrayIcon',
                'org.mxlinux.UpdaterSystemTrayIcon.Quit'
                ]

ret=0
if args.quit:
    logger.info("Try to quit MX Updater systray icon:")
    logger.info(" ".join(dbus_quit_cmd[-2:]))
    ret = subprocess.run(dbus_quit_cmd).returncode
    logger.info("Dbus signal send to quit MX Updater systray icon" )
    sys.exit(ret)

if args.restart:
    logger.info("Try to restart MX Updater systray icon:")
    logger.info(" ".join(dbus_quit_cmd[-2:]))
    ret = subprocess.run(dbus_quit_cmd).returncode
    logger.info("Dbus signal send to quit MX Updater systray icon" )


#----------
# Check autostart is enabled
#----------

# retrieve startup delay and validate
settings = QSettings('MX-Linux', 'mx-updater')
try:
    saved_delay = settings.value('Settings/start_at_login_delay', type=int)

    logger.debug("AutoStart saved_delay settings value is '%s'", saved_delay)

    # non-negative
    if saved_delay is not None and saved_delay >= 0:
        delay = saved_delay
    else:
        # use argument or default
        delay = default_delay
except (TypeError, ValueError):
    # If settings can't be converted or are invalid
    delay = default_delay


if args.wait:
    delay = args.wait
    if delay < 0:
        logger.debug("Settings/start_at_login_delay -w/wait '%s' negative value ignored - using default", delay)
        delay = default_delay
    delay = max(0, delay)
    logger.debug("AutoStart delay saved as '%s'", delay)
    settings.setValue('Settings/start_at_login_delay', delay)
    settings.sync()

delay = max(0, delay)

#---------------------------
# Autostart delayed startup
#---------------------------

# delay launch if autostart is specified
if args.autostart:
    if delay > 0:
        logger.info(f"MX Updater autostart is waiting {delay} seconds before starting")
        time.sleep(delay)


#----------
# startup
#----------

if args.debug:
    launch_args += ['--debug'] 
    
logger.info("MX Updater systray icon start:")

ret=0
while True:
    if args.debug:
        print()
        print(" ".join(launch_args[:-2]).replace("--", "\n--"))
        print(" ".join(launch_args[-2:]))
        logger.info(" ")
        logger.info(" ".join(launch_args[:-2]).replace("--", "\n--"))
        logger.info(" ".join(launch_args[-2:]))

    try:
        #ret = subprocess.run(launch_args).returncode
        logger.info("Launch  MX Updater systray icon")
        subprocess.Popen(
            launch_args,
            ##stdout=subprocess.DEVNULL,
            ##stderr=subprocess.DEVNULL,
            )

        break
        # Special code for restarting so the save path can be updated..
        #if ret != misc.EXIT_CODE_UPDATER_RESTART_:
        #    break
    except subprocess.CalledProcessError as e:
        print("Error launching MX Updater: %s", str(e))
        ret = e.returncode
        break
    except KeyboardInterrupt:
        break
#logger.info("MX Updater systray icon finished,  exit(%s)" % ret )

sys.exit(ret)

