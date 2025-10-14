from flask import Flask, request, jsonify
import numpy as np
import os
from flask_cors import CORS
from dotenv import load_dotenv
import pandas as pd
from dhan_client import DhanClient
import redis
import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor
import threading
from datetime import datetime, timezone
import math


# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Redis Connection (update host/port if not local)
redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

@app.route('/get_option_chain', methods=['GET', 'POST'])
def get_option_chain():
    data = request.get_json()
    underlying_scrip = data.get('underlying_scrip')
    underlying_seg = data.get('underlying_seg')

    # Generate cache key
    cache_key = f"option_chain:{underlying_scrip}_{underlying_seg}"
    
    # Check Redis cache
    cached_data = redis_client.get(cache_key)
    if cached_data:
        print(f"Cache hit for {cache_key}")

    else:
        print(f"Cache miss for {cache_key}. Data not found in cache.")

    processed_response = process_option_chain(json.loads(cached_data))
    
    return processed_response


@app.route('/get_expiries', methods=['GET','POST'])
def get_expiries():
    try:
        data = request.get_json()
        underlying_scrip = data.get('underlying_scrip')
        underlying_seg = data.get('underlying_seg')
        
        if not underlying_scrip or not underlying_seg:
            return jsonify({"error": "Missing underlying_scrip or underlying_seg"}), 400

        cache_key = f"expiry_date:{underlying_scrip}_{underlying_seg}"
    
        # Check Redis cache
        cached_data = redis_client.get(cache_key)
        return jsonify({'data': cached_data})
        
    except Exception as e:
        print(f"Error in get_expiries: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route('/get_all_scrips', methods=['GET'])
def get_all_scrips():

    csv_path = os.path.join(os.path.dirname(__file__), 'Dependencies', 'my_instruments.csv')
    try:
        instruments_df = pd.read_csv(csv_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"The file '{csv_path}' was not found. Please check the path and ensure the file exists.")

    filtered_df = instruments_df.replace({np.nan: None})
    scrips_data = filtered_df.to_dict('records')
        
    return jsonify(scrips_data)

@app.route('/get_nine_thirty_data', methods=['GET','POST'])
def get_nine_thirty_data():
    try:
        data = request.get_json()
        underlying_scrip = data.get('underlying_scrip')
        underlying_seg = data.get('underlying_seg')
        
        if not underlying_scrip or not underlying_seg:
            return jsonify({"error": "Missing underlying_scrip or underlying_seg"}), 400

        cache_key = f"nine_thirty_data:{underlying_scrip}_{underlying_seg}"
    
        # Check Redis cache
        cached_data = redis_client.get(cache_key)
        return jsonify({'data': cached_data})
    
    except Exception as e:
        print(f"Error in get_expiries: {str(e)}")
        return jsonify({"error": str(e)}), 500


def calculate_nine_thirty_strike_levels(nine_thirty_data, scrip_id, segment):
    if not nine_thirty_data or not nine_thirty_data['strikes']:
        return {}
    
    strikes_array = sorted(nine_thirty_data['strikes'].keys())
    chain = [{'strike': strike, 'put_ltp': nine_thirty_data['strikes'][strike]['p'], 
              'call_ltp': nine_thirty_data['strikes'][strike]['c']} for strike in strikes_array]
    nine_thirty_strike_levels = {}

    strikes = [float(s) for s in strikes_array]
    step = strikes[1] - strikes[0] if len(strikes) > 1 else 50
    lowest_strike = strikes_array[0]
    lowest_data = nine_thirty_data['strikes'][lowest_strike]
    hypothetical_low = {'strike': float(lowest_strike) - step, 'put_ltp': lowest_data['p'], 'call_ltp': lowest_data['c']}
    low_support = calculate_reversal(hypothetical_low, nine_thirty_data, scrip_id, segment)
    
    for i, row in enumerate(chain):
        support = low_support if i == 0 else calculate_reversal(row, nine_thirty_data, scrip_id, segment)
        if i < len(strikes) - 1:
            resistance = calculate_reversal(chain[i + 1], nine_thirty_data, scrip_id, segment)
        else:
            hypothetical_high = {**row, 'strike': float(row['strike']) + step}
            resistance = calculate_reversal(hypothetical_high, nine_thirty_data, scrip_id, segment)
        nine_thirty_strike_levels[row['strike']] = {
            'support': f"{support:.4f}",
            'resistance': f"{resistance:.4f}"
        }
    
    return nine_thirty_strike_levels

def calculate_reversal(row, nine_thirty_data, scrip_id, segment):
    RISK_FREE_RATE = -0.067
    P = row['put_ltp']
    C = row['call_ltp']
    K = row['strike']
    S = nine_thirty_data['s']
    
    strike_data = nine_thirty_data['strikes'].get(K)
    if strike_data:
        P = strike_data['p']
        C = strike_data['c']
    else:
        return 0
    t = calculate_t(scrip_id, segment)
    exp_term = math.exp(RISK_FREE_RATE * t)
    one_minus_exp = 1 - exp_term
    k = float(K)
    reversal = S - k + P - C + k * one_minus_exp
    return k + reversal

def calculate_t(scrip_id, segment):
    now = datetime.now(timezone.utc)
    cache_key = f"expiry_date:{scrip_id}_{segment}"
    selected_expiry = redis_client.get(cache_key)

    expiry_date = datetime.strptime(f"{selected_expiry} 15:30:00+05:30", "%Y-%m-%d %H:%M:%S%z")
    diff_ms = (expiry_date - now).total_seconds() * 1000
    if diff_ms <= 0:
        return 0
    diff_days_fractional = diff_ms / (1000 * 60 * 60 * 24)
    days = math.ceil(diff_days_fractional)
    return days / 365

def calc_nine_thirty_data(chain_data: dict, scrip_id, segment):
    
    nine_thirty_chain_data = {
        's': chain_data.get('last_price', 0),
        'strikes': {},
        'date': datetime.now().strftime('%Y-%m-%d')
    }
    for key, value in chain_data['oc'].items():
        nine_thirty_chain_data['strikes'][key] = {'p': value['pe']['last_price'], 'c': value['ce']['last_price']}
    
    nine_thirty_strike_levels = calculate_nine_thirty_strike_levels(nine_thirty_chain_data, scrip_id, segment)
    nine_thirty_data = {
        's': chain_data.get('last_price', 0),
        'strikes': {},
        'date': datetime.now().strftime('%Y-%m-%d'),
        'strikeLevels': dict(nine_thirty_strike_levels)
    }

    return nine_thirty_data

def is_start_of_trading_day():
    load_dotenv()
    nse_holidays = os.getenv('NSE_HOLIDAYS')
    state = False
    now = datetime.now()
    day = now.weekday()
    date_str = now.strftime('%Y-%m-%d')
    if (day < 5 and date_str not in nse_holidays):
        now = datetime.now()
        nine_thirty = datetime(now.year, now.month, now.day, 9, 30, 0)
        nine_thirty_one = datetime(now.year, now.month, now.day, 9, 31, 0)
        if nine_thirty <= now <= nine_thirty_one:
            state = True
    return state

# Function to fetch and cache option chain data
def fetch_and_cache_option_chain(dhan_client, redis_client, scrip_id, segment):
    while True:
        try:

            expiry_data = dhan_client.fetch_expiry_list(underlying_scrip=scrip_id,
                                            underlying_seg=segment)
            expiry_list = expiry_data.get('data', {})
            expiry_date = expiry_list[0]
            option_chain = dhan_client.fetch_option_chain(underlying_scrip=scrip_id,
                                                    underlying_seg=segment,
                                                    expiry=expiry_date)
            if option_chain.get('status') != 'success':
                logger.error(f"Failed to fetch option chain for {scrip_id} in {segment}")
                return
            cache_key_oc = f"option_chain:{scrip_id}_{segment}"
            cache_key_exp = f"expiry_date:{scrip_id}_{segment}"
            cache_key_nine_thirty_data = f"nine_thirty_data:{scrip_id}_{segment}"
            chain_data = option_chain.get('data', {})
            redis_client.set(cache_key_exp, expiry_date, ex=300)
            json_data = json.dumps(chain_data)  # Serialize the dict
            # Cache the processed response (TTL=30s for live data)
            redis_client.set(cache_key_oc, json_data, ex=300)
            cached_data = redis_client.get(cache_key_nine_thirty_data)
            if not cached_data and is_start_of_trading_day():
                nine_thirty_data = calc_nine_thirty_data(chain_data, scrip_id, segment)
                redis_client.set(cache_key_nine_thirty_data, json.dumps(nine_thirty_data), ex=86340)

            print("fetched option chain for:", scrip_id)
            time.sleep(3)  # To avoid hitting rate limits

        except Exception as e:
            logger.error(f"Error in fetch_and_cache_option_chain: {e}")
            return None
    

# Main function with concurrent tasks
def main_function():
     # Load environment variables from .env file
    load_dotenv()

    # Get credentials from .env
    CLIENT_ID = os.getenv('CLIENT_ID')
    # ACCESS_TOKEN = os.getenv('ACCESS_TOKEN')
    ACCESS_TOKENS = os.getenv('ACCESS_TOKENS').split(',') if os.getenv('ACCESS_TOKENS') else []

    if not CLIENT_ID or not ACCESS_TOKENS:
        raise ValueError("CLIENT_ID or ACCESS_TOKEN not found in .env file")
    
    # Create multiple DhanClient instances if ACCESS_TOKENS are provided
    dcs = [DhanClient(CLIENT_ID, os.getenv(token)) for token in ACCESS_TOKENS]

    # # Redis Connection (update host/port if not local)
    # redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    # Test connection (optional, can remove)
    try:
        redis_client.ping()
    except redis.ConnectionError:
        print("Warning: Redis connection failed. Caching disabled.")

    csv_path = os.path.join(os.path.dirname(__file__), 'Dependencies', 'my_instruments.csv')
    try:
        instruments_df = pd.read_csv(csv_path)
    except FileNotFoundError:
            raise FileNotFoundError(f"The file '{csv_path}' was not found. Please check the path and ensure the file exists.")
    
    with ThreadPoolExecutor(max_workers=6) as executor:
        for dc, scrip_id, segment in zip(dcs, instruments_df['scrip_id'], instruments_df['segment']):
            executor.submit(fetch_and_cache_option_chain, dc, redis_client, scrip_id, segment)


if __name__ == '__main__':
    # Start main function in a separate thread
    thread = threading.Thread(target=main_function, daemon=True)
    thread.start()
    
    # Run Flask app
    app.run(debug=True, port=5000)

