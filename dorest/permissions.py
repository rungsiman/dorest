"""Implementations of additional Django REST Framework permission validators

The Dorest project
:copyright: (c) 2020 Ichise Laboratory at NII & AIST
:author: Rungsiman Nararatwong
"""

from django.core.exceptions import ObjectDoesNotExist

from rest_framework.permissions import BasePermission


class OR(BasePermission):
    """'Or' operator for rest_framework's permission_classes"""

    def __init__(self, *args):
        self.validators = args

    def __call__(self, *args, **kwargs):
        return self

    def has_permission(self, request, view):
        return any(validator().has_permission(request, view) for validator in self.validators)


class NOT(BasePermission):
    """'Not' operator for rest_framework's permission_classes"""

    def __init__(self, validator):
        self.validator = validator

    def __call__(self, *args, **kwargs):
        return self

    def has_permission(self, request, view):
        return not self.validator().has_permission(request, view)


class IsAccountOwner(BasePermission):
    """Validate whether the target account in the request URL is owned by the user sending the request"""

    def has_permission(self, request, view, **kwargs):
        try:
            return kwargs['username'] == request.user.username
        except ObjectDoesNotExist:
            return False


class IsAccountManager(BasePermission):
    """Validate whether the account sending the request has the permission to manage other accounts"""

    def has_permission(self, request, view):
        return len(request.user.groups.filter(name='user_manager')) > 0


class IsDemoUser(BasePermission):
    """Validate whether the account is for demonstration"""

    def has_permission(self, request, view):
        return len(request.user.groups.filter(name='user_demo')) > 0


class IsTrustedUser(BasePermission):
    """Validate whether the account is trusted"""

    def has_permission(self, request, view):
        return len(request.user.groups.filter(name='user_trusted')) > 0
