"""Structured-endpoint manager

The Dorest project
:copyright: (c) 2020 Ichise Laboratory at NII & AIST
:author: Rungsiman Nararatwong
"""

import importlib
import inspect
import re
import os
import sys
from functools import partial
from typing import Any, Callable, List, Tuple, Type, Union
from types import ModuleType

from django.conf import settings
from django.core.handlers.wsgi import WSGIRequest
from django.urls import include, path, re_path, resolve
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from dorest.glossary import Glossary
from dorest.meta import Endpoint
from dorest import meta


def _get_module(module: Union[str, ModuleType]) -> ModuleType:
    return getattr(sys.modules, module, importlib.import_module(module)) if isinstance(module, str) else module


def _get_endpoint(method: str, branch: str, module: ModuleType = None) -> Tuple[Callable[..., Any], Union[Type, None]]:
    """Resolve the target endpoint from an API request

    A branch, within tree-structure packages, may either include a module or an endpoint function as a leaf.

    This function first assumes that the branch only include hierarchical packages as its nodes and the target module as its leaf.
    In the 'try' clause, the function will try to look for any default endpoints that matches the request method;
    if not found, it will try to find redirect operators that matches the request method, then look for the endpoint within the redirected module.

    If the branch contains an endpoint function as a leaf, the 'importlib.import_module' will fail to import and skip to the 'except' clause.

    :param method: An endpoint may accept multiple HTTP methods, the 'method' parameter specifies which method to be looking for
    :param branch: A string that indicates a branch containing packages as nodes and a module, function, or class as a leaf (e.g. 'pkg_a.pkg_b.leaf')
    :param module: A direct reference to the module which contains the endpoint. If set, the function will skip 'importlib.import_module'
    :return: A tuple containing the target endpoint function and, if applicable, its class (current version only support endpoint functions)
    """

    try:
        imported_module, endpoint_function = importlib.import_module(branch), None

        for func in [obj for obj in [getattr(imported_module, attr) for attr in dir(imported_module)]
                     if hasattr(obj, 'meta') and getattr(obj, '__module__', None) == imported_module.__name__]:
            if func.meta['default']:
                return func, None
            endpoint_function = func

        if endpoint_function is not None:
            return endpoint_function, None

        else:
            obj = getattr(imported_module, Glossary.REDIRECT.value)[method.lower()]

            if inspect.isfunction(obj):
                return obj, None
            else:
                return _get_endpoint(method, getattr(imported_module, Glossary.REDIRECT.value)[method.lower()].__name__)

    except ModuleNotFoundError:
        path = branch.split('.')
        target_function = path[-1]
        imported_module = importlib.import_module('.'.join(path[:-1])) if module is None else module
        obj = getattr(imported_module, target_function, None)

        if inspect.isfunction(obj) and hasattr(obj, 'meta'):
            if method in obj.meta['methods']:
                return obj, None
            else:
                raise MethodNotAllowed(method)

        else:
            raise AttributeError("Could not find endpoint '%s' with HTTP request method '%s' in '%s'" % (target_function, method, module))


