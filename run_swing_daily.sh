#!/bin/bash
export HOME=/home/ec2-user
export AWS_PROFILE=vishal-admin
export AWS_DEFAULT_REGION=us-east-1
cd /home/ec2-user/dev-sandbox
mkdir -p logs
D=$(date +%Y-%m-%d)
H=$(date +%H)
if [ "$H" -ge 9 ]; then
    .venv/bin/python run_swing.py scan --force >> logs/swing_${D}.log 2>&1
else
    .venv/bin/python run_swing.py monitor >> logs/swing_${D}.log 2>&1
fi
