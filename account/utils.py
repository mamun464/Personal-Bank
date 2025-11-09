from django.utils import timezone
import secrets
from .models import OtpToken
from rest_framework.exceptions import ValidationError
from django.utils.timezone import now
from decimal import Decimal
from user_wallet.models import WalletTransaction
from django.core.mail import EmailMessage


@staticmethod
def calculate_progress(today_total, seven_day_sum):
    """
    Compare today's total with the last 7-day total (not average).
    """
    if seven_day_sum <= 0:
        return (False, 0)

    progress_percentage = ((today_total - seven_day_sum) / seven_day_sum) * 100
    progress = progress_percentage > 0
    # Allow negatives and positives, no capping at 100
    return (progress, round(progress_percentage, 2))




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
        <head>
            <style>
                .detail-left {{
                font-family: 'Times New Roman', Times, serif;
                width: 30%;
                padding: 4px 0;
                }}
                .detail-right {{
                font-family: 'Times New Roman', Times, serif;
                padding: 4px 0;
                }}
                body {{
                background-color: #e2e1e0;
                font-size: 100%;
                line-height: 1.4;
                color: #000;
                margin: 0;
                padding: 0;
                }}
                #container-table {{
                max-width: 670px;
                margin: 50px auto 10px;
                background-color: #fff;
                padding: 10px 25px;
                border-radius: 3px;
                box-shadow: 0 1px 3px rgba(0,0,0,.12), 0 1px 2px rgba(0,0,0,.24);
                border-top: solid 10px #4BB900;
                }}
                h3, h2 {{
                font-family: 'Times New Roman', Times, serif;
                color: #009900;
                margin: 0;
                padding: 0;
                }}
                .header-logo {{
                float: left;
                width: 13%;
                }}
                .header-text {{
                font-family: 'Times New Roman', Times, serif;
                float: right;
                color: #009900;
                margin-top: 15px;
                }}
                caption h2 {{
                margin: 3px 0;
                }}
                tfooter td {{
                font-family: 'Times New Roman', Times, serif;
                font-size: 14px;
                padding: 40px 15px 0 0;
                }}
                .footer-note {{
                text-align: center;
                color: #CF3E3E;
                padding-top: 20px;
                }}
            </style>
        </head>
        <body>
        <table id="container-table" bgcolor="#fff" cellpadding="0" cellspacing="0">
            <tbody>
            <tr>
                <td>
                <img src="https://i.ibb.co/ddKKKJ6/bank-logo.png" alt="bank_logo" class="header-logo">
                <p class="header-text">Personal Bank</p>
                </td>
            </tr>
            <tr>
                <td align="center" style="padding-top:30px;">
                <h3>Transaction Confirmation Receipt</h3>
                </td>
            </tr>
            <tr><td style="height:10px;"></td></tr>
            <tr>
                <td style="font-family: 'Times New Roman', Times, serif; line-height: 1.4;">
                <b>Dear {customer_name},</b><br><br>
                Thank you for banking with Personal Bank. Your transaction details are given below:
                </td>
            </tr>
            <tr>
                <td>
                <table style="margin-top:40px; width:100%; font-family: 'Times New Roman', Times, serif;" cellpadding="0" cellspacing="0">
                    <caption style="text-align:center; margin-bottom: 20px;">
                    <h2>Fund transfer details</h2>
                    </caption>
                    <tr>
                    <td class="detail-left">Transaction Date</td>
                    <td class="detail-right">: {date_of_transaction}</td>
                    </tr>
                    <tr>
                    <td class="detail-left">Transaction ID</td>
                    <td class="detail-right">: {transaction_id}</td>
                    </tr>
                    
                    <tr>
                    <td class="detail-left">Transaction Type</td>
                    <td class="detail-right">: {transaction_type}</td>
                    </tr>
                    <tr>
                    <td class="detail-left">Payment Method</td>
                    <td class="detail-right">: {payment_method}</td>
                    </tr>
                    
                    <tr>
                    <td class="detail-left">Transaction Amount</td>
                    <td class="detail-right">: {amount:.2f} TK</td>
                    </tr>
                    <tr>
                    <td class="detail-left"><b>Credit Balance</b></td>
                    <td class="detail-right">: <b>{current_balance:.2f} SR</b></td>
                    </tr>
                    <tr>
                    <td class="detail-left">Processed by</td>
                    <td class="detail-right">: {processed_by_name}, Email: {processed_by_email}, Phone: {processed_by_phone}</td>
                    </tr>
                </table>
                </td>
            </tr>
            <tfooter>
                <tr>
                <td colspan="2" style="font-family: 'Times New Roman', Times, serif; font-size: 14px; padding: 40px 15px 0 0;">
                    <b>Thank you for banking with us. Please feel free to contact us, if you need any further information.</b><br><br>
                    <b>Phone:</b> 4215 (Local) or 0410648754<br>
                    <b>Email:</b> help@bank.com<br>
                </td>
                </tr>
                <tr>
                <td class="footer-note" colspan="2">
                    <b>**This is a system generated receipt. No signature required**</b>
                </td>
                </tr>
            </tfooter>
            </tbody>
        </table>
        </body>
    </html>
    """


def generate_otp_email_body_html(
    customer_name: str,
    otp_code: str
) -> str:
    """
    Generates a mobile responsive OTP email body with bank logo and name.
    No button, just show OTP code nicely.
    """

    return f"""
    <html>
        <head>
            <style>
                /* Responsive styles */
                @media only screen and (max-width: 600px) {{
                .header-container {{
                    display: block !important;
                    text-align: center !important;
                }}
                .header-logo {{
                    width: 40% !important;
                    margin: 0 auto 10px auto !important;
                    float: none !important;
                    display: block !important;
                }}
                .header-text {{
                    float: none !important;
                    display: block !important;
                    margin: 0 auto !important;
                    font-size: 22px !important;
                }}
                #container-table {{
                    width: 95% !important;
                    margin: 20px auto !important;
                    padding: 10px 15px !important;
                }}
                body, td, p {{
                    font-size: 16px !important;
                }}
                }}

                body {{
                background-color: #e2e1e0;
                font-family: 'Times New Roman', Times, serif;
                font-size: 18px;
                line-height: 1.4;
                color: #000;
                margin: 0;
                padding: 0;
                }}

                #container-table {{
                max-width: 670px;
                margin: 50px auto 10px;
                background-color: #fff;
                padding: 20px 30px;
                border-radius: 5px;
                box-shadow: 0 1px 3px rgba(0,0,0,.12), 0 1px 2px rgba(0,0,0,.24);
                border-top: solid 10px #4BB900;
                }}

                .header-container {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 30px;
                }}

                .header-logo {{
                width: 13%;
                float: left;
                }}

                .header-text {{
                font-size: 26px;
                color: #009900;
                font-weight: bold;
                float: right;
                }}

                h2 {{
                color: #009900;
                margin-bottom: 25px;
                font-weight: normal;
                }}

                .otp-code {{
                font-size: 36px;
                font-weight: bold;
                color: #4BB900;
                text-align: center;
                letter-spacing: 6px;
                margin: 20px 0 35px 0;
                font-family: monospace, Courier New, monospace;
                }}

                p {{
                margin: 0 0 15px 0;
                }}

                .footer-note {{
                text-align: center;
                color: #CF3E3E;
                margin-top: 40px;
                font-size: 14px;
                }}

            </style>
        </head>
        <body>
        <table id="container-table" cellpadding="0" cellspacing="0" role="presentation">
            <tbody>
            <tr>
                <td>
                <div class="header-container">
                    <img src="https://i.ibb.co/ddKKKJ6/bank-logo.png" alt="bank_logo" class="header-logo" />
                    <p class="header-text">Personal Bank</p>
                </div>
                </td>
            </tr>
            <tr>
                <td>
                <h2>Dear {customer_name},</h2>
                <p>Use the following One-Time Password (OTP) to complete your transaction or login. This OTP is valid for <b>60 minutes</b>.</p>
                <div class="otp-code">{otp_code}</div>
                <p>If you did not request this, please ignore this email or contact support immediately.</p>
                <p>Thank you for banking with Personal Bank.</p>
                </td>
            </tr>
            <tr>
                <td class="footer-note">
                **This is an automated message, please do not reply.**
                </td>
            </tr>
            </tbody>
        </table>
        </body>
    </html>
    """

def generate_password_reset_email_html(
    customer_name: str,
    reset_link: str,
    expiry_hours: int = 60
) -> str:
    """
    Generates a mobile-responsive password reset email with a button and
    alternative clickable link.
    """

    return f"""
    <html>
        <head>
            <style>
                /* Responsive */
                @media only screen and (max-width: 600px) {{
                .header-container {{
                    display: block !important;
                    text-align: center !important;
                }}
                .header-logo {{
                    width: 40% !important;
                    margin: 0 auto 10px auto !important;
                    float: none !important;
                    display: block !important;
                }}
                .header-text {{
                    float: none !important;
                    display: block !important;
                    margin: 0 auto !important;
                    font-size: 22px !important;
                }}
                #container-table {{
                    width: 95% !important;
                    margin: 20px auto !important;
                    padding: 10px 15px !important;
                }}
                body, td, p {{
                    font-size: 16px !important;
                }}
                .btn {{
                    width: 100% !important;
                    box-sizing: border-box;
                }}
                }}

                body {{
                background-color: #e2e1e0;
                font-family: 'Times New Roman', Times, serif;
                font-size: 18px;
                line-height: 1.4;
                color: #000;
                margin: 0;
                padding: 0;
                }}

                #container-table {{
                max-width: 670px;
                margin: 50px auto 10px;
                background-color: #fff;
                padding: 20px 30px;
                border-radius: 5px;
                box-shadow: 0 1px 3px rgba(0,0,0,.12), 0 1px 2px rgba(0,0,0,.24);
                border-top: solid 10px #4BB900;
                }}

                .header-container {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 30px;
                }}

                .header-logo {{
                width: 13%;
                float: left;
                }}

                .header-text {{
                font-size: 26px;
                color: #009900;
                font-weight: bold;
                float: right;
                }}

                h2 {{
                color: #009900;
                margin-bottom: 25px;
                font-weight: normal;
                }}

                .btn {{
                display: inline-block;
                background-color: #4BB900;
                color: white !important;
                text-decoration: none;
                padding: 12px 25px;
                border-radius: 4px;
                font-size: 18px;
                font-weight: bold;
                text-align: center;
                cursor: pointer;
                margin: 25px 0 15px 0;
                }}

                .alt-link {{
                font-size: 14px;
                color: #333;
                word-break: break-all;
                }}

                .footer-note {{
                text-align: center;
                color: #CF3E3E;
                margin-top: 40px;
                font-size: 14px;
                }}

            </style>
        </head>
        <body>
            <table id="container-table" cellpadding="0" cellspacing="0" role="presentation">
                <tbody>
                <tr>
                    <td>
                    <div class="header-container">
                        <img src="https://i.ibb.co/ddKKKJ6/bank-logo.png" alt="bank_logo" class="header-logo" />
                        <p class="header-text">Personal Bank</p>
                    </div>
                    </td>
                </tr>
                <tr>
                    <td>
                    <h2>Dear {customer_name},</h2>
                    <p>You requested to reset your password. Please click the button below to set a new password. The link will expire in <b>{expiry_hours} hours</b>.</p>

                    <a href="{reset_link}" target="_blank" rel="noopener noreferrer" class="btn">Reset Password</a>

                    <p>If the button does not work, copy and paste the following link into your browser:</p>
                    <p class="alt-link"><a href="{reset_link}" target="_blank" rel="noopener noreferrer">{reset_link}</a></p>

                    <p>If you did not request this password reset, please ignore this email or contact support immediately.</p>

                    <p>Thank you for banking with Personal Bank.</p>
                    </td>
                </tr>
                <tr>
                    <td class="footer-note">
                    **This is an automated message, please do not reply.**
                    </td>
                </tr>
                </tbody>
            </table>
        </body>
    </html>
    """
