#!/usr/bin/env python3

import subprocess
import smtplib
from email.message import EmailMessage
import logging
import os
import re
from dotenv import load_dotenv

load_dotenv(dotenv_path="/home/mpgetz/repos/mqtt_monitor/.env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("tunnel.log"), logging.StreamHandler()]
)

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

def send_email(subject, body):
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    recipient_list = [email.strip() for email in EMAIL_RECEIVER.split(",") if email.strip()]
    msg["To"] = ", ".join(recipient_list)
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            logging.info(f"Email sent to: {msg['To']}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

def start_cloudflared():
    logging.info("Starting cloudflared tunnel...")
    process = subprocess.Popen(
        ["cloudflared", "tunnel", "--url", "http://localhost:8000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Watch for the public URL
    public_url = None
    for line in iter(process.stdout.readline, ''):
        logging.info(line.strip())
        match = re.search(r"https://[a-zA-Z0-9\-]+\.trycloudflare\.com", line)
        if match:
            public_url = match.group(0)
            break

    if public_url:
        send_email(
            subject="Cloudflare Tunnel Started",
            body=f"BeeCam dashboard is available at:\n\n{public_url}"
        )
    else:
        logging.error("Tunnel started but no public URL was detected.")
        send_email("Cloudflare Tunnel FAILED", "Started tunnel, but no public URL was found.")

    # Let the tunnel keep running in background
    logging.info("Tunnel started. Letting process run in background.")

if __name__ == "__main__":
    start_cloudflared()
