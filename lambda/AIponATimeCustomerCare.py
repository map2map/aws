import os
import urllib.parse
import boto3
import uuid
from datetime import datetime, timezone

# DynamoDB table
DYNAMODB = boto3.resource("dynamodb")
TABLE = DYNAMODB.Table(os.environ["CUSTOMER_TABLE"])

BASE_URL = os.environ.get(
    "FUNCTION_URL",
    "https://efunxce4fimsccqw5fhgplrc5e0mrkdk.lambda-url.us-east-1.on.aws"
)


def append_to_transcript(call_sid: str, text: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    TABLE.update_item(
        Key={"CallSid": call_sid},
        UpdateExpression=(
            "SET Transcript = list_append("
            "if_not_exists(Transcript, :empty), :entry)"
        ),
        ExpressionAttributeValues={
            ":empty": [],
            ":entry": [{"Timestamp": timestamp, "Text": text}],
        },
    )


def lambda_handler(event: dict, context) -> dict:
    path = event.get("rawPath") or event.get("path") or ""
    params = urllib.parse.parse_qs(event.get("body") or "")
    call_sid = params.get("CallSid", [None])[0] or str(uuid.uuid4())
    from_number = params.get("From", [""])[0]

    def respond(twiml: str) -> dict:
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/xml"},
            "body": twiml
        }

    if path == "/voice":
        try:
            TABLE.put_item(Item={"CallSid": call_sid, "From": from_number})
        except Exception as e:
            print(f"Error writing initial record: {e}")

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Say voice="Polly.Niamh">'
            'Hi, welcome to AI pon A Time. How can we assist you today?'
            '</Say>'
            '<Gather input="speech" '
            f'action="{BASE_URL}/gather_concern" '
            'method="POST" speechTimeout="auto">'
            '<Say voice="Polly.Niamh">'
            'Please describe your issue or request after the beep.'
            '</Say>'
            '</Gather>'
            '<Say voice="Polly.Niamh">'
            'We didn\'t catch that. Goodbye!'
            '</Say>'
            '</Response>'
        )
        return respond(twiml)

    elif path == "/gather_concern":
        concern = params.get("SpeechResult", [""])[0]
        try:
            append_to_transcript(call_sid, f"Concern: {concern}")
        except Exception as e:
            print(f"Error appending concern: {e}")

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Say voice="Polly.Niamh">'
            'Sure, our team will work on this and get back to you. '
            'Meanwhile, kindly provide your email ID.'
            '</Say>'
            '<Gather input="speech" '
            f'action="{BASE_URL}/gather_email" '
            'method="POST" speechTimeout="auto">'
            '<Say voice="Polly.Niamh">'
            'Please say your email address now.'
            '</Say>'
            '</Gather>'
            '<Say voice="Polly.Niamh">'
            'We didn\'t receive your email. Thank you, have a wonderful day!'
            '</Say>'
            '</Response>'
        )
        return respond(twiml)

    elif path == "/gather_email":
        email = params.get("SpeechResult", [""])[0]
        try:
            append_to_transcript(call_sid, f"Email: {email}")
        except Exception as e:
            print(f"Error appending email: {e}")

        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Say voice="Polly.Niamh">'
            'Thank you. Have a wonderful day!'
            '</Say>'
            '</Response>'
        )
        return respond(twiml)

    elif path == "/voice-fallback":
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Say voice="Polly.Niamh">'
            "Sorry, we're experiencing technical difficulties. "
            'Please try again later.'
            '</Say>'
            '</Response>'
        )
        return respond(twiml)

    else:
        twiml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Say voice="Polly.Niamh">'
            'Sorry, something went wrong. Please try again later.'
            '</Say>'
            '</Response>'
        )
        return respond(twiml)
