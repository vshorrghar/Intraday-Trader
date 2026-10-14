#!/bin/bash
# enable_ssh.sh — Add current Mac IP to EC2 security group
# Run from Mac when SSH stops working: bash scripts/enable_ssh.sh

SG_ID="sg-09035a56f253ebf6e"
REGION="ap-south-1"
PROFILE="vishal-admin"

echo "Getting current IP..."
MY_IP=$(curl -4 -s https://checkip.amazonaws.com)
echo "Your IP: $MY_IP"

echo "Adding $MY_IP to security group $SG_ID..."
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 22 \
  --cidr ${MY_IP}/32 \
  --region $REGION \
  --profile $PROFILE
RC=$?
if [ $RC -eq 0 ]; then
  echo "✅ IP added successfully"
else
  echo "⚠️  authorize returned $RC — likely duplicate (fine) OR a real error (check message above)"
fi

echo ""
echo "Testing SSH..."
ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@13.206.144.6 "echo '✅ SSH working'"
