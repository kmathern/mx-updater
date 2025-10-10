#!/usr/bin/python3
# -*- coding: utf-8 -*-

from PyQt6.QtCore import QSettings
from typing import Dict, Any, Optional, List, Union, Type
from pprint import pprint

class UpdaterSettingsManager:
    def __init__(self, application_name: str = 'mx-updater'):
        """
        Initialize default internal settings
        
        :param application_name: used for QSettings
        """
        # default settings section
        self.section = 'Settings'
        # Initialize QSettings
        print(f'self.qsettings = QSettings("MX-Linux", "{application_name}")')
        self.qsettings = QSettings("MX-Linux", application_name)

        # internal settings dictionary
        self.settings: Dict[str, Any] = {}
        self.icons: Dict[str, Any] = {}

        
        # internal default settings 
        self.defaults: Dict[str, Dict[str, Any]] = {
            'Settings' : {
                'icon_look' : 'wireframe-dark',
                'wireframe_transparent' : True,
                'icon_look_allowed' : ( 'wireframe-dark',
                                        'wireframe-light',
                                        'classic',
                                        'pulse',
                                        'pulse-light'),
                'left_click' : 'view_and_upgrade',
                'left_click_allowed' : ('view_and_upgrade', 'ViewAndUpgrade',
                                        'package_installer', 'packageinstaller','PackageInstaller',
                                        'package_manager', 'packagemanager','PackageManager'
                                        ),
                'upgrade_assume_yes' : False,
                'upgrade_type' : 'full-upgrade',
                'upgrade_type_allowed' : (
                                        'dist-upgrade',
                                        'full-upgrade',
                                        'basic-upgrade',
                                        'upgrade'),
                'start_at_login' : True,
                'auto_close' : True,
                'auto_close_timeout' : 10,
                'use_dbus_notifications' : True,
                'use_nala' : False,
                'hide_until_upgrades_available' : False,
                #'''
                #IconLook=wireframe-dark
                #LeftClick=ViewAndUpgrade
                #UpgradeAssumeYes=false
                #UpgradeAutoClose=false
                #UpgradeType=dist-upgrade
                #WireframeTransparent=false
                #'''
                },
                'Icons' : {
                'icon_order' : [
                        'wireframe-dark',
                        'wireframe-light',
                        'classic',
                        'pulse',
                        'pulse-light',
                        ],

                'wireframe-dark' : {
                    'label' : 'wireframe dark',
                    'icon_some' : '/usr/share/icons/mnotify-some-wireframe.png',
                    'icon_none' : '/usr/share/icons/mnotify-none-wireframe-dark.png',
                    'icon_none_transparent' : '/usr/share/icons/mnotify-none-wireframe-dark-transparent.png',
                    },

                'wireframe-light' : {
                    'label' : 'wireframe light',
                    'icon_some' : '/usr/share/icons/mnotify-some-wireframe.png',
                    'icon_none' : '/usr/share/icons/mnotify-none-wireframe-light.png',
                    'icon_none_transparent' : '/usr/share/icons/mnotify-none-wireframe-light-transparent.png',
                    },

                'classic' : {
                    'label' : 'classic',
                    'icon_some' : '/usr/share/icons/mnotify-some-classic.png',
                    'icon_none' : '/usr/share/icons/mnotify-none-classic.png',
                    },
                'pulse' : {
                    'label' : 'pulse',
                    'icon_some' : '/usr/share/icons/mnotify-some-pulse.png',
                    'icon_none' : '/usr/share/icons/mnotify-none-pulse.png',
                    },
                'pulse-light' : {
                    'label' : 'pulse light',
                    'icon_some' : '/usr/share/icons/mnotify-pulse-green.png',
                    'icon_none' : '/usr/share/icons/mnotify-pulse-white.png',
                    },
                },
            }


        if self.is_fluxbox_running():
            icon_look_fluxbox = 'pulse-light'
            self.defaults['Settings']['icon_look'] = icon_look_fluxbox


    def get_typed_setting(self,
            settings: QSettings,
            internal_dict: Dict[str, Union[int, bool, str, float]],
            key: str
        ) -> Union[int, bool, str, float]:
        """
        Retrieve a setting with type based on the default value
        in the internal dictionary.
        
        Args:
            settings: QSettings instance
            internal_dict: Dictionary with default values
            key: Setting key to retrieve
        
        Returns:
            Value with the same type as in the internal dictionary
        """
        # Get the default value's type from the internal dictionary
        default_value = internal_dict.get(key)
        if default_value is None:
            raise KeyError(f"Key {key} not found in internal 'defaults' dictionary")
        
        default_type = type(default_value)
        
        # Retrieve the raw value from QSettings section "Settings"
        stored_value = settings.value(f"Settings/{key}", default_value)
        if key == 'wireframe_transparent':
            #print(f"Debug: {key} : stored_value = {stored_value} stored_value-type {type(stored_value).__name__}")
            #print(f"Debug: default_type {default_type}")
            pass
        # Handle type conversion for boolean values
        if default_type is bool:

            # Comprehensive list of false values
            false_values = ['false', 'False', 'no', 'No', '0', 0, 0.0, False]
            
            # return as is if already a bool 
            if isinstance(stored_value, bool):
                if key == 'wireframe_transparent':
                    #print(f"return as is if already a bool: {stored_value}")
                    pass
                return stored_value
    
            # check trueness for numeric values (int or float), 
            if isinstance(stored_value, (int, float)):
                return bool(stored_value)
    
            # If it's a string, try to convert to numeric
            if isinstance(stored_value, str):

                if key == 'wireframe_transparent':
                    #print(f"Debug: {key} : stored_value = {stored_value}") 
                    #print(f"Debug: default_type {default_type}")
                    pass

                try:
                    # Try converting to int first
                    numeric_value = int(stored_value.strip())
                    if key == 'wireframe_transparent':
                        #print(f"Try converting to int first: {numeric_value} -> {bool(numeric_value)}")
                        pass
                    return bool(numeric_value)
                except ValueError:
                    if key == 'wireframe_transparent':
                        #print(f"Debug Try Int Except: {key} : stored_value = {stored_value}") 
                        pass
                    try:
                        # If int conversion fails, try float
                        numeric_value = float(stored_value.strip())
                        return bool(numeric_value)
                    except ValueError:
                        if key == 'wireframe_transparent':
                            #print(f"Debug Try float Except : {key} : stored_value = {stored_value}")
                            ret = stored_value.strip().lower() in ['true', 'yes']
                            #print(f"Debug Try float return : {ret}") 
                            
                        # If numeric conversion fails, check string "trueness"
                        return stored_value.strip().lower() in ['true', 'yes']
                if key == 'wireframe_transparent':
                    #print(f"Debug Try: {key} : stored_value = {stored_value}") 
                    pass

        
            # Fallback to default
            if key == 'wireframe_transparent':
                #print(f"Fallback to default: {default_value}")
                pass
            return default_value
        
        # Handle type conversion for integer values
        elif default_type is int:
            if isinstance(stored_value, str):
                try:
                    return int(stored_value)
                except ValueError:
                    # Fallback to default if conversion fails
                    return default_value
            elif isinstance(stored_value, (int, float)):
                return int(stored_value)
        
        # Handle type conversion for float values
        elif default_type is float:
            if isinstance(stored_value, str):
                try:
                    return float(stored_value)
                except ValueError:
                    # Fallback to default if conversion fails
                    return default_value
            elif isinstance(stored_value, (int, float)):
                return float(stored_value)
        
        # Handle type conversion for string values
        elif default_type is str:
            return str(stored_value)
        
        # If no conversion is needed or possible, return the stored value
        return stored_value
    
    
    def load_setting(self, key: str, default_value: Any = None) -> Any:
        """
        Load one setting valus with validation
        
        :param key: settings key
        :param default_value: fallback value
        :return: validated setting value
        """
        
        defaults_section = self.defaults.get(self.section, {})
        # if no specific default is provided use default from the section 
        if default_value is None:
            default_value = defaults_section.get(key)
            #default_value = self.defaults.get(section, {}).get(key)
        
        # QSettings key
        qsettings_key = f"{self.section}/{key}"

        # get value with type from defaults
        value = self.get_typed_setting(self.qsettings, defaults_section, key)
        
        # check against allowed values
        allowed_key = f"{key}_allowed"
        allowed_values = defaults_section.get(allowed_key)
        
        if allowed_values and value not in allowed_values:
            # Fallback to default if value is not in allowed list
            value = default_value
        
        # save retrieved and validated settings internally
        if self.section not in self.settings:
            self.settings[self.section] = {}
        self.settings[self.section][key] = value
        
        return value

    def load_all_settings(self) -> Dict[str, Any]:
        """
        Load all settings
        
        :return: Processed settings dictionary
        """
        # Load default settings
        defaults_section = self.defaults.get(self.section, {})
        for key in defaults_section:
            # Skip keys that are "allowed" lists or complex nested structures
            if (key.endswith('_allowed') or
                type(defaults_section[key]).__name__ in ('dict', 'list')
                ):
                continue
            
            # Load each setting, using section defaults
            #print(f"DEBUG: self.load_setting('{self.section}', '{key}')")
            self.load_setting(key)
        
        return self.settings.get(self.section, {})
    
    def save_setting(self, key: str, value: Any):
        """
        Save a specific setting
        
        :param key: Specific setting key
        :param value: Value to save
        """
        section = self.section
        # Construct QSettings key
        qsettings_key = f"{section}/{key}"
        
        # Validate against allowed values if applicable
        allowed_key = f"{key}_allowed"
        allowed_values = self.defaults.get(section, {}).get(allowed_key)
        
        if allowed_values and value not in allowed_values:
            raise ValueError(f"Value {value} not in allowed values for {key}")
        
        # Save to QSettings
        self.qsettings.setValue(qsettings_key, value)
        self.qsettings.sync()
        
        # Update internal settings
        if section not in self.settings:
            self.settings[section] = {}
        self.settings[section][key] = value
    
    def get_icon_set_config(self) -> Dict[str, Any]:
        """
        Retrieve icon set configurations
        
        :return: Icon configuration dictionary
        """
        icons = self.defaults.get('Icons', {})
        return icons
    
    def get_icon_look_config(self, icon_look: str) -> Dict[str, str]:
        """
        Retrieve icon configuration
        
        :param icon_name: Name of the icon set
        :return: Icon configuration dictionary
        """
        icons = self.defaults.get('Icons', {})
        return icons.get(icon_look, {})
    
    def get_icon_order(self) -> List[str]:
        """
        Get the ordered list of icon sets
        
        :return: List of icon set names
        """
        return self.defaults.get('Icons', {}).get('icon_order', [])

    def is_fluxbox_running(self):
        """
        Detect if Fluxbox is running by checking pidof or pgrep
        
        Returns:
            bool: True if Fluxbox is running, False otherwise
        """
        import os
        try:
            # Check for pidof first
            if os.path.isfile('/usr/bin/pidof') and os.access('/usr/bin/pidof', os.X_OK):
                result = os.system('/usr/bin/pidof fluxbox > /dev/null 2>&1')
                return result == 0
            
            # Fallback to pgrep
            if os.path.isfile('/usr/bin/pgrep') and os.access('/usr/bin/pgrep', os.X_OK):
                result = os.system('/usr/bin/pgrep fluxbox > /dev/null 2>&1')
                return result == 0
            
            # No suitable command found
            return False
        
        except Exception:
            return False
    

