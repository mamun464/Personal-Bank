import uuid
from django.db import models
from django.utils.timezone import now
from account.models import User  # Replace 'your_app' with the actual app where your User model is defined
from django.core.exceptions import ValidationError
from django.db.models.signals import pre_save
from django.dispatch import receiver
import random
import string
from account.permissions import AUTHORIZED_ROLES

class Wallet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.PROTECT, related_name="wallet")
    account_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.pk is not None:
            # Check if this is an update (object exists in DB)
            if Wallet.objects.filter(pk=self.pk).exists():
                self.updated_at = now()
        super(Wallet, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.name}'s Wallet with Balance: {self.account_balance}"



def generate_unique_transaction_id():
    """Generate a unique 10-character alphanumeric transaction ID."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))

class WalletTransaction(models.Model):
    TRANSACTION_TYPE_CHOICES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('payment_out', 'Payment Out')
    ]

    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('wallet', 'Wallet'),
        ('other', 'Other'),
        
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.CharField( max_length=15,unique=True,editable=False)
    customer = models.ForeignKey(User, on_delete=models.PROTECT, related_name="transactions_User")
    date_of_transaction = models.DateField(null=False, blank=False,default=now)
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPE_CHOICES)
    payment_method = models.CharField(max_length=50, choices=PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    document_photo_url = models.URLField(max_length=1024, null=True, blank=True)  # Allow null/blank
    receipt_reference_no = models.CharField(unique=True, max_length=255, null=True, blank=True)  # Allow null/blank
    
    processed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="processed_withdrawals")
    
    created_at = models.DateTimeField(auto_now_add=True)  # Set only on creation
    updated_at = models.DateTimeField(null=True, blank=True)  # Set only on updates

    def save(self, *args, **kwargs):
        """
        Override the save method to always call clean before saving.
        """
        self.clean()  # Call the clean method to perform validation
        if self.pk is not None:
            # Check if this is an update (object exists in DB)
            if WalletTransaction.objects.filter(pk=self.pk).exists():
                self.updated_at = now()
        super(WalletTransaction, self).save(*args, **kwargs)
        

    def clean(self):
        """
        Add conditional validation for mandatory fields based on transaction type.
        """
        if self.transaction_type in ['deposit'] and self.payment_method == 'bank_transfer' and not self.receipt_reference_no:
            raise ValidationError({'receipt_reference_no': 'This field is required for this Transaction Type.'})
        if self.transaction_type in ['deposit'] and self.payment_method == 'bank_transfer' and not self.document_photo_url:
            raise ValidationError({'document_photo_url': 'This field is required for this Transaction Type.'})
        
        if self.processed_by and self.processed_by.role not in AUTHORIZED_ROLES:
            raise ValidationError("Only admin, employee, or CEO can be assigned as 'processed_by'")

    def __str__(self):
        return f"({self.customer.name}) - {self.transaction_type} - {self.amount}"


@receiver(pre_save, sender=WalletTransaction)
def add_transaction_id(sender, instance, **kwargs):
    """Assign a unique transaction_id if not already set."""
    if not instance.transaction_id:
        while True:
            transaction_id = generate_unique_transaction_id()
            if not WalletTransaction.objects.filter(transaction_id=transaction_id).exists():
                instance.transaction_id = f"TX{transaction_id}"
                break
