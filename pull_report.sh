#!/bin/bash
# Pull latest analysis report from EC2 to local Mac
# Usage: ./pull_report.sh

EC2_IP="3.108.156.101"
KEY="$HOME/Downloads/wealth-builder-pro.pem"
REMOTE_FILE="~/wealth-builder-pro/output/latest_analysis.json"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)/output/reports"

mkdir -p "$LOCAL_DIR"

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M")
FILENAME="analysis_${TIMESTAMP}.json"

scp -i "$KEY" -o StrictHostKeyChecking=no "ec2-user@${EC2_IP}:${REMOTE_FILE}" "${LOCAL_DIR}/${FILENAME}" 2>&1

if [ $? -eq 0 ]; then
    ln -sf "${FILENAME}" "${LOCAL_DIR}/latest.json"

    # Rebuild data.json for dashboard
    python3 -c "
import json
with open('${LOCAL_DIR}/latest.json') as f:
    d = json.load(f)
pa = d.get('portfolio_analysis', d)
if 'portfolio_analysis' in pa: pa = pa['portfolio_analysis']
ms = d.get('market_scan', {})
ld = d.get('live_data', {})
m = {}
m.update(pa)
m['long_term_picks'] = ms.get('long_term_picks', [])
m['intraday_setups'] = ms.get('intraday_setups', [])
m['sectors_to_watch'] = ms.get('sectors_to_watch', [])
m['promoter_signals'] = ms.get('promoter_signals', [])
m['market_summary'] = ms.get('market_summary', '')
m['fii_dii_interpretation'] = ms.get('fii_dii_interpretation', '')
m['fii_dii'] = ld.get('fii_dii', {})
m['generated_at'] = d.get('generated_at', '')
with open('${LOCAL_DIR}/data.json', 'w') as f:
    json.dump(m, f, indent=2, ensure_ascii=False)
"

    # Start local server if not running
    if ! lsof -i :9999 > /dev/null 2>&1; then
        cd "${LOCAL_DIR}" && python3 -m http.server 9999 &
        sleep 1
    fi

    echo "✅ Report saved: output/reports/${FILENAME}"
    echo "🌐 Dashboard: http://localhost:9999/dashboard.html"
    open http://localhost:9999/dashboard.html
else
    echo "❌ Failed to pull report. Check EC2 is running and key path."
fi