from PyQt6.QtCore import QSettings
from pprint import pprint

def qsettings_to_nested_dict(qsettings, group=""):
    result = {}
    original_group = qsettings.group()
    
    if group:
        qsettings.beginGroup(group)
    
    for key in qsettings.childKeys():
        value = qsettings.value(key)
        
        # Type conversion logic
        if value == 'true':
            value = True
        elif value == 'false':
            value = False
        else:
            # Try converting to int or float if possible
            try:
                value = int(value)
            except (ValueError, TypeError):
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    pass  # Keep as original string if conversion fails
        
        result[key] = value
    
    for child_group in qsettings.childGroups():
        result[child_group] = qsettings_to_nested_dict(qsettings, child_group)
    
    qsettings.endGroup()
    qsettings.beginGroup(original_group)
    
    return result

def print_settings(settings):
    """Convenience function to print QSettings as a nested dictionary"""
    from pprint import pprint
    settings_dict = qsettings_to_nested_dict(settings)
    pprint(settings_dict)

import inspect
from PyQt6.QtCore import QSettings
import json

def pprint_qsettings_NotUsed(settings, var_name=None, format='dict', indent=2):
    """
    Robust QSettings pretty printer with flexible naming
    
    Args:
        settings (QSettings): The QSettings object to print
        var_name (str, optional): Explicitly provide variable name
        format (str): Output format ('dict', 'json', 'assignment')
        indent (int): Number of spaces for indentation
    """
    # Naming priority:
    # 1. Explicitly provided name
    # 2. Automatically detected name
    # 3. Fallback to generic 'settings'
    if var_name is None:
        try:
            # Attempt to detect variable name
            frame = inspect.currentframe().f_back
            detected_names = [
                name for name, val in frame.f_locals.items() 
                if val is settings
            ]
            var_name = detected_names[0] if detected_names else 'settings'
        except Exception:
            var_name = 'settings'

    # Rest of the printing logic remains the same
    settings_dict = qsettings_to_nested_dict(settings)
    
    if format == 'dict':
        # Standard dictionary representation
        print(f"{var_name} = " + json.dumps(settings_dict, 
                                            indent=indent, 
                                            ensure_ascii=False))
    elif format == 'json':
        # Pure JSON output
        print(json.dumps(settings_dict, 
                         indent=indent, 
                         ensure_ascii=False))
    elif format == 'assignment':
        # Python-like assignment representation
        print(f"{var_name} = {{")
        for key, value in settings_dict.items():
            print(f"    {repr(key)}: {repr(value)},")
        print("}")
    else:
        raise ValueError("Invalid format. Choose 'dict', 'json', or 'assignment'")

