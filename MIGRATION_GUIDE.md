# Migration Guide — Move to Personal AWS Account

## What You Need

| Service | Purpose | Monthly Cost |
|---------|---------|-------------|
| EC2 (t3.small, Mumbai) | Runs trading scripts | ₹1,260 |
| Bedrock (Claude Sonnet) | AI trade selection | ₹450 |
| S3 | Dashboard JSON storage | ₹50 |
| CloudFront | Dashboard HTTPS access | ₹50 |
| **Total** | | **₹1,800/month** |

You do NOT need Kiro on the new account. Kiro is only for code editing on your laptop.

## Step-by-Step

### 1. Create Personal AWS Account

- Go to https://aws.amazon.com → Create Account
- Use your personal email (not corporate)
- Add a credit card for billing

### 2. Enable Bedrock Model Access

- Go to AWS Console → Bedrock → Model access (region: us-east-1)
- Request access to: `Anthropic Claude Sonnet 4.5`
- Takes 1-2 minutes to approve

### 3. Create IAM User

```bash
aws iam create-user --user-name trading-bot
aws iam attach-user-policy --user-name trading-bot --policy-arn arn:aws:iam::aws:policy/AmazonBedrockFullAccess
aws iam attach-user-policy --user-name trading-bot --policy-arn arn:aws:iam::aws:policy/AmazonEC2FullAccess
aws iam attach-user-policy --user-name trading-bot --policy-arn arn:aws:iam::aws:policy/AmazonS3FullAccess
aws iam attach-user-policy --user-name trading-bot --policy-arn arn:aws:iam::aws:policy/CloudFrontFullAccess
aws iam create-access-key --user-name trading-bot
```

Save the access key ID and secret.

### 4. Launch EC2 (Mumbai)

```bash
# Set region
export AWS_DEFAULT_REGION=ap-south-1

# Create key pair
aws ec2 create-key-pair --key-name trading-key --query 'KeyMaterial' --output text > ~/trading-key.pem
chmod 400 ~/trading-key.pem

# Create security group (SSH from your IP only)
MY_IP=$(curl -s https://checkip.amazonaws.com)
SG_ID=$(aws ec2 create-security-group --group-name trading-sg --description "Trading bot" --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id $SG_ID --protocol tcp --port 22 --cidr ${MY_IP}/32

# Get latest Amazon Linux 2023 AMI
AMI_ID=$(aws ec2 describe-images --owners amazon --filters "Name=name,Values=al2023-ami-2023*-x86_64" "Name=state,Values=available" --query "Images | sort_by(@, &CreationDate) | [-1].ImageId" --output text)

# Launch t3.small
aws ec2 run-instances \
  --image-id $AMI_ID \
  --instance-type t3.small \
  --key-name trading-key \
  --security-group-ids $SG_ID \
  --block-device-mappings '[{"DeviceName":"/dev/xvda","Ebs":{"VolumeSize":20,"VolumeType":"gp3"}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=dev-sandbox}]'
```

### 5. Setup EC2

SSH in and run:

```bash
# Install Python
sudo dnf install -y python3.13 python3.13-pip git cronie
sudo systemctl enable crond && sudo systemctl start crond

# Clone code
git clone https://github.com/vshorrghar/Intraday-Trader.git ~/dev-sandbox
cd ~/dev-sandbox
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install scipy numpy

# Setup AWS credentials
mkdir -p ~/.aws
cat > ~/.aws/credentials << EOF
[default]
aws_access_key_id = YOUR_ACCESS_KEY
aws_secret_access_key = YOUR_SECRET_KEY
EOF

cat > ~/.aws/config << EOF
[default]
region = us-east-1
output = json
EOF
```

### 6. Update config.yaml

Edit `config/config.yaml` with your Dhan broker credentials:

```yaml
dhan:
  client_id: "YOUR_DHAN_CLIENT_ID"
  api_key: "YOUR_DHAN_API_KEY"
  api_secret: "YOUR_DHAN_API_SECRET"
  totp_secret: "YOUR_TOTP_SECRET"
  pin: "YOUR_PIN"
```

### 7. Setup Cron

```bash
# Edit cron (times in UTC — 09:20 IST = 03:50 UTC)
crontab -e
```

Add:
```
50 3 * * 1-5 /home/ec2-user/dev-sandbox/run_fno_daily.sh
55 3 * * 1-5 /home/ec2-user/dev-sandbox/run_daily.sh
50 9 * * 1-5 /home/ec2-user/dev-sandbox/sync_dashboard.sh
```

### 8. Setup Dashboard (S3 + CloudFront)

```bash
# Create private S3 bucket
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
BUCKET="dev-sandbox-dashboard-${ACCOUNT_ID}"
aws s3 mb s3://${BUCKET} --region ap-south-1
aws s3api put-public-access-block --bucket ${BUCKET} --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Create CloudFront OAC
OAC_ID=$(aws cloudfront create-origin-access-control --origin-access-control-config '{"Name":"dashboard-oac","SigningProtocol":"sigv4","SigningBehavior":"always","OriginAccessControlOriginType":"s3"}' --query 'OriginAccessControl.Id' --output text)

# Create CloudFront distribution (replace BUCKET and OAC_ID)
# Then add bucket policy allowing only CloudFront to read
```

### 9. Test

```bash
cd ~/dev-sandbox
source .venv/bin/activate
export AWS_DEFAULT_REGION=us-east-1
python run_intraday.py --force   # Should scan NSE + call Bedrock
python run_fno.py --force        # Should fetch option chains + call Bedrock
```

### 10. Go Live

Change in `config/config.yaml`:
```yaml
intraday:
  broker: "dhan"
  # Remove --force from run_daily.sh (let it respect market hours)

fno:
  mode: "live"   # Change from "paper" to "live"
```

Add ₹1.5 Lakh to your Dhan account. Done.

## Monthly Cost Summary

| Item | Cost |
|------|------|
| EC2 t3.small (24/7) | ₹1,260 |
| Bedrock (~4 calls/day × 22 days) | ₹450 |
| S3 + CloudFront | ₹100 |
| **Total** | **₹1,810/month** |

Expected earnings: ₹2,000-5,000/day × 22 days = ₹44,000-110,000/month

## Notes

- EC2 must be in Mumbai (ap-south-1) — NSE blocks non-Indian IPs
- Bedrock must be in us-east-1 (Claude Sonnet availability)
- Keep the GitHub repo private — it has your broker config
- Rotate Dhan API keys every 90 days
