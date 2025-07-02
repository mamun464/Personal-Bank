
from rest_framework import serializers
from account.models import User
from django import forms
from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed
from django.utils import timezone


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