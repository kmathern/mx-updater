#!/usr/bin/python3


#########

import argparse
import os
import sys
import subprocess
import stat
import tempfile
import contextlib
import re
import psutil
import json
import glob
import hashlib
import signal

import threading
import time

import dbus
import dbus.service

import dbus.mainloop.glib
from gi.repository import GLib
import logging
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple, Optional
from colorama import Fore, Style
from colorama import init as color_init
color_init(autoreset=True)

# Constants
# d-bus
SYSTEM_SERVICE_NAME = "org.mxlinux.UpdaterSystemMonitor"
SYSTEM_OBJECT_PATH  = "/org/mxlinux/UpdaterSystemMonitor"
SYSTEM_INTERFACE    = "org.mxlinux.UpdaterSystemMonitor"

# updater-monitor
DEFAULT_LOGFILE = Path("/var/log/mx-updater-monitor.log")
RUNTIME_SENTINEL = Path("/run/mx-updater-monitor.started")
STATE_DIR  = Path("/var/lib/mx-updater-monitor")
STATE_FILE = STATE_DIR / "state.json"
TRAYICON_LOCK_NAME = "mx-updater-systrayicon"
TRAYICON_LOCK_RE = re.compile(rf"^{TRAYICON_LOCK_NAME}-(\d+)\.lock$")

# apt
SYNAPTIC_EXE = "/usr/sbin/synaptic"
SYNPREF      = "/var/lib/synaptic/preferences"
APTPREF      = "/etc/apt/preferences"

# locks
DEFAULT_LOCKS = [
    "/var/lib/dpkg/lock-frontend",
    "/var/lib/apt/lists/lock",
    "/var/lib/dpkg/lock",
]

# apps which blocks check_for_updates until closed
RUNNING_BLOCKING_APPS = [
     "/usr/bin/mx-packageinstaller",
     "/usr/sbin/synaptic",
     "/usr/bin/mx-repo-manager",
     "/usr/bin/apt",
     "/usr/bin/apt-get",
     "/usr/bin/aptitude",
     "/usr/bin/nala",
     "/usr/sbin/minstall",
     "/usr/bin/repo-manager",
     "/usr/bin/packageinstaller",
]
   
# run time
IDLE_TIMEOUT = 4 * 60  # seconds



UpgTuple   = Tuple[int, int, int, int]

logger = logging.getLogger(__name__)

def parse_args():
    p = argparse.ArgumentParser(description="MX Updater System Monitor")
    p.add_argument("--no-log-file", action="store_true",
                   help="disable logging to file; stderr only")
    p.add_argument("--debug",   action="store_true",
                   help="enable DEBUG logging")
    p.add_argument("--no-checksum",   action="store_true",
                   help="disable releases checksum validation ")
    p.add_argument("--no-color",   action="store_true",
                   help="disable ANSI-color logging")
    return p.parse_args()

def ensure_root():
    if os.geteuid() != 0:
        sys.stderr.write("ERROR: Must be run as root. Exiting.\n")
        sys.exit(1)

def setup_logging(use_file: bool, debug: bool):
    level = logging.DEBUG if debug else logging.INFO
    handlers = [logging.StreamHandler(sys.stderr)]

    if use_file:
        try:
            DEFAULT_LOGFILE.parent.mkdir(parents=True, exist_ok=True)
            # Test whether is writable
            with DEFAULT_LOGFILE.open("a"):
                pass
            fh = logging.FileHandler(DEFAULT_LOGFILE, mode="a")
            handlers.insert(0, fh)
        except Exception as e:
            sys.stderr.write(f"ERROR: Cannot open {DEFAULT_LOGFILE}: {e}\n")
            sys.exit(1)

    formatter = CustomFormatter("%(asctime)s %(levelname)s %(message)s")
    # configure handlers with custom formatter
    for handler in handlers:
        handler.setFormatter(formatter)
    # configure the logging
    logging.basicConfig(level=level, handlers=handlers)
    return logging.getLogger(__name__)


class CustomFormatter(logging.Formatter):
    # Define ANSI escape codes for colors

    COLORS = {
        'DEBUG':    Style.BRIGHT + Fore.CYAN,     # Bright Cyan
        'INFO':     Style.BRIGHT + Fore.BLUE,     # Bright Blue
        'WARNING':  Style.BRIGHT + Fore.YELLOW,   # Bright Yellow
        'ERROR':    Style.BRIGHT + Fore.RED ,     # Bright Red
        'CRITICAL': Style.BRIGHT + Fore.MAGENTA,  # Bright Purple
        'RESET':    Style.RESET_ALL,              # Reset to default
    }                                        


    def format(self, record):
        # customize INFO message
        if record.levelname == "INFOXXXX":
            adjusted_message = f"INFO: {record.getMessage()}"
            record.msg = adjusted_message  # Update the message in the record

        # get default formatted message
        formatted_message = super().format(record)

        if record.levelname == "INFO":
            #formatted_message = formatted_message.replace("INFO     ", "")
            formatted_message = formatted_message.replace("INFO ", "")

        if record.levelname != "INFO":
            # apply color to log level name
            level_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
            if args.no_color:
                level_name = f"[{record.levelname}]"
            else:
                level_name = f"{level_color}[{record.levelname}]{self.COLORS['RESET']}"
            
            # replace level name in formatted message
            formatted_message = formatted_message.replace(record.levelname, level_name)

        return formatted_message


