import configparser
import os
from configparser import RawConfigParser

config = RawConfigParser()
config_path = os.path.join(os.path.dirname(__file__), 'settings.ini')
config.read(config_path)

# ── Execution environment ────────────────────────────────────────────────────
# Every reader below falls back to the LOCAL default when the section/option is
# missing, so an settings.ini that predates these sections keeps behaving
# exactly as it did before.

def get_execution_type():
    """
    'local' or 'azure'.

    The IQEA_EXECUTION_TYPE environment variable wins over settings.ini so the
    same image can be repointed from the Azure portal without a rebuild. Any
    unrecognised value falls back to 'local' — the safe direction, since local
    is the behaviour that already works.
    """
    value = (os.environ.get('IQEA_EXECUTION_TYPE')
             or config.get('EXECUTION', 'execution_type', fallback='local'))
    value = (value or '').strip().lower()
    return value if value in ('local', 'azure') else 'local'


def is_azure():
    return get_execution_type() == 'azure'


def is_local():
    return get_execution_type() == 'local'


# ── Browser (azure only — local ignores all of these) ────────────────────────

def get_selenium_remote_url():
    return os.environ.get('SELENIUM_REMOTE_URL') or config.get(
        'BROWSER', 'selenium_remote_url', fallback='http://chrome:4444/wd/hub')


def get_novnc_path():
    return os.environ.get('IQEA_NOVNC_PATH') or config.get(
        'BROWSER', 'novnc_path', fallback='/vnc/')


def get_window_size():
    """Returns (width, height) as ints."""
    raw = config.get('BROWSER', 'window_size', fallback='1920,1080')
    try:
        width, height = [int(x.strip()) for x in raw.split(',')[:2]]
        return width, height
    except (ValueError, IndexError):
        return 1920, 1080


def get_browser_pool_size():
    try:
        return max(1, int(config.get('BROWSER', 'browser_pool_size', fallback='1')))
    except ValueError:
        return 1


def get_session_timeout_mins():
    try:
        return max(1, int(config.get('BROWSER', 'session_timeout_mins', fallback='30')))
    except ValueError:
        return 30


def get_recorder_poll_secs():
    """
    Seconds between recorder monitor-thread polls.

    Defaults differ by environment: 2s locally (unchanged from the hardcoded
    value it replaces) and 5s in azure, where every poll is an HTTP round trip
    to a shared Grid and there may be many people recording at once.
    """
    raw = config.get('BROWSER', 'recorder_poll_secs', fallback='').strip()
    if raw:
        try:
            return max(0.5, float(raw))
        except ValueError:
            pass
    return 5.0 if is_azure() else 2.0


def debug_logs_enabled():
    """
    Per-poll debug printing from the recorder threads.

    On locally (unchanged behaviour), off in azure unless explicitly enabled —
    the recorder prints a block per thread per poll, which multiplied by the
    number of concurrent users would dominate the Azure log stream and bill.
    """
    raw = config.get('EXECUTION', 'debug_logs', fallback='').strip().lower()
    if raw in ('true', '1', 'yes'):
        return True
    if raw in ('false', '0', 'no'):
        return False
    return not is_azure()


# ── OCR ──────────────────────────────────────────────────────────────────────

def get_tesseract_cmd():
    """Absolute path to the tesseract binary, or '' to resolve from PATH."""
    return (os.environ.get('TESSERACT_CMD')
            or config.get('OCR', 'tesseract_cmd', fallback='')).strip()


def prefer_vision_ocr():
    return config.get('OCR', 'prefer_vision_ocr',
                      fallback='false').strip().lower() in ('true', '1', 'yes')


def get_source():
    return config.get('GENERAL', 'source')  # source can be 'file' or 'database'
def get_model():
    return config.get('GENERAL', 'model')
def get_db_url():
    DB_USER = config.get('DATABASE', 'DB_USER')
    DB_PASS = config.get('DATABASE', 'DB_PASS_1') # ensure to choose the valid postgres db password
    DB_HOST = config.get('DATABASE', 'DB_HOST')
    DB_PORT = config.get('DATABASE', 'DB_PORT')
    DB_NAME = config.get('DATABASE', 'DB_NAME')
    DB_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return DB_URL

def get_update_user():
    return config.get('DATABASE', 'DB_USER') # change the username for database updates

def get_api_key():
    return config.get('API', 'Api_key')
def get_xpath_key():
    raw = config.get("XPATH", "allowed_tags")
    allowed_tags = [x.strip() for x in raw.split(",") if x.strip()]
    print("xpath_allowed_tags",allowed_tags)
    return allowed_tags

