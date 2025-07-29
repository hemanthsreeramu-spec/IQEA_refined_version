import configparser
import os

def get_source():
    config = configparser.ConfigParser()
    config_path = os.path.join(os.path.dirname(__file__), 'settings.ini')
    config.read(config_path)
    return config.get('GENERAL', 'source')