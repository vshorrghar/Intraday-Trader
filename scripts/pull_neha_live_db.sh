#!/bin/bash
# Pull neha-live.db from S3 (synced by NEW EC2)
# Used before reading neha-live data on OLD EC2

export AWS_PROFILE=vishal-admin
S3_PATH=s3://dev-sandbox-dashboard-176767908884/db-sync/neha-live.db
LOCAL_PATH=/home/ec2-user/dev-sandbox/database/neha-live.db

aws s3 cp "$S3_PATH" "$LOCAL_PATH" --quiet --region ap-south-1
