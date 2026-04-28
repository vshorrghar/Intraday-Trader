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
