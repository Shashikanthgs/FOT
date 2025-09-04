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


def process_option_chain(chain_data):
    # Process the option chain data as needed
    
    underlying_price = chain_data.get('last_price', 0)
    oc = chain_data.get('oc', {})

    strikes = sorted([float(k) for k in oc.keys()])
    processed_chain = []
    total_call_oi = total_call_vol = total_put_oi = total_put_vol = 0
    total_call_oi_chg = total_put_oi_chg = 0

    for strike in strikes:
        str_strike = f"{strike:.6f}"
        ce = oc.get(str_strike, {}).get('ce', {})
        pe = oc.get(str_strike, {}).get('pe', {})

        def get_val(d, key): return d.get(key, 0)

        ce_ltp = get_val(ce, 'last_price')
        ce_prev_close = get_val(ce, 'previous_close_price')
        ce_chg_pct = ((ce_ltp - ce_prev_close) / ce_prev_close * 100) if ce_prev_close else 0
        ce_oi = get_val(ce, 'oi')
        ce_prev_oi = get_val(ce, 'previous_oi')
        ce_oi_chg = ce_oi - ce_prev_oi
        ce_vol = get_val(ce, 'volume')
        ce_iv = get_val(ce, 'implied_volatility')
        ce_intrinsic = max(underlying_price - strike, 0)
        ce_tv = ce_ltp - ce_intrinsic

        pe_ltp = get_val(pe, 'last_price')
        pe_prev_close = get_val(pe, 'previous_close_price')
        pe_chg_pct = ((pe_ltp - pe_prev_close) / pe_prev_close * 100) if pe_prev_close else 0
        pe_oi = get_val(pe, 'oi')
        pe_prev_oi = get_val(pe, 'previous_oi')
        pe_oi_chg = pe_oi - pe_prev_oi
        pe_vol = get_val(pe, 'volume')
        pe_iv = get_val(pe, 'implied_volatility')
        pe_intrinsic = max(strike - underlying_price, 0)
        pe_tv = pe_ltp - pe_intrinsic

        pcr_oi = (pe_oi / ce_oi) if ce_oi > 0 else 0
        pcr_vol = (pe_vol / ce_vol) if ce_vol > 0 else 0

        processed_chain.append({
            'strike': strike,
            'pcr_oi': round(pcr_oi, 2),
            'pcr_vol': round(pcr_vol, 2),
            'call_iv': round(ce_iv, 2),
            'call_tv': round(ce_tv, 2),
            'call_oi_chg': ce_oi_chg,
            'call_oi': ce_oi,
            'call_vol': ce_vol,
            'call_chg_pct': round(ce_chg_pct, 2),
            'call_ltp': round(ce_ltp, 2),
            'put_ltp': round(pe_ltp, 2),
            'put_chg_pct': round(pe_chg_pct, 2),
            'put_vol': pe_vol,
            'put_oi': pe_oi,
            'put_oi_chg': pe_oi_chg,
            'put_tv': round(pe_tv, 2),
            'put_iv': round(pe_iv, 2)
        })

        total_call_oi += ce_oi
        total_call_vol += ce_vol
        total_put_oi += pe_oi
        total_put_vol += pe_vol
        total_call_oi_chg += ce_oi_chg
        total_put_oi_chg += pe_oi_chg

    total_pcr_oi = (total_put_oi / total_call_oi) if total_call_oi > 0 else 0
    total_pcr_vol = (total_put_vol / total_call_vol) if total_call_vol > 0 else 0
    atm_strike = min(strikes, key=lambda x: abs(x - underlying_price))

    return jsonify({
        'underlying_price': underlying_price,
        'atm_strike': atm_strike,
        'chain': processed_chain,
        'totals': {
            'total_pcr_oi': round(total_pcr_oi, 2),
            'total_pcr_vol': round(total_pcr_vol, 2),
            'total_call_oi': total_call_oi,
            'total_call_vol': total_call_vol,
            'total_put_oi': total_put_oi,
            'total_put_vol': total_put_vol,
            'total_call_oi_chg': total_call_oi_chg,
            'total_put_oi_chg': total_put_oi_chg
        }
    })

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
            
        return jsonify(expiry_list)
        
    except Exception as e:
        print(f"Error in get_expiries: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/get_option_chain', methods=['POST'])
def get_option_chain():
    data = request.get_json()
    underlying_scrip = data.get('underlying_scrip')
    underlying_seg = data.get('underlying_seg')
    expiry = data.get('expiry')

    if not underlying_scrip or not underlying_seg or not expiry:
        return jsonify({"error": "Missing underlying_scrip or underlying_seg or expiry"}), 400

    option_chain = dhan_client.fetch_option_chain(
        underlying_scrip=underlying_scrip,
        underlying_seg=underlying_seg,
        expiry=expiry
    )

    if option_chain is None:
        return jsonify({'error': 'Failed to fetch option chain data'}), 500

    # Process and return the option chain data
    processed_chain = process_option_chain(chain_data = option_chain.get('data', {}))
    
    return processed_chain


@app.route('/get_all_scrips', methods=['GET'])
def get_all_scrips():

    if dhan_client.instruments_df.empty:
        return jsonify({"error": "Instrument data not loaded"}), 500

    filtered_df = dhan_client.instruments_df.replace({np.nan: None})
    return jsonify(filtered_df.to_dict('records'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)