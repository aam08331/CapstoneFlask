import json
from flask import Blueprint, jsonify, request, current_app, render_template, redirect, url_for
import requests
import uuid
import threading
import time
import pandas as pd
from flask_mail import Message
from board.mail import mail
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
#from board import app
from flask import current_app

bp = Blueprint("pages", __name__)

scheduler = BackgroundScheduler()
scheduler.start()

emails = []

@bp.route("/")
def home():
    return render_template("pages/home.html")

@bp.route("/about")
def about():
    return render_template("pages/about.html")

# Store scraping jobs in memory (for demo)
SCRAPE_JOBS = {}

@bp.route("/start_scrape", methods=["POST"])
def start_scrape():
    job_id = str(uuid.uuid4())
    SCRAPE_JOBS[job_id] = {"status": "pending", "result": None, "error": None}

    thread = threading.Thread(target=run_scrape_job, args=(job_id,))
    thread.start()

    return jsonify({"job_id": job_id})

@bp.route("/scrape_status")
def scrape_status():
    job_id = request.args.get("job_id")
    if not job_id or job_id not in SCRAPE_JOBS:
        return jsonify({"error": "Invalid or missing job_id"}), 400

    job = SCRAPE_JOBS[job_id]
    return jsonify({
        "status": job["status"],
        "result": job["result"],
        "error": job["error"]
    })

def run_scrape_job(job_id):
    SCRAPE_JOBS[job_id]["status"] = "in progress"
    try:
        import selenium
        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        import pandas as pd

        # AchtBytes Login Credentials (REPLACE THESE)
        EMAIL = "vtn96492@uga.edu"
        PASSWORD = "Capstone25!"

        # Set up Chrome options and logging preferences
        chrome_options = Options()
        # Uncomment for headless mode if desired:
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--remote-debugging-port=9222")
        chrome_options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

        # Path to your ChromeDriver
        from selenium.webdriver.chrome.service import Service
        service = Service("/usr/local/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Open the login page
        driver.get("https://iot.achtbytes.com/copc/tenant")
        time.sleep(15)  # Wait for the page to load

        # Log in to AchtBytes
        driver.find_element(By.ID, "signInName").send_keys(EMAIL)
        driver.find_element(By.ID, "password").send_keys(PASSWORD + Keys.RETURN)
        time.sleep(15)  # Wait for login to complete

        # Click the assets button
        driver.find_element(By.ID, "nav-item-assets-overview").click()
        time.sleep(5)

        # XPath for online asset cards
        cards_xpath = "//a[contains(@class, 'overview-link') and .//span[text()='Online']]"

        cards = driver.find_elements(By.XPATH, cards_xpath)
        num_cards = len(cards)
        print(f"Found {num_cards} online asset card(s).")

        bearer_tokens = []
        telemetry_requests = {}

        for i in range(num_cards):
            try:
                card = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, f"({cards_xpath})[{i+1}]"))
                )
                card.click()
                print(f"\nClicked on card {i+1}/{num_cards}.")
                time.sleep(10)  # Allow time for network requests

                logs = driver.get_log("performance")
                for entry in logs:
                    log_entry = json.loads(entry["message"])["message"]
                    if log_entry.get("method") == "Network.requestWillBeSent":
                        request_data = log_entry.get("params", {}).get("request", {})
                        headers = request_data.get("headers", {})
                        url = request_data.get("url", "")
                        token = None
                        if "Authorization" in headers and "Bearer" in headers["Authorization"]:
                            token = headers["Authorization"].split("Bearer ")[1]
                            bearer_tokens.append(token)
                            print(f"🔑 Bearer Token Captured: {token}")
                        if "telemetry" in url and token:
                            telemetry_requests[url] = token
                            print(f"📡 Telemetry Request Captured: {url} → Token: {token}")

                print(f"✅ Captured {len(telemetry_requests)} Telemetry Requests so far.")
                print(f"✅ Captured {len(bearer_tokens)} Bearer Tokens so far.")

                driver.find_element(By.ID, "nav-item-assets-overview").click()
                time.sleep(5)

            except Exception as e:
                print(f"Error processing card {i+1}: {e}")

        time.sleep(10)
        driver.quit()

        # Optionally write CSVs (not required for functionality)
        if telemetry_requests:
            df_telemetry = pd.DataFrame(
                list(telemetry_requests.items()), 
                columns=["Telemetry URL", "Bearer Token"]
            )
            df_telemetry.to_csv("telemetry_requests.csv", index=False)
            print("\nTelemetry Requests saved to telemetry_requests.csv")
        else:
            print("\n❌ No telemetry requests captured.")

        if bearer_tokens:
            unique_tokens = list(set(bearer_tokens))
            df_tokens = pd.DataFrame(unique_tokens, columns=["Bearer Token"])
            df_tokens.to_csv("bearer_tokens.csv", index=False)
            print("\nBearer Tokens saved to bearer_tokens.csv")
        else:
            print("\n❌ No bearer tokens captured.")

        # ==========================
        # END SELENIUM SCRIPT CODE
        # ==========================

        # Now, use the telemetry_requests to fetch telemetry data
        telemetry_data = {}
        for url, token in telemetry_requests.items():
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(url, headers=headers)
            try:
                data = response.json()  # Assume API returns JSON
                telemetry_data[url] = data
            except Exception as e:
                telemetry_data[url] = {"error": str(e)}

        result_data = {
            "telemetry_requests": telemetry_requests,
            "unique_tokens": list(set(bearer_tokens)),
            "telemetry_data": telemetry_data  # New: telemetry data from API calls
        }

        SCRAPE_JOBS[job_id]["status"] = "complete"
        SCRAPE_JOBS[job_id]["result"] = result_data
    except Exception as e:
        SCRAPE_JOBS[job_id]["status"] = "error"
        SCRAPE_JOBS[job_id]["error"] = str(e)

