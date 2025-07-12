from django.contrib import admin
from .models import Wallet,WalletTransaction

class WalletAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'account_balance', 'created_at', 'updated_at')
    search_fields = ('user__name', 'user__email')  # Adjust field names to your User model
    list_filter = ('created_at', 'updated_at')
    ordering = ('-created_at',)

class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = (
        'transaction_id', 'customer', 'date_of_transaction', 'transaction_type', 
        'payment_method', 'amount', 'processed_by', 'created_at', 'updated_at'
    )
    list_filter = ('transaction_type', 'payment_method', 'date_of_transaction', 'created_at')
    search_fields = (
        'transaction_id', 'customer__name', 'customer__email', 'receipt_reference_no', 'processed_by__name'
    )
    readonly_fields = ('transaction_id', 'created_at', 'updated_at')
    ordering = ('-date_of_transaction', '-created_at')

    fieldsets = (
        (None, {
            'fields': (
                'transaction_id', 'customer', 'date_of_transaction', 'transaction_type', 'payment_method', 
                'amount', 'document_photo_url', 'receipt_reference_no', 'processed_by'
            )
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
admin.site.register(WalletTransaction, WalletTransactionAdmin)
admin.site.register(Wallet, WalletAdmin)
