from django.utils import timezone
import secrets
from .models import OtpToken
from rest_framework.exceptions import ValidationError

@staticmethod
def flattened_serializer_errors(serializer):
    """
    Collect all serializer error messages, join them into a single string,
    and raise a ValidationError with the combined message.
    """
    all_errors = []
    for field_errors in serializer.errors.values():
        if isinstance(field_errors, list):
            all_errors.extend(field_errors)
        else:
            all_errors.append(str(field_errors))
    
    # Join all messages into a single string separated by " | "
    error_message = " | ".join(all_errors)
    return error_message


def generate_unique_otp():
    """
    Generate a unique 6-digit OTP with minimal repetition.
    """
    MAX_REPEAT_TIMEDELTA = timezone.timedelta(minutes=10)  # Adjust as needed

    # Generate an initial OTP
    otp = secrets.randbelow(10**6)  # Generate a random 6-digit number
    otp_str = f"{otp:06d}"  # Convert to a 6-digit string

    # Check if the OTP already exists within the specified timeframe
    while OtpToken.objects.filter(otp_code=otp_str, otp_created_at__gte=timezone.now() - MAX_REPEAT_TIMEDELTA).exists():
        # If the OTP already exists, generate a new one
        otp = secrets.randbelow(10**6)
        otp_str = f"{otp:06d}"

    return otp_str

from django.core.mail import EmailMessage
# import os

@staticmethod
def send_email(data):
    try:
        email = EmailMessage (
            subject=data['subject'],
            body=data['body'],
            # from_email="mamun.kfz@gmail.com",
            to=[data['to_email']]
        )
        email.send()
        return True  # Return True if email sent successfully
    except Exception as e:
        print(str(e))
        return False  # Return False if email sending fails
