import os
from flask import Flask
import redis
from dotenv import load_dotenv
import pandas as pd
from flask_cors import CORS
from .config import DevelopmentConfig


def create_app(config_class=None):
    app = Flask(__name__)
    
    # Config
    if config_class is None:
        config_class = DevelopmentConfig
    app.config.from_object(config_class)
    
    # CORS
    CORS(app, origins=app.config['CORS_ALLOWED_ORIGINS'])
    
    # Redis
    load_dotenv()
    
    # Initialize Redis client
    redis_client = redis.Redis(
        host=os.getenv('REDIS_HOST'),
        port=6379,
        db=0
    )
    try:
        if redis_client.ping():
            print("Redis connection successful!")
        else:
            print("Redis server did not respond to PING.")
    except redis.exceptions.ConnectionError as e:
        print(f"Could not connect to Redis: {e}")
        raise
    
    from .main import main_bp
    app.register_blueprint(main_bp)
    
    return app
