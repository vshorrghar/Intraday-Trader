#!/bin/bash
export HOME=/home/ec2-user
export AWS_PROFILE=vishal-admin
export AWS_DEFAULT_REGION=us-east-1
cd /home/ec2-user/dev-sandbox
mkdir -p logs
D=$(date +%Y-%m-%d)
.venv/bin/python run_intraday.py --force >> logs/midday_${D}.log 2>&1
