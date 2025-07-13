from rest_framework import serializers
from .models import WalletTransaction
from account.serializer import UserProfileSerializer
from account.permissions import AUTHORIZED_ROLES
from account.permissions import is_user_verified
from account.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'phone_no', 'role', 'user_profile_img'] 
class WalletTransactionListSerializer(serializers.ModelSerializer):
    customer = UserSerializer(read_only=True)
    processed_by = UserSerializer(read_only=True)
    class Meta:
        model = WalletTransaction
        fields = '__all__'
class WalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WalletTransaction
        fields = [
            'id',
            'transaction_id',
            'date_of_transaction',
            'customer',
            'transaction_type',
            'payment_method',
            'amount',
            'document_photo_url',
            'receipt_reference_no',
            'processed_by',
        ]
        read_only_fields = ['id', 'transaction_id']

    def validate(self, attrs):
        processed_by = attrs.get('processed_by')
        payment_method = attrs.get('payment_method')
        receipt_reference_no = attrs.get('receipt_reference_no')
        document_photo_url = attrs.get('document_photo_url')
        customer = attrs.get('customer')
        transaction_type = attrs.get('transaction_type')
        
        # ✅ Check if customer is verified
        if not is_user_verified(customer):
            raise serializers.ValidationError({
                "customer": "Customer is not verified or active."
            })     

        # ✅ Bank transfer-specific validation
        if transaction_type == 'deposit' and payment_method == 'bank_transfer':
            if not receipt_reference_no:
                raise serializers.ValidationError({
                    'receipt_reference_no': 'This field is required for bank transfer deposits.'
                })
            if not document_photo_url:
                raise serializers.ValidationError({
                    'document_photo_url': 'This field is required for bank transfer deposits.'
                })
        else:
            # ✅ In all other cases, nullify these fields
            attrs['receipt_reference_no'] = None
            attrs['document_photo_url'] = None

        # ✅ Role-based permission check
        if processed_by and processed_by.role.lower() not in AUTHORIZED_ROLES:
            raise serializers.ValidationError({
                "processed_by": "Only admin, employee, or CEO can be assigned as 'processed_by'."
            })

        # ✅ Prevent self-processing
        if processed_by and processed_by.id == customer:
            raise serializers.ValidationError({
                "processed_by": "You cannot process your own transactions."
            })

        return attrs

    def create(self, validated_data):
        request = self.context.get('request')
        user = request.user

        validated_data['processed_by'] = user
        return super().create(validated_data)