def walk_endpoints(branch: str, reduce: bool = False) -> dict:
    """Walk and generate descriptions of structured API endpoints

    The structure of the returned dictionary is as followed:
    ---
        {
            'package': {
                'subpackage': {
                    'module': {
                        '*': [ ... function descriptions ... ]
                    }
                }
            }
        }
    ---

    In case the structural organization of an API results in some packages containing only one subpackage or module (other than the package's
    __init__.py), with the 'reduce' parameter true, all sequences of these packages will be merged in the returned dictionary.
    When reduced, the above example will become:
    ---
        {
            'package/subpackage/module': {
                '*': [ ... function descriptions ... ]
            }
        }
    ---

    :param branch: The root of structured API endpoints (or a part of interest within the structure)
    :param reduce: Reduce the returned dictionary
    :return: A description of the tree
    """

    def attach_endpoint(sub_api_tree: dict, sub_branch: List[str], endpoint: callable) -> None:
        if len(sub_branch):
            sub_branch_head = sub_branch.pop(0)

            if sub_branch_head not in sub_api_tree:
                sub_api_tree[sub_branch_head] = dict()

            attach_endpoint(sub_api_tree[sub_branch_head], sub_branch, endpoint)

        else:
            if '*' not in sub_api_tree:
                sub_api_tree['*'] = [Endpoint(endpoint).rest(brief=True)]
            else:
                sub_api_tree['*'].append(Endpoint(endpoint).rest(brief=True))

    root_module = importlib.import_module(branch)
    root_path = os.path.dirname(root_module.__file__)

    # Generate a list of all Python scripts
    py_files = [os.path.join(dirpath, filename) for dirpath, dirnames, filenames in os.walk(root_path) for filename in filenames
                if os.path.splitext(filename)[1] == '.py']

    # Generate a list of all modules for import from the list of Python scripts
    modules = [('%s.%s' % (branch, py_file.replace(os.path.dirname(root_module.__file__), '').replace('__init__', '').replace('.py', '')
                           .replace('/', '.').strip('.'))).strip('.') for py_file in py_files]

    # Remove the root endpoint
    modules = [module for module in modules if module != branch]
    api_tree = dict()

    # Fill the API tree with descriptions of the functions
    for module in modules:
        sub_module = importlib.import_module(module)
        funcs = [obj for obj in [getattr(sub_module, attr) for attr in dir(sub_module)]
                 if hasattr(obj, 'meta') and hasattr(obj, '__module__') and obj.__module__ == sub_module.__name__]
        sub_branch = module.replace(branch, '').strip('.')

        for func in funcs:
            attach_endpoint(api_tree, sub_branch.split('.'), func)

    return api_tree if not reduce else Endpoint.reduce(api_tree)


@api_view(['DELETE', 'GET', 'PATCH', 'POST', 'PUT'])
@permission_classes([AllowAny])
def _reply(request: WSGIRequest, topic: str, message: Union[dict, str], status: int) -> Response:
    """Create Django REST Framework's Response object from a text message

    :param request: A request sent from Django REST Framework (despite not being used, this parameter is mandatory)
    :param topic: The topic of the message
    :param message: The message
    :param status: HTTP status code
    :return: Django REST Framework's Response object
    """

    return Response({topic: message}, status=status)


