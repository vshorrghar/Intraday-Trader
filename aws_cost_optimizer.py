#!/usr/bin/env python3
"""AWS Cost Anomaly Detector & Quick-Win Optimizer.

Scans your AWS account for cost anomalies, idle resources, and
quick optimization opportunities. Uses your current AWS credentials.

Usage: python aws_cost_optimizer.py
"""

import sys
from datetime import datetime, timedelta
from collections import defaultdict

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


REGION = "ap-south-1"
FINDINGS = []


def add_finding(severity, category, resource, message, savings=""):
    FINDINGS.append({
        "severity": severity,
        "category": category,
        "resource": resource,
        "message": message,
        "savings": savings,
    })


# ── Cost Anomaly Detection ───────────────────────────────────────────

def check_cost_anomalies():
    """Compare daily costs over last 14 days to detect spikes."""
    ce = boto3.client("ce", region_name="us-east-1")
    now = datetime.utcnow()
    start = (now - timedelta(days=14)).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")

    try:
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start, "End": end},
            Granularity="DAILY",
            Metrics=["BlendedCost"],
        )
        daily_costs = []
        for period in resp.get("ResultsByTime", []):
            cost = float(period["Total"]["BlendedCost"]["Amount"])
            date = period["TimePeriod"]["Start"]
            daily_costs.append((date, cost))

        if len(daily_costs) < 3:
            return daily_costs

        # Calculate average excluding last 2 days
        baseline = [c for _, c in daily_costs[:-2]]
        avg = sum(baseline) / len(baseline) if baseline else 0

        # Check last 2 days for spikes (>50% above average)
        for date, cost in daily_costs[-2:]:
            if avg > 0.01 and cost > avg * 1.5:
                add_finding(
                    "🔴 HIGH", "Cost Spike",
                    f"Daily cost on {date}",
                    f"${cost:.2f} vs ${avg:.2f} avg (>{(cost/avg - 1)*100:.0f}% above baseline)",
                    f"Investigate ${cost - avg:.2f}/day excess",
                )

        # Check for steady increase (last 3 days all above average)
        recent = [c for _, c in daily_costs[-3:]]
        if all(c > avg * 1.2 for c in recent) and avg > 0.01:
            add_finding(
                "🟡 MEDIUM", "Cost Trend",
                "Last 3 days",
                f"Costs trending up: avg ${sum(recent)/3:.2f}/day vs baseline ${avg:.2f}/day",
            )

        return daily_costs
    except ClientError as e:
        print(f"  ⚠️  Cost Explorer: {e}")
        return []


