from flask import Flask, send_file, request, abort, jsonify
from twilio.rest import Client
from services.geocoding import reverse_geocode
from services.pdf_generator import generate_pdf
import secrets
import time
import os
# from dotenv import load_dotenv

# load_dotenv('details.env')

# ── Config ─────────────────────────────────────────────────────────────────────
BASE_URL    = os.getenv("BASE_URL")
account_sid = os.getenv("account_sid")
auth_token  = os.getenv("auth_token")
API_KEY     = os.getenv("API_KEY")
TOKEN_EXPIRY_SECONDS = 300  # PDF link valid for 5 minutes

client = Client(account_sid, auth_token)
app    = Flask(__name__)

# ── In-memory stores ───────────────────────────────────────────────────────────
joined_users = set()   # WhatsApp numbers that sent START
TOKENS = {}            # { token: { "expires": float, "pdf_path": str } }


@app.before_request
def log_request():
    print("Incoming request:", request.path)
# ══════════════════════════════════════════════════════════════════════════════
# index route for cron job  
@app.route("/")
def index():
    return {"status": "ok"}, 200

# ══════════════════════════════════════════════════════════════════════════════
# SECURITY — Protect /trigger-alert with API key from React Native
# ══════════════════════════════════════════════════════════════════════════════
@app.before_request
def check_api_key():
    if request.path == '/trigger-alert':
        key = request.headers.get("X-API-Key")
        if key != API_KEY:
            return jsonify({"error": "Unauthorized"}), 401


# ══════════════════════════════════════════════════════════════════════════════
# WHATSAPP WEBHOOK
# Doctors message this number to enroll/unenroll.
# START  → add to alert list
# CANCEL → remove from alert list
# HELP   → usage info
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/whatsapp", methods=["POST"])
def whatsapp_webhook():
    from_number = request.form.get("From")
    body = request.form.get("Body", "").strip().lower()

    if body == "start":
        joined_users.add(from_number)
        client.messages.create(
            from_="whatsapp:" + os.getenv("from_number_whatsapp"),
            to=from_number,
            body=(
                "Welcome to the Medical Alert System!\n"
                "You have been successfully enrolled in the Medical Alert System.\n\n"
                "Important Information:\n"
                "* This system is intended to deliver critical patient health alerts only.\n"
                "* Access to shared reports is restricted to authorized recipients only. "
                "Please do not forward report links.\n"
                "* This system is intended to support clinical decision-making and does "
                "not replace professional medical judgment.\n"
                "* In the event of a medical emergency, local emergency response protocols "
                "should be followed immediately.\n\n"
                "Type *Help* for more information on how to use this service.\n\n"
                "*By continuing to use this service, you acknowledge and accept "
                "these conditions.*"
            )
        )

    elif body == "cancel":
        joined_users.discard(from_number)
        client.messages.create(
            from_="whatsapp:" + os.getenv("from_number_whatsapp"),
            to=from_number,
            body=(
                "You have been successfully unsubscribed from the Medical Alert System.\n\n"
                "You will no longer receive automated medical alerts through this "
                "WhatsApp service.\n\n"
                "If this action was taken in error, you may re-enroll at any time "
                "by sending *START*.\n\n"
                "For urgent medical situations, follow standard institutional emergency "
                "response procedures."
            )
        )

    elif body == "help":
        client.messages.create(
            from_="whatsapp:" + os.getenv("from_number_whatsapp"),
            to=from_number,
            body=(
                "Medical Alert System - Help Information\n\n"
                "This system provides automated notifications for critical patient "
                "health events, including secure access to diagnostic reports and "
                "emergency voice alerts.\n\n"
                "System Commands:\n"
                "* START  - Enroll and receive medical alerts\n"
                "* CANCEL - Unsubscribe from medical alerts\n"
                "* HELP   - Display this help information\n"
                "* STOP   - Exit the WhatsApp service\n\n"
                "Additional Information:\n"
                "* Alerts are generated automatically based on detected abnormal "
                "health activity.\n"
                "* Shared medical reports are protected by secure, time-limited "
                "access links.\n"
                "* This system is intended to support clinical workflows and does "
                "not replace professional medical judgment.\n\n"
                "For medical emergencies, follow standard institutional emergency "
                "response procedures."
            )
        )

    return "", 200


# ══════════════════════════════════════════════════════════════════════════════
# PDF SERVE — Secure one-time token access
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/pdf")
def serve_pdf():
    token = request.args.get("token")

    if not token or token not in TOKENS:
        abort(403)

    if TOKENS[token]["expires"] < time.time():
        del TOKENS[token]
        abort(403)

    pdf_path = TOKENS[token]["pdf_path"]
    del TOKENS[token]  # One-time use — invalidate immediately after access

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name="ecg_report.pdf"
    )