class LockerChecker:
    def __init__(self,  lock_paths = None):
        self.lock_paths = lock_paths or DEFAULT_LOCKS;
        self._ensure_root()

    def _ensure_root(self):
        if os.geteuid() != 0:
            sys.stderr.write(f"ERROR: {SYSTEM_SERVICE_NAME} must be run as root.\n")
            sys.exit(1)

    def _get_holder(self, path: str):
        """
        Return a tuple (pid,  proc name) for first locked path.
        """
        holder = ()
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                for f in proc.open_files():
                    if f.path == path:
                        holder = (proc.info['pid'], proc.info['name'])
                        return holder
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        return holder

    def is_apt_locked(self):
        """
        Return a tuple (path,  holder } for first locked path.
        """
        result = ()
        for path in self.lock_paths:
            holder = self._get_holder(path)
            if holder:
                result = ( path, holder)
                break
        return result


    def which_running(self, exec_paths: List[str]) -> Tuple[bool, Set[str]]:
        """
        Scan /proc for running processes whose executable matches
        any in exec_paths.
        
        Returns:
          (found_any: bool, running: set_of_matched_paths)
        
        exec_paths should be absolute paths to the binaries.
        """
        # normalize to real (canonical) paths
        wanted: Set[str] = {os.path.realpath(p) for p in exec_paths}
        running: Set[str] = set()
    
        for entry in os.listdir('/proc'):
            if not entry.isdigit():
                continue
            pid = entry
            exe_link = os.path.join('/proc', pid, 'exe')
            try:
                target = os.path.realpath(exe_link)
            except (FileNotFoundError, PermissionError):
                # process gone or inaccessible: skip
                continue
    
            if target in wanted:
                running.add(target)
                break
    
        return (bool(running), running)



