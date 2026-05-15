#!/bin/bash
# Push neha-live.db to S3 (so OLD EC2 can read it)
# Run from cron on NEW EC2 every 15 min during market hours

export AWS_PROFILE=vishal-admin
DB_PATH=/home/ec2-user/dev-sandbox/database/neha-live.db
S3_PATH=s3://dev-sandbox-dashboard-176767908884/db-sync/neha-live.db

if [ -f "$DB_PATH" ]; then
    aws s3 cp "$DB_PATH" "$S3_PATH" --quiet --region ap-south-1
    echo "$(date): Synced neha-live.db to S3"
else
    echo "$(date): ERROR - neha-live.db not found at $DB_PATH"
    exit 1
fi