# ══════════════════════════════════════════════════════════════════════════════
# MAIN ALERT ENDPOINT — Called by React Native when model fires an alert
#
# Expected JSON body:
# {
#   "patient": {
#     "name": "John Doe",
#     "age": 58,
#     "user_name": "johndoe",
#     "device_name": "AD8232 + ESP32"
#   },
#   "prediction": {
#     "condition":    "Arrhythmia",
#     "severity":     "High",
#     "confidence":   0.94,
#     "heart_rate":   112,
#     "rhythm_class": "A"
#   },
#   "location": {
#     "lat": 10.0261,
#     "lng": 76.3083
#   },
#   "ecg_snapshot": [0.12, -0.34, 0.87, ...]
# }
# ══════════════════════════════════════════════════════════════════════════════
@app.route("/trigger-alert", methods=["POST"])
def trigger_alert():
    data = request.get_json()

    patient    = data["patient"]
    prediction = data["prediction"]
    location   = data["location"]
    ecg_data   = data["ecg_snapshot"]
    model_name = data["model_name"]
    name      = patient["name"]
    condition = prediction["condition"]
    severity  = prediction["severity"]

    # Step 1 — Reverse geocode lat/lng → human address + Maps link
    location_info = reverse_geocode(location["lat"], location["lng"])
    address   = location_info["address"]
    maps_link = location_info["maps_link"]

    # Format pincode digits for TTS (prevents "6 lakh eighty one thousand...")
    postcode_tts = " ".join(list(str(location_info.get("postcode", ""))))

    # Step 2 — Generate PDF (no location inside — doctors don't need it)
    pdf_path, pdf_filename = generate_pdf(
        patient    = patient,
        prediction = prediction,
        ecg_data   = ecg_data,
        model_name = model_name
    )

    # Step 3 — Secure one-time token for PDF
    token = secrets.token_urlsafe(32)
    TOKENS[token] = {
        "expires":  time.time() + TOKEN_EXPIRY_SECONDS,
        "pdf_path": pdf_path
    }
    pdf_url = f"{BASE_URL}/pdf?token={token}"

    results = {}

    # Step 4 — WhatsApp to DOCTORS
    # Contains: patient details + secure PDF link. No location (they are remote).
    if joined_users:
        to_whatsapp = list(joined_users)[-1]
        wa_msg = (
            f"*MEDICAL ALERT - Cardiac Event Detected*\n\n"
            f"*Patient:*    {name}\n"
            f"*Age:*        {patient.get('age', 'N/A')}\n"
            f"*Condition:*  {condition}\n"
            f"*Severity:*   {severity}\n"
            f"*Confidence:* {prediction.get('confidence', 0) * 100:.1f}%\n"
            f"*Heart Rate:* {prediction.get('heart_rate', 'N/A')} bpm\n\n"
            f"_This is an automated alert. Clinical correlation is required._"
        )
        wa = client.messages.create(
            from_="whatsapp:" + os.getenv("from_number_whatsapp"),
            to=to_whatsapp,
            body=wa_msg,
            media_url=[pdf_url]
        )
        results["whatsapp_sid"] = wa.sid
    else:
        results["whatsapp_sid"] = "No WhatsApp users currently enrolled"

    # Step 5 — Voice call to RELATIVES / AMBULANCE
    # Reads name, condition, severity, and structured address aloud.
    twiml = f"""
    <Response>
        <Say voice="alice" language="en-IN">
            Attention. This is an automated medical alert.
            Abnormal cardiac activity has been detected and immediate attention is required.
            <break time="0.5s"/>
            Patient Name: {name}.
            Detected Condition: {condition}.
            Severity Level: {severity}.
            <break time="0.5s"/>
            Patient Location: {location_info.get('road', '')}, {location_info.get('suburb', '')},
            {location_info.get('city', '')}, {location_info.get('state', '')}.
            Pincode: {postcode_tts}.
            <break time="0.5s"/>
            Please contact emergency services immediately and proceed to the patient location.
            This is an automated message. Please do not reply to this call.
        </Say>
    </Response>
    """
    call = client.calls.create(
        twiml=twiml,
        to=os.getenv("to_number"),
        from_=os.getenv("from_number"),
    )
    results["call_sid"] = call.sid

    # Step 6 — SMS to RELATIVES / AMBULANCE
    # Contains: name, condition, severity, address, and clickable Maps link.
    sms = client.messages.create(
        from_=os.getenv("from_number"),
        to=os.getenv("to_number"),
        body=(
            f"MEDICAL ALERT: Cardiac event detected.\n"
            f"Patient: {name} | Age: {patient.get('age', 'N/A')}\n"
            f"Condition: {condition} | Severity: {severity}\n"
            f"Location: {address[:120]}\n"
            f"Navigate: {maps_link}\n"
            f"Please seek immediate medical assistance."
        )
    )
    results["sms_sid"] = sms.sid

    return jsonify({
        "status":   "Alert sent successfully",
        "pdf_url":  pdf_url,
        "location": location_info,
        **results
    }), 200

@app.route("/test", methods=["POST"])
def trigger_alert1():
    data = request.get_json()

    patient    = data["patient"]
    prediction = data["prediction"]
    location   = data["location"]
    ecg_data   = data["ecg_snapshot"]
    model_name = data["model_name"]
    name      = patient["name"]
    condition = prediction["condition"]
    severity  = prediction["severity"]

    

    return jsonify({
        "status":   "Alert sent successfully",
        "patient": name,
        "condition": condition,
        "severity": severity,
        "ecg_data": ecg_data,
        "location": location,
        "prediction": prediction
    }), 200

if __name__ == "__main__":
    app.run(port=5000, debug=True)