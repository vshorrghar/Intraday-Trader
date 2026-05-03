---
inclusion: auto
---

# AWS Credentials — Always Unset Before Re-setting

When running any AWS CLI command or testing AWS credentials with the `vishal-admin` profile, ALWAYS unset all AWS environment variables first, then re-set them:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN AWS_PROFILE AWS_DEFAULT_REGION
export AWS_PROFILE=vishal-admin
export AWS_DEFAULT_REGION=us-east-1
```

This prevents stale env vars from overriding the credentials file. Apply this pattern in shell scripts and before any `aws` CLI calls.

# CRITICAL: Never Git Push from MacBook

NEVER run `git push` from the MacBook. Code Defender (Palisade) monitors all git operations on the corporate laptop and will:
- Block the push
- Send an alert email to the user's manager
- Flag the repository

Always push from EC2 instead:
1. SCP files to EC2: `scp -i ~/Downloads/wealth-builder-pro.pem <file> ec2-user@13.206.144.6:~/dev-sandbox/`
2. SSH to EC2 and run `git add`, `git commit`, `git push` there

The EC2 does NOT have Code Defender installed.
