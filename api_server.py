#!/usr/bin/env python3
"""
Settings API Server for Trading Dashboard
Runs on port 8080 on EC2
Handles profile settings read/write and Dhan balance fetch
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import yaml
import os
import json
import pyotp
import requests
from datetime import datetime

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROFILES_DIR = os.path.join(BASE_DIR, 'config', 'profiles')

# Profile passwords
PROFILE_PASSWORDS = {
    'vishal-live': 'vishal@431303',
    'vishal': 'vishal@431303',
    'neha': 'neha@123',
}

def verify_password(profile, password):
    return PROFILE_PASSWORDS.get(profile) == password

def load_profile(profile_name):
    path = os.path.join(PROFILES_DIR, f'{profile_name}.yaml')
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return yaml.safe_load(f)

def save_profile(profile_name, data):
    path = os.path.join(PROFILES_DIR, f'{profile_name}.yaml')
    with open(path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True)

def get_dhan_balance(profile_data):
    try:
        dhan = profile_data.get('dhan', {})
        code = pyotp.TOTP(dhan['totp_secret']).now()
        url = "https://auth.dhan.co/app/generateAccessToken?dhanClientId={}&pin={}&totp={}".format(
            dhan['client_id'], dhan['pin'], code
        )
        resp = requests.post(url, timeout=15)
        token = resp.json().get('accessToken', '')
        if token:
            headers = {'access-token': token, 'Content-Type': 'application/json'}
            m = requests.get('https://api.dhan.co/v2/fundlimit', headers=headers, timeout=10)
            data = m.json()
            return float(data.get('availabelBalance', 
                        data.get('availableBalance', 
                        data.get('sodLimit', 0))))
    except Exception as e:
        print(f"Balance fetch error: {e}")
    return None

@app.route('/api/auth', methods=['POST'])
def authenticate():
    data = request.json
    profile = data.get('profile')
    password = data.get('password')
    if verify_password(profile, password):
        return jsonify({'success': True, 'profile': profile})
    return jsonify({'success': False, 'error': 'Invalid password'}), 401

@app.route('/api/settings', methods=['GET'])
def get_settings():
    profile = request.args.get('profile')
    password = request.args.get('password')
    if not verify_password(profile, password):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = load_profile(profile)
    if not data:
        return jsonify({'error': 'Profile not found'}), 404
    
    # Return only settings (not credentials)
    settings = {
        'profile_name': data.get('profile', {}).get('name', profile),
        'display_name': data.get('profile', {}).get('display_name', profile),
        'intraday': {
            'daily_capital_limit': data.get('intraday', {}).get('daily_capital_limit', 0),
            'per_trade_max_capital': data.get('intraday', {}).get('per_trade_max_capital', 0),
            'max_trades_per_day': data.get('intraday', {}).get('max_trades_per_day', 2),
            'daily_loss_limit': data.get('intraday', {}).get('daily_loss_limit', 0),
            'min_confidence_score': data.get('intraday', {}).get('min_confidence_score', 7),
            'vix_threshold': data.get('intraday', {}).get('vix_threshold', 18),
        },
        'fno': {
            'mode': data.get('fno', {}).get('mode', 'paper'),
            'paper_capital': data.get('fno', {}).get('paper_capital', 0),
            'daily_capital_limit': data.get('fno', {}).get('daily_capital_limit', 0),
            'per_trade_max_capital': data.get('fno', {}).get('per_trade_max_capital', 0),
            'daily_loss_limit': data.get('fno', {}).get('daily_loss_limit', 0),
            'max_lots_per_trade': data.get('fno', {}).get('max_lots_per_trade', 1),
        }
    }
    return jsonify(settings)

@app.route('/api/settings', methods=['POST'])
def save_settings():
    password = request.args.get('password')
    profile = request.args.get('profile')
    if not verify_password(profile, password):
        return jsonify({'error': 'Unauthorized'}), 401
    
    new_settings = request.json
    data = load_profile(profile)
    if not data:
        return jsonify({'error': 'Profile not found'}), 404
    
    # Update only allowed fields
    if 'intraday' in new_settings:
        if 'intraday' not in data:
            data['intraday'] = {}
        allowed = ['daily_capital_limit', 'per_trade_max_capital', 
                   'max_trades_per_day', 'daily_loss_limit',
                   'min_confidence_score', 'vix_threshold']
        for key in allowed:
            if key in new_settings['intraday']:
                data['intraday'][key] = new_settings['intraday'][key]
    
    if 'fno' in new_settings:
        if 'fno' not in data:
            data['fno'] = {}
        allowed = ['daily_capital_limit', 'per_trade_max_capital',
                   'daily_loss_limit', 'max_lots_per_trade', 'paper_capital']
        for key in allowed:
            if key in new_settings['fno']:
                data['fno'][key] = new_settings['fno'][key]
    
    save_profile(profile, data)
    return jsonify({'success': True, 'saved_at': datetime.now().isoformat()})

@app.route('/api/balance', methods=['GET'])
def get_balance():
    profile = request.args.get('profile')
    password = request.args.get('password')
    if not verify_password(profile, password):
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = load_profile(profile)
    if not data:
        return jsonify({'error': 'Profile not found'}), 404
    
    balance = get_dhan_balance(data)
    return jsonify({'balance': balance, 'profile': profile})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'time': datetime.now().isoformat()})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)
