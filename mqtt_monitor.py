import ssl
import paho.mqtt.client as mqtt
import smtplib
from email.message import EmailMessage
import logging
import sqlite3
from datetime import datetime
import json
import atexit
import os
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("mqtt_alerts.log"),
        logging.StreamHandler()
    ]
)

EMAIL_ACTIVE = True # SET TO TRUE FOR ONLY ONE LISTENER (SET UP AS SERVICE ON MOSCA)

MQTT_BROKER = os.getenv("MQTT_BROKER")
MQTT_PORT = int(os.getenv("MQTT_PORT", 8883))  # fallback
MQTT_USERNAME = os.getenv("MQTT_USERNAME")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "#")
CA_CERT = "./mycert.crt"

EMAIL_SENDER = os.getenv("EMAIL_SENDER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER")
SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

def on_connect(client, userdata, flags, reasonCode, properties):
    if reasonCode == 0:
        print("Connected to broker.")
        client.subscribe(MQTT_TOPIC)
        print(f"Subscribed to topic: '{MQTT_TOPIC}'")
    else:
        print(f"Connection failed with code {reasonCode}")

def send_email_alert(subject, body):
    msg = EmailMessage()
    msg.set_content(body)
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER

    if isinstance(EMAIL_RECEIVER, str): # HANDLE SINGLE OR MULTIPLE ADDRESSES
        recipient_list = [EMAIL_RECEIVER]
    else:
        recipient_list = EMAIL_RECEIVER
    msg["To"] = ", ".join(recipient_list)

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
            logging.debug(f"Alert email sent successfully to {msg['To']}")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")

def on_message(client, userdata, msg):
    topic = msg.topic
    message = msg.payload.decode()
    timestamp = datetime.now().replace(microsecond=0).isoformat()
    station = topic.split("/")[0]

    print(f"{topic}\t{message}")

    if EMAIL_ACTIVE and "alerts" in topic.lower():
        subject = f"ALERT: Weather Station Message"
        body = f"Topic: {topic}\nMessage: {message}"
        send_email_alert(subject, body)

    if "/sensors" in topic:
        try:
            data = json.loads(message)    
            for key, value in data.items():
                if key == "time":
                    continue
                sensor_cursor.execute(
                    "INSERT INTO sensor_data (timestamp, station, field, value) VALUES (?, ?, ?, ?)",
                    (timestamp, station, key, str(value))
                )
            sensor_conn.commit()

        except json.JSONDecodeError:
            logging.warning(f"Non-JSON sensor message received: {message}")
            sensor_cursor.execute(
                "INSERT INTO sensor_data (timestamp, station, field, value) VALUES (?, ?, ?, ?)",
                (timestamp, station, "raw", message)
            )
            sensor_conn.commit()

    elif "alerts" in topic.lower():
        event_cursor.execute(
            "INSERT INTO alerts (timestamp, message) VALUES (?, ?)",
            (timestamp, message)
        )
        event_conn.commit()

    elif "/status/" in topic:
        event_cursor.execute(
            "INSERT INTO system_events (timestamp, station, message) VALUES (?, ?, ?)",
            (timestamp, station, message)
        )
        event_conn.commit()

def send_test_email():
    logging.info("Sending test email...")
    subject = "MQTT ALERT"
    body = "WE'RE IN BUSINESS"
    send_email_alert(subject, body)

def close_databases():
    sensor_conn.close()
    event_conn.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        send_test_email()

    else:
        sensor_conn = sqlite3.connect("sensor_data.db")
        sensor_cursor = sensor_conn.cursor()
        sensor_cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                station TEXT,
                field TEXT,
                value TEXT
            )
        ''')
        sensor_conn.commit()

        event_conn = sqlite3.connect("system_events.db")
        event_cursor = event_conn.cursor()
        event_cursor.execute('''
            CREATE TABLE IF NOT EXISTS system_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                station TEXT,
                message TEXT
            )
        ''')
        event_conn.commit()

        event_cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                station TEXT,
                message TEXT
            )
        ''')
        event_conn.commit()

        atexit.register(close_databases)

        client = mqtt.Client(client_id=f"opti", callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        client.tls_set(
            ca_certs=CA_CERT,
            certfile=None,
            keyfile=None,
            cert_reqs=ssl.CERT_REQUIRED,
            tls_version=ssl.PROTOCOL_TLS
        )

        client.on_connect = on_connect
        client.on_message = on_message

        try:
            client.connect(MQTT_BROKER, MQTT_PORT, 60)
            client.loop_forever()

        except Exception as e:
            print(f"Connection error: {e}")
