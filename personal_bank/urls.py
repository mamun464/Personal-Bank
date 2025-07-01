from django.urls import path, include, re_path
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('user-api/', include('account.urls')),
]
