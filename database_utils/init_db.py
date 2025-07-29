# init_db.py
from sqlalchemy import create_engine
from config.db_config import DB_URL
from database_utils.base import Base

# Import all models to register them with Base
#import memory_storage
import models

def init_db():
    engine = create_engine(DB_URL)
    Base.metadata.create_all(engine)
    print("✅ All tables created!")

init_db()
