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


def create_response(
    message: str, 
    gather_action: str = None, 
    gather_prompt: str = None,
    input_type: str = 'speech',  # 'speech' or 'dtmf'
    num_digits: int = 1
) -> str:
    """
    Helper function to create TwiML responses.
    
    Args:
        message: The message to speak
        gather_action: The URL to send the gathered input to
        gather_prompt: The prompt to read before gathering input
        input_type: Type of input to gather ('speech' or 'dtmf')
        num_digits: Number of digits to collect (for DTMF)
    """
    response = VoiceResponse()
    
    def clean_text(text):
        if not text:
            return ""
        # Remove any non-printable characters except spaces and newlines
        return ''.join(char for char in str(text) if char.isprintable() or char in ' \n\r\t')
    
    try:
        if gather_action and gather_prompt:
            if input_type == 'dtmf':
                gather = Gather(
                    input='dtmf',
                    num_digits=num_digits,
                    action=gather_action,
                    method='POST',
                    timeout=10
                )
                gather.say(clean_text(gather_prompt), voice='Polly.Niamh', language='en-US')
                response.append(gather)
                # If no input, redirect to the same URL to loop the message
                response.redirect(gather_action)
            else:  # speech input
                gather = Gather(
                    input='speech',
                    action=gather_action,
                    method='POST',
                    speech_timeout='auto',
                    timeout=10
                )
                gather.say(clean_text(gather_prompt), voice='Polly.Niamh', language='en-US')
                response.append(gather)
                response.say("We didn't catch that. Goodbye!", voice='Polly.Niamh', language='en-US')
        else:
            response.say(clean_text(message), voice='Polly.Niamh', language='en-US')
        
        return str(response)
    except Exception as e:
        print(f"Error creating response: {str(e)}")
        error_response = VoiceResponse()
        error_response.say(
            "Thank you for calling. We're experiencing technical difficulties. Please try again later.",
            voice='Polly.Niamh',
            language='en-US'
        )
        return str(error_response)

def lambda_handler(event: dict, context) -> dict:
    path = event.get("rawPath") or event.get("path") or ""
    params = urllib.parse.parse_qs(event.get("body") or "")
    call_sid = params.get("CallSid", [None])[0] or str(uuid.uuid4())
    from_number = params.get("From", [""])[0]
    digits = params.get("Digits", [""])[0]  # For DTMF input

    def respond(twiml: str) -> dict:
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "text/xml"},
            "body": twiml
        }

    match path:
        case "/voice":
            # Initial call handler - ask user to press any key to continue
            try:
                TABLE.put_item(Item={"CallSid": call_sid, "From": from_number})
            except Exception as e:
                print(f"Error writing initial record: {e}")
            
            twiml = create_response(
                message="Thank you for calling AI pon A Time. ",
                gather_action=f"{BASE_URL}/welcome",
                gather_prompt="Please press any key to continue.",
                input_type='dtmf',
                num_digits=1
            )
            return respond(twiml)
            
        case "/welcome":
            # After user presses any key, proceed with the main menu
            twiml = create_response(
                message="Hi, welcome to AI pon A Time. ",
                gather_action=f"{BASE_URL}/gather_concern",
                gather_prompt="Please describe your issue or request after the beep.",
                input_type='speech'
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
