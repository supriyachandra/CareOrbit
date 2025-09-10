# app/utils/sms.py
import os
from twilio.rest import Client

# Load Twilio credentials from environment variables
ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
AUTH_TOKEN  = os.getenv("TWILIO_AUTH_TOKEN")
FROM_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Initialize Twilio client
_twilio = Client(ACCOUNT_SID, AUTH_TOKEN)

def send_appointment_sms(to_number: str,
                         patient_name: str,
                         doctor_name: str,
                         queue_no: str,
                         appt_time: str | None = None):
    """
    Send an appointment SMS and return the Message SID.
    """
    lines = [
        "CareOrbit Appointment",
        f"Patient: {patient_name}" if patient_name else None,
        f"Doctor: {doctor_name}",
        f"Queue No: {queue_no}",
        f"Time: {appt_time}" if appt_time else None,
        "— See you soon!"
    ]
    body = "\n".join([l for l in lines if l])

    msg = _twilio.messages.create(
        body=body,
        from_=FROM_NUMBER,
        to=to_number   # must be E.164 format, e.g. +9198xxxxxxx
    )
    return msg.sid
