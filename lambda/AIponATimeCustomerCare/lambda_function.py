import os
import urllib.parse
import boto3
import uuid
from datetime import datetime, timezone
from twilio.twiml.voice_response import VoiceResponse

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


def create_response(message: str, gather_action: str = None, gather_prompt: str = None) -> str:
    """Helper function to create TwiML responses."""
    response = VoiceResponse()
    
    if gather_action and gather_prompt:
        gather = response.gather(
            input='speech',
            action=gather_action,
            method='POST',
            speech_timeout='auto'
        )
        gather.say(gather_prompt, voice='Polly.Niamh')
        response.say("We didn't catch that. Goodbye!", voice='Polly.Niamh')
    else:
        response.say(message, voice='Polly.Niamh')
    
    return str(response)

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

    match path:
        case "/voice":
            try:
                TABLE.put_item(Item={"CallSid": call_sid, "From": from_number})
            except Exception as e:
                print(f"Error writing initial record: {e}")
            
            twiml = create_response(
                "Hi, welcome to AI pon A Time. How can we assist you today?",
                gather_action=f"{BASE_URL}/gather_concern",
                gather_prompt="Please describe your issue or request after the beep."
            )
            return respond(twiml)

        case "/gather_concern":
            concern = params.get("SpeechResult", [""])[0]
            try:
                append_to_transcript(call_sid, f"Concern: {concern}")
            except Exception as e:
                print(f"Error appending concern: {e}")
            
            twiml = create_response(
                "Sure, our team will work on this and get back to you. "
                "Meanwhile, kindly provide your email ID.",
                gather_action=f"{BASE_URL}/gather_email",
                gather_prompt="Please say your email address now."
            )
            return respond(twiml)

        case "/gather_email":
            email = params.get("SpeechResult", [""])[0]
            try:
                append_to_transcript(call_sid, f"Email: {email}")
            except Exception as e:
                print(f"Error appending email: {e}")
            
            twiml = create_response("Thank you. Have a wonderful day!")
            return respond(twiml)

        case "/voice-fallback":
            twiml = create_response(
                "Sorry, we're experiencing technical difficulties. Please try again later."
            )
            return respond(twiml)

        case _:
            twiml = create_response(
                "Sorry, something went wrong. Please try again later."
            )
            return respond(twiml)
