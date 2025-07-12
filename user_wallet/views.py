from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from account.renderers import UserRenderer,UserRendererWithDecimal
from django.db import transaction
from user_wallet.models import Wallet,WalletTransaction
from user_wallet.serializer import WalletTransactionSerializer
from account.permissions import IsAuthorizedUser,IsNotCustomerSelf,IsCustomerRoleOnly
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


class TransactionAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated,IsAuthorizedUser,IsNotCustomerSelf,IsCustomerRoleOnly]
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

                    wallet = Wallet.objects.select_for_update().get(user=user.id)

                    # added to the user's pending balance
                    wallet.account_balance += Decimal(custom_data.get('amount', 0))
                    wallet.save()
                    serializer.save()

                    # logger.info(f"Deposit request placed successfully & added {custom_data.get('amount', 0)} to pending balance.")
                    return Response({
                        'success': True,
                        'status': status.HTTP_200_OK,
                        'message': "Deposit successfully placed."
                    }, status=status.HTTP_200_OK)

            error_messages = []
            for field, errors in serializer.errors.items():
                for error in errors:
                    if field == 'payment_method':
                        # Dynamically get the valid choices for 'payment_method'
                        valid_choices = [choice[0] for choice in WalletTransaction.PAYMENT_METHOD_CHOICES]
                        error_messages.append(
                            f"{field}: Invalid value. Choose one of the following valid options: {', '.join(valid_choices)}."
                        )
                    else:
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