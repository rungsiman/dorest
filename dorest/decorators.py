"""Dorest's endpoint and Django-related decorators

The Dorest project
:copyright: (c) 2020 Ichise Laboratory at NII & AIST
:author: Rungsiman Nararatwong
"""

import importlib
from functools import wraps
from typing import Any, Callable, List, Union

from django.conf import settings
from django.utils.translation import ugettext_lazy as _

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from dorest.glossary import Glossary


def endpoint(methods: List[str], default: bool = False, throttle: str = 'base', requires: Union[tuple, list] = None,
             include_request: str = None) -> Callable[..., Any]:
    """Intercept requests and transform them into function calls with arguments

    :param methods: HTTP request method
    :param default: Set as module's default endpoint in case no specific function or class name is specified in the request
    :param throttle: Throttle type
    :param requires: A list of required access permissions
    :param include_request: Include 'request' parameter in the function call
    :return: An output of the function as Django REST Framework's Response object,
             or the target function if called directly (not as an endpoint)
    """

    endpoint.meta = locals()

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            if len(args) == 1 and isinstance(args[0], Request):
                try:
                    request = args[0]

                    # Extract request's body from requests using methods other than GET
                    body = {key: value for key, value in request.data.items()}
                    parameters = request.META[Glossary.META_ENDPOINT.value].parse(**{**dict(request.GET), **body})

                    if include_request is not None:
                        parameters[include_request] = request

                    # A request is handled differently based on how the endpoint is defined (as a class or a function)
                    if Glossary.META_CLASS.value in request.META and request.META[Glossary.META_CLASS.value] is not None:
                        return Response({'data': func(request.META[Glossary.META_CLASS.value][1], **parameters)}, status=status.HTTP_200_OK)
                    else:
                        return Response({'data': func(**parameters)}, status=status.HTTP_200_OK)

                except TypeError as error:
                    return Response({'detail': str(error)}, status=status.HTTP_400_BAD_REQUEST)

            else:
                return func(*args, **kwargs)

        if hasattr(settings, 'DOREST'):
            throttle_class = settings.DOREST.get('DEFAULT_THROTTLE_CLASSES', None)

            if throttle_class is not None and len(throttle_class) > 0:
                throttle_class_branch = [node.split('.') for node in throttle_class]
                wrapper.throttle_classes = [getattr(importlib.import_module('.'.join(node[:-1])), node[-1]) for node in throttle_class_branch]

        wrapper.meta = endpoint.meta

        if requires is not None:
            wrapper.permission_classes = requires

        return wrapper

    return decorator


def require(validators: Union[tuple, list]):
    """Django's standard permission_required decorator does not recognize 'user' in 'request'
    received from Django rest_framework's APIView, resulting in the user being treated as anonymous.

    This custom implementation solves the issue, as well as removes a redirect URL since
    this channel of communication does not provide a user interface.

    :param: validators: A tuple of permission validators.
                        By default, a user must have all required permissions to perform an action.
                        However, if only one permission was needed, set 'or' as the first member of the tuple.

                        For example:
                        (p1, p2, ('or', p3, p4))
                        In this case, a user must have permissions p1 and p2, and she must also have p3 or p4
                        in order to perform an action.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            """Receive HTTP request handler (function) of Django rest_framework's APIView class.
            ---

            args: [0] an object of a class inherited from Django's view
                  [1] an object of rest_framework.request.Request
            """

            if 'request' in kwargs and _require_operator(validators, **kwargs):
                return func(*args, **kwargs)
            elif _require_operator(validators, args[1], args[0], **kwargs):
                return func(*args, **kwargs)
            else:
                return Response({'detail': _('Permission required')}, status=403)

        return wrapper

    return decorator


def _require_operator(validators: Union[tuple, list], request: Request, view: APIView, **kwargs) -> bool:
    """Validate and applie AND operator on the results produced by the validators

    :param validators: A tuple of validators
    :param request: A request sent from Django REST framework
    :param view: Django REST framework API view
    :param kwargs: Validator's argument
    :return: Validation result
    """

    def validate(validator):
        if type(validator) is tuple or type(validator) is list:
            return _require_operator(validator, request, view)

        elif type(validator) is str:
            return request.user.has_perm(validator)

        else:
            validator_instance = validator()

            try:
                return validator_instance.has_permission(request, view, **kwargs)
            except TypeError:
                return validator_instance.has_permission(request, view)

    # 'operator_or()' returns a list with 'or' as its first member
    if type(validators) is not tuple and type(validators) is not list:
        return validate(validators)

    elif validators[0] == 'or':
        return any([validate(v) for v in validators[1:]])

    elif validators[0] == 'not':
        return not validate(validators[1])

    else:
        return all([validate(v) for v in validators])


def operator_or(*args):
    """Another form of 'or' operator in 'permissions._require_operator'.
    Instead of setting the first member of the tuple as 'or', e.g., 'permissions.require(p1, p2, ("or", p3, p4))',
    this function offers a different format that does not include an operator as a member.

    For convenience, import this function as '_or'.
    The above example can then be written as 'permissions.require(p1, p2, _or(p3, p4))'.
    """

    return ('or',) + args


def operator_not(validator):
    """Another form of 'not' operator in 'permissions._require_operator'.

    Warning: While 'permissions.operator_or' accepts multiple arguments, this operator accepts only one validator
    """

    return 'not', validator


def mandate(**params):
    """Check whether all required request parameters are included in an HTTP request to an APIView
    :param params: parameter 'fields' contains required request parameters
                   parameter 'strict_fields' are 'fields' that cannot be blank
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            """Receive HTTP request handler (function) of Django rest_framework's APIView class."""

            # Assign rest_framework.request.Request object to 'request' variable, which is to be validated
            request = args[1]

            missings = []
            blanks = []
            fields = params['fields'] if 'fields' in params else [] + params['strict_fields'] if 'strict_fields' in params else []
            strict_fields = params['strict_fields'] if 'strict_fields' in params else []

            for kwarg in fields:
                if kwarg not in request.data and kwarg not in request.GET:
                    missings.append(kwarg)

            for kwarg in strict_fields:
                if kwarg in request.data and len(request.data[kwarg]) == 0:
                    blanks.append(kwarg)

            if len(missings) > 0 or len(blanks):
                return Response({'detail': _('Parameters missing or containing blank value'),
                                 'missing': missings,
                                 'blank': blanks}, status=400)

            return func(*args, **kwargs)

        return wrapper

    return decorator
