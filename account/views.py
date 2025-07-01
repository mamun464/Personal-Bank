from django.shortcuts import render
from account.renderers import UserRenderer
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from account.serializer import UserRegistrationSerializer, UserProfileSerializer
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import login
from .utils import generate_unique_otp,send_email
from account.models import OtpToken

# token generator
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


class UserRegistrationView(APIView):
    renderer_classes = [UserRenderer]
    def post(self,request,format=None):

        serializer = UserRegistrationSerializer(data=request.data)

        required_fields = ['name','email', 'phone_no','date_of_birth','password', 'confirm_password']
        for field in required_fields:
            if field not in request.data or not request.data[field]:
                return Response({
                    'success': False,
                    'status': status.HTTP_400_BAD_REQUEST,
                    'message': f'{field} is missing or empty',
                }, status=status.HTTP_400_BAD_REQUEST)
            


        
        

        try:
            if serializer.is_valid():
                with transaction.atomic():
                    new_user = serializer.save()
                    # Immediately create the wallet for the new user
                    # user_wallet = Wallet.objects.create(user=new_user)
                    # user_wallet.balance_threshold_pct = 20
                    # user_wallet.save()
                    token=get_tokens_for_user(new_user)
                    

                    # Auto login on registration
                    new_user.last_login = timezone.now()
                    new_user.save()
                    login(request, new_user)
                    user_serializer = UserProfileSerializer(new_user)
                    user_data = user_serializer.data

                    try:
                        otp=OtpToken.objects.create(user=new_user,otp_code=generate_unique_otp(), otp_expires_at=timezone.now() + timezone.timedelta(hours=1))
                    except Exception as e:
                        return Response({
                        'success': True,
                        'status':200,
                        'message': f'Registration successful & OTP create Failed',
                        'email_sent': False,
                        'error': f'OTP create Failed: {str(e)}',
                        'token': token,
                        'user': user_data,
                        
                        },status=status.HTTP_200_OK)
                #Send the Mail OTP verification
                bodyContent = f"Here is your OTP: {otp.otp_code}"
                data={
                    'subject': 'Email Verification Code',
                    'body': bodyContent,
                    'to_email': new_user.email,

                }

                email_sent=send_email(data)

                if email_sent:
                    return Response({
                    'success': True,
                    'status': status.HTTP_200_OK,
                    'message': 'Registration successful & OTP sent to email address',
                    'email_sent': True,
                    'token': token,
                    'user': user_data,
                    
                    },status=status.HTTP_200_OK)
                else:
                    return Response({
                        'success': True,
                        'status': status.HTTP_200_OK,
                        'message': 'Registration successful & OTP sending failed to email address',
                        'email_sent': True,
                        'user': user_data,
                        'token': token,
                        
                    }, status=status.HTTP_200_OK)

                
            else:
                errors = serializer.errors
                error_messages = []
                for field, messages in errors.items():
                    error_messages.append(f"{field}: {messages[0]}")  # Concatenate field name and error message
                return Response({
                    "success": False,
                    "status": 400,
                    "message": "\n".join(error_messages)  # Join error messages with newline character
                }, status=status.HTTP_400_BAD_REQUEST)
            
        except Exception as e:
            return Response({
                'success': False,
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f"Registration Failed: {str(e)}",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)  
            