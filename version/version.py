
# version/version.py

import logging
import subprocess

class Version:
    version = "@VERSION@"
    pkgname = "@PKGNAME@"


class VersionMonitor:
    def __init__(self, package_name):
        """
        Initialize version monitor for a specific package

        Args:
            package_name (str): Name of the package to monitor
        """
        self.package_name = package_name

        self.running_version = Version.version
        logging.info(f"Running version of {package_name}: {self.running_version}")

        self.initial_installed_version = self._get_current_installed_version()
        logging.info(f"Initial version of {package_name}: {self.initial_installed_version}")


    def _get_current_installed_version(self):
        """
        Retrieve current installed package version

        Returns:
            str or None: Package version or None if not found
        """
        version, status = self.get_package_version(self.package_name)
        return version if version and status in ['ii', 'hi'] else None

    def check_version_change(self):
        """
        Check if package version has changed

        Returns:
            bool: True if version changed, False otherwise
        """
        # Skip if initial version was not set or not running installed version
        if (not self.initial_installed_version or
            self.initial_installed_version != self.running_version):
            return False

        current_version = self._get_current_installed_version()

        # Check for version change
        if (current_version and
            current_version != self.initial_installed_version):
            logging.info("Package version changed: %s -> %s",
                         self.initial_installed_version, current_version
                         )
            return True

        return False

    def get_package_version(self, package_name):
        """
        Retrieve package version and status using dpkg-query.

        Args:
            package_name (str): Name of the package to query

        Returns:
            tuple: (version, status) or (None, None) if package not found or status invalid
        """
        try:
            # Run dpkg-query to get abriavvated status abd version
            # Run dpkg-query to get abriavvated status abd version
            result = subprocess.run(
                ['dpkg-query', '-f', '${db:Status-Abbrev} ${Version}', '-W', package_name],
                capture_output=True,
                text=True,
                check=False
            )

            # Check if command was successful
            if result.returncode != 0:
                logging.warning(f"Package {package_name} not found")
                return None, None

            # Strip whitespace and split status and version
            output = result.stdout.strip()
            if not output:
                logging.warning(f"No output for package {package_name}")
                return None, None

            status, version = output.split(maxsplit=1)

            # Check if status is valid (installed or on hold)
            if status in ['ii', 'hi']:
                return version, status

            logging.warning(f"Invalid package status: {status}")
            return None, None

        except Exception as e:
            logging.error(f"Error querying package version: {e}")
            return None, None


        """
        # Check if version changed
        if self.version_monitor.check_version_change():
            # Call your existing restart function
            #self.restart_application()
            restart = self.actions.get("updater_restart")
            if restart:
                restart.trigger()

            action = self.actions.get("updater_restart")
            if action:
                action.trigger()

        """
