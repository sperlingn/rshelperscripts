from locale import windows_locale
from ctypes import windll

__LOCALE__ = windows_locale[windll.kernel32.GetUserDefaultUILanguage()]


BEAMNAME_QUADRANT_TO_NAME = ["LAO", "LPO", "RPO", "RAO",
                             "AP", "L Lat", "PA", "R Lat"]

BEAMNAME_BREAST_SC_PA = ["SCLV", "PAB"]

if __LOCALE__ == 'en_US':
    pass
elif __LOCALE__ == '':
    pass
