#!/usr/bin/env python3
"""Quick AWS account resource scanner.

Scans the current AWS account for active resources across common services
and prints a summary. Uses your current AWS credentials.
"""

import json
import sys
from datetime import datetime, timedelta

import boto3
from botocore.exceptions import ClientError, NoCredentialsError


def get_session_info():
    """Get current AWS identity."""
    sts = boto3.client("sts")
    identity = sts.get_caller_identity()
    return {
        "Account": identity["Account"],
        "UserId": identity["UserId"],
        "Arn": identity["Arn"],
    }


def scan_ec2(region):
    """Scan EC2 instances."""
    ec2 = boto3.client("ec2", region_name=region)
    instances = []
    try:
        resp = ec2.describe_instances()
        for res in resp["Reservations"]:
            for inst in res["Instances"]:
                name = ""
                for tag in inst.get("Tags", []):
                    if tag["Key"] == "Name":
                        name = tag["Value"]
                instances.append({
                    "InstanceId": inst["InstanceId"],
                    "Name": name,
                    "Type": inst["InstanceType"],
                    "State": inst["State"]["Name"],
                    "LaunchTime": inst.get("LaunchTime", "").isoformat() if inst.get("LaunchTime") else "",
                })
    except ClientError as e:
        instances.append({"error": str(e)})
    return instances


def scan_s3():
    """Scan S3 buckets."""
    s3 = boto3.client("s3")
    buckets = []
    try:
        resp = s3.list_buckets()
        for b in resp.get("Buckets", []):
            buckets.append({
                "Name": b["Name"],
                "Created": b["CreationDate"].isoformat() if b.get("CreationDate") else "",
            })
    except ClientError as e:
        buckets.append({"error": str(e)})
    return buckets


def scan_rds(region):
    """Scan RDS instances."""
    rds = boto3.client("rds", region_name=region)
    dbs = []
    try:
        resp = rds.describe_db_instances()
        for db in resp["DBInstances"]:
            dbs.append({
                "DBInstanceId": db["DBInstanceIdentifier"],
                "Engine": db["Engine"],
                "Class": db["DBInstanceClass"],
                "Status": db["DBInstanceStatus"],
                "Storage": f"{db.get('AllocatedStorage', '?')} GB",
            })
    except ClientError as e:
        dbs.append({"error": str(e)})
    return dbs


def scan_lambda(region):
    """Scan Lambda functions."""
    lam = boto3.client("lambda", region_name=region)
    functions = []
    try:
        resp = lam.list_functions()
        for fn in resp.get("Functions", []):
            functions.append({
                "Name": fn["FunctionName"],
                "Runtime": fn.get("Runtime", "N/A"),
                "Memory": f"{fn.get('MemorySize', '?')} MB",
                "LastModified": fn.get("LastModified", ""),
            })
    except ClientError as e:
        functions.append({"error": str(e)})
    return functions


def scan_dynamodb(region):
    """Scan DynamoDB tables."""
    ddb = boto3.client("dynamodb", region_name=region)
    tables = []
    try:
        resp = ddb.list_tables()
        for name in resp.get("TableNames", []):
            tables.append({"TableName": name})
    except ClientError as e:
        tables.append({"error": str(e)})
    return tables


def scan_cloudformation(region):
    """Scan CloudFormation stacks."""
    cfn = boto3.client("cloudformation", region_name=region)
    stacks = []
    try:
        resp = cfn.list_stacks(StackStatusFilter=[
            "CREATE_COMPLETE", "UPDATE_COMPLETE", "ROLLBACK_COMPLETE",
        ])
        for s in resp.get("StackSummaries", []):
            stacks.append({
                "StackName": s["StackName"],
                "Status": s["StackStatus"],
                "Created": s.get("CreationTime", "").isoformat() if s.get("CreationTime") else "",
            })
    except ClientError as e:
        stacks.append({"error": str(e)})
    return stacks


def scan_ecs(region):
    """Scan ECS clusters."""
    ecs = boto3.client("ecs", region_name=region)
    clusters = []
    try:
        resp = ecs.list_clusters()
        for arn in resp.get("clusterArns", []):
            clusters.append({"ClusterArn": arn})
    except ClientError as e:
        clusters.append({"error": str(e)})
    return clusters


def scan_sqs(region):
    """Scan SQS queues."""
    sqs = boto3.client("sqs", region_name=region)
    queues = []
    try:
        resp = sqs.list_queues()
        for url in resp.get("QueueUrls", []):
            queues.append({"QueueUrl": url})
    except ClientError as e:
        queues.append({"error": str(e)})
    return queues


def get_cost_summary():
    """Get MTD cost from Cost Explorer."""
    ce = boto3.client("ce", region_name="us-east-1")
    now = datetime.utcnow()
    start = now.replace(day=1).strftime("%Y-%m-%d")
    end = now.strftime("%Y-%m-%d")
    try:
        resp = ce.get_cost_and_usage(
            TimePeriod={"Start": start, "End": end},
            Granularity="MONTHLY",
            Metrics=["BlendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        services = []
        for group in resp.get("ResultsByTime", [{}])[0].get("Groups", []):
            amount = float(group["Metrics"]["BlendedCost"]["Amount"])
            if amount > 0.001:
                services.append({
                    "Service": group["Keys"][0],
                    "Cost": f"${amount:.2f}",
                })
        services.sort(key=lambda x: float(x["Cost"].replace("$", "")), reverse=True)
        total = sum(
            float(g["Metrics"]["BlendedCost"]["Amount"])
            for g in resp.get("ResultsByTime", [{}])[0].get("Groups", [])
        )
        return {"total": f"${total:.2f}", "by_service": services}
    except ClientError as e:
        return {"error": str(e)}


def print_section(title, items, empty_msg="None found"):
    """Print a formatted section."""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")
    if not items:
        print(f"  {empty_msg}")
        return
    for item in items:
        if "error" in item:
            print(f"  ⚠️  Error: {item['error']}")
        else:
            parts = [f"{k}: {v}" for k, v in item.items() if v]
            print(f"  • {' | '.join(parts)}")


def main():
    region = "ap-south-1"  # Default region for your account

    print("\n🔍 AWS Account Resource Scanner")
    print("=" * 60)

    # Identity
    try:
        identity = get_session_info()
        print(f"  Account:  {identity['Account']}")
        print(f"  Identity: {identity['Arn']}")
        print(f"  Region:   {region}")
        print(f"  Scanned:  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
    except (NoCredentialsError, ClientError) as e:
        print(f"  ❌ Auth failed: {e}")
        sys.exit(1)

    # Cost
    print(f"\n{'='*60}")
    print("  💰 Month-to-Date Cost")
    print(f"{'='*60}")
    cost = get_cost_summary()
    if "error" in cost:
        print(f"  ⚠️  {cost['error']}")
    else:
        print(f"  Total MTD: {cost['total']}")
        for svc in cost.get("by_service", [])[:10]:
            print(f"    {svc['Service']}: {svc['Cost']}")

    # Resources
    print_section("🖥️  EC2 Instances", scan_ec2(region))
    print_section("🪣 S3 Buckets", scan_s3())
    print_section("🗄️  RDS Databases", scan_rds(region))
    print_section("⚡ Lambda Functions", scan_lambda(region))
    print_section("📊 DynamoDB Tables", scan_dynamodb(region))
    print_section("📦 CloudFormation Stacks", scan_cloudformation(region))
    print_section("🐳 ECS Clusters", scan_ecs(region))
    print_section("📬 SQS Queues", scan_sqs(region))

    print(f"\n{'='*60}")
    print("  ✅ Scan complete!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
