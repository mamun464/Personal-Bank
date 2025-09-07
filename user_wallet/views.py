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
from django.db.models import Sum, Case, When, F, DecimalField


logger = logging.getLogger(__name__)


class WalletOverviewOptimizedAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        current_year = now().year

        # --- 1) Realtime balance ---
        if user.role in AUTHORIZED_ROLES:
            ceo_user = User.objects.filter(role="CEO").first()
            realtime_balance = (
                Wallet.objects.filter(user=ceo_user)
                .values_list("account_balance", flat=True)
                .first()
                if ceo_user else 0
            )
            transactions_queryset = WalletTransaction.objects.filter(
                created_at__year=current_year
            )
        else:
            wallet = Wallet.objects.filter(user=user).first()
            realtime_balance = wallet.account_balance if wallet else 0
            transactions_queryset = WalletTransaction.objects.filter(
                customer=user,
                created_at__year=current_year
            )

        # --- 2) Monthly net transactions in a single query ---
        monthly_data = (
            transactions_queryset
            .annotate(month=F('created_at__month'))
            .values('month')
            .annotate(
                net=Sum(
                    Case(
                        When(transaction_type='deposit', then=F('amount')),
                        When(transaction_type='withdrawal', then=-F('amount')),
                        When(transaction_type='payment_out', then=-F('amount')),
                        default=0,
                        output_field=DecimalField()
                    )
                )
            )
            .order_by('month')
        )

        # Prepare list only up to current month
        current_month = now().month
        monthly_transactions = [0] * current_month
        for entry in monthly_data:
            month_idx = entry['month'] - 1
            if month_idx < current_month:
                monthly_transactions[month_idx] = float(entry['net'] or 0)

        response_data = {
            "realtime_balance": float(realtime_balance or 0),
            "monthly_transactions": monthly_transactions
        }

        serializer = WalletOverviewSerializer(response_data)
        return Response({
            "success": True,
            "status": 200,
            "message": "Wallet overview fetched successfully.",
            "data": serializer.data
        })

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
            # ✅ Admins, employees, ceo can view all transactions
            if user.role in AUTHORIZED_ROLES:
                queryset = WalletTransaction.objects.all().order_by('-created_at')
            else:
                # ✅ Customers can only see their own transactions
                queryset = WalletTransaction.objects.filter(customer=user).order_by('-created_at')

            # ✅ Dynamic filters
            customer = request.GET.get("customer")
            date_of_transaction = request.GET.get("date_of_transaction")
            transaction_type = request.GET.get("transaction_type")
            payment_method = request.GET.get("payment_method")

            filters = {}
            if customer:
                filters["customer__id"] = customer
            if date_of_transaction:
                filters["date_of_transaction"] = date_of_transaction
            if transaction_type:
                filters["transaction_type__iexact"] = transaction_type
            if payment_method:
                filters["payment_method__iexact"] = payment_method

            queryset = queryset.filter(**filters)

            # Apply global pagination
            paginator = PageNumberPagination()
            paginated_qs = paginator.paginate_queryset(queryset, request)
            serializer = WalletTransactionListSerializer(paginated_qs, many=True)
            
            retrieve_transactions = {
                    'transactions_data': serializer.data,
                    'pagination': {
                        'total_items': paginator.page.paginator.count,  # Total number of products
                        'page_size': paginator.page_size,  # Number of products per page
                        'current_page': paginator.page.number,  # Current page number
                        'total_pages': paginator.page.paginator.num_pages,  # Total number of pages
                        'next': paginator.get_next_link(),  # URL for the next page
                        'previous': paginator.get_previous_link(),  # URL for the previous page
                    }
                }

            return Response({
                'success': True,
                'status': status.HTTP_200_OK,
                'message': "Transaction list fetched successfully.",
                'data': retrieve_transactions
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Transaction list error: {str(e)}")
            return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


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