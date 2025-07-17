# permissions.py
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from account.models import User
from uuid import UUID


AUTHORIZED_ROLES = ['admin', 'CEO', 'employee']
ROLE_HIERARCHY = {
    'admin': 3,
    'CEO': 2,
    'employee': 1,
    'customer': 0
}

class CanChangeActiveStatus(BasePermission):
    """
    Custom permission to allow only authorized users to change is_active status.
    - Only users with roles in AUTHORIZED_ROLES can perform the action.
    - Users cannot change their own status.
    - Users cannot change the status of others with the same or higher role.
    """

    def has_permission(self, request, view):
        requester = request.user
        user_id = view.kwargs.get('user_id')  # Assuming user_id is in the URL

        if requester.role not in AUTHORIZED_ROLES:
            raise PermissionDenied("Only authorized users can perform this action.")

        if str(requester.id) == user_id:
            raise PermissionDenied("You are not allowed to change your own active status.")

        target_user = get_object_or_404(User, id=user_id)

        if ROLE_HIERARCHY[requester.role] <= ROLE_HIERARCHY[target_user.role]:
            raise PermissionDenied("You cannot change the status of a user with the same or higher role.")

        return True

    
class IsAuthorizedUser(BasePermission):
    """
    Grants access only to users with roles in AUTHORIZED_ROLES.
    """

    def has_permission(self, request, view):
        if request.user.role in AUTHORIZED_ROLES:
            return True
        raise PermissionDenied("You do not have permission to perform this action.")
    
class TargetUserMustBeCustomer(BasePermission):
    """
    Allows access only if the 'customer' in request data has role='customer'.
    """

    def has_permission(self, request, view):
        customer_id = request.data.get('customer')

        if not customer_id:
            raise PermissionDenied("Customer ID is required.")

        try:
            try:
                valid_uuid = UUID(customer_id)
            except ValueError:
                raise PermissionDenied("Invalid customer ID. Must be a valid UUID.")
            customer = User.objects.get(id=customer_id)
        except User.DoesNotExist:
            raise PermissionDenied("Customer not found.")

        if customer.role != 'customer':
            raise PermissionDenied("Only users with role 'customer' can be assigned balances.")

        return True
    
class IsUserVerifiedAndEnabled(BasePermission):
    """
    Allows access only to users who are email-verified and active.
    """

    def has_permission(self, request, view):
        user = request.user

        if not user.is_authenticated:
            raise PermissionDenied("Authentication credentials were not provided.")

        if not user.is_active:
            raise PermissionDenied("Your account is not active. Please contact support.")

        if not getattr(user, 'is_verified', False):
            raise PermissionDenied("Your email address is not verified. Please verify your email to continue.")

        return True
    
class IsNotCustomerSelf(BasePermission):
    """
    Prevent users from performing wallet transactions on themselves.
    """

    def has_permission(self, request, view):
        # Allow all requests to pass this permission phase
        return True

    def has_object_permission(self, request, view, obj):
        # Only used if object-level permission check is triggered
        return obj.customer.id != request.user.id

    def has_permission(self, request, view):
        customer_id = request.data.get('customer')
        if str(request.user.id) == str(customer_id):
            raise PermissionDenied("You are not allowed to operate on your own wallet.")
        return True

@staticmethod
def is_authorized_role(user):
    return user and user.role in AUTHORIZED_ROLES

@staticmethod
def is_user_verified(user):
    """
    Returns True if the user is verified and active.
    Accepts either a User instance or a UUID.
    """
    try:
        if isinstance(user, UUID) or isinstance(user, str):
            user = User.objects.get(id=user)
        return user.is_verified and user.is_active
    except (User.DoesNotExist, ValueError, TypeError):
        return False

