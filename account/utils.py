from django.utils import timezone
import secrets
from .models import OtpToken
from rest_framework.exceptions import ValidationError
from django.utils.timezone import now
from decimal import Decimal
from user_wallet.models import WalletTransaction

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
def send_email(data, is_html=False):
    """
    Send email as plain text by default, or as HTML if is_html=True.

    Args:
        data: dict with keys 'subject', 'body', 'to_email'
        is_html: bool, default False; if True send HTML email
    """
    try:
        email = EmailMessage(
            subject=data['subject'],
            body=data['body'],
            # from_email=settings.DEFAULT_FROM_EMAIL,
            to=[data['to_email']]
        )
        if is_html:
            email.content_subtype = "html"  # Send as HTML

        email.send()
        return True
    except Exception as e:
        print(str(e))
        return False
    
def get_display_label(value, choices):
    for key, label in choices:
        if key == value:
            return label
    return value
    
def generate_transaction_email_body_html(
    transaction_id: str, customer_name: str, transaction_type: str,
    amount, current_balance, payment_method: str,
    date_of_transaction: str,
    processed_by_name: str,processed_by_email: str, processed_by_phone: str
) -> str:
    """
    Generates an HTML email body for a completed wallet transaction.
    """
    # Ensure amount and balance are float or Decimal before formatting
    try:
        transaction_type = get_display_label(transaction_type, WalletTransaction.TRANSACTION_TYPE_CHOICES)
        payment_method = get_display_label(payment_method, WalletTransaction.PAYMENT_METHOD_CHOICES)
        amount = float(amount)
        if not date_of_transaction:
            date_of_transaction = now().date()
    except (ValueError, TypeError):
        amount = 0.0

    try:
        current_balance = float(current_balance)
    except (ValueError, TypeError):
        current_balance = 0.0

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; font-size: 14px; color: #333;">
        <p>Dear {customer_name},</p>

        <p>
            We would like to inform you that a <strong>{transaction_type}</strong> transaction has been successfully completed on your wallet account.
        </p>

        <h4 style="margin-bottom: 10px;">Transaction Details:</h4>
        <ul style="margin-top: 0;">
            <li><strong>Transaction ID:</strong> {transaction_id}</li>
            <li><strong>Amount:</strong> {float(amount):.2f}</li>
            <li><strong>Transaction Type:</strong> {transaction_type}</li>
            <li><strong>Payment Method:</strong> {payment_method}</li>
            <li><strong>Date of Transaction:</strong> {date_of_transaction}</li>
            
        </ul>

        <!-- Centered Gray Box for Wallet Balance -->
        <div style="background-color: #f0f0f0; padding: 20px; margin: 30px auto; text-align: center; border-radius: 8px; width: 50%;">
            <span style="font-size: 24px; font-weight: bold; color: #000;">
                Current Wallet Balance: {float(current_balance):.2f}
            </span>
        </div>

        <p>
            If this transaction was not authorized by you, please contact our support team immediately.
        </p>


        <!-- Signature section, avoid Gmail trimming -->
        <div style="margin-top: 30px; padding: 15px; border-top: 1px solid #ccc; background-color: #fafafa;">
            <p style="margin: 0; font-weight: 600; color: #222;">We’re here to help you anytime.</p>
            <p style="margin: 8px 0 0 0; color: #444;">
                Processed By: <strong>{processed_by_name}</strong><br>
                Email: <a href="mailto:{processed_by_email}" style="color: #2a7ae2;">{processed_by_email}</a><br>
                Phone: <a href="tel:{processed_by_phone}" style="color: #2a7ae2;">{processed_by_phone}</a>
            </p>
        </div>
    </body>
    </html>
    """