class UpdaterSystemMonitor(dbus.service.Object):
    """
    D-Bus service that provides a simple interface to get number of available updates.
    """
    def __init__(self, bus):
        bus_name = dbus.service.BusName(SYSTEM_SERVICE_NAME, bus=bus)
        super().__init__(bus_name, SYSTEM_OBJECT_PATH)

        self.loop = GLib.MainLoop()
        self._lock = threading.Lock()

        self._full_upgrades_available = (0, 0, 0, 0)
        self._basic_upgrades_available = (0, 0, 0, 0)
        self._upgrades_available = { "full-upgrade": self._full_upgrades_available,
                                     "basic-upgrade": self._basic_upgrades_available,
                                    }
        """
        with self._lock:

            loaded_state = self.load_state()
    
            if loaded_state is not None and self.validate_state(loaded_state, ""):
    
                self._full_upgrades_available = loaded_state["upgrades-available"]["full-upgrade"]
                self._basic_upgrades_available = loaded_state["upgrades-available"]["basic-upgrade"]
                self._upgrades_available = { "full-upgrade": self._full_upgrades_available,
                                             "basic-upgrade": self._basic_upgrades_available,
                                            }
        """
        
        self._check_in_progress = False
        self._idle_timeout = IDLE_TIMEOUT
        self.timer = None
        self.refresh_signal = None

        state, needs_check = self.init_state(no_checksum=args.no_checksum)

        self._full_upgrades_available = state["upgrades-available"]["full-upgrade"]
        self._basic_upgrades_available = state["upgrades-available"]["basic-upgrade"]
        self._upgrades_available = { "full-upgrade": self._full_upgrades_available,
                                     "basic-upgrade": self._basic_upgrades_available,
                                    }
        
        # On first activation create RUNTIME_SENTINEL and kick off scan
        #if not RUNTIME_SENTINEL.exists() or not STATE_FILE.exists():
        if not RUNTIME_SENTINEL.exists() or needs_check:
            if not RUNTIME_SENTINEL.exists():
                logging.debug(f"On first activation afer boot create runtime sentinel {RUNTIME_SENTINEL}")
                RUNTIME_SENTINEL.touch()
            if needs_check:
                logging.debug(f"Initial state validation failed -> check_for_updades sceduled ")
            logging.debug(f"Initiated: Check for Updades")
            self._spawn_scan()

        """
        def signal_handler(sig, frame):
            logging.debug(f"Received termination signal {sig}. Cleaning up...")
            # Perform any necessary cleanup here
            self.loop.quit()
        """
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGHUP, self.signal_handler)

    
        # catch Ctrl-C
        #for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        #    signal.signal(sig, lambda *a: self.loop.quit())

    def run(self):
        logging.info(f"Starting UpdaterSystemMonitor; will auto-exit after idle timeout {IDLE_TIMEOUT} seconds")
        # Start the idle timer immediately, so if *nothing* ever calls us
        # we still exit after EXIT_DELAY_MS
        self.reset_timer()
        self.loop.run()
        self.cancel_timer()
        # cleanup
        logging.debug("Clean exit.")


    def signal_handler(self, sig, frame):
        logging.debug(f"Received termination signal {sig} - cleaning up...")
        # Perform any necessary cleanup here
        if self.timer:
            self.timer.cancel()
        self.loop.quit()

    def cancel_timer(self):
        with self._lock:
            if self.timer:
                logging.debug("Idle timer cancelled")
                self.timer.cancel()
                self.timer = None
            else:
                logging.debug("Idle timer not set")

    def reset_timer(self):
        with self._lock:
            if self._check_in_progress:
                if self.timer:
                    logging.debug("Resetting the idle timer")
                    self.timer.cancel()
                    self.timer = None
                return

            if self.timer:
                logging.debug("Resetting the idle timer")
                self.timer.cancel()
                self.timer = None
            else:
                logging.debug("Starting the idle timer")

        self.timer = threading.Timer(self._idle_timeout, self.shutdown)
        self.timer.start()

    def shutdown(self):
        logging.info("Idle timeout reached. Shutdown due to inactivity.")
        # Clean up and exit
        self.cancel_timer()
        # Stop the mainloop
        self.loop.quit()

    @dbus.service.method(SYSTEM_INTERFACE, in_signature="", out_signature="")
    def Quit(self):
        """
        Called by client to shut us down cleanly.
        """
        logging.debug("Got a call to Quit")
        self.cancel_timer()
        # Stop the mainloop
        self.loop.quit()

    @dbus.service.method(SYSTEM_INTERFACE, name="upgrades_available", in_signature="", out_signature="a{sau}")
    def GetUpgradesAvailable(self):
        """
        Public D-Bus method.  Returns dict of tuples of available upgrades.
        """
        self.reset_timer()
        return self._upgrades_available


    @dbus.service.method(SYSTEM_INTERFACE, name="full_upgrades_available", in_signature="", out_signature="au")
    def GetFullUpgradesAvailable(self):
        """
        Public D-Bus method.  Returns tuples of available full-upgrades.
        """
        self.reset_timer()
        return self._full_upgrades_available


    @dbus.service.method(SYSTEM_INTERFACE, name="basic_upgrades_available", in_signature="", out_signature="au")
    def GetBasicUpgradesAvailable(self):
        """
        Public D-Bus method.  Returns tuples of available basic-upgrades.
        """
        self.reset_timer()
        return self._basic_upgrades_available

    @dbus.service.method(SYSTEM_INTERFACE, in_signature="", out_signature="")
    def Refresh(self):
        """
        Public D-Bus method.  Activates and returns immediately.
        """
        with self._lock:
            self.refresh_signal = True
        #self._emit_signals()
        # Launch the background thread
        logging.info("Recieved a Refresh d-bus call")
        self._spawn_scan()

    @dbus.service.method(SYSTEM_INTERFACE, in_signature="", out_signature="")
    def StateChanged(self):
        """
        Public D-Bus method.  Returns immediately. If a check_for_upgrade is already
        running, this call is simply ignored.
        """
        logging.info("Recieved a StateChanged d-bus call")

        # check any systray-ison clients are running
        if any_updater_systray_icons_running():
            logger.debug("At least one updater systray icon is alive.")
        else:
            logger.debug("No updater systray tray icons running. Nothing to do.")
            return
 
        # Launch the background thread
        self._spawn_scan()

    @dbus.service.signal(SYSTEM_INTERFACE, signature="a{sau}")
    def UpgradesChanged(self, upgrades_available):
        logging.debug(f"Emit signal UpgradesChanged: {upgrades_available}")

    @dbus.service.signal(SYSTEM_INTERFACE, signature="au")
    def FullUpgradesChanged(self, full_upgrades_available):
        logging.debug(f"Emit signal FullUpgradesChanged: {full_upgrades_available}")

    @dbus.service.signal(SYSTEM_INTERFACE, signature="au")
    def BasicUpgradesChanged(self, basic_upgrades_available):
        logging.debug(f"Emit signal BasicUpgradesChanged: {basic_upgrades_available}")

        
    def _spawn_scan(self):
        """Helper: start the background thread for _run_check_for_updades."""
        self.reset_timer()
        with self._lock:
            if self._check_in_progress:
                # another thread is already doing - ignored
                return
            # mark that we’re about to launch a check
            self._check_in_progress = True
        t = threading.Thread(target=self._run_check_for_updades, daemon=True)
        t.start()


    def _run_check_for_updades(self):
        """
        Run Check for Updates. When done, clear the flag and
        possibly emit UpgradesChanged.
        """

        # stop idle timeout
        self.cancel_timer()

        locker = LockerChecker()

        apt_is_locked = locker.is_apt_locked()
        found_blocker, running_blocker = locker.which_running(RUNNING_BLOCKING_APPS)
        log_lock = True
        apt_blocker  = ""
        # wait until apt is not longer locked and no b locking apps are running
        while apt_is_locked or found_blocker:
            if apt_is_locked:
                path = apt_is_locked[0]
                pid = apt_is_locked[1][0]
                proc = apt_is_locked[1][1]
                if log_lock:
                    logging.debug(f"Apt is locked: {path} by {proc} [{pid}]")
                    log_lock = False
                    apt_blocker  = ""
            elif found_blocker:
                blocking_app = running_blocker.pop()
                if not blocking_app in apt_blocker:
                    logging.debug(f"Waiting until blocking app is closed: {blocking_app}")
                    apt_blocker = blocking_app
                    log_lock = True

            time.sleep(2)
            apt_is_locked = locker.is_apt_locked()
            found_blocker, running_blocker = locker.which_running(RUNNING_BLOCKING_APPS)


        logging.debug("Apt is not locked. Blocking apps not running.")
        try:
            logging.debug("Starting Check for Updates")
            time.sleep(1)
            #-----------------
            # get upgrades available
            #-----------------
            with self._lock:

                loaded_state = self.load_state()
                new_state = loaded_state
                old_checksum = ""
                if loaded_state is not None and self.validate_state(loaded_state, ""):
                    self._full_upgrades_available =  loaded_state.get("upgrades-available",{}).get("full-upgrade", self._full_upgrades_available)
                    self._basic_upgrades_available =  loaded_state.get("upgrades-available",{}).get("basic-upgrade", self._basic_upgrades_available)
                    self._upgrades_available = loaded_state.get("upgrades-available", self._upgrades_available)
                    old_checksum = loaded_state.get("checksum-of-releases", old_checksum) 

                old = self._upgrades_available
                full_old = self._full_upgrades_available
                basic_old = self._basic_upgrades_available

            """        
            new_state = {
            "upgrades-available": {
                "full-upgrade":  self._full_upgrades_available, 
                "basic-upgrade": self._basic_upgrades_available, 
                },
            "checksum-of-releases": checksum
            }
            """

            #----------------------------
            # full-upgrade : dist-upgrade
            #----------------------------
            upgrade_type = "full-upgrade"
            with self.apt_preferences() as prefs:
                logging.debug(f"upgrade_type {upgrade_type}, using prefs file: {prefs!r}")
                nums = self.get_upgrade_info(upgrade_type=upgrade_type, preferences=prefs)
                (upgraded, newly_installed, to_remove, not_upgraded) = nums
                logging.debug(nums)

            full_new = (upgraded, newly_installed, to_remove, not_upgraded)
            # Only update & signal if changed
            if full_new != full_old:
                with self._lock:
                    self._full_upgrades_available = full_new
                    new_state["upgrades-available"][upgrade_type] = self._full_upgrades_available
                self.save_state(new_state)
                
                # Emit the D-Bus signal
                logging.info("New state for '%s'saved: %s", upgrade_type, new_state )
                logging.info("Emit FullUpgradesChanged D-Bus signal.")
                self.FullUpgradesChanged(full_new)
            elif self.refresh_signal:
                    self.FullUpgradesChanged(full_new)
            new = { "full-upgrade": full_new }

            #------------------------
            # basic-upgrade : upgrade
            #------------------------
            upgrade_type = "basic-upgrade"
            basic_upgrade_type = "upgrade"
            with self.apt_preferences() as prefs:
                logging.debug(f"upgrade_type {upgrade_type}, using prefs file: {prefs!r}")
                nums = self.get_upgrade_info(upgrade_type=basic_upgrade_type, preferences=prefs)
                (upgraded, newly_installed, to_remove, not_upgraded) = nums
                logging.debug(nums)

            basic_new = (upgraded, newly_installed, to_remove, not_upgraded)
            # Only update & signal if changed
            if basic_new != basic_old:
                with self._lock:
                    self._basic_upgrades_available = basic_new
                    new["basic-upgrade"] = basic_new
                    new_state["upgrades-available"][upgrade_type] = self._basic_upgrades_available
                self.save_state(new_state)

                # Emit the D-Bus signal
                logging.info("New state for '%s'saved: %s", upgrade_type, new_state )
                logging.info("Emit BasicUpgradesChanged D-Bus signal.")
                self.BasicUpgradesChanged(basic_new)
            elif self.refresh_signal:
                    self.BasicUpgradesChanged(basic_new)
            new["basic-upgrade"] = basic_new

            new_checksum = self.generate_apt_releases_checksum()
            
            new_state = {
            "upgrades-available": {
                "full-upgrade":  self._full_upgrades_available, 
                "basic-upgrade": self._basic_upgrades_available, 
                },
            "checksum-of-releases": new_checksum
            }
            if not new_checksum == old_checksum:
                self.save_state(new_state)
            
            # only update & signal if changed or refresh_signal received
            if new != old:
                with self._lock:
                    self._upgrades_available = new
                # emit the D-Bus signal
                logging.info("Emit UpgradesChanged D-Bus signal.")
                self.UpgradesChanged(new)
            else:
                if self.refresh_signal:
                    self.UpgradesChanged(new)
            
 
        except Exception as e:
            logging.error(f"Somthing went wrong: {e}")
        finally:
            # clear flags, even on error
            with self._lock:
                self._check_in_progress = False
                self.refresh_signal = False
            self.reset_timer()

    def _emit_signals(self):
        # Emit D-Bus signals
        self.FullUpgradesChanged(self._full_upgrades_available)
        self.BasicUpgradesChanged(self._basic_upgrades_available)
        self.UpgradesChanged(self._upgrades_available)


    def extract_first_summary(self, text):
        """
        From multiline APT output, find the first non-indented line with
        exactly four integers, then return the four integers space-separated.
        """
        pattern = re.compile(r"""
            ^(?!\s)      # line does NOT start with whitespace
            [^\d]*       # skip any non-digit chars
            (\d+)        # capture 1st integer
            [^\d]+
            (\d+)        # 2nd
            [^\d]+
            (\d+)        # 3rd
            [^\d]+
            (\d+)        # 4th
            [^\d]*$      # skip trailing non-digits
        """, re.VERBOSE)
    
        for line in text.splitlines():
            if not line or line[0].isspace():
                continue
    
            m = pattern.match(line)
            if m:
                nums = m.groups()
                return nums
        return ("", "", "", "")
    
    
    def is_regular_text_file(self,path):
        """
        Return True if path exists, is a regular file, and is readable.
        """
        try:
            st = os.stat(path)
        except FileNotFoundError:
            return False
    
        # must be a regular file
        if not stat.S_ISREG(st.st_mode):
            return False
    
        # must be readable
        if not os.access(path, os.R_OK):
            return False
    
        return True
    
    def choose_tmpfs_dir(self):
    
        # 1) XDG_RUNTIME_DIR
        xdg = os.environ.get("XDG_RUNTIME_DIR")
        if xdg and os.path.isdir(xdg) and os.access(xdg, os.W_OK):
            return xdg
    
        # 2) /run/user/$UID
        uid = os.geteuid()
        runuser = f"/run/user/{uid}"
        if os.path.isdir(runuser) and os.access(runuser, os.W_OK):
            return runuser
    
        # 3) POSIX shm mounts
        for d in ("/run/shm", "/dev/shm"):
            if os.path.isdir(d) and os.access(d, os.W_OK):
                return d
    
        # 4) fallback
        return tempfile.gettempdir()
    
    
    def find_apt_preferences(self):
    
        # check synaptic executable
        if not (os.path.isfile(SYNAPTIC_EXE) and os.access(SYNAPTIC_EXE, os.X_OK)):
            return None
    
        # check synaptic prefs is a regular, readable file
        if not self.is_regular_text_file(SYNPREF):
            return None
    
        with open(SYNPREF, "r", encoding="utf-8", errors="ignore") as f:
            syn_lines = f.readlines()
    
        # must contain a Package: line
        if not any(line.lstrip().startswith("Package:") for line in syn_lines):
            return None
    
        # check /etc/apt/preferences if it exists and is regular text
        if not os.path.exists(APTPREF):
            return SYNPREF
    
        if not self.is_regular_text_file(APTPREF):
            # Treat as “not there” if it's not a normal file
            return SYNPREF
    
        with open(APTPREF, "r", encoding="utf-8", errors="ignore") as f:
            apt_lines = f.readlines()
    
        # if only empty or comment lines, use synaptic prefs
        def is_real_line(l):
            s = l.strip()
            return s != "" and not s.startswith("#")
    
        if not any(is_real_line(l) for l in apt_lines):
            return SYNPREF
    
        # with entries in /etc/apt/preferences.
        # Merge it with synaptic prefs into a temp file.
        euid = os.geteuid()
        target_dir = self.choose_tmpfs_dir()
        prefix = f"apt_pref.{euid}."
        tf = tempfile.NamedTemporaryFile(
            mode="w",
            dir=target_dir,
            prefix=prefix,
            delete=False,
            encoding="utf-8",
        )
    
        try:
            tf.writelines(apt_lines)
            tf.write("\n")
            tf.writelines(syn_lines)
        finally:
            tf.close()
    
        return tf.name
    
    @contextlib.contextmanager
    def apt_preferences(self):
        """
        Context manager that yields the path to the appropriate apt prefs
        file (either the synaptic one or a merged temp file, or none),
        and cleans up the temp file on exit.
        """
        path = self.find_apt_preferences()
        try:
            yield path
        finally:
            if path and path != SYNPREF:
                try:
                    os.remove(path)
                except OSError:
                    pass
    
    
    def get_upgrade_info(self, upgrade_type="full-upgrade", preferences=None):
        # Run the apt-get command and capture the output
        command = [
            'apt-get', '-q',
            '-o', 'quiet::NoStatistics=true',
            '-o', 'quiet::NoProgress=true',
            '-o', 'Debug::NoLocking=true',
            '-o', 'Apt::Get::Show-Upgraded=false',
            '-o', 'APT::Get::Show-User-Simulation-Note=false',
            '-o', 'APT::Get::Show-Versions=false',
            '-o', 'Apt::Get::Trivial-Only=true',
        ]

        if not upgrade_type or upgrade_type not in ["dist-upgrade", "full-upgrade", "upgrade"]:
            upgrade_type = "full-upgrade"
           
        if upgrade_type == "upgrade":
            command += ['-o', 'APT::Get::Upgrade-Allow-New=false']
            
        if preferences:
            command += ['-o', f'Dir::Etc::preferences={preferences}']
    
        command.append(upgrade_type)
        logging.debug(f"Command: {' '.join(command)}")
        result = subprocess.run(command, env={'LC_ALL': 'C'}, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout
    
        (upgraded, newly_installed, to_remove, not_upgraded) =  ("", "", "", "")
        nums = (upgraded, newly_installed, to_remove, not_upgraded)
        if result:
            (upgraded, newly_installed, to_remove, not_upgraded) = self.extract_first_summary(result)
            if upgraded:
                upgraded = int(upgraded)
                newly_installed = int(newly_installed) if newly_installed else 0
                to_remove = int(to_remove) if to_remove else 0 
                not_upgraded = int(not_upgraded) if not_upgraded else 0
                nums = (upgraded, newly_installed, to_remove, not_upgraded)
        return nums

    # -- state
    def init_state(self, no_checksum: bool) -> Tuple[Dict[str, Any], bool]:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
    
        logger.debug(" ... intial state info")

        fresh_checksum = self.generate_apt_releases_checksum() if not no_checksum else ""
        raw = self.load_state()
    
        if raw is not None and self.validate_state(raw, fresh_checksum):
            if no_checksum:
                logger.info("Existing state is valid.")
            else:
                logger.info("Existing state is valid. No upgrade check needed.")
            return raw, False
    
        # Fresh start
        if no_checksum:
            logger.info("Initializing fresh state.")
        else:
            logger.info("Initializing fresh state. Scheduling upgrade check.")
        new_state = {
            "upgrades-available": {
                "full-upgrade":  (0, 0, 0, 0),
                "basic-upgrade": (0, 0, 0, 0),
            },
        }
        if fresh_checksum:
            new_state["checksum-of-releases"] = fresh_checksum
        self.save_state(new_state)
        return new_state, True
    
    

    def is_valid_upg_tuple(self, obj: Any) -> bool:
        return (
            isinstance(obj, (list, tuple))
            and len(obj) == 4
            and all(isinstance(x, int) for x in obj)
        )
    


    def load_state(self) -> Optional[Dict[str, Any]]:
        logger.info("loading state file '%s'", STATE_FILE)
        try:
            with STATE_FILE.open("r", encoding="utf-8") as f:
                state = json.load(f)
                #logger.debug(f"loaded state={json.dumps(state, indent=2)}")
                return state
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.info("Could not load state file %s: %s", STATE_FILE, e)
            return None

    def validate_state(self, data: Dict[str, Any], fresh_checksum: str) -> bool:
        if fresh_checksum:
            logger.debug(f"Validate state file with checksum {fresh_checksum!r}")
        else:
            logger.debug(f"Validate state file without checksum.")
            
        try:
            fu = data["upgrades-available"]["full-upgrade"]
            bu = data["upgrades-available"]["basic-upgrade"]
            if fresh_checksum:
                checksum = data["checksum-of-releases"]
        except (KeyError, TypeError) as e:
            logger.warning("State file missing required keys or wrong structure: %s", e)
            return False
    
        if not self.is_valid_upg_tuple(fu):
            logger.warning("Invalid full-upgrades tuple")
            return False
    
        if not self.is_valid_upg_tuple(bu):
            logger.warning("Invalid basic-upgrades tuple")
            return False
    
        if fresh_checksum:
            if checksum != fresh_checksum:
                logger.info("Release checksum mismatch (old=%s, new=%s)", checksum, fresh_checksum)
                return False
    
        return True
    
   
    def save_state(self, data: Dict[str, Any]) -> None:
        tmp = STATE_FILE.with_suffix(".tmp")
        # write and flush+fsync temp file
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
    
        # atomic replace
        os.replace(tmp, STATE_FILE)
    
        # fsync the directory to ensure the rename is durable (best-effort)
        try:
            dirfd = os.open(str(STATE_FILE.parent), os.O_DIRECTORY)
            try:
                os.fsync(dirfd)
            finally:
                os.close(dirfd)
        except Exception:
            # ignore filesystems that don't support directory fsync or other errors
            pass
    
        logger.info("State saved to %s", STATE_FILE)
        #logger.debug("saved state=%s", json.dumps(data, indent=2))
    
    
    # -- checksum 
    def generate_apt_releases_checksum(self):
        """
        Replicates somthing like the shell one-liner:
          sha256sum /dev/null /var/lib/apt/lists/*Release \
          2>/dev/null \
          | cut -d ' ' -f1 \
          | sort -u \
          | sha256sum - \
          | cut -d ' ' -f1
    
        Returns:
          A SHA256 hex-digest string of the sorted, unique list of per-file hashes.
        """
        logger.debug(" ... generate apt releases checksum")
    
        files = [
            "/dev/null", 
            "/etc/apt/preferences",
            "/var/lib/dpkg/status",
            "/var/lib/synaptic/preferences", 
            *glob.glob("/var/lib/apt/lists/*Release"),   # '*' unpacks the glob list
            *glob.glob("/etc/apt/preferences.d/*"),      # 
            *glob.glob("/var/lib/synaptic/preferences")  # 
        ]
    
        # generate sha256 hex digests for each file
        digests = set()
        for path in files:
            try:
                h = hashlib.sha256()
                with open(path, "rb") as f:
                    # read 8K chunks
                    for chunk in iter(lambda: f.read(8192), b""):
                        h.update(chunk)
                digests.add(h.hexdigest())
            except (OSError, IOError):
                # ignore file vanished, permissions, etc. -- just skip it
                continue
    
        # sort digests and join with '\n'
        sorted_digests = sorted(digests)
        joined = "\n".join(sorted_digests) + "\n"
        joined_bytes = joined.encode("utf-8")
    
        # generate final sha256 hash
        final_hash = hashlib.sha256(joined_bytes).hexdigest()
        return final_hash
    


def any_updater_systray_icons_running() -> bool:
    
    # Check /run/lock
    run_lock = Path("/run/lock")
    if run_lock.is_dir():
        for p in run_lock.iterdir():
            if not p.is_file():
                continue
            m = TRAYICON_LOCK_RE.match(p.name)
            if not m:
                continue

            # process lock file
            if _lock_file_alive(p):
                return True

    # Check each /run/user/<UID>/<TRAYICON_LOCK_NAME>-<UID>.lock
    run_user = Path("/run/user")
    if run_user.is_dir():
        for uid_dir in run_user.iterdir():
            if not (uid_dir.is_dir()
                    and uid_dir.name.isdigit()
                    and int(uid_dir.name) >= 1000
                ):
                continue

            lock_file = uid_dir / f"{TRAYICON_LOCK_NAME}-{uid_dir.name}.lock"
            if lock_file.is_file():
                if _lock_file_alive(lock_file):
                    return True

    return False


def is_process_alive(pid: int) -> bool:
    """Return True if a process with this PID exists."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True

def _lock_file_alive(p: Path) -> bool:
    """
    Return True if the PID in p is alive.  
    If p is unreadable or contains garbage, assume alive.
    If PID is dead, delete the file and return False.
    """
    try:
        text = p.read_text().strip()
        pid = int(text)
    except (OSError, ValueError):
        # unreadable or not an int: treat as alive to avoid false negatives
        return True

    if is_process_alive(pid):
        return True

    # stale lock—clean it up
    try:
        p.unlink()
    except OSError:
        pass
    return False



"""
def signal_handler(sig, frame):
    logging.debug(f"Received termination signal {sig}. Cleaning up...")
    # Perform any necessary cleanup here
    self.loop.quit()
"""

if __name__ == "__main__":

    args = parse_args()

    # check root
    ensure_root()

    # setup logging
    setup_logging(use_file=not args.no_log_file, debug=args.debug)
    logger.info('>>> %s initiated <<<', SYSTEM_SERVICE_NAME)
    if not args.no_log_file:
        logger.debug("Logging enabled log-file used at '%r'", DEFAULT_LOGFILE)

    # Inform on args.debug
    if args.debug:
        # some expensive debug-only setup or logic
        logger.debug("Running extra debug initialization")

    # confirm debug by logger
    if logger.isEnabledFor(logging.DEBUG):
        # alternative or complementary debug logic
        logger.debug("Logger confirmed DEBUG is enabled")

    # show we use color or not
    if not args.no_color:
        # logging with ANSI color
        if args.debug:
            logger.warning("Logging with ANSI-colors!")
    else:
        # logging w/o ANSI color
        logger.debug("Logging without ANSI-colors.")


    """
    # check any systray-ison clients are running
    if any_updater_systray_icons_running():
        logger.debug("At least one apt_systray_icon client is alive.")
    else:
        logger.debug("No systray tray icons running. Nothing to do. Exiting")
        sys.exit(0)
    """
    
    # we use releases checksums by default if not disabled
    if args.no_checksum:
        logger.debug("Initial state without releases checksum valdiation")
    else:
        logger.debug("Initial state with releases checksum valdiation")

    logger.info('>>> {0} Starting "{1}" {2} <<<'.format( '-' * 10, SYSTEM_SERVICE_NAME, '-' * 20,))

    #signal.signal(signal.SIGTERM, signal_handler)
    #signal.signal(signal.SIGINT, signal_handler)
    #signal.signal(signal.SIGHUP, signal_handler)

    # set GLib’s mainLoop as default
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)

    # connect to system bus
    try:
        bus = dbus.SystemBus()
        logger.debug(f"Ok, connected to system bus.")
    except dbus.DBusException as e:
        logger.error(f"Unable to connect to system bus: {e}", file=sys.stderr)
        sys.exit(1)

    # if already running, bail out - no double runs
    try:
        if bus.name_has_owner(SYSTEM_SERVICE_NAME):
            logger.info(f"{SYSTEM_SERVICE_NAME} is already running, exiting.")
            sys.exit(0)
        else:
            logger.debug(f"{SYSTEM_SERVICE_NAME} appears to be not running.")

    except dbus.DBusException as e:
        logger.error(f"Error checking name ownership: {e}", file=sys.stderr)
        sys.exit(1)

    # request bus name
    try:
        result = bus.request_name(
            SYSTEM_SERVICE_NAME,
            dbus.bus.NAME_FLAG_DO_NOT_QUEUE
        )
    except dbus.DBusException as e:
        logger.error(f"Failed to request name {SYSTEM_SERVICE_NAME}: {e}", file=sys.stderr)
        sys.exit(1)

    if result != dbus.bus.REQUEST_NAME_REPLY_PRIMARY_OWNER:
        logger.error(f"Could not become primary owner (got {result}), exiting.")
        sys.exit(1)

    # some helper info:
    logger.debug(" qdbus6 --system org.mxlinux.UpdaterSystemMonitor /org/mxlinux/UpdaterSystemMonitor ")
    logger.debug(" qdbus6 --system --literal org.mxlinux.UpdaterSystemMonitor /org/mxlinux/UpdaterSystemMonitor org.mxlinux.UpdaterSystemMonitor.GetUpgradesAvailable ")
    logger.debug(" qdbus6 --system --literal org.mxlinux.UpdaterSystemMonitor /org/mxlinux/UpdaterSystemMonitor org.mxlinux.UpdaterSystemMonitor.GetFullUpgradesAvailable ")
    logger.debug(" qdbus6 --system --literal org.mxlinux.UpdaterSystemMonitor /org/mxlinux/UpdaterSystemMonitor org.mxlinux.UpdaterSystemMonitor.GetBasicUpgradesAvailable ")
    logger.debug(" qdbus6 --system org.mxlinux.UpdaterSystemMonitor /org/mxlinux/UpdaterSystemMonitor org.mxlinux.UpdaterSystemMonitor.StateChanged ")
    logger.debug(" qdbus6 --system org.mxlinux.UpdaterSystemMonitor /org/mxlinux/UpdaterSystemMonitor org.mxlinux.UpdaterSystemMonitor.Refresh ")
    logger.debug(" qdbus6 --system org.mxlinux.UpdaterSystemMonitor /org/mxlinux/UpdaterSystemMonitor org.mxlinux.UpdaterSystemMonitor.Quit ")
    logger.debug(" qdbus6 --system org.mxlinux.UpdaterSystemMonitor /org/mxlinux/UpdaterSystemMonitor org.freedesktop.DBus.Introspectable.Introspect ")

    logger.info("Running Updater System Monitor...")
    logger.info(f"{SYSTEM_SERVICE_NAME} now running; entering mainloop.")

    monitor = UpdaterSystemMonitor(bus)
    # start the monitor
    monitor.run()
    # info on closing
    logger.info("Deactivating Updater System Monitor...")
    sys.exit(0)
