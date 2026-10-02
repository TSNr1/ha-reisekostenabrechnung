"""Konstanten der Reisekosten-Integration."""
DOMAIN = "reisekosten"

CONF_PERSON = "person"
CONF_ZONE = "zone"
CONF_NOTIFY = "notify_service"
CONF_COMPANY = "company"
CONF_NAME = "person_name"
CONF_STREET = "street"
CONF_CITY = "city"
CONF_CALENDARS = "calendars"
OPT_CALENDAR_REQUIRED = "calendar_required"   # nur bei passendem Kalendertermin nachfragen

# Optionen
OPT_RULES = "rules"
OPT_ACCOUNTS = "accounts"
OPT_UPLOAD_ONEDRIVE = "upload_onedrive"
ONEDRIVE_FOLDER = "Reisekosten"        # Unterordner im App-Ordner von OneDrive
OPT_OUTPUT_DIR = "output_dir"       # leer = <config>/www/reisekosten
ACC_PER_DIEM = "account_per_diem"
ACC_KM = "account_km"
ACC_CONTRA = "account_contra"
ACC_PAYMENT = "payment"

DEFAULT_ZONE = "zone.home"
OUTPUT_SUBDIR = ("www", "reisekosten")        # erreichbar unter /local/reisekosten/
OUTPUT_URL = "/local/reisekosten"
ARRIVAL_DEBOUNCE_SECONDS = 180                # so lange muss die Person "zuhause" sein
STORAGE_KEY = f"{DOMAIN}.data"
STORAGE_VERSION = 1
ACTION_PREFIX = "RK_"