@bp.route("/dashboard")
def dashboard():
    return render_template("pages/dashboard.html")

@bp.route("/carbon-emissions")
def carbon_emissions():
    return render_template("pages/carbon_emissions.html")

job = None

@bp.route('/subscribe', methods=['GET', 'POST'])
def subscribe():
    global job
    global emails
    if request.method == 'POST':
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        email = request.form.get('email')

        if not first_name or not last_name or not email:
            return render_template('pages/subscribe.html', error="All fields are required.")
        if(not email in emails):
            emails.append(email)
            # construct confirmation email 
            subject = "Subscription Confirmed"
            body = f"Hello {first_name},\n\nThank you for subscribing to the weekly reports from the Capstone - Traffic Monitoring Dashboard!"

            msg = Message(subject=subject, sender="capstonetestingtester@gmail.com", recipients=[email])
            msg.body = body
            if(not job):
                scheduler.add_job(
                        sendWeeklyUpdate, 
                        trigger=CronTrigger(day_of_week='sun', hour=0, minute=27),
                        args=[current_app._get_current_object(), email],
                        max_instances=1  
                )
                job = 1

            try:
                mail.send(msg)
                return render_template('pages/subscribe.html', success="You've been subscribed successfully!")
            except Exception as e:
                return render_template('pages/subscribe.html', error=f"Failed to send email: {str(e)}")
        else:
            return render_template('pages/subscribe.html', error="Email already set for subscription")
    # render empty form
    return render_template('pages/subscribe.html')

def sendWeeklyUpdate(app, email):
    with app.app_context():
        subject = "Weekly Progress Report"
        body = f"Weekly reports from the Capstone - Traffic Monitoring Dashboard!"

        msg = Message(subject=subject, sender="capstonetestingtester@gmail.com", recipients=[email])
        msg.body = body

        try:
            mail.send(msg)
            print("Weekly update sent")
        except Exception as e:
            print(f"Weekly update failed: {str(e)}")

@bp.route('/fetch-data', methods=['GET'])
def fetch_data():
    url = "https://testapi.io/api/aam08331/Testapi"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()  
        return jsonify(response.json())
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500
    
@bp.route('/send-data', methods=['POST'])
def send_data():
    url = "https://testapi.io/api/aam08331/Testapi"
    data = {"name": "John", "age": 30}

    try:
        response = requests.post(url, json=data, timeout=5)
        response.raise_for_status()
        return jsonify(response.json())
    except requests.exceptions.RequestException as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/carbon/<int:kiloWattHrs>', methods=['GET'])
def carbon(kiloWattHrs):
    # Constant
    tonToPounds = 2204.6

    # SRSO region
    actual = (3.94 * 10e-4)  * tonToPounds * kiloWattHrs

    return jsonify({"result": actual})

@bp.route('/send-email', methods=['POST'])
def send_email():
    data = request.get_json()
    recipient = data.get("recipient")
    subject = data.get("subject", "No Subject")
    body = data.get("body", "Hello, this is a test email!")

    if not recipient:
        return jsonify({"error": "Recipient email is required"}), 400

    msg = Message(subject=subject, sender="capstonetestingtester@gmail.com", recipients=[recipient])
    msg.body = body

    try:
        mail.send(msg)
        return jsonify({"message": "Email sent successfully!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    