# Use pprint for more Python-like output
from pprint import PrettyPrinter
import inspect
from PyQt6.QtCore import QSettings

def pprint_qsettings(settings, var_name=None, format='pprint', indent=2):
    """
    QSettings pretty printer with multiple output formats
    """
    # Naming detection logic
    if var_name is None:
        try:
            frame = inspect.currentframe().f_back
            detected_names = [
                name for name, val in frame.f_locals.items() 
                if val is settings
            ]
            var_name = detected_names[0] if detected_names else 'settings'
        except Exception:
            var_name = 'settings'

    # Convert QSettings to dictionary
    settings_dict = qsettings_to_nested_dict(settings)
    
    if format == 'pprint':
        # Use pprint for more Python-like output
        print(f"{var_name} = ", end='')
        pp = PrettyPrinter(indent=indent)
        pp.pprint(settings_dict)
    elif format == 'json':
        # JSON output (using previous custom JSON dumper)
        print(custom_json_dumps(settings_dict, indent=indent))
    elif format == 'assignment':
        # Python-like assignment representation
        print(f"{var_name} = {{")
        for key, value in settings_dict.items():
            print(f"    {repr(key)}: {repr(value)},")
        print("}")
    else:
        raise ValueError("Invalid format. Choose 'pprint', 'json', or 'assignment'")

