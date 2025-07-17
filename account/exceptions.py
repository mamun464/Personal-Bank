# exceptions.py

from rest_framework.views import exception_handler
from rest_framework.response import Response

def custom_exception_handler(exc, context):
    # Call Django REST Framework's default exception handler first
    response = exception_handler(exc, context)

    # Customize the error response format if it exists
    if response is not None:
        response.data = {
            "success": False,
            "status": response.status_code,
            "message": response.data['detail'] if 'detail' in response.data else str(exc)
        }

    return response
