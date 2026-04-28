"""AWS Cost Monitor - Track daily spending to keep bills in check.

Queries AWS Cost Explorer API to monitor spending by service.
Generates daily/weekly/monthly cost reports with alerts for unusual spikes.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class AWSCostMonitor:
    """Monitor AWS costs and generate spending reports."""

    def __init__(self, region: str = "us-east-1"):
        """Initialize Cost Explorer client.

        Note: Cost Explorer API is only available in us-east-1 region.

        Args:
            region: AWS region (Cost Explorer always uses us-east-1)
        """
        self.ce_client = boto3.client("ce", region_name="us-east-1")
        self.sts_client = boto3.client("sts", region_name=region)

        # Get account ID
        try:
            self.account_id = self.sts_client.get_caller_identity()["Account"]
        except Exception as e:
            logger.warning("Could not get account ID: %s", e)
            self.account_id = "unknown"

    def get_daily_costs(self, days: int = 7) -> Dict[str, float]:
        """Get daily costs for the last N days.

        Args:
            days: Number of days to retrieve (default 7)

        Returns:
            Dict mapping date (YYYY-MM-DD) to total cost in USD
        """
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        try:
            response = self.ce_client.get_cost_and_usage(
                TimePeriod={
                    "Start": start_date.strftime("%Y-%m-%d"),
                    "End": end_date.strftime("%Y-%m-%d"),
                },
                Granularity="DAILY",
                Metrics=["UnblendedCost"],
            )

            daily_costs = {}
            for result in response.get("ResultsByTime", []):
                date = result["TimePeriod"]["Start"]
                cost = float(result["Metrics"]["UnblendedCost"]["Amount"])
                daily_costs[date] = cost

            logger.info("Retrieved %d days of cost data", len(daily_costs))
            return daily_costs

        except ClientError as e:
            logger.error("Failed to get daily costs: %s", e)
            return {}

    def get_costs_by_service(self, days: int = 30) -> Dict[str, float]:
        """Get costs grouped by AWS service for the last N days.

        Args:
            days: Number of days to analyze (default 30)

        Returns:
            Dict mapping service name to total cost in USD
        """
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        try:
            response = self.ce_client.get_cost_and_usage(
                TimePeriod={
                    "Start": start_date.strftime("%Y-%m-%d"),
                    "End": end_date.strftime("%Y-%m-%d"),
                },
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
                GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
            )

            service_costs = {}
            for result in response.get("ResultsByTime", []):
                for group in result.get("Groups", []):
                    service = group["Keys"][0]
                    cost = float(group["Metrics"]["UnblendedCost"]["Amount"])

                    if service in service_costs:
                        service_costs[service] += cost
                    else:
                        service_costs[service] = cost

            # Sort by cost (highest first)
            service_costs = dict(sorted(service_costs.items(), key=lambda x: x[1], reverse=True))

            logger.info("Retrieved costs for %d services", len(service_costs))
            return service_costs

        except ClientError as e:
            logger.error("Failed to get costs by service: %s", e)
            return {}

    def get_month_to_date_cost(self) -> float:
        """Get total cost from start of current month to today.

        Returns:
            Total cost in USD for current month
        """
        today = datetime.now().date()
        first_day = today.replace(day=1)

        try:
            response = self.ce_client.get_cost_and_usage(
                TimePeriod={
                    "Start": first_day.strftime("%Y-%m-%d"),
                    "End": today.strftime("%Y-%m-%d"),
                },
                Granularity="MONTHLY",
                Metrics=["UnblendedCost"],
            )

            if response.get("ResultsByTime"):
                cost = float(response["ResultsByTime"][0]["Metrics"]["UnblendedCost"]["Amount"])
                logger.info("Month-to-date cost: $%.2f", cost)
                return cost

            return 0.0

        except ClientError as e:
            logger.error("Failed to get month-to-date cost: %s", e)
            return 0.0

    def get_forecast_month_end(self) -> float:
        """Get forecasted cost for end of current month.

        Returns:
            Forecasted total cost in USD for current month
        """
        today = datetime.now().date()
        first_day = today.replace(day=1)

        # Next month's first day
        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)

        try:
            response = self.ce_client.get_cost_forecast(
                TimePeriod={
                    "Start": first_day.strftime("%Y-%m-%d"),
                    "End": next_month.strftime("%Y-%m-%d"),
                },
                Metric="UNBLENDED_COST",
                Granularity="MONTHLY",
            )

            cost = float(response["Total"]["Amount"])
            logger.info("Forecasted month-end cost: $%.2f", cost)
            return cost

        except ClientError as e:
            logger.error("Failed to get cost forecast: %s", e)
            return 0.0

    def detect_cost_anomalies(self, days: int = 7, threshold_pct: float = 50.0) -> List[Dict]:
        """Detect unusual cost spikes compared to recent average.

        Args:
            days: Number of days to analyze
            threshold_pct: Percentage increase to flag as anomaly (default 50%)

        Returns:
            List of anomalies with date, cost, and increase %
        """
        daily_costs = self.get_daily_costs(days=days)

        if len(daily_costs) < 3:
            logger.warning("Not enough data to detect anomalies")
            return []

        dates = sorted(daily_costs.keys())
        costs = [daily_costs[d] for d in dates]

        # Calculate average of all but last day
        avg_cost = sum(costs[:-1]) / len(costs[:-1]) if len(costs) > 1 else costs[0]

        anomalies = []
        for i, date in enumerate(dates):
            cost = costs[i]

            if i > 0:  # Skip first day
                prev_avg = sum(costs[:i]) / i

                if prev_avg > 0:
                    increase_pct = ((cost / prev_avg) - 1) * 100

                    if increase_pct > threshold_pct:
                        anomalies.append({
                            "date": date,
                            "cost": cost,
                            "average": prev_avg,
                            "increase_pct": increase_pct,
                        })

        logger.info("Detected %d cost anomalies", len(anomalies))
        return anomalies

    def generate_cost_report(self, output_dir: str = "output/cost_reports") -> str:
        """Generate comprehensive cost report.

        Args:
            output_dir: Directory to save report

        Returns:
            Path to generated report file
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = output_path / f"aws_cost_report_{timestamp}.txt"

        # Gather all cost data
        daily_costs = self.get_daily_costs(days=7)
        service_costs = self.get_costs_by_service(days=30)
        mtd_cost = self.get_month_to_date_cost()
        forecast_cost = self.get_forecast_month_end()
        anomalies = self.detect_cost_anomalies(days=7)

        # Generate report
        with open(report_file, "w") as f:
            f.write("=" * 80 + "\n")
            f.write("AWS COST MONITORING REPORT\n")
            f.write(f"Account: {self.account_id}\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

            # Month-to-date summary
            f.write("📊 CURRENT MONTH SUMMARY\n")
            f.write("-" * 80 + "\n")
            f.write(f"Month-to-Date Cost:    ${mtd_cost:.2f}\n")
            f.write(f"Forecasted Month-End:  ${forecast_cost:.2f}\n")
            f.write(f"Days Remaining:        {self._days_left_in_month()}\n")
            f.write("\n\n")

            # Daily costs (last 7 days)
            f.write("📅 DAILY COSTS (Last 7 Days)\n")
            f.write("-" * 80 + "\n")
            if daily_costs:
                total_week = sum(daily_costs.values())
                avg_daily = total_week / len(daily_costs)

                for date in sorted(daily_costs.keys(), reverse=True):
                    cost = daily_costs[date]
                    f.write(f"{date}:  ${cost:>8.2f}\n")

                f.write("-" * 80 + "\n")
                f.write(f"Total (7 days):  ${total_week:.2f}\n")
                f.write(f"Average/day:     ${avg_daily:.2f}\n")
            else:
                f.write("No daily cost data available.\n")
            f.write("\n\n")

            # Costs by service (last 30 days)
            f.write("🔧 COSTS BY SERVICE (Last 30 Days)\n")
            f.write("-" * 80 + "\n")
            if service_costs:
                total_services = sum(service_costs.values())

                for service, cost in service_costs.items():
                    pct = (cost / total_services * 100) if total_services > 0 else 0
                    f.write(f"{service:<40}  ${cost:>8.2f}  ({pct:>5.1f}%)\n")

                f.write("-" * 80 + "\n")
                f.write(f"Total: ${total_services:.2f}\n")
            else:
                f.write("No service cost data available.\n")
            f.write("\n\n")

            # Cost anomalies
            if anomalies:
                f.write("🚨 COST ANOMALIES DETECTED\n")
                f.write("-" * 80 + "\n")
                for anomaly in anomalies:
                    f.write(f"{anomaly['date']}:  ${anomaly['cost']:.2f} ")
                    f.write(f"(+{anomaly['increase_pct']:.1f}% vs avg ${anomaly['average']:.2f})\n")
                f.write("\n")
            else:
                f.write("✅ No unusual cost spikes detected.\n\n")

            # Recommendations
            f.write("💡 COST OPTIMIZATION TIPS\n")
            f.write("-" * 80 + "\n")
            self._write_recommendations(f, service_costs, mtd_cost)

            f.write("\n" + "=" * 80 + "\n")
            f.write("END OF REPORT\n")
            f.write("=" * 80 + "\n")

        logger.info("Cost report generated: %s", report_file)
        return str(report_file)

    def _days_left_in_month(self) -> int:
        """Calculate days remaining in current month."""
        today = datetime.now().date()

        if today.month == 12:
            next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            next_month = today.replace(month=today.month + 1, day=1)

        return (next_month - today).days

    def _write_recommendations(self, f, service_costs: Dict[str, float], mtd_cost: float):
        """Write cost optimization recommendations to report."""
        # Check for high-cost services
        if service_costs:
            top_service = max(service_costs, key=service_costs.get)
            top_cost = service_costs[top_service]

            f.write(f"• Highest cost service: {top_service} (${top_cost:.2f})\n")

            # Bedrock-specific recommendations
            if "Bedrock" in top_service or "bedrock" in top_service.lower():
                f.write("  → Consider caching AI responses to reduce API calls\n")
                f.write("  → Use shorter prompts and lower max_tokens where possible\n")
                f.write("  → Batch analysis requests instead of individual calls\n")

            # EC2 recommendations
            if "EC2" in service_costs:
                f.write("• EC2 running 24/7 costs ~$30/month for t3.medium\n")
                f.write("  → Stop instance when not using to save ~$27/month\n")
                f.write("  → Consider Reserved Instances if running continuously\n")

            # S3 recommendations
            if "S3" in service_costs or "Simple Storage Service" in service_costs:
                f.write("• S3 storage costs accumulate over time\n")
                f.write("  → Enable lifecycle policies to move old data to Glacier\n")
                f.write("  → Delete temporary/cache files older than 30 days\n")

        # General recommendations
        f.write("• Review costs weekly to catch spikes early\n")
        f.write("• Set up AWS Budgets to get email alerts at $50, $100 thresholds\n")
        f.write("• Tag resources to track costs by project/environment\n")


def main():
    """Run cost monitoring and generate report."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 80)
    print("AWS COST MONITOR")
    print("=" * 80)
    print()

    try:
        monitor = AWSCostMonitor()

        print(f"📊 Monitoring AWS account: {monitor.account_id}")
        print()

        # Get current costs
        print("Fetching cost data...")
        mtd = monitor.get_month_to_date_cost()
        forecast = monitor.get_forecast_month_end()

        print(f"  ✅ Month-to-date: ${mtd:.2f}")
        print(f"  ✅ Forecast month-end: ${forecast:.2f}")
        print()

        # Generate full report
        print("Generating detailed report...")
        report_path = monitor.generate_cost_report()
        print(f"  ✅ Report saved: {report_path}")
        print()

        print("Done! Review the report for cost breakdown and optimization tips.")

    except Exception as e:
        logger.error("Cost monitoring failed: %s", e, exc_info=True)
        print(f"\n❌ Error: {e}")
        print("\nMake sure you have:")
        print("  1. Valid AWS credentials configured")
        print("  2. Cost Explorer API enabled in your account")
        print("  3. Permissions for ce:GetCostAndUsage and ce:GetCostForecast")
        return 1

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
