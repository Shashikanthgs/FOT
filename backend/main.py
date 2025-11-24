import email
from flask import Blueprint, request, jsonify, current_app
import numpy as np
import os
from dotenv import load_dotenv
import pandas as pd
import json
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import math
import smtplib
from email.message import EmailMessage

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

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

@main_bp.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@main_bp.route('/api/get_option_chain', methods=['GET', 'POST'])
def get_option_chain():
    data = request.get_json() or {}
    underlying_scrip = data.get('underlying_scrip')
    underlying_seg = data.get('underlying_seg')

    if not underlying_scrip or not underlying_seg:
        return jsonify({'error': 'Missing underlying_scrip or underlying_seg'}), 400

    cache_key = f"option_chain:{underlying_scrip}_{underlying_seg}"
    cached_data = current_app.redis_client.get(cache_key)
    if not cached_data:
        return jsonify({'error': 'Data not available in cache'}), 404

    # cached_data is stored as JSON string -> ensure it's a Python dict
    if isinstance(cached_data, (bytes,)):
        cached_data = cached_data.decode('utf-8')
    try:
        chain_dict = json.loads(cached_data)
    except Exception:
        return jsonify({'error': 'Cached data corrupted'}), 500

    processed_response = process_option_chain(chain_dict)
    return processed_response


@main_bp.route('/api/get_expiries', methods=['GET','POST'])
def get_expiries():
    try:
        data = request.get_json() or {}
        underlying_scrip = data.get('underlying_scrip')
        underlying_seg = data.get('underlying_seg')
        
        if not underlying_scrip or not underlying_seg:
            return jsonify({"error": "Missing underlying_scrip or underlying_seg"}), 400

        cache_key = f"expiry_date:{underlying_scrip}_{underlying_seg}"
        cached_data = current_app.redis_client.get(cache_key)
        if cached_data is None:
            return jsonify({'data': None})
        if isinstance(cached_data, (bytes,)):
            cached_data = cached_data.decode('utf-8')
        return jsonify({'data': cached_data})
        
    except Exception as e:
        print(f"Error in get_expiries: {str(e)}")
        return jsonify({"error": str(e)}), 500


@main_bp.route('/api/get_all_scrips', methods=['GET'])
def get_all_scrips():

    csv_path = os.path.join(os.path.dirname(__file__), 'Dependencies', 'my_instruments.csv')
    try:
        instruments_df = pd.read_csv(csv_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"The file '{csv_path}' was not found. Please check the path and ensure the file exists.")

    filtered_df = instruments_df.replace({np.nan: None})
    scrips_data = filtered_df.to_dict('records')
        
    return jsonify(scrips_data)

@main_bp.route('/api/get_nine_thirty_data', methods=['GET','POST'])
def get_nine_thirty_data():
    try:
        data = request.get_json() or {}
        underlying_scrip = data.get('underlying_scrip')
        underlying_seg = data.get('underlying_seg')
        
        if not underlying_scrip or not underlying_seg:
            return jsonify({"error": "Missing underlying_scrip or underlying_seg"}), 400

        cache_key = f"nine_thirty_data:{underlying_scrip}_{underlying_seg}"
        cached_data = current_app.redis_client.get(cache_key)
        if cached_data is None:
            return jsonify({'data': None})
        if isinstance(cached_data, (bytes,)):
            cached_data = cached_data.decode('utf-8')
        return jsonify({'data': cached_data})
    
    except Exception as e:
        print(f"Error in get_nine_thirty_data: {str(e)}")
        return jsonify({"error": str(e)}), 500


def calculate_nine_thirty_strike_levels(nine_thirty_data, scrip_id, segment, redis_client):
    if not nine_thirty_data or not nine_thirty_data.get('strikes'):
        return {}
    
    strikes_array = sorted(list(nine_thirty_data['strikes'].keys()), key=lambda x: float(x))
    chain = [{'strike': float(strike), 'put_ltp': nine_thirty_data['strikes'][strike]['p'], 
              'call_ltp': nine_thirty_data['strikes'][strike]['c']} for strike in strikes_array]
    nine_thirty_strike_levels = {}

    strikes = [float(s) for s in strikes_array]
    step = strikes[1] - strikes[0] if len(strikes) > 1 else 50
    lowest_strike = strikes_array[0]
    lowest_data = nine_thirty_data['strikes'][lowest_strike]
    hypothetical_low = {'strike': float(lowest_strike) - step, 'put_ltp': lowest_data['p'], 'call_ltp': lowest_data['c']}
    low_support = calculate_reversal(hypothetical_low, nine_thirty_data, scrip_id, segment, redis_client)
    
    for i, row in enumerate(chain):
        support = low_support if i == 0 else calculate_reversal(row, nine_thirty_data, scrip_id, segment, redis_client)
        if i < len(strikes) - 1:
            resistance = calculate_reversal(chain[i + 1], nine_thirty_data, scrip_id, segment, redis_client)
        else:
            hypothetical_high = {**row, 'strike': float(row['strike']) + step}
            resistance = calculate_reversal(hypothetical_high, nine_thirty_data, scrip_id, segment, redis_client)
        nine_thirty_strike_levels[row['strike']] = {
            'support': f"{support:.4f}",
            'resistance': f"{resistance:.4f}"
        }
    
    return nine_thirty_strike_levels

