from flask import Flask, request, jsonify, make_response
import numpy as np
import requests
import os
from flask_cors import CORS
from dotenv import load_dotenv
import traceback
from datetime import datetime
from cachetools import TTLCache
import pandas as pd
from dhan_client import DhanClient

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": "*",  # Allow all origins for development
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization", "Accept"],
        "expose_headers": ["Content-Type"],
        "supports_credentials": True
    }
})

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Load environment variables from .env file
load_dotenv()

# Get credentials from .env
CLIENT_ID = os.getenv('CLIENT_ID')
ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')

if not CLIENT_ID or not ACCESS_TOKEN:
    raise ValueError("CLIENT_ID or ACCESS_TOKEN not found in .env file")

# Load environment variables from .env file
dhan_client = DhanClient(client_id=CLIENT_ID, 
                         access_token=ACCESS_TOKEN,
                         base_url="https://api.dhan.co/v2")


@app.route('/get_expiries', methods=['POST'])
def get_expiries():
    try:
        data = request.get_json()
        underlying_scrip = data.get('underlying_scrip')
        underlying_seg = data.get('underlying_seg')
        
        if not underlying_scrip or not underlying_seg:
            return jsonify({"error": "Missing underlying_scrip or underlying_seg"}), 400

        print(f'Fetching expiries for scrip: {underlying_scrip}, segment: {underlying_seg}')
        expiry_list = dhan_client.fetch_expiry_list(
            underlying_scrip=underlying_scrip,
            underlying_seg=underlying_seg
        )
        
        if expiry_list is None:
            return jsonify({'error': 'Failed to fetch expiry list data'}), 500
            
        return expiry_list
        
    except Exception as e:
        print(f"Error in get_expiries: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_option_chain', methods=['POST'])
def get_option_chain():
    
    return


@app.route('/get_all_scrips', methods=['GET', 'OPTIONS'])
def get_all_scrips():
    
    if request.method == 'OPTIONS':
        return make_response('', 200)

    if dhan_client.instruments_df.empty:
        return jsonify({"error": "Instrument data not loaded"}), 500

    filtered_df = dhan_client.instruments_df.replace({np.nan: None})
    return jsonify(filtered_df.to_dict('records'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)