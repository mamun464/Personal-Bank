from django.db import models
import uuid
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.utils.timezone import now
import secrets
import random
from django.core.exceptions import ValidationError


# Create your UserManager here.
class UserManager(BaseUserManager):
    def create_user(self, name, email, phone_no, password=None, confirm_password=None,**extra_fields,):

        # print(f"Input: {email}")
        
        if not name:
            raise ValueError("Name must be provided")
        if not phone_no:
            raise ValueError("Phone No. must be provided")
        if not email:
            raise ValueError("email must be provided")
        if not password:
            raise ValueError('Password is not provided')

        extra_fields.setdefault('is_active',True)
        extra_fields.setdefault('is_staff',False)
        extra_fields.setdefault('is_superuser',False)

        user = self.model(
            name = name,
            email=email.lower(),
            phone_no = phone_no,
            **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        # print(user)
        return user

    def create_superuser(self, name, email, phone_no, password, **extra_fields):
        extra_fields.setdefault('is_staff',True)
        extra_fields.setdefault('is_superuser',True)
        extra_fields.setdefault('role','admin')
        return self.create_user(
            name=name,
            email=email,
            phone_no=phone_no,
            password=password,
            **extra_fields
            )
    


# Create your User Model here.
class User(AbstractBaseUser,PermissionsMixin):
    # Abstractbaseuser has password, last_login, is_active by default
    # mendatory Fields
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = None
    name = models.CharField(max_length=100, null=False)
    email = models.EmailField(db_index=True, unique=True,null=False, max_length=254)
    phone_no=models.CharField(db_index=True,max_length=20, null=False,unique=True)
    date_of_birth = models.DateField(null=True, blank=True)
    is_verified =models.BooleanField(default=False)

    # Non mandatory Fields
    user_profile_img = models.URLField(blank=True,null=True)
    role = models.CharField(max_length=20, choices=[('customer', 'Customer'), ('admin', 'Admin'),('CEO', 'CEO'),('employee', 'Employee')], default='customer')

    is_staff = models.BooleanField(default=False) # must needed, otherwise you won't be able to loginto django-admin.
    is_active = models.BooleanField(default=True) # must needed, otherwise you won't be able to loginto django-admin.
    is_superuser = models.BooleanField(default=False) # this field we inherit from PermissionsMixin.

    created_at = models.DateTimeField(auto_now_add=True,editable=False)
    updated_at = models.DateTimeField(null=True, blank=True)  # Set only on updates

    

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name','phone_no']

    class Meta:
        verbose_name = 'User'
        verbose_name_plural = 'Users'

        constraints = [
        models.UniqueConstraint(
            fields=['role'],
            condition=models.Q(role='CEO'),
            name='unique_ceo_role'
        )
    ]


    def save(self, *args, **kwargs):
        # --- Prevent multiple CEOs ---
        if self.role == 'CEO':
            # Exclude current instance if updating
            existing_ceo = User.objects.filter(role='CEO').exclude(pk=self.pk)
            if existing_ceo.exists():
                raise ValidationError("There can be only one CEO in the system.")

        if self.pk is not None:
            # Check if this is an update (object exists in DB)
            if User.objects.filter(pk=self.pk).exists():
                self.updated_at = now()
        super(User, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.phone_no})"

    def has_perm(self, perm, obj=None):
        "Does the user have a specific permission?"
        # Simplest possible answer: Yes, always
        return self.is_superuser

    def has_module_perms(self, app_label):
        "Does the user have permissions to view the app `app_label`?"
        # Simplest possible answer: Yes, always
        return True
    

def generate_otp_code():
    return secrets.token_hex(3)

class OtpToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otps")
    otp_code = models.CharField(max_length=6, editable=False, default=generate_otp_code)
    otp_created_at = models.DateTimeField(auto_now_add=True)
    otp_expires_at = models.DateTimeField(blank=True, null=True)
    max_otp_try = models.IntegerField(default=3)
    max_otp_try_expires = models.DateTimeField(blank=True, null=True)
    is_used = models.BooleanField(default=False)
    
    
    def __str__(self):
        return self.user.email

def generate_unique_job_id():
    """Generate a unique 10-digit integer job ID."""
    return random.randint(1000000000, 9999999999)