def calculate_reversal(row, nine_thirty_data, scrip_id, segment, redis_client):
    RISK_FREE_RATE = -0.067
    P = row.get('put_ltp') if isinstance(row, dict) else row['put_ltp']
    C = row.get('call_ltp') if isinstance(row, dict) else row['call_ltp']
    K = float(row.get('strike') if isinstance(row, dict) else row['strike'])
    # prefer nine_thirty_data's S if provided
    S = nine_thirty_data.get('s', 0)
    strike_data = nine_thirty_data.get('strikes', {}).get(str(K)) or nine_thirty_data.get('strikes', {}).get(K)
    if strike_data:
        P = strike_data.get('p', P)
        C = strike_data.get('c', C)
    else:
        # if strike data missing, return 0 as safe default
        return 0
    t = calculate_t(scrip_id, segment, redis_client)
    exp_term = math.exp(RISK_FREE_RATE * t)
    one_minus_exp = 1 - exp_term
    reversal = S - K + P - C + K * one_minus_exp
    return K + reversal

def calculate_t(scrip_id, segment, redis_client):
    now = datetime.now(timezone.utc)
    cache_key = f"expiry_date:{scrip_id}_{segment}"
    selected_expiry = redis_client.get(cache_key)
    if selected_expiry is None:
        return 0
    if isinstance(selected_expiry, (bytes,)):
        selected_expiry = selected_expiry.decode('utf-8')
    expiry_date = datetime.strptime(f"{selected_expiry} 15:30:00+05:30", "%Y-%m-%d %H:%M:%S%z")
    diff_ms = (expiry_date - now).total_seconds() * 1000
    if diff_ms <= 0:
        return 0
    diff_days_fractional = diff_ms / (1000 * 60 * 60 * 24)
    days = math.ceil(diff_days_fractional)
    return days / 365

