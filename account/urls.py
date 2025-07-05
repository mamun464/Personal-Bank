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
    
]