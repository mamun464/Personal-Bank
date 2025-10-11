from django.urls import path
from account.views import *
urlpatterns = [
    path('register/', UserRegistrationView.as_view(),name='register'),
    path('login/', UserLoginView.as_view(),name='login'),

    path("verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("resend-otp/", ResendOtpView.as_view(), name="resend-otp"),
    path("check-email-verified/", CheckEmailVerifiedView.as_view(), name="check-email-verified"),

    path('send-reset-link/', SendPasswordResetEmailView.as_view(),name='send-reset-link'),
    path('rest-password/<uid>/<token>/', UserPasswordResetView.as_view(),name='rest-password'),

    path('user-list/', UserListView.as_view(), name='user-list'),
    
    path('change-active-status/', ChangeUserActiveStatusView.as_view(), name='change-active-status'),
    path('update-profile/', UpdateOwnProfileView.as_view(), name='update-own-profile'),
    path('user-update/<int:user_id>/', UserUpdateAPIView.as_view(), name='user-update'),
    path('profile/', UserProfileDetailView.as_view(), name='user-profile-detail'),
    
]
