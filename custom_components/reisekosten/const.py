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
CONF_EMPLOYMENT = "employment"                # self_employed | employee | both
CONF_CHART = "chart"                          # skr03 | skr04 | custom
CONF_WORK_ZONE = "work_zone"                  # Arbeitsstätte (Zone), nur für Angestellte
CONF_ODOMETER = "odometer"                    # Kilometerzähler-Sensor für den Kilometer-Vorschlag
EMPLOYMENT_OPTIONS = ("self_employed", "employee", "both")
CHART_OPTIONS = ("skr03", "skr04", "custom")
ACTIVITY_SELF, ACTIVITY_EMPLOYEE = "self", "employee"
# Standardkonten je Kontenrahmen und Tätigkeit: Verpflegungsmehraufwand / Fahrtkosten
ACCOUNT_TABLE = {
    "skr03": {ACTIVITY_SELF: ("4674", "4673"), ACTIVITY_EMPLOYEE: ("4664", "4663")},
    "skr04": {ACTIVITY_SELF: ("6674", "6673"), ACTIVITY_EMPLOYEE: ("6664", "6663")},
}

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
OUTPUT_SUBDIR = ("reisekosten",)               # <config>/reisekosten - NICHT unter www (dort wäre es öffentlich)
PDF_VIEW_URL = "/api/reisekosten/pdf/{number}"  # nur mit Anmeldung bzw. signiertem Link abrufbar
ARRIVAL_DEBOUNCE_SECONDS = 180                # so lange muss die Person "zuhause" sein
STORAGE_KEY = f"{DOMAIN}.data"
STORAGE_VERSION = 1
ACTION_PREFIX = "RK_"
