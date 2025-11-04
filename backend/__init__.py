import os
from flask import Flask
import redis
from dotenv import load_dotenv
import pandas as pd
from flask_cors import CORS
from .config import DevelopmentConfig
from .redis_client import get_redis_client  # new

def create_app(config_class=None):
    app = Flask(__name__)
    
    # Config
    if config_class is None:
        config_class = DevelopmentConfig
    app.config.from_object(config_class)
    
    # CORS
    CORS(app, resources={
        r"/*": {
            "origins": app.config['CORS_ALLOWED_ORIGINS'],
            "methods": ["GET", "POST", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            }
            }, 
            supports_credentials=True
    )
    
    # Redis (use centralized factory so worker & app share same config/behaviour)
    load_dotenv()
    redis_client = get_redis_client()
    app.redis_client = redis_client

    from .main import main_bp
    app.register_blueprint(main_bp)
    
    return app