def handle(request: WSGIRequest, root: Union[str, ModuleType]) -> Response:
    """Handle a redirected request from Django REST Framework, call the target endpoint and gets the result, then create a wrapped response

    This function also provides special responses, which are either an API structure or a detailed description of specific endpoint function.
    To get an API structure, append '?**' after a parent endpoint.

    For example, suppose an API is structured as followed:
    ~~~~~~~~~~~~~~~~~~~~~~~
        + parent_pkg
        | + pkg_a
        | |- module_a.py
        | |- module_b.py
        | + pkg_b
        | | + pkg_c
        | | |- module_c.py
    ~~~~~~~~~~~~~~~~~~~~~~~
    and the root of the structured endpoints is 'http://domain/api/parent_pkg', which points to the 'parent_pkg' package,
    a GET request with URI 'http://domain/api/parent_pkg?**' will return the description of the 'parent_pkg' package, including its
    subpackages, modules, and endpoint functions. 'http://domain/api/parent_pkg/pkg_a?**' will return only those within the 'pkg_a' package.

    In case the structural organization of an API results in some packages containing only one subpackage or module (other than the package's
    __init__.py), appending the 'reduce' key to the request URI will merge all sequences of these packages. In the above example,
    'http://domain/api/parent_pkg?**&reduce' will return the API structure with 'pkg_b/pkg_c/module_c' keyword.

    To get a description of a particular endpoint function, append '?*' to the URI, e.g., 'http://domain/api/parent_pkg/pkg_a/module_a/func?*'

    :param request: A request sent from Django REST Framework
    :param root: The root package of the structured endpoints
    :return: Django REST Framework's Response object
    """

    # 'request.GET' is a QueryDict. When appending '?**' to the URI, '**' becomes a dictionary key
    if '**' in request.GET:
        route = re.sub(r'\.\*$', '', resolve(request.path_info).route)
        branch = ('%s.%s' % (root if isinstance(root, str) else root.__name__, re.sub(r'^/%s' % route, '', request.path).replace('/', '.'))).strip('.')
        return _reply(request, 'api', walk_endpoints(branch, 'reduce' in request.GET), status.HTTP_200_OK)

    else:
        route = re.sub(r'\.\*$', '', resolve(request.path_info).route)
        branch = '%s.%s' % (root if isinstance(root, str) else root.__name__, re.sub(r'^/%s' % route, '', request.path).replace('/', '.'))

        # Given the request URI and method, try to find the target endpoint
        try:
            endpoint, request.META[Glossary.META_CLASS.value] = _get_endpoint(request.method, branch, root if isinstance(root, str) else None)
            request.META[Glossary.META_ENDPOINT.value] = meta.Endpoint(endpoint)
        except MethodNotAllowed as error:
            return _reply(request, 'detail', error.detail, status.HTTP_403_FORBIDDEN)
        except AttributeError as error:
            return _reply(request, 'detail', str(error), status.HTTP_403_FORBIDDEN)

        if '*' in request.GET:
            return _reply(request, 'help', request.META[Glossary.META_ENDPOINT.value].rest(brief='brief' in request.GET), status.HTTP_200_OK)
        else:
            view = api_view([request.method])(endpoint)

            if hasattr(settings, 'REST_FRAMEWORK'):
                throttle_rates = settings.REST_FRAMEWORK.get('DEFAULT_THROTTLE_RATES', None)

                if throttle_rates is not None and getattr(endpoint, 'meta')['throttle'] in throttle_rates:
                    view.view_class.throttle_custom_scope = getattr(endpoint, 'meta')['throttle']

            return view(request)


def redirect(*, methods: List[str], at: Union[str, ModuleType], to: [str, ModuleType]) -> None:
    """Redirect an API request to the target module containing endpoints

    To redirect an API request, call this function in the redirecting module
    Since the call is in the redirecting module, the 'at' parameter should normally be '__name__', e.g.:
    ---
        redirect(methods=['GET'], at=__name__, to='api.target.func')
    ---

    This function sets the redirect attribute of the module in which it is called.
    The attribute will later be evaluated and acted upon by the 'handle' function as it processes API requests.

    :param methods: HTTP methods that this redirect rule applies
    :param at: The redirecting module
    :param to: The target module
    :return: None
    """

    caller, target = _get_module(at), _get_module(to)
    [setattr(caller, Glossary.REDIRECT.value, {**getattr(caller, Glossary.REDIRECT.value, {}), **{method.lower(): target}}) for method in methods]


def bind(package: Union[str, ModuleType], *, to: Union[str, ModuleType], url: str = r'.*') -> None:
    """Bind a package of structured endpoints to a manager

    ...

    :param package: The package of structured endpoints
    :param to: The target module
    :param url: URL path to the target module
    :return: None
    """

    pkg, anchor = _get_module(package), _get_module(to)
    setattr(anchor, 'urlpatterns',
            getattr(anchor, 'urlpatterns', []) + [re_path(url, csrf_exempt(partial(handle, root=pkg)))])


def extend(pattern: str, *, at: Union[str, ModuleType], to: Union[str, ModuleType]) -> None:
    """Extend 'urlpatterns' to handle requests other than those handled by Dorest managers

    The extended patterns are defined in a separate file indicated in the 'to' parameter.

    :param pattern: URL pattern according to Django URL handling specification
    :param at: The source module
    :param to: The extension module
    :return: None
    """

    caller = _get_module(at)
    setattr(caller, 'urlpatterns', getattr(caller, 'urlpatterns', []) + [path(pattern, include(to))])
