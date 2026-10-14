#!/bin/bash
# Swing paper trading cron wrapper.
# Usage: bash run_swing_paper.sh --profile vishal --mode scan
#        bash run_swing_paper.sh --profile vishal --mode monitor
#        bash run_swing_paper.sh --profile vishal --mode refresh

APP_DIR="/home/ec2-user/dev-sandbox"
LOG_DIR="${APP_DIR}/logs"
PYTHON="${APP_DIR}/.venv/bin/python"

# Args: --profile {name} --mode {refresh|scan|monitor}
PROFILE=""
MODE=""
while [[ $# -gt 0 ]]; do
    case $1 in
        --profile) PROFILE=$2; shift 2;;
        --mode) MODE=$2; shift 2;;
        *) shift;;
    esac
done

if [ -z "$PROFILE" ] || [ -z "$MODE" ]; then
    echo "Usage: bash run_swing_paper.sh --profile <name> --mode <refresh|scan|monitor>"
    exit 1
fi

cd $APP_DIR
export AWS_PROFILE=vishal-admin

case $MODE in
    refresh)
        $PYTHON backtest/fetch_swing_data.py --profile $PROFILE \
            >> $LOG_DIR/swing_refresh_${PROFILE}_$(date +%Y-%m-%d).log 2>&1
        ;;
    scan)
        $PYTHON run_swing.py --profile $PROFILE --action scan \
            >> $LOG_DIR/swing_${PROFILE}_$(date +%Y-%m-%d).log 2>&1
        ;;
    monitor)
        $PYTHON run_swing.py --profile $PROFILE --action monitor \
            >> $LOG_DIR/swing_${PROFILE}_$(date +%Y-%m-%d).log 2>&1
        ;;
    *)
        echo "Unknown mode: $MODE (use refresh|scan|monitor)"
        exit 1
        ;;
esac
