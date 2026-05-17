#!/bin/bash
# F&O Mark-to-Market update - runs every 30 min during market hours
cd /home/ec2-user/dev-sandbox
.venv/bin/python3 scripts/fno_mtm_run.py >> logs/fno_pnl_update.log 2>&1
