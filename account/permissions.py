# permissions.py
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied


class CanChangeActiveStatus(BasePermission):
    """
    Custom permission to allow only admin and manager to update is_active status.
    Managers cannot update their own status.
    """

    def has_permission(self, request, view):
        requester = request.user
        user_id = view.kwargs.get('user_id')  # from the URL

        if requester.role not in ['admin', 'manager', 'employee']:
            raise PermissionDenied("Only admin or employee can perform this action.")

        if requester.role == 'manager' and str(requester.id) == user_id:
            raise PermissionDenied("Managers are not allowed to change their own active status.")

        return True
    
authorized_role=['admin', 'employee', 'CEO']
@staticmethod
def is_authorized_role(user):
    return user and user.role in ['admin', 'employee', 'CEO']

