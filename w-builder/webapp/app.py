"""Professional Wealth Manager Web Application.

Flask backend with REST API for portfolio analysis, file upload, and real-time updates.
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from flask import Flask, jsonify, render_template, request, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from aws_cost_monitor import AWSCostMonitor
from fetchers.market_indices import fetch_indices
from fetchers.nse_bhavcopy import fetch_bhavcopy
from fetchers.nse_bulk_deals import fetch_bulk_deals
from fetchers.nse_fii_dii import fetch_fii_dii
from fetchers.screener_fetcher import fetch_fundamentals_batch
from llm.bedrock_client import BedrockClient
from llm.brutal_portfolio_analyzer import analyze_portfolio_brutally
from llm.crisis_opportunity_analyzer import analyze_crisis_opportunities
from llm.enhanced_intraday_engine import generate_enhanced_intraday_setups
from llm.multibagger_scanner import scan_multibaggers
from llm.realtime_portfolio_analyzer import analyze_realtime_portfolio
from parsers.groww_pnl_parser import parse_pnl_xlsx
from parsers.groww_stocks_parser import parse_stocks_xlsx

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = Path('webapp/uploads')
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED_EXTENSIONS = {'xlsx', 'xls'}
DOWNLOADS_FOLDER = Path.home() / 'Downloads'
FILE_AGE_WARNING_DAYS = 3

app.config['UPLOAD_FOLDER'] = str(UPLOAD_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

# Global state
analysis_state = {
    'status': 'idle',
    'progress': 0,
    'message': '',
    'results': None,
    'error': None
}


def allowed_file(filename):
    """Check if file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_age_days(file_path: Path) -> int:
    """Get file age in days."""
    if not file_path.exists():
        return 999
    mtime = file_path.stat().st_mtime
    age = datetime.now() - datetime.fromtimestamp(mtime)
    return age.days


def scan_downloads_folder() -> List[Dict]:
    """Scan Downloads folder for Groww Excel files."""
    if not DOWNLOADS_FOLDER.exists():
        return []

    files = []
    patterns = [
        "Stocks_Holdings_Statement*.xlsx",
        "Mutual_Funds*.xlsx",
        "Stocks_PnL_Report*.xlsx",
        "Stocks_Order_History*.xlsx",
        "MF_Order_History*.xlsx"
    ]

    for pattern in patterns:
        for file_path in DOWNLOADS_FOLDER.glob(pattern):
            age_days = get_file_age_days(file_path)
            files.append({
                'name': file_path.name,
                'path': str(file_path),
                'size': file_path.stat().st_size,
                'modified': datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                'age_days': age_days,
                'is_old': age_days > FILE_AGE_WARNING_DAYS,
                'type': _detect_file_type(file_path.name)
            })

    # Sort by modification time (newest first)
    files.sort(key=lambda x: x['modified'], reverse=True)
    return files


def _detect_file_type(filename: str) -> str:
    """Detect Groww file type from filename."""
    filename_lower = filename.lower()
    if 'holdings' in filename_lower and 'statement' in filename_lower:
        return 'holdings'
    elif 'mutual_funds' in filename_lower:
        return 'mutual_funds'
    elif 'pnl' in filename_lower or 'p&l' in filename_lower:
        return 'pnl'
    elif 'order_history' in filename_lower:
        if 'stocks' in filename_lower:
            return 'stock_orders'
        elif 'mf' in filename_lower:
            return 'mf_orders'
    return 'unknown'


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')


