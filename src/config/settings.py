import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    BOT_TOKEN: str = os.getenv('BOT_TOKEN', '')
    DATABASE_URL: str = os.getenv('DATABASE_URL', '')
    REDIS_URL: str = os.getenv('REDIS_URL', '')

settings = Settings()