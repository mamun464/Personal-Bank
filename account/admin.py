from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import User


class UserAdmin(BaseUserAdmin):
    ordering = ['email']
    list_display = [
    'id', 'email', 'name', 'phone_no', 'date_of_birth', 'user_profile_img', 
    'role', 'is_active', 'is_staff', 'is_superuser', 'created_at', 'updated_at'
    ]

    list_filter = ['role', 'is_active', 'is_staff', 'is_superuser']

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        (_('Personal Info'), {'fields': ('name', 'phone_no', 'date_of_birth', 'user_profile_img')}),
        (_('Permissions'), {'fields': ('is_active', 'is_staff', 'is_superuser', 'role', 'groups', 'user_permissions')}),
        (_('Important Dates'), {'fields': ('last_login', 'created_at', 'updated_at')}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('name', 'email', 'phone_no', 'password1', 'password2', 'role', 'is_active', 'is_staff'),
        }),
    )

    search_fields = ['email', 'name', 'phone_no']


admin.site.register(User, UserAdmin)
