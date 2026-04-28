#!/bin/bash
cd /home/ec2-user/dev-sandbox
export AWS_PROFILE=vishal-admin
export AWS_DEFAULT_REGION=ap-south-1
aws s3 sync dashboard/ s3://dev-sandbox-dashboard-176767908884/ --exclude "*.DS_Store" --quiet
echo "$(date): Dashboard synced to S3" >> /home/ec2-user/dev-sandbox/logs/sync.log
