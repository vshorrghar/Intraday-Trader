#!/bin/bash
cd /home/ec2-user/dev-sandbox
source .venv/bin/activate
export AWS_PROFILE=vishal-admin
PROFILE=$1
shift
.venv/bin/python run_swing.py --profile "$PROFILE" "$@"
