import configparser
import os

config = configparser.RawConfigParser()
config_path = os.path.join(os.path.dirname(__file__), 'settings.ini')
config.read(config_path)

def get_source():
    return config.get('GENERAL', 'source')  # source can be 'file' or 'database'

def get_db_url():
    DB_USER = config.get('DATABASE', 'DB_USER')
    DB_PASS = config.get('DATABASE', 'DB_PASS_2') # ensure to choose the valid postgres db password
    DB_HOST = config.get('DATABASE', 'DB_HOST')
    DB_PORT = config.get('DATABASE', 'DB_PORT')
    DB_NAME = config.get('DATABASE', 'DB_NAME')
    DB_URL = f"postgresql+psycopg2://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    return DB_URL

def get_update_user():
    return config.get('DATABASE', 'DB_UPDATE_USER') # change the username for database updates
