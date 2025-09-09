#!/usr/bin/python3

import os
import gettext

class Translator:
    def __init__(self, textdomain=None, textdomaindir=None):
        self.textdomain = textdomain or os.getenv('TEXTDOMAIN')
        self.textdomaindir = textdomaindir or os.getenv('TEXTDOMAINDIR') or '/usr/share/locale'
        self._ = self._setup_translation()
        self._gtk40 = self._setup_gtk_translation("gtk40")
        self._gtk30 = self._setup_gtk_translation("gtk30")
        self._gtk40_ctxt = self._setup_gtk_translation("gtk40", "accessibility")
        self._gtk30_ctxt = self._setup_gtk_translation("gtk30", "Stock label")
        self._gtk20_ctxt = self._setup_gtk_translation("gtk20", "Stock label")

    def _setup_translation(self):
        """Set up the translation based on the TEXTDOMAIN and TEXTDOMAINDIR."""
        if self.textdomain:
            try:
                translation = gettext.translation(self.textdomain, self.textdomaindir, fallback=True)
                translation.install()
                return translation.gettext  # Use the translation function
            except FileNotFoundError:
                #print(f"Warning: Translation files for domain '{self.textdomain}' not found in '{self.textdomaindir}'. Falling back to untranslated messages.")
                return lambda msg: msg  # Identity function if translation files are not found
        else:
            return lambda msg: msg  # Identity function if TEXTDOMAIN is not set

    def _setup_gtk_translationXXX(self, textdomain):
        """Set up the GTK translation for a specific text domain."""
        #textdomaindir = self.textdomaindir
        textdomaindir = '/usr/share/locale'
        try:
            translation = gettext.translation(textdomain, textdomaindir, fallback=True)
            translation.install()
            return translation.gettext  # Use the translation function
        except FileNotFoundError:
            #print(f"Warning: Translation files for domain '{textdomain}' not found in '{textdomaindir}'.")
            return lambda msg: msg  # Identity function if translation files are not found


    def _setup_gtk_translation(self, textdomain, msgctxt=None):
        """Set up the GTK translation for a specific text domain."""
        textdomaindir = '/usr/share/locale'
        try:
            translation = gettext.translation(textdomain, textdomaindir, fallback=True)
            translation.install()
            
            if msgctxt:
                # If a message context is provided, return pgettext
                return lambda msg: translation.pgettext(msgctxt, msg)
            else:
                # Otherwise, return gettext
                return translation.gettext  # Use the standard translation function
        except FileNotFoundError:
            #print(f"Warning: Translation files for domain '{textdomain}' not found in '{textdomaindir}'.")
            return lambda msg: msg  # Identity function if translation files are not found
    
    def translate(self, message):

        #print(f"Try translated message '{message}'") # debug
        gtk_msgs = ["_OK", "_Cancel", "_Close", "_Copy", "_Help",
                    "Clear", "Filter by" ]
        pyqt_msgs = [m.replace('_', '&') for m in gtk_msgs]
    
        # First try to translate using the default translation domain
        translated_msg = self._(message)
        if message in gtk_msgs or message in pyqt_msgs:
            #print(f"Msg translated with default textdomain {message} -> {translated_msg}")
            pass
        
        # If the translation is not the same as the original message, return translated message
        if translated_msg != message:
            if message in gtk_msgs or message in pyqt_msgs:
                #print(f"Msg translated with default textdomain {message} -> {translated_msg}")
                pass
            return translated_msg
    
        # If the message is neither in GTK format nor in PyQt format, return the untranslated message
        if message not in gtk_msgs and message not in pyqt_msgs:
            return translated_msg
        
        # Check if the message is in the PyQt format and convert it to GTK format
        if message in pyqt_msgs:
            msg = message.replace('&', '_')  # Convert to GTK format
        else:
            msg = message  # Keep the original message if not in PyQt format

      
        """Translate the message using the installed translation function."""
        # print(f"(self._gtk30({msg}): {self._gtk30(msg)}") # debug
        # print(f"(self._gtk30_ctxt({msg}): {self._gtk30_ctxt(msg)}") # debug
        #print(f"(self._gtk40({msg}): {self._gtk40(msg)}") # debug
        #print(f"(self._gtk40_ctxt({msg}): {self._gtk40_ctxt(msg)}") # debug

        # First try to translate using gtk30 with msgctxt
        translated_msg = self._gtk20_ctxt(msg)
        
        # If the translation is the same as the original message, try gtk30 with ctxt
        if translated_msg == msg:
            translated_msg = self._gtk30_ctxt(msg)

        
        # If the translation is the same as the original message, try gtk30 without ctxt
        if translated_msg == msg:
            translated_msg = self._gtk30(msg)
        
        # If the translation is still same as the original message, try gtk40
        if translated_msg == msg:
            translated_msg = self._gtk40_ctxt(msg)
        
        # If the translation is still same as the original message, try gtk40
        if translated_msg == msg:
            translated_msg = self._gtk40(msg)
        
        # If the original message was in PyQt format, convert the translation back
        """
        if message in pyqt_msgs:
            translated_msg = translated_msg.replace('_', '&')  # Convert back to PyQt format
        """
        if message in pyqt_msgs:
            #print(f"Translated message '{msg}' used: {translated_msg.replace('_', '&')}") # debug
            #return translated_msg.replace('_', '&')  # Convert back to PyQt format
            translated_msg = translated_msg.replace('_', '&')  # Convert back to PyQt format

        #print(f"Translated message '{msg}' used: {translated_msg}") # debug
    
        return translated_msg  # Return the translated message
        
    
