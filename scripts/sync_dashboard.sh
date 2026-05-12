#!/bin/bash
# Manual dashboard sync to S3 + CloudFront invalidation

TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")
CREDS=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/iam/security-credentials/EpoxyChronicleInstanceRole)

export AWS_ACCESS_KEY_ID=$(echo $CREDS | python3 -c "import sys,json; print(json.load(sys.stdin)['AccessKeyId'])")
export AWS_SECRET_ACCESS_KEY=$(echo $CREDS | python3 -c "import sys,json; print(json.load(sys.stdin)['SecretAccessKey'])")
export AWS_SESSION_TOKEN=$(echo $CREDS | python3 -c "import sys,json; print(json.load(sys.stdin)['Token'])")
export AWS_DEFAULT_REGION=ap-south-1

cd /home/ec2-user/dev-sandbox

echo "Syncing to S3..."
aws s3 sync dashboard/ s3://dev-sandbox-dashboard-176767908884/ --delete

echo "Invalidating CloudFront..."
aws cloudfront create-invalidation \
  --distribution-id E3NXP6TCRJKVX1 \
  --paths "/*" \
  --region us-east-1

echo "Done — dashboard live at https://d2q1cy3ph7jbd0.cloudfront.net"
