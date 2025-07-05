
from rest_framework import serializers
from account.models import User
from django import forms
from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed
from django.utils import timezone
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.encoding import smart_str,force_bytes,DjangoUnicodeDecodeError
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from decouple import config
from django.core.exceptions import ValidationError
from .utils import send_email

base_url = config('FRONTEND_BASE_URL')

class SendPasswordResetEmailSerializer(serializers.Serializer): 
    email = serializers.EmailField(max_length=254)

    class Meta:
            fields = ['email']

    def validate(self, attrs):
        email = attrs.get('email')
        if User.objects.filter(email=email).exists():
            user= User.objects.get(email=email)
            EncodedUserId = urlsafe_base64_encode(force_bytes(user.id))
            print(EncodedUserId)
            token = PasswordResetTokenGenerator().make_token(user)
            print('Password ResetToken:',token)
            PassResetLink = f'{base_url}/api/user/rest-password/'+EncodedUserId+'/'+token+'/'
            print('PassResetLink:',PassResetLink)

            #Email Send Code
            bodyContent = 'Click here to RESET YOUR PASSWORD: '+PassResetLink
            data={
                'subject': 'Reset Your Password',
                'body': bodyContent,
                'to_email': user.email

            }
            email_sent=send_email(data)
            if not email_sent:
                raise ValidationError("Failed to send password reset email. Please try again later.")
            
            return attrs
        else:
            raise ValidationError("Email not registered in central Database!")
        
class VerifyEmailSerializer(serializers.Serializer):
    otp_code = serializers.CharField(max_length=6)

# For User data pass
class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        exclude = ['password']

class UserLoginSerializer(serializers.ModelSerializer):
        email = serializers.CharField(max_length=20)
        class Meta:
            model = User
            fields = ['email', 'password',]

        def validate(self, data):
            email = data.get('email')
            password = data.get('password')

            user = authenticate(email=email, password=password)
            
            if user is not None:
                if not user.is_active:
                    raise AuthenticationFailed('Account disabled, contact with Administrator')

                # Update last_login time for the user
                user.last_login = timezone.now()
                user.save()

                # Return both the authenticated user and validated data
                return {'user': user, 'data': data}
            else:
                raise AuthenticationFailed(f'Invalid credentials, Please try again with correct credentials')
            
class UserRegistrationSerializer(serializers.ModelSerializer):
    
    confirm_password = serializers.CharField(style={'input_type': 'password'}, write_only=True)

    class Meta:
        model = User
        fields = ['name','email', 'phone_no','date_of_birth','password','confirm_password']
        extra_kwargs = {
            'password':{'write_only':True}
        }

    
    def validate(self, attrs):
        password = attrs.get('password')
        confirm_password = attrs.get('confirm_password')
        email = (attrs.get('email')).lower()
        print('Email-From-Validation:', email)
        #validate password and confirm password is same
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(f"{email} with this email already exists.")
        #validate password and confirm password is same
        if(password != confirm_password):
            raise serializers.ValidationError("Confirm password not match with password!")

        return attrs
    
    def create(self, validated_data):
        return User.objects.create_user(**validated_data)