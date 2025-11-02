import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY')
    
class DevelopmentConfig(Config):
    DEBUG = True
    CORS_ALLOWED_ORIGINS = os.getenv('DEV_CORS_ORIGINS', 'http://localhost:3000,http://127.0.0.1:3000').split(',')

class ProductionConfig(Config):
    DEBUG = False
    CORS_ALLOWED_ORIGINS = os.getenv('CORS_ALLOWED_ORIGINS', '').split(',')