def calc_nine_thirty_data(chain_data: dict, scrip_id, segment, redis_client):
    
    nine_thirty_chain_data = {
        's': chain_data.get('last_price', 0),
        'strikes': {},
        'date': datetime.now().strftime('%Y-%m-%d')
    }
    for key, value in chain_data.get('oc', {}).items():
        nine_thirty_chain_data['strikes'][str(key)] = {'p': value['pe']['last_price'], 'c': value['ce']['last_price']}
    
    nine_thirty_strike_levels = calculate_nine_thirty_strike_levels(nine_thirty_chain_data, scrip_id, segment, redis_client)
    nine_thirty_data = {
        's': chain_data.get('last_price', 0),
        'strikes': nine_thirty_chain_data['strikes'],
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
            if not expiry_list:
                logger.error(f"No expiry list for {scrip_id} {segment}, retrying")
                time.sleep(5)
                continue
            expiry_date = expiry_list[0]
            option_chain = dhan_client.fetch_option_chain(underlying_scrip=scrip_id,
                                                    underlying_seg=segment,
                                                    expiry=expiry_date)
            # DO NOT return on non-success; retry after a short sleep
            if option_chain.get('status') != 'success':
                logger.error(f"Failed to fetch option chain for {scrip_id} in {segment}. Status: {option_chain.get('status')}. Retrying...")
                time.sleep(5)
                continue

            cache_key_oc = f"option_chain:{scrip_id}_{segment}"
            cache_key_exp = f"expiry_date:{scrip_id}_{segment}"
            cache_key_nine_thirty_data = f"nine_thirty_data:{scrip_id}_{segment}"
            chain_data = option_chain.get('data', {})

            # expiry
            redis_client.set(cache_key_exp, expiry_date, ex=300)

            # Cache the processed response (TTL=300s for live data)
            json_data = json.dumps(chain_data)
            set_res = redis_client.set(cache_key_oc, json_data, ex=300)
            logger.info(f"Redis SET {cache_key_oc} -> {set_res}")

            # Verify immediately: read-back and TTL
            try:
                stored = redis_client.get(cache_key_oc)
                stored_len = len(stored) if stored else 0
                ttl = redis_client.ttl(cache_key_oc)
                logger.info(f"Redis VERIFY {cache_key_oc}: size={stored_len} ttl={ttl}")
            except Exception as re:
                logger.error(f"Redis verify error for {cache_key_oc}: {re}")

            cached_data = redis_client.get(cache_key_nine_thirty_data)
            if not cached_data and is_start_of_trading_day():
                nine_thirty_data = calc_nine_thirty_data(chain_data, scrip_id, segment, redis_client)
                redis_client.set(cache_key_nine_thirty_data, json.dumps(nine_thirty_data), ex=86340)

            logger.info("fetched option chain for: %s", scrip_id)
            time.sleep(3)  # To avoid hitting rate limits

        except Exception as e:
            logger.error(f"Error in fetch_and_cache_option_chain for {scrip_id}: {e}")
            time.sleep(5)
            continue

def background_task(redis_client, dhan_clients, instruments):
    """
    instruments: pandas.DataFrame with columns ['scrip_id','segment', ...]
    dhan_clients: list of DhanClient instances (can be fewer than instruments; will be used round-robin)
    """
    # instruments is a DataFrame; ensure we assign clients round-robin and keep threads alive
    if len(dhan_clients) == 0:
        logger.error("No Dhan clients available in background_task")
        return

    with ThreadPoolExecutor(max_workers=min(12, max(1, len(instruments)))) as executor:
        for idx, row in instruments.iterrows():
            try:
                scrip_id = int(row['scrip_id'])
                segment = row['segment']
            except Exception as ex:
                logger.error(f"Skipping invalid instrument row {idx}: {ex}")
                continue
            dc = dhan_clients[idx % len(dhan_clients)]
            executor.submit(fetch_and_cache_option_chain, dc, redis_client, scrip_id, segment)

@main_bp.route('/api/debug/redis_status', methods=['GET'])
def debug_redis_status():
    """
    Returns simple counts and a small sample from Redis to verify the worker writes are visible.
    """
    try:
        r = current_app.redis_client
        # Use patterns that the worker writes
        option_keys = r.keys('option_chain:*') or []
        expiry_keys = r.keys('expiry_date:*') or []
        nine_keys = r.keys('nine_thirty_data:*') or []

        sample = {}
        if option_keys:
            sample_key = option_keys[0]
            try:
                sample_val = r.get(sample_key)
            except Exception as ex:
                sample_val = f"error_reading:{ex}"
            sample[sample_key] = sample_val

        return jsonify({
            'option_chain_count': len(option_keys),
            'expiry_count': len(expiry_keys),
            'nine_thirty_count': len(nine_keys),
            'sample': sample
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def _send_approval_email(user_data):
    """
    Send email to approver (ADMIN_EMAIL) with user details.
    Uses SMTP_* env vars if provided; otherwise logs and skips.
    """
    admin_email = os.getenv('ADMIN_EMAIL')
    if not admin_email:
        logger.warning("ADMIN_EMAIL not configured; skipping notification email")
        return False

    smtp_host = os.getenv('SMTP_HOST')
    smtp_port = int(os.getenv('SMTP_PORT', 587))
    smtp_user = os.getenv('SMTP_USER')
    smtp_pass = os.getenv('SMTP_PASSWORD')
    from_addr = os.getenv('SMTP_FROM', smtp_user or f"noreply@{os.getenv('HOSTNAME','localhost')}")

    subject = f"New Signup Request: {user_data.get('email')}"
    body = f"""A new user has signed up and requires approval:

    Email: {user_data.get('email')}
    Created At: {user_data.get('createdAt')}
    To approve/reject, visit the admin portal.
    """

    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = from_addr
    msg['To'] = admin_email
    msg.set_content(body)

    # Try SMTP if configured
    if smtp_host and smtp_user and smtp_pass:
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as s:
                s.starttls()
                s.login(smtp_user, smtp_pass)
                s.send_message(msg)
            logger.info(f"Notification email sent to approver: {admin_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send notification email: {e}")
            return False
    else:
        # SMTP not configured — log and continue
        logger.info("SMTP not configured; email not sent. Payload:\n%s", body)
        return False

@main_bp.route('/api/signin', methods=['POST'])
def signin():
    try:
        data = request.get_json(force=True)
        if not data:
            return jsonify({"error": "Invalid JSON"}), 400

        email = data.get('email', '').strip().lower()
        password = data.get('password')

        if not email or password is None:
            return jsonify({"error": "Email and password required"}), 400

        r = current_app.redis_client
        entries = r.lrange('users', 0, -1)

        if not entries:
            return jsonify({"error": "Invalid credentials"}), 400

        # Find matching approved user
        for entry in entries:
            user = json.loads(entry)
            if (user.get('email', '').lower() == email and
                str(user.get('password')) == str(password)):  # handles number/string

                if user.get('status') != 'approved':
                    return jsonify({"error": "Account not approved"}), 403

                # Success
                return jsonify({
                    "message": "Login successful",
                    "user": {
                        "email": user['email'],
                        "status": user['status'],
                        "expiryDate": user.get('expiryDate')
                    }
                }), 200

        return jsonify({"error": "Invalid credentials"}), 400

    except Exception as e:
        logger.error("Signin error: %s", e)
        return jsonify({"error": "Server error"}), 500    

@main_bp.route('/api/signup', methods=['POST'])
def signup():
    """
    Accepts user signup data, stores to Redis pending list and notifies the approver via email.
    """
    try:
        data = request.get_json() or {}
        email = data.get('email')
        # phone = data.get('phone')
        # dob = data.get('dob')
        # state = data.get('state')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': 'email and password are required'}), 400
        
        r = current_app.redis_client
        # Check if email already exists
        entries = r.lrange('pending_users', 0, -1) or []
        if any(json.loads(e).get('email') == email for e in entries):
            return jsonify({"error": "Email already registered"}), 400

        # build pending user object
        pending_user = {
            'email': email,
            # 'phone': phone,
            # 'dob': dob,
            # 'state': state,
            'password': password,  # you may want to hash in real app
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'status': 'pending'
        }

        # push to Redis list 'pending_users'
        r.rpush('pending_users', json.dumps(pending_user))

        # send notification to approver (best-effort)
        _send_approval_email(pending_user)

        return jsonify({'message': 'Signup submitted. Approver has been notified.'}), 201
    except Exception as e:
        logger.error("Error in /signup: %s", e)
        return jsonify({'error': str(e)}), 500


def _require_admin(req):
    """
    Helper to validate admin secret in header 'X-ADMIN-KEY'
    """
    admin_secret = os.getenv('ADMIN_SECRET')
    provided = req.get('X_ADMIN_KEY')
    if not admin_secret or provided != admin_secret:
        return False
    return True


@main_bp.route('/api/admin/pending', methods=['GET', 'POST'])
def admin_pending():
    """
    Return list of pending signups. Requires X-ADMIN-KEY header.
    """
    try:
        data = request.get_json() or {}
        if not _require_admin(data):
            return jsonify({'error': 'unauthorized'}), 401

        r = current_app.redis_client
        entries = r.lrange('pending_users', 0, -1) or []
        parsed = [json.loads(e) for e in entries]
        return jsonify({'pending': parsed})
    except Exception as e:
        logger.error("Error in /admin/pending: %s", e)
        return jsonify({'error': str(e)}), 500


@main_bp.route('/api/admin/action', methods=['GET', 'POST'])
def admin_action():
    """
    Approve or reject a pending user.
    Body: { "email": "<email>", "action": "approve"|"reject", "expiryDate": "<iso date>" }
    Requires X-ADMIN-KEY header.
    """
    try:
        data = request.get_json() or {}
        if not _require_admin(data):
            return jsonify({'error': 'unauthorized'}), 401

        email = data.get('email')
        action = data.get('action')
        expiry = data.get('expiryDate')

        if not email or action not in ('approve', 'reject'):
            return jsonify({'error': 'invalid payload'}), 400

        r = current_app.redis_client
        # find pending entry and remove it
        entries = r.lrange('pending_users', 0, -1) or []
        matched = None
        for e in entries:
            try:
                obj = json.loads(e)
            except Exception:
                continue
            if obj.get('email') == email:
                matched = obj
                # remove this specific element
                r.lrem('pending_users', 1, e)
                break

        if not matched:
            return jsonify({'error': 'user not found in pending list'}), 404

        if action == 'approve':
            # mark approved and push to 'users' list
            matched['status'] = 'approved'
            if expiry:
                matched['expiryDate'] = expiry
            else:
                matched['expiryDate'] = None
            r.rpush('users', json.dumps(matched))
            return jsonify({'message': 'user approved'}), 200

        # reject
        matched['status'] = 'rejected'
        r.rpush('rejected_users', json.dumps(matched))
        return jsonify({'message': 'user rejected'}), 200

    except Exception as e:
        logger.error("Error in /admin/action: %s", e)
        return jsonify({'error': str(e)}), 500