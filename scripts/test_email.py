#!/usr/bin/env python3
"""Quick test: send a test email via SES to verify the pipeline works."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from reports.ses_sender import send_email

SENDER = "vshorrghar@gmail.com"
RECIPIENT = "vshorrghar@gmail.com"
REGION = "ap-south-1"

html = """
<html><body style="font-family:sans-serif;padding:20px">
<h2 style="color:#16a34a">✅ Wealth Builder Pro — Test Email</h2>
<p>If you're reading this, SES email delivery is working.</p>
<table style="border-collapse:collapse;margin-top:10px">
<tr><td style="padding:6px 12px;background:#f0fdf4;font-weight:bold">Sender</td><td style="padding:6px 12px">vshorrghar@gmail.com</td></tr>
<tr><td style="padding:6px 12px;background:#f0fdf4;font-weight:bold">Region</td><td style="padding:6px 12px">ap-south-1</td></tr>
<tr><td style="padding:6px 12px;background:#f0fdf4;font-weight:bold">Status</td><td style="padding:6px 12px;color:#16a34a;font-weight:bold">🟢 Working</td></tr>
</table>
<p style="color:#64748b;font-size:12px;margin-top:20px">Sent from EC2 Mumbai by Wealth Builder Pro</p>
</body></html>
"""

print("📧 Sending test email...")
ok = send_email(html, "🧪 WBP Test Email", SENDER, RECIPIENT, REGION)
if ok:
    print("✅ Email sent! Check your inbox.")
else:
    print("❌ Email failed. Check SES config:")
    print("   1. Is vshorrghar@gmail.com verified in SES ap-south-1?")
    print("   2. Is SES still in sandbox mode? (sandbox = can only send to verified emails)")
    print("   3. Does the EC2 IAM role have ses:SendEmail permission?")
