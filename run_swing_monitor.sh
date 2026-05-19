#!/bin/bash
cd /home/ec2-user/dev-sandbox
source .venv/bin/activate
export AWS_PROFILE=vishal-admin
PROFILE=$1
shift
.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
from swing.monitor import SwingMonitor
from swing.models import SwingConfig
import yaml
from pathlib import Path

profile_name = '$PROFILE'
profile_path = Path(f'config/profiles/{profile_name}.yaml')
if not profile_path.exists():
    print(f'Profile not found: {profile_path}')
    sys.exit(1)

with open(profile_path) as f:
    profile_data = yaml.safe_load(f)

config = SwingConfig.from_yaml(profile_data, profile_name)
monitor = SwingMonitor(config=config, broker=None, db=None)
monitor.run_monitor_cycle()
" "$@"