def check_cost_by_service():
    """Find top cost services and month-over-month changes."""
    ce = boto3.client("ce", region_name="us-east-1")
    now = datetime.utcnow()

    # This month
    this_start = now.replace(day=1).strftime("%Y-%m-%d")
    this_end = now.strftime("%Y-%m-%d")

    # Last month
    last_end = now.replace(day=1) - timedelta(days=1)
    last_start = last_end.replace(day=1).strftime("%Y-%m-%d")
    last_end_str = last_end.strftime("%Y-%m-%d")

    try:
        # This month by service
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": this_start, "End": this_end},
            Granularity="MONTHLY",
            Metrics=["BlendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        this_month = {}
        for group in resp.get("ResultsByTime", [{}])[0].get("Groups", []):
            svc = group["Keys"][0]
            cost = float(group["Metrics"]["BlendedCost"]["Amount"])
            if cost > 0.01:
                this_month[svc] = cost

        # Last month by service
        resp2 = ce.get_cost_and_usage(
            TimePeriod={"Start": last_start, "End": last_end_str},
            Granularity="MONTHLY",
            Metrics=["BlendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        last_month = {}
        for group in resp2.get("ResultsByTime", [{}])[0].get("Groups", []):
            svc = group["Keys"][0]
            cost = float(group["Metrics"]["BlendedCost"]["Amount"])
            if cost > 0.01:
                last_month[svc] = cost

        # Flag services with >30% increase
        for svc, cost in this_month.items():
            prev = last_month.get(svc, 0)
            if prev > 0.5 and cost > prev * 1.3:
                pct = (cost / prev - 1) * 100
                add_finding(
                    "🟡 MEDIUM", "Service Cost Increase",
                    svc,
                    f"${cost:.2f} this month vs ${prev:.2f} last month (+{pct:.0f}%)",
                    f"~${cost - prev:.2f}/month potential",
                )

        # Flag new services not in last month
        for svc, cost in this_month.items():
            if svc not in last_month and cost > 1.0:
                add_finding(
                    "🟡 MEDIUM", "New Service Cost",
                    svc,
                    f"${cost:.2f} — new service not present last month",
                )

        return this_month, last_month
    except ClientError as e:
        print(f"  ⚠️  Cost by service: {e}")
        return {}, {}


# ── Resource Optimization Checks ─────────────────────────────────────

def check_idle_ec2():
    """Find stopped EC2 instances (still incur EBS costs)."""
    ec2 = boto3.client("ec2", region_name=REGION)
    try:
        resp = ec2.describe_instances(
            Filters=[{"Name": "instance-state-name", "Values": ["stopped"]}]
        )
        for res in resp["Reservations"]:
            for inst in res["Instances"]:
                name = ""
                for tag in inst.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                add_finding(
                    "🟢 LOW", "Idle EC2",
                    f"{inst['InstanceId']} ({name or 'unnamed'})",
                    f"Stopped {inst['InstanceType']} — still paying for EBS volumes",
                    "Terminate if unused",
                )
    except ClientError:
        pass


def check_unattached_ebs():
    """Find EBS volumes not attached to any instance."""
    ec2 = boto3.client("ec2", region_name=REGION)
    try:
        resp = ec2.describe_volumes(
            Filters=[{"Name": "status", "Values": ["available"]}]
        )
        total_gb = 0
        for vol in resp["Volumes"]:
            size = vol["Size"]
            total_gb += size
            add_finding(
                "🟢 LOW", "Unattached EBS",
                f"{vol['VolumeId']} ({size} GB, {vol['VolumeType']})",
                "Volume not attached to any instance",
                f"~${size * 0.10:.2f}/month (gp3 pricing)",
            )
        if total_gb > 0:
            add_finding(
                "🟡 MEDIUM", "Unattached EBS Total",
                f"{total_gb} GB total unattached",
                f"Total unattached storage across all volumes",
                f"~${total_gb * 0.10:.2f}/month",
            )
    except ClientError:
        pass


def check_old_snapshots():
    """Find EBS snapshots older than 90 days."""
    ec2 = boto3.client("ec2", region_name=REGION)
    try:
        resp = ec2.describe_snapshots(OwnerIds=["self"])
        cutoff = datetime.utcnow() - timedelta(days=90)
        old_count = 0
        total_size = 0
        for snap in resp["Snapshots"]:
            if snap["StartTime"].replace(tzinfo=None) < cutoff:
                old_count += 1
                total_size += snap.get("VolumeSize", 0)
        if old_count > 0:
            add_finding(
                "🟢 LOW", "Old Snapshots",
                f"{old_count} snapshots older than 90 days ({total_size} GB)",
                "Review and delete unnecessary snapshots",
                f"~${total_size * 0.05:.2f}/month (snapshot pricing)",
            )
    except ClientError:
        pass


def check_elastic_ips():
    """Find unassociated Elastic IPs (charged when not attached)."""
    ec2 = boto3.client("ec2", region_name=REGION)
    try:
        resp = ec2.describe_addresses()
        for addr in resp["Addresses"]:
            if "InstanceId" not in addr and "NetworkInterfaceId" not in addr:
                add_finding(
                    "🟡 MEDIUM", "Unused Elastic IP",
                    addr["PublicIp"],
                    "Elastic IP not associated — charged $3.65/month since Feb 2024",
                    "$3.65/month",
                )
    except ClientError:
        pass


def check_idle_rds():
    """Find RDS instances that might be oversized or idle."""
    rds = boto3.client("rds", region_name=REGION)
    cw = boto3.client("cloudwatch", region_name=REGION)
    try:
        resp = rds.describe_db_instances()
        for db in resp["DBInstances"]:
            db_id = db["DBInstanceIdentifier"]
            # Check CPU utilization over last 7 days
            try:
                metrics = cw.get_metric_statistics(
                    Namespace="AWS/RDS",
                    MetricName="CPUUtilization",
                    Dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_id}],
                    StartTime=datetime.utcnow() - timedelta(days=7),
                    EndTime=datetime.utcnow(),
                    Period=86400,
                    Statistics=["Average"],
                )
                if metrics["Datapoints"]:
                    avg_cpu = sum(d["Average"] for d in metrics["Datapoints"]) / len(metrics["Datapoints"])
                    if avg_cpu < 5:
                        add_finding(
                            "🟡 MEDIUM", "Underutilized RDS",
                            f"{db_id} ({db['DBInstanceClass']})",
                            f"Avg CPU {avg_cpu:.1f}% over 7 days — consider downsizing",
                            "Downsize instance class",
                        )
            except ClientError:
                pass
    except ClientError:
        pass


def check_idle_load_balancers():
    """Find load balancers with zero healthy targets."""
    elbv2 = boto3.client("elbv2", region_name=REGION)
    try:
        resp = elbv2.describe_load_balancers()
        for lb in resp["LoadBalancers"]:
            lb_arn = lb["LoadBalancerArn"]
            lb_name = lb["LoadBalancerName"]
            # Check target groups
            tg_resp = elbv2.describe_target_groups(LoadBalancerArn=lb_arn)
            all_empty = True
            for tg in tg_resp["TargetGroups"]:
                health = elbv2.describe_target_health(TargetGroupArn=tg["TargetGroupArn"])
                if health["TargetHealthDescriptions"]:
                    all_empty = False
                    break
            if all_empty and tg_resp["TargetGroups"]:
                add_finding(
                    "🟡 MEDIUM", "Idle Load Balancer",
                    lb_name,
                    "ALB/NLB with no healthy targets — ~$16-22/month base cost",
                    "~$16-22/month",
                )
    except ClientError:
        pass


def check_nat_gateways():
    """Flag NAT Gateways — common cost surprise."""
    ec2 = boto3.client("ec2", region_name=REGION)
    try:
        resp = ec2.describe_nat_gateways(
            Filter=[{"Name": "state", "Values": ["available"]}]
        )
        count = len(resp.get("NatGateways", []))
        if count > 0:
            add_finding(
                "🟡 MEDIUM", "NAT Gateway Cost",
                f"{count} NAT Gateway(s) active",
                f"Each costs ~$32/month + data processing charges",
                f"~${count * 32}/month base",
            )
    except ClientError:
        pass


def check_s3_lifecycle():
    """Check S3 buckets without lifecycle policies."""
    s3 = boto3.client("s3")
    try:
        buckets = s3.list_buckets().get("Buckets", [])
        for b in buckets:
            name = b["Name"]
            try:
                s3.get_bucket_lifecycle_configuration(Bucket=name)
            except ClientError as e:
                if "NoSuchLifecycleConfiguration" in str(e):
                    add_finding(
                        "🟢 LOW", "S3 No Lifecycle",
                        name,
                        "No lifecycle policy — old objects never transition to cheaper storage",
                        "Add lifecycle rules for IA/Glacier transition",
                    )
    except ClientError:
        pass


def check_ec2_previous_gen():
    """Flag EC2 instances using previous-generation instance types."""
    ec2 = boto3.client("ec2", region_name=REGION)
    prev_gen = {"t2", "m4", "c4", "r4", "m3", "c3", "r3", "i2", "d2"}
    try:
        resp = ec2.describe_instances(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        )
        for res in resp["Reservations"]:
            for inst in res["Instances"]:
                itype = inst["InstanceType"]
                family = itype.split(".")[0]
                if family in prev_gen:
                    name = ""
                    for tag in inst.get("Tags", []):
                        if tag["Key"] == "Name":
                            name = tag["Value"]
                    add_finding(
                        "🟢 LOW", "Previous-Gen EC2",
                        f"{inst['InstanceId']} ({name or 'unnamed'})",
                        f"{itype} is previous-gen — newer types are cheaper & faster",
                        "Switch to t3/m5/c5/r5 equivalent",
                    )
    except ClientError:
        pass


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("\n🔍 AWS Cost Anomaly & Optimization Scanner")
    print("=" * 60)

    try:
        sts = boto3.client("sts")
        identity = sts.get_caller_identity()
        print(f"  Account:  {identity['Account']}")
        print(f"  Identity: {identity['Arn']}")
        print(f"  Region:   {REGION}")
        print(f"  Scanned:  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    except (NoCredentialsError, ClientError) as e:
        print(f"  ❌ Auth failed: {e}")
        sys.exit(1)

    print(f"\n{'─'*60}")
    print("  Analyzing costs...")
    daily = check_cost_anomalies()
    this_month, last_month = check_cost_by_service()

    if daily:
        print(f"\n  📊 Daily costs (last 14 days):")
        for date, cost in daily[-7:]:
            bar = "█" * int(min(cost * 2, 40))
            print(f"    {date}: ${cost:>8.2f} {bar}")

    if this_month:
        total = sum(this_month.values())
        print(f"\n  💰 MTD Total: ${total:.2f}")
        print(f"  Top services:")
        for svc, cost in sorted(this_month.items(), key=lambda x: -x[1])[:8]:
            print(f"    ${cost:>8.2f}  {svc}")

    print(f"\n{'─'*60}")
    print("  Scanning for optimization opportunities...")
    check_idle_ec2()
    check_unattached_ebs()
    check_old_snapshots()
    check_elastic_ips()
    check_idle_rds()
    check_idle_load_balancers()
    check_nat_gateways()
    check_s3_lifecycle()
    check_ec2_previous_gen()

    # Print findings
    print(f"\n{'='*60}")
    print(f"  📋 FINDINGS ({len(FINDINGS)} total)")
    print(f"{'='*60}")

    if not FINDINGS:
        print("  ✅ No issues found — your account looks clean!")
    else:
        by_severity = defaultdict(list)
        for f in FINDINGS:
            by_severity[f["severity"]].append(f)

        for sev in ["🔴 HIGH", "🟡 MEDIUM", "🟢 LOW"]:
            items = by_severity.get(sev, [])
            if not items:
                continue
            print(f"\n  {sev} ({len(items)})")
            print(f"  {'─'*56}")
            for f in items:
                print(f"  [{f['category']}] {f['resource']}")
                print(f"    → {f['message']}")
                if f["savings"]:
                    print(f"    💡 {f['savings']}")
                print()

    # Summary
    total_savings = 0
    for f in FINDINGS:
        s = f["savings"]
        if "$" in s:
            try:
                val = float(s.split("$")[1].split("/")[0])
                total_savings += val
            except (ValueError, IndexError):
                pass

    if total_savings > 0:
        print(f"  💰 Estimated potential savings: ~${total_savings:.2f}/month")

    print(f"\n{'='*60}")
    print("  ✅ Scan complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
