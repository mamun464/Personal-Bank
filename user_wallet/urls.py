from django.urls import path
from user_wallet.views import *

urlpatterns = [
    path('transaction/', TransactionAPIView.as_view(), name='transaction'),
    # path('withdraw', WithdrawMoneyView.as_view(), name='withdraw-money'),

    # path('transaction-history/', TransactionHistoryView.as_view(), name='transaction-history'),
    # path('transaction/', WalletTransactionDetailView.as_view(), name='transaction-detail'),

    # path('balance/', WalletBalanceView.as_view(), name='wallet-balance'),

    

    # path('withdraw-details/', WithdrawRequestDetailView.as_view(), name='withdraw-request-detail'),


]