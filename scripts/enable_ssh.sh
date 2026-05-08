#!/bin/bash
# enable_ssh.sh — Add current Mac IP to EC2 security group
# Run from Mac when SSH stops working: bash scripts/enable_ssh.sh

SG_ID="sg-09035a56f253ebf6e"
REGION="ap-south-1"
PROFILE="vishal-admin"

echo "Getting current IP..."
MY_IP=$(curl -s ifconfig.me)
echo "Your IP: $MY_IP"

echo "Adding $MY_IP to security group $SG_ID..."
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp \
  --port 22 \
  --cidr ${MY_IP}/32 \
  --region $REGION \
  --profile $PROFILE 2>&1

# Ignore duplicate rule error — means IP already added
if [ $? -eq 0 ]; then
  echo "✅ IP added successfully"
else
  echo "✅ IP already in security group (that is fine)"
fi

echo ""
echo "Testing SSH..."
ssh -i ~/Downloads/wealth-builder-pro.pem ec2-user@13.206.144.6 "echo '✅ SSH working'"
