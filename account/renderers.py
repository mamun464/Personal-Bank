from rest_framework import renderers
import json
from decimal import Decimal

class UserRenderer(renderers.JSONRenderer):
    charset = 'utf-8'
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = ''
        # print("Inside Render funtion")
        if 'ErrorDetail' in str(data):
            # print("Inside ErrorDetails funtion")
            response = json.dumps(data)
        else:
            response = json.dumps(data)
            # print("Inside Else funtion")

        return response
    
class UserRendererWithDecimal(renderers.JSONRenderer):
    charset = 'utf-8'
    
    def render(self, data, accepted_media_type=None, renderer_context=None):
        # Custom method to handle Decimal type
        def decimal_default(obj):
            if isinstance(obj, Decimal):
                return str(obj)  # Convert Decimal to string
            raise TypeError(f"Type {obj.__class__.__name__} not serializable")

        response = ''
        
        # Check if the response contains an 'ErrorDetail'
        if 'ErrorDetail' in str(data):
            response = json.dumps(data, default=decimal_default)
        else:
            response = json.dumps(data, default=decimal_default)
        
        return response