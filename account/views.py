from django.shortcuts import render
from account.renderers import UserRenderer
from rest_framework.response import Response
from rest_framework import status,serializers
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from account.serializer import UserRegistrationSerializer, UserProfileSerializer,UserLoginSerializer,VerifyEmailSerializer,SendPasswordResetEmailSerializer,UserPasswordRestSerializer,UserActiveStatusSerializer,UserProfileUpdateSerializer,UserListSerializer,UserUpdateSerializer,AuthorizedUserSerializer
from django.utils import timezone
from django.db import transaction
from django.contrib.auth import login
from .utils import generate_unique_otp,send_email,flattened_serializer_errors,generate_otp_email_body_html
from account.models import OtpToken,User
from rest_framework.exceptions import AuthenticationFailed,ValidationError,PermissionDenied
from drf_yasg.utils import swagger_auto_schema
import re
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from account.permissions import hasChangePermission,is_authorized_role,IsAuthorizedUser,GRAND_AUTHORIZED_ROLES,CanCreateAuthorizedUser,IsUserVerifiedAndEnabled,AUTHORIZED_ROLES
from drf_yasg import openapi
import uuid
from user_wallet.models import Wallet
from rest_framework.pagination import PageNumberPagination
from django.db.models import Q



# token generator
def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class UserUpdateAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthorizedUser,hasChangePermission,IsUserVerifiedAndEnabled]
    renderer_classes = [UserRenderer]

    def patch(self, request, user_id):
        try:
            user_to_update = User.objects.get(id=user_id)
        except (ValueError, User.DoesNotExist):
            return Response({
                "success": False,
                "status": 400,
                "message": "Invalid or non-existent user ID"
            }, status=status.HTTP_400_BAD_REQUEST)
            
        requester = request.user
        # Block self-update for authorized users
        if requester.id == user_to_update.id :
            return Response({
                'success': False,
                'status': status.HTTP_403_FORBIDDEN,
                'message': 'You cannot update your own account via this endpoint.'
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = UserUpdateSerializer(user_to_update, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'status': status.HTTP_200_OK,
                'message': f"{user_to_update.name}'s info updated successfully.",
            }, status=status.HTTP_200_OK)

        return Response({
            'success': False,
            'status': status.HTTP_200_OK,
            'message': 'Invalid data provided. {str(serializer.errors)}',
        }, status=status.HTTP_400_BAD_REQUEST)
        
class UserListView(APIView):
    """
    API view to get list of customers and suppliers with filtering capabilities
    Only accessible by admin users
    """
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthorizedUser,IsUserVerifiedAndEnabled]
    renderer_classes = [UserRenderer]
    
    def get(self, request):
        try:
            # Get query parameters for filtering
            search = request.query_params.get('search', '')
            is_active = request.query_params.get('is_active')
            is_verified = request.query_params.get('is_verified')
            filter_type = request.query_params.get('filter_type')
            
            requester = request.user
            if filter_type == 'authorized':
                users = User.objects.filter(role__in=AUTHORIZED_ROLES).exclude(role='admin')
            else:
                # Start with all users excluding admins
                users = User.objects.exclude(role__in=AUTHORIZED_ROLES)
            
            # Apply filters
            if is_active is not None:
                is_active_bool = is_active.lower() == 'true'
                users = users.filter(is_active=is_active_bool)
            
            if is_verified is not None:
                is_verified_bool = is_verified.lower() == 'true'
                users = users.filter(is_verified=is_verified_bool)
            
            # Apply search filter
            if search:
                users = users.filter(
                    Q(name__icontains=search) |
                    Q(email__icontains=search) |
                    Q(phone_no__icontains=search)
                )
            
            # Order by creation date (newest first)
            users = users.order_by('-created_at')
            
            # Apply pagination
            paginator = PageNumberPagination()
            paginator.page_size = 5  # 20 users per page
            paginated_users = paginator.paginate_queryset(users, request)
            
            # Serialize the data
            serializer = UserListSerializer(paginated_users, many=True)
            
            return Response({
                'success': True,
                'status': status.HTTP_200_OK,
                'message': f'Successfully retrieved {len(serializer.data)} users',
                'data': {
                    'users': serializer.data,
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
            
        except Exception as e:
            return Response({
                'success': False,
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f'An error occurred while retrieving users: {str(e)}',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        

class UserProfileDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated,IsUserVerifiedAndEnabled]

    @swagger_auto_schema(
        operation_description="Get user profile details. Admins can pass `user_id` to view others. Customers can only view their own.",
        manual_parameters=[
            openapi.Parameter(
                'user_id',
                openapi.IN_QUERY,
                type=openapi.TYPE_STRING,
                description="Optional - UUID of the user (admin only)",
                required=False
            )
        ],
        responses={200: UserProfileSerializer}
    )
    def get(self, request):
        user_id = request.query_params.get('user_id')

        if request.user.role == 'customer':
            # Customers can only view their own profile
            target_user = request.user
        elif is_authorized_role(request.user):
            # Admins can view their own or others
            if user_id:
                try:
                    valid_uuid = uuid.UUID(user_id.strip())  # Strip extra whitespace and validate
                    target_user = User.objects.get(id=valid_uuid)
                except (ValueError, User.DoesNotExist):
                    return Response({
                        "success": False,
                        "status": 400,
                        "message": "Invalid or non-existent user_id"
                    }, status=status.HTTP_400_BAD_REQUEST)
            else:
                target_user = request.user
        else:
            return Response({
                "success": False,
                "status": 403,
                "message": "You are not authorized to access this resource."
            }, status=status.HTTP_403_FORBIDDEN)

        serializer = UserProfileSerializer(target_user)
        return Response({
            "success": True,
            "status": 200,
            "message": "User profile fetched successfully.",
            "user_data": serializer.data
        }, status=status.HTTP_200_OK)

class UpdateOwnProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated,IsUserVerifiedAndEnabled]

    @swagger_auto_schema(request_body=UserProfileUpdateSerializer)
    def patch(self, request):
        user = request.user
        serializer = UserProfileUpdateSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                "success": True,
                "status": status.HTTP_200_OK,
                "message": "Profile updated successfully",
                "user_data": UserProfileSerializer(user).data
            }, status=status.HTTP_200_OK)


        return Response({
            "success": False,
            "status": status.HTTP_400_BAD_REQUEST,
            "message": flattened_serializer_errors(serializer)
        }, status=status.HTTP_400_BAD_REQUEST)



class ChangeUserActiveStatusView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, hasChangePermission,IsUserVerifiedAndEnabled]

    @swagger_auto_schema(
        operation_description="Change the 'is_active' status of a user using query param 'user_id'",
        manual_parameters=[
            openapi.Parameter(
                'user_id',
                openapi.IN_QUERY,
                description="UUID of the user",
                type=openapi.TYPE_STRING,
                required=True
            )
        ],
        request_body=UserActiveStatusSerializer,
        responses={
            200: openapi.Response(description="Success", schema=UserActiveStatusSerializer),
            400: "Invalid data or missing user_id",
            404: "User not found"
        }
    )
    def patch(self, request):
        required_fields = ['user_id']
        for field in required_fields:
            if field not in request.query_params or not request.query_params[field]:
                return Response({
                    'success': False,
                    'status': status.HTTP_400_BAD_REQUEST,
                    'message': f'{field} is missing or empty in the params',
                }, status=status.HTTP_400_BAD_REQUEST)
        
        required_fields = [ 'is_active']
        for field in required_fields:
            if field not in request.data or not request.data[field]:
                return Response({
                    'success': False,
                    'status': status.HTTP_400_BAD_REQUEST,
                    'message': f'{field} is missing or empty in body',
                }, status=status.HTTP_400_BAD_REQUEST)

        user_id = request.query_params.get('user_id')
        # print("Received user_id:", user_id)  # Debugging line

        try:
                valid_uuid = uuid.UUID(user_id.strip())  # Strip extra whitespace and validate
                user = User.objects.get(id=valid_uuid)
        except (ValueError, User.DoesNotExist):
            return Response({
                "success": False,
                "status": 400,
                "message": "Invalid or non-existent user id"
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = UserActiveStatusSerializer(user, data=request.data, partial=True)
        if serializer.is_valid():
            new_status = serializer.validated_data['is_active']
            if user.is_active == new_status:
                return Response({
                    "success": False,
                    "status": status.HTTP_400_BAD_REQUEST,
                    "message": f"{user.name} is already {'active' if new_status else 'inactive'}."
                }, status=status.HTTP_400_BAD_REQUEST)

            serializer.save()
            return Response({
                "success": True,
                "status": status.HTTP_200_OK,
                "message": f"{user.name}'s account has been {'activated' if new_status else 'deactivated'} successfully."
            }, status=status.HTTP_200_OK)

        return Response({
            "success": False,
            "status": status.HTTP_400_BAD_REQUEST,
            "message": flattened_serializer_errors(serializer)
        }, status=status.HTTP_400_BAD_REQUEST)

class UserPasswordResetView(APIView):
    renderer_classes = [UserRenderer]
    @swagger_auto_schema(request_body=UserPasswordRestSerializer)
    def post(self, request, uid, token, format=None):

        required_fields = [ 'password', 'confirm_password']
        for field in required_fields:
            if field not in request.data or not request.data[field]:
                return Response({
                    'success': False,
                    'status': status.HTTP_400_BAD_REQUEST,
                    'message': f'{field} is missing or empty in body',
                }, status=status.HTTP_400_BAD_REQUEST)

        serializer = UserPasswordRestSerializer(data=request.data, context={'uid': uid, 'token': token})
        try:
            serializer.is_valid(raise_exception=True)
            return Response({
                'success': True,
                'status': status.HTTP_200_OK,
                'message': 'Password Reset successfully'
            }, status=status.HTTP_200_OK)
        except serializers.ValidationError as e:
            error_messages = []
            for messages in e.detail.values():
                error_messages.extend(messages)
            message = " ".join(error_messages) if error_messages else "Invalid data provided."
            return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': message
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({
                'success': False,
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f"An unexpected error occurred: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class SendPasswordResetEmailView(APIView):
    renderer_classes = [UserRenderer]
    @swagger_auto_schema(request_body=SendPasswordResetEmailSerializer)
    def post(self, request, format=None):
        required_fields = [ 'email']
        for field in required_fields:
            if field not in request.data or not request.data[field]:
                return Response({
                    'success': False,
                    'status': status.HTTP_400_BAD_REQUEST,
                    'message': f'{field} is missing or empty in body',
                }, status=status.HTTP_400_BAD_REQUEST)
            
        serializer = SendPasswordResetEmailSerializer(data=request.data)
        
        try:
            serializer.is_valid(raise_exception=True)
        except Exception as e:
            error_messages = []
            if hasattr(e, 'detail') and isinstance(e.detail, dict):
                for messages in e.detail.values():
                    if isinstance(messages, list):
                        error_messages.extend([str(msg) for msg in messages])
                    else:
                        error_messages.append(str(messages))
            else:
                error_messages.append(str(e))    # fallback if e.detail doesn't exist

            return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': "Failed to send password reset link: " + ", ".join(error_messages),
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'status': status.HTTP_200_OK,
            'message': 'Password reset link sent to your registered email. Please check your inbox.'
        }, status=status.HTTP_200_OK)

class CheckEmailVerifiedView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated,IsUserVerifiedAndEnabled]
    renderer_classes = [UserRenderer]
    def get(self, request):

        user = request.user
        if user.is_verified:
            return Response({
                'success': True,
                'verified': True,
                'status': status.HTTP_200_OK,
                'message': 'Email address is verified',
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': True,
                'verified': False,
                'status': status.HTTP_200_OK,
                'message': 'Email address is not verified',
            }, status=status.HTTP_200_OK)

class ResendOtpView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    renderer_classes = [UserRenderer]
    def post(self, request):

        user = request.user

        try:
            # # Mark all OTPs for this user as used
            OtpToken.objects.filter(user=user, is_used=False).update(is_used=True)
            
        except User.DoesNotExist:
            return Response({
                'success': False,
                'status': status.HTTP_404_NOT_FOUND,
                'message': 'Email address does not exist',
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
                # Handle database integrity error
            return Response({
                'success': False,
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f"Email verification Code resend Failed: {str(e)}",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            
        otp = OtpToken.objects.filter(user=user).last()
        if not otp:
            try:
                otp=OtpToken.objects.create(user=user,otp_code=generate_unique_otp(), otp_expires_at=timezone.now() + timezone.timedelta(hours=1))
            except Exception as e:
                return Response({
                'success': False,
                'status':status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f'OTP create Failed',
                'error': f'OTP create Failed: {str(e)}',
                
                },status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            msg=f"BrandNew: {otp.otp_code}"
        else:
            # otp=OtpToken.objects.create(user=user,otp_code=generate_unique_otp(), otp_expires_at=timezone.now() + timezone.timedelta(hours=1))
            # msg="Exist otp token found"
            # msg=otp.otp_code
            previous_max_otp_try=otp.max_otp_try
            previous_max_otp_try_expires = otp.max_otp_try_expires

            current_max_otp_try=None
            current_max_otp_try_expires = None
            
            if previous_max_otp_try <= 0 and previous_max_otp_try_expires > timezone.now():
                # Calculate remaining time
                remaining_time = previous_max_otp_try_expires - timezone.now()
                remaining_minutes = remaining_time.total_seconds() // 60  # Convert remaining time to minutes
                return Response({
                    'success': False,
                    'status': status.HTTP_400_BAD_REQUEST,
                    'message': f'Max Limit crossed for OTP sent. Please try again after {remaining_minutes} minutes.',
            }, status=status.HTTP_400_BAD_REQUEST)
            
            elif previous_max_otp_try <= 0 and previous_max_otp_try_expires < timezone.now():
                current_max_otp_try = 3
                current_max_otp_try_expires = None

            else:
                current_max_otp_try = previous_max_otp_try-1

            if current_max_otp_try == 0:
                current_max_otp_try_expires= timezone.now() + timezone.timedelta(hours=1)
            
            otp=OtpToken.objects.create(
                user=user,
                otp_code=generate_unique_otp(),
                otp_expires_at=timezone.now() + timezone.timedelta(hours=1),
                max_otp_try= current_max_otp_try,
                max_otp_try_expires=current_max_otp_try_expires,
                )
            
            msg=f"Renew: {otp.otp_code}"

        bodyContent = generate_otp_email_body_html(user.name,otp.otp_code)
        data={
            'subject': 'OTP Verification Code',
            'body': bodyContent,
            'to_email': otp.user.email,

        }
        
        email_sent=send_email(data,is_html=True)


        if email_sent:
            return Response({
                'success': True,
                'status': status.HTTP_200_OK,
                'message': 'OTP successfully sent to registered email',
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': 'Failed to send OTP by email',
            }, status=status.HTTP_400_BAD_REQUEST)

class VerifyEmailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    renderer_classes = [UserRenderer]

    @swagger_auto_schema(request_body=VerifyEmailSerializer)
    def post(self, request):

        required_fields = [ 'otp_code']
        for field in required_fields:
            if field not in request.data or not request.data[field]:
                return Response({
                    'success': False,
                    'status': status.HTTP_400_BAD_REQUEST,
                    'message': f'{field} is missing or empty in body',
                }, status=status.HTTP_400_BAD_REQUEST)

        otp_code = request.data.get('otp_code')
        user_email = request.user.email

        # Retrieve the OTP token associated with the user's email
        try:
            otp_token = OtpToken.objects.filter(user__email=user_email, is_used=False).last()
            if otp_token is None:
                return Response({
                    'success': False,
                    'status': status.HTTP_404_NOT_FOUND,
                    'message': 'OTP is already used or Not found.',
                }, status=status.HTTP_404_NOT_FOUND)
            
        except OtpToken.DoesNotExist:
            return Response({
                'success': False,
                'status': status.HTTP_404_NOT_FOUND,
                'message': 'The OTP is invalid.',
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f'An error occurred while processing the request. {str(e)}',
        })
        
        if str(otp_token.otp_code) != otp_code:
            try:
                otp_token = OtpToken.objects.get(user__email=user_email, otp_code=otp_code)
            # print("Current read: ",otp_token.otp_code)
            except OtpToken.DoesNotExist:
                return Response({
                    'success': False,
                    'status': status.HTTP_404_NOT_FOUND,
                    'message': 'Incorrect OTP provided. Please try again.',
                }, status=status.HTTP_404_NOT_FOUND)
            
            if otp_token.is_used:
                return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': 'Already used OTP provided. Please try again.',
            }, status=status.HTTP_400_BAD_REQUEST)
            
            return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': 'Previous OTP provided. Please try again.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # Check if the OTP token is expired
        print(f"Current OTP Token Expiry: {otp_token.otp_expires_at}, Current Time: {timezone.now()}")
        if otp_token.otp_expires_at < timezone.now():
            return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': 'OTP token expired.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # Mark the OTP token as used
        otp_token.is_used = True
        try:
            otp_token.save()
        except Exception as e:
            # Handle database integrity error
            return Response({
                'success': False,
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f'Error marking OTP token as used :{str(e)}',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        # update the user database update the email verified true
        try:
            with transaction.atomic():
                user_update = User.objects.get(email=user_email)
                user_update.is_verified=True
                user_update.save()
        
        except User.DoesNotExist:
            return Response({
                'success': False,
                'status': status.HTTP_404_NOT_FOUND,
                'message': 'Email address does not exist',
            }, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            # Handle database integrity error
            return Response({
                'success': False,
                'status': status.HTTP_500_INTERNAL_SERVER_ERROR,
                'message': f'Error marking OTP as used :{str(e)}',
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'success': True,
            'status': status.HTTP_200_OK,
            'message': 'Email verification successful.',
        }, status=status.HTTP_200_OK)

# login   views here
class UserLoginView(APIView):
    renderer_classes = [UserRenderer]

    @swagger_auto_schema(request_body=UserLoginSerializer)
    def post(self, request, format=None):
        serializer = UserLoginSerializer(data=request.data)

        required_fields = ['email', 'password']
        for field in required_fields:
            if field not in request.data or not request.data[field]:
                return Response({
                    'success': False,
                    'status': status.HTTP_400_BAD_REQUEST,
                    'message': f'{field} is missing or empty in body',
                }, status=status.HTTP_400_BAD_REQUEST)

        try:
            validated_data = serializer.validate(request.data)
            user = validated_data['user']
            
            #Implement wallet feature
            if not Wallet.objects.filter(user=user).exists():
                Wallet.objects.create(user=user)
            

            user.last_login = timezone.now()
            user.save()
            login(request, user)
            token = get_tokens_for_user(user)

            user_serializer = UserProfileSerializer(user)
            user_data = user_serializer.data

            return Response({
                'success': True,
                'status': status.HTTP_200_OK,
                'message': 'Successfully logged in',
                'token': token,
                'user_data': user_data,
            }, status=status.HTTP_200_OK)

        except (AuthenticationFailed, ValidationError) as e:
            status_code = status.HTTP_401_UNAUTHORIZED if isinstance(e, AuthenticationFailed) else status.HTTP_400_BAD_REQUEST
            return Response({
                'success': False,
                'status': status_code,
                'message': str(e),  # Use the error message from the exception
            }, status=status_code)

        except Exception as e:
            error_messages = []
            for field, messages in e.detail.items():
                error_messages.append(f"{field}: {messages[0]}")
            return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': "\n".join(error_messages),
            }, status=status.HTTP_400_BAD_REQUEST)

class AuthorizeUserRegistrationView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [CanCreateAuthorizedUser,IsAuthorizedUser,IsUserVerifiedAndEnabled]
    renderer_classes = [UserRenderer]

    def post(self, request, format=None):
        # Required fields
        required_fields = ['name', 'email', 'phone_no', 'role']
        for field in required_fields:
            if field not in request.data or not request.data[field]:
                return Response({
                    'success': False,
                    'status': 400,
                    'message': f"'{field}' is missing or empty in body",
                }, status=status.HTTP_400_BAD_REQUEST)

        # Validate phone number
        phone_no = request.data.get('phone_no', '')
        phone_pattern = r'^\+[0-9]+$'
        if not re.match(phone_pattern, phone_no):
            print("Phone number validation failed.")
            return Response({
                'success': False,
                'status': 400,
                'message': 'Invalid phone number. Only numbers are allowed, with an optional leading (+)',
            }, status=status.HTTP_400_BAD_REQUEST)
        
        data_copy = request.data.copy()

        # 2) Inject temporary password
        auto_password = "123456"
        data_copy['password'] = auto_password
        serializer = AuthorizedUserSerializer(data=data_copy)

        try:
            if serializer.is_valid():
                with transaction.atomic():
                    # Create user (password auto "123456" in serializer)
                    new_user = serializer.save()
                    token=get_tokens_for_user(new_user)

                    try:
                        otp=OtpToken.objects.create(user=new_user,otp_code=generate_unique_otp(), otp_expires_at=timezone.now() + timezone.timedelta(hours=1))
                    except Exception as e:
                        return Response({
                        'success': True,
                        'status':200,
                        'message': f'Registration successful & OTP create Failed',
                        'email_sent': False,
                        'error': f'OTP create Failed: {str(e)}'
                        
                        },status=status.HTTP_200_OK)
                    
                #Send the Mail OTP verification
                bodyContent = generate_otp_email_body_html(new_user.name,otp.otp_code, temp_password=auto_password)
                data={
                    'subject': 'Email Verification Code & Default Password',
                    'body': bodyContent,
                    'to_email': new_user.email,

                }

                email_sent=send_email(data, is_html=True)

                if email_sent:
                    return Response({
                    'success': True,
                    'status': status.HTTP_200_OK,
                    'message': f"{new_user.role.capitalize()} account created successfully & OTP sent to email address",
                    'email_sent': True
                    
                    },status=status.HTTP_200_OK)
                else:
                    return Response({
                        'success': True,
                        'status': status.HTTP_200_OK,
                        'message': f"{new_user.role.capitalize()} account created successfully & OTP sending failed to email address",
                        'email_sent': True
                        
                    }, status=status.HTTP_200_OK)    

            else:
                # Build field: message error format like your customer view
                errors = serializer.errors
                msgs = [f"{field}: {msg[0]}" for field, msg in errors.items()]
                return Response({
                    'success': False,
                    'status': 400,
                    'message': "\n".join(msgs)
                }, status=status.HTTP_400_BAD_REQUEST)

        except PermissionDenied as e:
            return Response({
                'success': False,
                'status': 403,
                'message': str(e),
            }, status=status.HTTP_403_FORBIDDEN)

        except Exception as e:
            return Response({
                'success': False,
                'status': 500,
                'message': f"User creation failed: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UserRegistrationView(APIView):
    renderer_classes = [UserRenderer]
    @swagger_auto_schema(request_body=UserRegistrationSerializer)
    def post(self,request,format=None):

        serializer = UserRegistrationSerializer(data=request.data)

        required_fields = ['name','email', 'phone_no','date_of_birth','password', 'confirm_password']
        for field in required_fields:
            if field not in request.data or not request.data[field]:
                return Response({
                    'success': False,
                    'status': status.HTTP_400_BAD_REQUEST,
                    'message': f'{field} is missing or empty in body',
                }, status=status.HTTP_400_BAD_REQUEST)
            


        phone_no = request.data.get('phone_no', '')

        # Define a regex pattern to allow only numbers and an optional leading '+'
        phone_no_pattern = r'^\+[0-9]+$'

        if not re.match(phone_no_pattern, phone_no):
            return Response({
                'success': False,
                'status': status.HTTP_400_BAD_REQUEST,
                'message': 'Invalid phone number. Only numbers are allowed, with an optional leading (+)',
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            if serializer.is_valid():
                with transaction.atomic():
                    new_user = serializer.save()
                    
                    # Immediately create the wallet for the new user
                    user_wallet = Wallet.objects.create(user=new_user)

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
                        'status':500,
                        'message': f'Registration failed because OTP creation failed',
                        'email_sent': False,
                        'error': f'OTP create Failed: {str(e)}',
                        },status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                #Send the Mail OTP verification
                bodyContent = generate_otp_email_body_html(new_user.name,otp.otp_code)
                data={
                    'subject': 'Email Verification Code',
                    'body': bodyContent,
                    'to_email': new_user.email,

                }

                email_sent=send_email(data,is_html=True)

                if email_sent:
                    return Response({
                    'success': True,
                    'status': status.HTTP_200_OK,
                    'message': 'Registration successful & OTP sent to email address',
                    'email_sent': True,
                    'token': token,
                    'user_data': user_data,
                    
                    },status=status.HTTP_200_OK)
                else:
                    return Response({
                        'success': True,
                        'status': status.HTTP_200_OK,
                        'message': 'Registration successful & OTP sending failed to email address',
                        'email_sent': False,
                        'user_data': user_data,
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
            

