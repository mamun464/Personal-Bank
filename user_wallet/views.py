from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from account.renderers import UserRenderer,UserRendererWithDecimal
from django.db import transaction
from user_wallet.models import Wallet,WalletTransaction
from account.models import User
from user_wallet.serializer import WalletTransactionSerializer,WalletTransactionListSerializer,WalletOverviewSerializer
from account.permissions import IsAuthorizedUser,IsNotCustomerSelf,TargetUserMustBeCustomer,AUTHORIZED_ROLES,IsUserVerifiedAndEnabled
from decimal import Decimal
import logging
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
import uuid
from account.utils import send_email,generate_transaction_email_body_html,calculate_progress
from django.utils.timezone import now, timedelta
from django.db.models.functions import ExtractMonth
from django.db.models import Sum
from collections import defaultdict
from datetime import datetime
from django.template.loader import render_to_string
from weasyprint import HTML, CSS
from django.utils.dateparse import parse_date
from django.http import HttpResponse
import tempfile
from datetime import date
from django.contrib.staticfiles import finders
import io
import base64
from barcode import Code128            
from barcode.writer import ImageWriter  
from django.conf import settings
import os



logger = logging.getLogger(__name__)


class SingleTransactionPDFView(APIView):
    """
    Generate PDF for a single transaction by transaction_id
    """
    permission_classes = [IsAuthenticated,IsUserVerifiedAndEnabled]
    authentication_classes = [JWTAuthentication]
    renderer_classes = [UserRenderer]
    def get(self, request):
        try:
            required_fields = ['transaction_id']
            for field in required_fields:
                if field not in request.query_params or not request.query_params[field]:
                    return Response({
                        'success': False,
                        'status': status.HTTP_400_BAD_REQUEST,
                        'message': f'{field} is missing or empty in the params',
                    }, status=status.HTTP_400_BAD_REQUEST)
            transaction_id = request.query_params.get('transaction_id')
            # Fetch transaction object
            transaction = WalletTransaction.objects.select_related("customer", "processed_by").get(transaction_id=transaction_id)

            user = request.user
            customer = transaction.customer

            if not (user.role in AUTHORIZED_ROLES or user.id == customer.id):
                return Response({
                    "success": False,
                    "status": status.HTTP_403_FORBIDDEN,
                    "message": "You are not authorized to download PDF for this transaction."
                }, status=status.HTTP_403_FORBIDDEN)
            
            # --- Generate barcode image as Base64 --- 🔹 NEW BLOCK
            buffer = io.BytesIO()
            Code128(transaction.transaction_id, writer=ImageWriter()).write(buffer)
            barcode_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            buffer.close()

            # Render HTML template
            html_string = render_to_string('transaction_details.html', {
                'transaction': transaction,
                "today": date.today(),
                "barcode_base64": barcode_base64,
                "generated_by": user.name if user.id != customer.id else f"{user.name} -(Self)",
               'STATIC_ROOT': str(settings.STATIC_ROOT),  # pass absolute path for images
            })

            # --- Prepare CSS path ---
            css_path = os.path.join(settings.STATIC_ROOT, "CSS", "transaction_receipt.css")
            if not os.path.exists(css_path):
                raise FileNotFoundError(f"CSS file not found: {css_path}")

            # --- Generate PDF ---
            html = HTML(string=html_string, base_url=str(settings.STATIC_ROOT))
            with tempfile.NamedTemporaryFile(delete=True) as tmpfile:
                html.write_pdf(
                    target=tmpfile.name,
                    stylesheets=[CSS(filename=css_path)]
                )
                tmpfile.seek(0)
                pdf_content = tmpfile.read()

            # --- Return PDF response ---
            response = HttpResponse(pdf_content, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="Transaction_{transaction.transaction_id}.pdf"'
            return response

        except WalletTransaction.DoesNotExist:
            return Response({
                "success": False,
                "status": status.HTTP_404_NOT_FOUND,
                "message": f"Transaction with id '{transaction_id}' does not exist."
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({
                "success": False,
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": f"An error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
class GenerateStatementPdfAPIView(APIView):
    permission_classes = [IsAuthenticated,IsUserVerifiedAndEnabled]
    authentication_classes = [JWTAuthentication]
    renderer_classes = [UserRenderer]
    def get(self, request, *args, **kwargs):
        show_all_customers = False
        try:
            user = request.user
            customer_id = request.GET.get("customer")
            start_date = request.GET.get("start_date")
            end_date = request.GET.get("end_date")
            css_path = finders.find("CSS/statement_templates.css")
            required_fields = ['start_date', 'end_date']
            for field in required_fields:
                if field not in request.query_params or not request.query_params[field]:
                    return Response({
                        'success': False,
                        'status': status.HTTP_400_BAD_REQUEST,
                        'message': f'{field} is missing or empty in the params',
                    }, status=status.HTTP_400_BAD_REQUEST)

            start_date_parsed = parse_date(start_date)
            end_date_parsed = parse_date(end_date)

            if end_date_parsed < start_date_parsed:
                return Response({
                    'success': False,
                    'status': status.HTTP_400_BAD_REQUEST,
                    'message': 'End date cannot be before the start date.'
                }, status=status.HTTP_400_BAD_REQUEST)
    

            # --- Build queryset based on role ---
            transactions = WalletTransaction.objects.select_related("customer", "processed_by").all()

            if customer_id:
                if not user.role in AUTHORIZED_ROLES:
                    return Response({
                        "success": False,
                        "status": status.HTTP_403_FORBIDDEN,
                        "message": "You are not authorized to download statements for other customers."
                    }, status=status.HTTP_403_FORBIDDEN)
                
            if user.role in AUTHORIZED_ROLES:
                # Authorized user
                if customer_id:
                    customer_id =  uuid.UUID(customer_id)
                    transactions = transactions.filter(customer_id=customer_id)
                else:
                    show_all_customers = True
            else:
                # Other users can only download their own transactions
                transactions = transactions.filter(customer=user)
            # Filter by date range
            transactions = transactions.filter(
                                created_at__date__gte=start_date_parsed,
                                created_at__date__lte=end_date_parsed
                            ).order_by('-created_at')

            if not transactions.exists():
                return Response({
                    "success": False,
                    "status": status.HTTP_404_NOT_FOUND,
                    "message": "No transactions found for the given filters."
                }, status=status.HTTP_404_NOT_FOUND)

            # --- Prepare customer info ---
            first_transaction = transactions.first()
            customer = {
                "name": first_transaction.customer.name,
                "email": first_transaction.customer.email,
                "phone_no": first_transaction.customer.phone_no,
            }

            # --- Render HTML ---
            html_string = render_to_string("statement_templates.html", {
                "customer": customer,
                "transactions": transactions,
                "from_date": start_date_parsed,
                "to_date": end_date_parsed,
                "today": date.today(),
                "generated_by": user.name if user.id != customer.get("id") else f"{user.name} -(Self)",
                "show_all_customers": show_all_customers, 
                "STATIC_ROOT": str(settings.STATIC_ROOT),
            })
            
            css_path = os.path.join(str(settings.STATIC_ROOT), "CSS", "templates.css")
            if not os.path.exists(css_path):
                raise FileNotFoundError(f"CSS file not found: {css_path}")

            html = HTML(string=html_string, base_url=str(settings.STATIC_ROOT)) 
            # --- Generate PDF ---
            with tempfile.NamedTemporaryFile(delete=True) as tmpfile:
                html.write_pdf(
                    target=tmpfile.name,
                    stylesheets=[CSS(filename=css_path)],
                )
                tmpfile.seek(0)
                pdf_content = tmpfile.read()

            # --- Return PDF response ---
            response = HttpResponse(pdf_content, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="Account_Statement_{customer.get("name","User")}.pdf"'
            return response

        except Exception as e:
            return Response({
                "success": False,
                "status": status.HTTP_400_BAD_REQUEST,
                "message": "Something went wrong: " + str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
        

class WalletOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated,IsUserVerifiedAndEnabled]
    authentication_classes = [JWTAuthentication]
    renderer_classes = [UserRenderer]

    def get(self, request):
        user = request.user
        today = now().date()
        current_year = today.year
        current_month = today.month

        # --- Step 1: Realtime balance ---
        if user.role in AUTHORIZED_ROLES:
            ceo_user = User.objects.filter(role="CEO").first()
            wallet = Wallet.objects.filter(user=ceo_user).first()
            realtime_balance = wallet.account_balance if wallet else 0.0
            tx_queryset = WalletTransaction.objects.filter(created_at__year=current_year)
        else:
            wallet = Wallet.objects.filter(user=user).first()
            realtime_balance = wallet.account_balance if wallet else 0.0
            tx_queryset = WalletTransaction.objects.filter(customer=user, created_at__year=current_year)

        # --- Step 2: Annotate month ---
        tx_queryset = tx_queryset.annotate(month=ExtractMonth('created_at')).order_by('customer_id', 'month', '-created_at')

        # --- Step 3: Pick latest transaction per user per month and sum ---
        monthly_dict = defaultdict(dict)  # {month: {customer_id: cumulative_balance}}
        for tx in tx_queryset:
            if tx.customer_id not in monthly_dict[tx.month]:
                monthly_dict[tx.month][tx.customer_id] = float(tx.cumulative_balance or 0)

        # --- Step 4: Sum latest balances per month ---
        monthly_transactions = []
        for m in range(1, current_month + 1):
            month_sum = sum(monthly_dict[m].values()) if m in monthly_dict else 0.0
            monthly_transactions.append(month_sum)

        return Response({
            "success": True,
            "status": 200,
            "message": "Wallet overview fetched successfully.",
            "data": {
                "realtime_balance": float(realtime_balance),
                "monthly_transactions": monthly_transactions,
            }
        }, status=status.HTTP_200_OK)

class DashboardOverviewAPIView(APIView):
    permission_classes = [IsAuthenticated,IsUserVerifiedAndEnabled,IsAuthorizedUser]
    authentication_classes = [JWTAuthentication]
    renderer_classes = [UserRenderer]
    def get(self, request):
        try:
            today = now().date()
            seven_days_ago = today - timedelta(days=7)
            print("seven_days_ago:", seven_days_ago)

            # --- Today's totals ---
            today_deposit_total = WalletTransaction.objects.filter(
                transaction_type='deposit', created_at__date=today
            ).aggregate(total=Sum('amount'))['total'] or 0

            today_withdraw_total = WalletTransaction.objects.filter(
                transaction_type='withdrawal', created_at__date=today
            ).aggregate(total=Sum('amount'))['total'] or 0

            today_payout_total = WalletTransaction.objects.filter(
                transaction_type='payment_out', created_at__date=today
            ).aggregate(total=Sum('amount'))['total'] or 0

            today_balance = today_deposit_total - (today_withdraw_total + today_payout_total)

            # --- Last 7 days totals (excluding today) ---
            deposit_sum_7_days = WalletTransaction.objects.filter(
                transaction_type='deposit',
                created_at__date__range=[seven_days_ago, today - timedelta(days=1)]
            ).aggregate(total=Sum('amount'))['total'] or 0

            withdraw_sum_7_days = WalletTransaction.objects.filter(
                transaction_type='withdrawal',
                created_at__date__range=[seven_days_ago, today - timedelta(days=1)]
            ).aggregate(total=Sum('amount'))['total'] or 0

            payout_sum_7_days = WalletTransaction.objects.filter(
                transaction_type='payment_out',
                created_at__date__range=[seven_days_ago, today - timedelta(days=1)]
            ).aggregate(total=Sum('amount'))['total'] or 0

            balance_sum_7_days = deposit_sum_7_days - (withdraw_sum_7_days + payout_sum_7_days)

            # print("today_deposit_total:", today_deposit_total)
            # print("today_withdraw_total:", today_withdraw_total)
            # print("today_balance:", today_balance)
            # print("----------------------------------------")
            # print("deposit_sum_7_days:", deposit_sum_7_days)
            # print("withdraw_sum_7_days:", withdraw_sum_7_days)
            # print("balance_sum_7_days:", balance_sum_7_days)

            deposit_progress, deposit_percentage = calculate_progress(today_deposit_total, deposit_sum_7_days)
            withdraw_progress, withdraw_percentage = calculate_progress(today_withdraw_total, withdraw_sum_7_days)
            balance_progress, balance_percentage = calculate_progress(today_balance, balance_sum_7_days)

            # --- Final API response ---
            data = {
                "deposit": {
                    "field": "Deposit",
                    "total_amount": float(today_deposit_total),
                    "progress": deposit_progress,
                    "progress_percentage": deposit_percentage
                },
                "withdrawal": {
                    "field": "Withdrawal",
                    "total_amount": float(today_withdraw_total),
                    "progress": withdraw_progress,
                    "progress_percentage": withdraw_percentage
                },
                "todays_balance": {
                    "field": "Today’s Balance",
                    "total_amount": float(today_balance),
                    "progress": balance_progress,
                    "progress_percentage": balance_percentage
                }
            }

            return Response({
                'success': True,
                'status': status.HTTP_200_OK,
                'message': "Dashboard overview data fetched successfully.",
                'data': data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f"Something went wrong: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class WalletTransactionDetailAPIView(APIView):
    permission_classes = [IsAuthenticated,IsUserVerifiedAndEnabled]
    authentication_classes = [JWTAuthentication]
    renderer_classes = [UserRenderer]
    def get(self, request):
        user = request.user
        required_fields = ['UUId']
        for field in required_fields:
            if field not in request.query_params or not request.query_params[field]:
                return Response({
                    'success': False,
                    'status': status.HTTP_400_BAD_REQUEST,
                    'message': f'{field} is missing or empty in the params',
                }, status=status.HTTP_400_BAD_REQUEST)

        UUId = request.query_params.get('UUId')
        try:
            uuid.UUID(UUId)
        except (ValueError, Exception) as e:
            return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': f'Invalid UUID: {str(e)}',
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Fetch transaction using transaction_id (UUID field)
            transaction = WalletTransaction.objects.get(id=UUId)

            # ✅ Authorization check
            if user.role not in AUTHORIZED_ROLES and transaction.customer != user:
                return Response({
                    'success': False,
                    'status': status.HTTP_403_FORBIDDEN,
                    'message': "You are not authorized to view this transaction.",
                    'data': None
                },status=status.HTTP_403_FORBIDDEN)

            serializer = WalletTransactionListSerializer(transaction)
            return Response({
                'success': True,
                'status': status.HTTP_200_OK,
                'message': "Transaction details fetched successfully.",
                'data': serializer.data
            })

        except WalletTransaction.DoesNotExist:
            return Response({
                'success': False,
                'status': status.HTTP_404_NOT_FOUND,
                'message': 'Transaction not found.',
                'data': None
            },status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({
                'success': False,
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f"Something went wrong: {str(e)}",
                'data': None
            },status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class TransactionListAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication,IsUserVerifiedAndEnabled]
    renderer_classes = [UserRenderer]
    def get(self, request):
        user = request.user
        try:
            required_fields = ['date_filter_type']
            for field in required_fields:
                if field not in request.query_params or not request.query_params[field]:
                    return Response({
                        'success': False,
                        'status': status.HTTP_400_BAD_REQUEST,
                        'message': f'{field} is missing or empty in the params',
                    }, status=status.HTTP_400_BAD_REQUEST)
            # Base queryset with related customer to avoid N+1 queries
            queryset = WalletTransaction.objects.all().select_related("customer", "processed_by").order_by('-created_at')

            # Query params
            customer = request.GET.get("customer")
            transaction_type = request.GET.get("transaction_type")
            payment_method = request.GET.get("payment_method")
            date_filter_type = request.GET.get("date_filter_type")
            date_of_transaction = request.GET.get("date_of_transaction")
            start_date = request.GET.get("start_date")
            end_date = request.GET.get("end_date")
            transaction_id = request.GET.get("transaction_id")

            # ----------------------------------------
            # Authorization & customer filtering
            # ----------------------------------------
            if user.role not in AUTHORIZED_ROLES:
                # Non-authorized users: only their transactions
                queryset = queryset.filter(customer=user)
            elif customer:
                try:
                    customer_id = uuid.UUID(customer)
                    queryset = queryset.filter(customer__id=customer_id)
                except (ValueError, Exception) as e:
                    return Response({
                        'success': False,
                        'status': status.HTTP_400_BAD_REQUEST,
                        'message': "Something went wrong with customer ID filter: " + str(e)
                    }, status=status.HTTP_400_BAD_REQUEST)

            # ----------------------------------------
            # Other filters
            # ----------------------------------------
            if transaction_id:
                queryset = queryset.filter(transaction_id__icontains=transaction_id) 
            if transaction_type:
                queryset = queryset.filter(transaction_type__iexact=transaction_type)
            if payment_method:
                queryset = queryset.filter(payment_method__iexact=payment_method)

            # ----------------------------------------
            # Date filtering
            # ----------------------------------------
            if date_filter_type:
                if date_filter_type not in ["single", "range"]:
                    return Response({
                        'success': False,
                        'status': status.HTTP_400_BAD_REQUEST,
                        'message': "date_filter_type must be 'single' or 'range'."
                    }, status=status.HTTP_400_BAD_REQUEST)

                if date_filter_type == "single" and date_of_transaction:
                    try:
                        start = datetime.strptime(date_of_transaction, "%Y-%m-%d")
                        end = start + timedelta(days=1)
                        queryset = queryset.filter(created_at__gte=start, created_at__lt=end)
                    except ValueError:
                        return Response({
                            'success': False,
                            'status': status.HTTP_400_BAD_REQUEST,
                            'message': "Invalid 'date_of_transaction'. Use YYYY-MM-DD."
                        }, status=status.HTTP_400_BAD_REQUEST)

                elif date_filter_type == "range":
                    if not (start_date and end_date):
                        return Response({
                            'success': False,
                            'status': status.HTTP_400_BAD_REQUEST,
                            'message': "Both start_date and end_date are required for range."
                        }, status=status.HTTP_400_BAD_REQUEST)

                    try:
                        start = datetime.strptime(start_date, "%Y-%m-%d")
                        end = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
                    except ValueError:
                        return Response({
                            'success': False,
                            'status': status.HTTP_400_BAD_REQUEST,
                            'message': "Invalid date format. Use YYYY-MM-DD."
                        }, status=status.HTTP_400_BAD_REQUEST)

                    if end < start:
                        return Response({
                            'success': False,
                            'status': status.HTTP_400_BAD_REQUEST,
                            'message': "End date cannot be before start date."
                        }, status=status.HTTP_400_BAD_REQUEST)

                    queryset = queryset.filter(created_at__gte=start, created_at__lt=end)

            # ----------------------------------------
            # Pagination
            # ----------------------------------------
            paginator = PageNumberPagination()
            paginated_qs = paginator.paginate_queryset(queryset, request)
            serializer = WalletTransactionListSerializer(paginated_qs, many=True)

            # ----------------------------------------
            # Response
            # ----------------------------------------
            return Response({
                'success': True,
                'status': status.HTTP_200_OK,
                'message': "Transaction list fetched successfully.",
                'data': {
                    'transactions_data': serializer.data,
                    'pagination': {
                        'total_items': paginator.page.paginator.count,
                        'page_size': paginator.page_size,
                        'current_page': paginator.page.number,
                        'total_pages': paginator.page.paginator.num_pages,
                        'next': paginator.get_next_link(),
                        'previous': paginator.get_previous_link(),
                    }
                }
            }, status=status.HTTP_200_OK)

        # ----------------------------------------
        # Catch specific exceptions
        # ----------------------------------------
        except ValueError as ve:
            logger.error(f"Value error: {str(ve)}")
            return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': str(ve)
            }, status=status.HTTP_400_BAD_REQUEST)

        except WalletTransaction.DoesNotExist:
            return Response({
                'success': False,
                'status': status.HTTP_404_NOT_FOUND,
                'message': "No transactions found."
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"Unexpected error in TransactionListAPIView: {str(e)}")
            return Response({
                'success': False,
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': "An unexpected error occurred. Please try again later."
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
class TransactionAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated,IsAuthorizedUser,IsUserVerifiedAndEnabled,IsNotCustomerSelf,TargetUserMustBeCustomer]
    renderer_classes = [UserRenderer]

    def post(self, request):
        """Handles the deposit request, does not update the balance until admin approval"""
        
        user = request.user
        custom_data = request.data.copy()

        try:
            # Proceed with serializer if data is valid
            with transaction.atomic():
                serializer = WalletTransactionSerializer(data=custom_data, context={'request': request})
                if serializer.is_valid():
                    customer_id = custom_data.get('customer')
                    ceo_wallet = Wallet.objects.select_for_update().get(user__role='CEO')
                    wallet = Wallet.objects.select_for_update().get(user=customer_id)
                    customer = wallet.user
                    transaction_type = custom_data.get('transaction_type')

                    if transaction_type == 'deposit':
                        wallet.account_balance += Decimal(custom_data.get('amount', 0))
                        ceo_wallet.account_balance += Decimal(custom_data.get('amount', 0))

                    elif transaction_type in ['withdrawal', 'payment_out']:
                        amount = Decimal(custom_data.get('amount', 0))
                        ceo_wallet.account_balance -= amount
                        if wallet.account_balance >= amount:
                            wallet.account_balance -= amount
                        else:
                            raise ValueError("Insufficient funds for this transaction.")

                    wallet.save()
                    instance=serializer.save()
                    ceo_wallet.save()
                    bodyContent = generate_transaction_email_body_html(instance.transaction_id,customer.name, transaction_type, custom_data.get('amount', 0), wallet.account_balance, custom_data.get('payment_method'), custom_data.get('date_of_transaction'), user.name, user.email, user.phone_no)
                    data={
                        'subject': 'Transaction Confirmation Information',
                        'body': bodyContent,
                        'to_email': customer.email,

                    }
                    
                    send_email(data, is_html=True)

                    # logger.info(f"Transaction request placed successfully & added {custom_data.get('amount', 0)} to balance.")
                    return Response({
                        'success': True,
                        'status': status.HTTP_200_OK,
                        'transaction_id': instance.transaction_id,
                        'message': "Transaction successfully placed."
                    }, status=status.HTTP_200_OK)

            error_messages = []
            for field, errors in serializer.errors.items():
                for error in errors:
                    error_messages.append(f"{field}: {error}")
                    
            logger.error("\n".join(error_messages))
            return Response({
                "success": False,
                "status": 400,
                "message": "\n".join(error_messages)  # Join error messages with newline character
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # Extract the error message if it's a ValidationError
            if hasattr(e, 'message_dict'):  # For ValidationError with a dict
                error_message = ', '.join([f"{key}: {', '.join(values)}" for key, values in e.message_dict.items()])
            elif hasattr(e, 'messages'):  # For ValidationError with a list of messages
                error_message = ', '.join(e.messages)
            else:  # Fallback to the string representation
                error_message = str(e)
            logger.error(error_message)
            return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': error_message
            }, status=status.HTTP_400_BAD_REQUEST)