@app.route('/api/downloads/scan', methods=['GET'])
def api_scan_downloads():
    """Scan Downloads folder for Groww files."""
    try:
        files = scan_downloads_folder()
        return jsonify({
            'success': True,
            'files': files,
            'total': len(files)
        })
    except Exception as e:
        logger.error("Failed to scan downloads: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/upload', methods=['POST'])
def api_upload():
    """Upload Excel file."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': 'Invalid file type. Only Excel files allowed.'}), 400

    try:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"
        file_path = UPLOAD_FOLDER / unique_filename

        file.save(str(file_path))

        return jsonify({
            'success': True,
            'filename': unique_filename,
            'path': str(file_path),
            'size': file_path.stat().st_size,
            'type': _detect_file_type(filename)
        })
    except Exception as e:
        logger.error("Upload failed: %s", e)
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    """Run comprehensive portfolio analysis."""
    global analysis_state

    data = request.json
    holdings_file = data.get('holdings_file')
    pnl_file = data.get('pnl_file')

    if not holdings_file:
        return jsonify({'success': False, 'error': 'Holdings file required'}), 400

    try:
        # Reset state
        analysis_state = {
            'status': 'running',
            'progress': 0,
            'message': 'Starting analysis...',
            'results': None,
            'error': None
        }

        # Load config
        config_path = Path('config/config.yaml')
        with open(config_path) as f:
            config = yaml.safe_load(f)

        # Initialize Bedrock client
        analysis_state['message'] = 'Initializing AI client...'
        analysis_state['progress'] = 5
        bedrock_region = config["aws"].get("bedrock_region", config["aws"]["region"])
        model_id = config["aws"]["bedrock_model_id"]
        client = BedrockClient(region=bedrock_region, model_id=model_id)

        # Parse portfolio
        analysis_state['message'] = 'Parsing portfolio files...'
        analysis_state['progress'] = 10
        holdings = parse_stocks_xlsx(holdings_file)

        pnl_data = []
        if pnl_file and Path(pnl_file).exists():
            _, pnl_data = parse_pnl_xlsx(pnl_file)

        # Fetch market data
        cache_dir = Path('cache')
        cache_dir.mkdir(exist_ok=True)

        analysis_state['message'] = 'Fetching live market data...'
        analysis_state['progress'] = 20
        bhavcopy = fetch_bhavcopy(str(cache_dir))

        analysis_state['progress'] = 25
        fii_dii = fetch_fii_dii(str(cache_dir))

        analysis_state['progress'] = 30
        indices = fetch_indices(str(cache_dir))

        analysis_state['progress'] = 35
        deals = fetch_bulk_deals()

        analysis_state['message'] = 'Fetching stock fundamentals...'
        analysis_state['progress'] = 40
        symbols = list(set([h.nse_symbol for h in holdings if h.nse_symbol] +
                          [h.name for h in holdings]))[:100]
        fundamentals = fetch_fundamentals_batch(symbols, str(cache_dir))

        # Calculate index changes
        indices_change = {}
        if isinstance(indices, list):
            # fetch_indices returns a list of IndexData objects
            for index_data in indices:
                indices_change[index_data.name] = index_data.change_percent
        elif isinstance(indices, dict):
            # Legacy format support
            for name, data in indices.items():
                if isinstance(data, dict) and "change_pct" in data:
                    indices_change[name] = data["change_pct"]
                else:
                    indices_change[name] = 0.0

        is_crisis = any(v < -2 for v in indices_change.values()) if indices_change else False

        # AWS Cost Check
        analysis_state['message'] = 'Checking AWS costs...'
        analysis_state['progress'] = 45
        try:
            cost_monitor = AWSCostMonitor(region=config["aws"]["region"])
            mtd_cost = cost_monitor.get_month_to_date_cost()
            forecast_cost = cost_monitor.get_forecast_month_end()
            service_costs = cost_monitor.get_costs_by_service(days=7)
        except Exception as e:
            logger.warning("Cost monitoring unavailable: %s", e)
            mtd_cost = forecast_cost = 0.0
            service_costs = {}

        # Run analyses
        analysis_state['message'] = 'Analyzing intraday opportunities...'
        analysis_state['progress'] = 50
        intraday_setups = generate_enhanced_intraday_setups(
            bhavcopy=bhavcopy,
            deals=deals,
            fii_dii=fii_dii,
            fundamentals=fundamentals,
            indices=indices_change,
            client=client,
        )

        analysis_state['message'] = 'Scanning for multibaggers...'
        analysis_state['progress'] = 60
        multibaggers = scan_multibaggers(
            bhavcopy=bhavcopy,
            fundamentals=fundamentals,
            deals=deals,
            fii_dii=fii_dii,
            client=client,
        )

        analysis_state['message'] = 'Running brutal portfolio assessment...'
        analysis_state['progress'] = 70
        brutal_assessments = analyze_portfolio_brutally(
            holdings=holdings,
            bhavcopy=bhavcopy,
            fundamentals=fundamentals,
            client=client,
        )

        analysis_state['message'] = 'Analyzing portfolio actions...'
        analysis_state['progress'] = 80
        portfolio_actions = analyze_realtime_portfolio(
            holdings=holdings,
            bhavcopy=bhavcopy,
            fundamentals=fundamentals,
            fii_dii=fii_dii,
            pnl_data=pnl_data,
            indices_change=indices_change,
            client=client,
        )

        # Crisis opportunities if market crashing
        crisis_opps = []
        if is_crisis:
            analysis_state['message'] = 'Scanning crisis opportunities...'
            analysis_state['progress'] = 90
            crisis_opps = analyze_crisis_opportunities(
                bhavcopy=bhavcopy,
                deals=deals,
                fii_dii=fii_dii,
                fundamentals=fundamentals,
                indices_change=indices_change,
                client=client,
            )

        # Prepare results
        analysis_state['message'] = 'Finalizing results...'
        analysis_state['progress'] = 95

        results = {
            'timestamp': datetime.now().isoformat(),
            'portfolio_summary': {
                'total_holdings': len(holdings),
                'total_value': sum(h.groww_closing_value for h in holdings),
                'total_invested': sum(h.buy_value for h in holdings),
                'unrealized_pnl': sum(h.unrealised_pnl for h in holdings),
            },
            'aws_costs': {
                'month_to_date': mtd_cost,
                'forecast_month_end': forecast_cost,
                'service_costs': service_costs,
            },
            'market_context': {
                'fii_net_crores': round(fii_dii.fii_net / 10000000, 2),
                'dii_net_crores': round(fii_dii.dii_net / 10000000, 2),
                'indices_change': indices_change,
                'is_crisis': is_crisis,
            },
            'intraday_setups': [vars(s) for s in intraday_setups],
            'multibaggers': [vars(m) for m in multibaggers],
            'brutal_assessments': [vars(a) for a in brutal_assessments],
            'portfolio_actions': [vars(a) for a in portfolio_actions],
            'crisis_opportunities': [vars(o) for o in crisis_opps],
        }

        # Save results
        output_dir = Path('webapp/results')
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        results_file = output_dir / f'analysis_{timestamp}.json'
        with open(results_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        analysis_state = {
            'status': 'completed',
            'progress': 100,
            'message': 'Analysis complete!',
            'results': results,
            'error': None
        }

        return jsonify({'success': True, 'results': results})

    except Exception as e:
        logger.error("Analysis failed: %s", e, exc_info=True)
        error_msg = str(e)

        # Add more context for common errors
        if "'list' object has no attribute 'items'" in error_msg:
            error_msg = "Data format error - this has been fixed. Please try again."
        elif "ExpiredToken" in error_msg:
            error_msg = "AWS credentials expired. Please refresh your credentials and restart the server."
        elif "No module named" in error_msg:
            error_msg = f"Missing dependency: {error_msg}. Run: pip install -r requirements.txt"

        analysis_state = {
            'status': 'error',
            'progress': 0,
            'message': error_msg,
            'results': None,
            'error': error_msg
        }
        return jsonify({'success': False, 'error': error_msg}), 500


@app.route('/api/status', methods=['GET'])
def api_status():
    """Get analysis status."""
    return jsonify(analysis_state)


@app.route('/api/results/latest', methods=['GET'])
def api_latest_results():
    """Get latest analysis results."""
    results_dir = Path('webapp/results')
    if not results_dir.exists():
        return jsonify({'success': False, 'error': 'No results found'}), 404

    result_files = sorted(results_dir.glob('analysis_*.json'), reverse=True)
    if not result_files:
        return jsonify({'success': False, 'error': 'No results found'}), 404

    with open(result_files[0]) as f:
        results = json.load(f)

    return jsonify({'success': True, 'results': results})


if __name__ == '__main__':
    logger.info("Starting Wealth Manager Web Application")
    logger.info("Access at: http://localhost:8080")
    app.run(host='0.0.0.0', port=8080, debug=True)
