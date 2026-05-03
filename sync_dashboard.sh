#!/bin/bash
export HOME=/home/ec2-user
export AWS_PROFILE=vishal-admin
cd /home/ec2-user/dev-sandbox
source .venv/bin/activate

# Build cumulative history from all daily reports
python scripts/update_history.py 2>&1

# Sync dashboard data to S3 (skip index.html — its locked)
export AWS_DEFAULT_REGION=ap-south-1
aws s3 sync dashboard/ s3://dev-sandbox-dashboard-176767908884/ --exclude "*.DS_Store" --exclude "index.html" --quiet