# Example usage
class UpdaterApp:
    def __init__(self):
        # Initialize settings manager
        self.settings_manager = UpdaterSettingsManager()
        
        # Load all settings
        self.settings = self.settings_manager.load_all_settings()
        
        # Example of using specific settings
        self.upgrade_type = self.settings_manager.load_setting('upgrade_type')
        self.icon_look = self.settings_manager.load_setting('icon_look')
        
        # Get icon configuration
        current_icon_config = self.settings_manager.get_icon_look_config(self.icon_look)


if __name__ == '__main__':
    

    pp = PrettyPrinter(indent=2)

    settings_manager = UpdaterSettingsManager()

    icon_look = settings_manager.load_setting('icon_look')
    print(f"icon_look = {icon_look}")

    print("#------------------------------------------------------------------")
    print("#------------------------------------------------------------------")
    # Load all settings
    all_settings = settings_manager.load_all_settings()
    print("all_settings :")
    pprint(all_settings)
    print("#------------------------------------------------------------------")
    print("#------------------------------------------------------------------")
    exit(0)

    upgrade_type = settings_manager.load_setting('upgrade_type')
    print(f"upgrade_type = {upgrade_type}")
    
    upgrade_assume_yes = settings_manager.load_setting('upgrade_assume_yes')
    print(f"upgrade_assume_yes = {upgrade_assume_yes}")

    start_at_login = settings_manager.load_setting('start_at_login')
    print(f"start_at_login = {start_at_login}")


    wireframe_transparent = settings_manager.load_setting('wireframe_transparent')
    print(f"wireframe_transparent = {wireframe_transparent}")

    icon_config = settings_manager.get_icon_look_config(icon_look)
    pprint(icon_config)

    wireframe_transparent = settings_manager.load_setting('wireframe_transparent')
    print(f"wireframe_transparent = {wireframe_transparent}")

    settings_manager.qsettings.sync()

    print("#------------------------------------------------------------------")
    qsettings = settings_manager.qsettings

    # Print nested settings
    #settings_dict = qsettings_to_nested_dict(qsettings)
    #pprint(settings_dict)
    #print_settings(qsettings)
    
    wireframe_transparent = qsettings.value('Settings/wireframe_transparent', type=bool)
    print(f"wireframe_transparent = {wireframe_transparent}")
    pprint_qsettings(qsettings, var_name='my_settings', format='pprint')

    #qsettings = QSettings("MX-Linux", "mx-updater")
    #pprint_qsettings(qsettings, var_name='my_qsettings', format='pprint')

    icon_look = settings_manager.load_setting('icon_look')
    print(f"Loaded icon_look = {icon_look}")
    settings_manager.save_setting('icon_look', 'pulse')
    icon_look = settings_manager.load_setting('icon_look')
    print(f"Loaded saved icon_look = {icon_look}")

    icon_look_config = settings_manager.get_icon_look_config(icon_look)
    print(f"icon_look_config '{icon_look}' : ")
    pp.pprint(icon_look_config)
    
    icon_set_config = settings_manager.get_icon_set_config()
    print(f"get_icon_set_config: ")
    pp.pprint(icon_set_config)
    
    icon_order = settings_manager.get_icon_order()
    print(f"get_icon_order: ")
    pp.pprint(icon_order)
    
    """
    def pprint_qsettings(settings, format='dict', indent=2):
    Pretty print QSettings with dynamic variable name detection
    
    Args:
        settings (QSettings): The QSettings object to print
        format (str): Output format ('dict', 'json', 'assignment')
        indent (int): Number of spaces for indentation
    """

    
"""
[Settings]
auto_close=True
auto_close_timeout=12
hide_until_upgrades_available=false
icon_look=pulse
left_click=view_and_upgrade
start_at_login=1
upgrade_assume_yes=0
upgrade_type=basic-upgrade
use_dbus_notifications=false
use_nala=true
wireframe_transparent=0
"""
