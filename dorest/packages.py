"""Package manager

The Dorest project
:copyright: (c) 2020 Ichise Laboratory at NII & AIST
:author: Rungsiman Nararatwong
"""

import importlib
import sys
import os
from functools import partial
from typing import Union
from types import ModuleType

from django.core.handlers.wsgi import WSGIRequest
from django.urls import re_path
from django.views.decorators.csrf import csrf_exempt

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from . import conf as _conf, struct as _struct, resources as dr_resources

DEFAULT_STRUCTURE = {'struct': 'endpoints', 'resources': 'resources',
                     'conf': 'conf', 'private': 'private', 'templates': 'templates'}


def _get_module(module: Union[str, ModuleType]) -> ModuleType:
    return getattr(sys.modules, module, importlib.import_module(module)) if isinstance(module, str) else module


def bind(site: Union[str, ModuleType], *, to: Union[str, ModuleType], url: str = None) -> None:
    def resolve_module(key: str, partial_path: Union[bool, str]) -> str:
        if partial_path is None:
            return '%s.%s' % (package.__name__.replace('.package', ''), DEFAULT_STRUCTURE[key].replace('/', '.'))
        else:
            return '%s.%s' % (package.__name__.replace('.package', ''), partial_path.replace('/', '.'))

    def resolve_path(key: str, package_patch: str, partial_path: Union[bool, str]) -> str:
        if partial_path is None:
            return '%s%s' % (package_patch, DEFAULT_STRUCTURE[key])
        else:
            return '%s%s' % (package_patch, partial_path)

    site, caller = _get_module(site), _get_module(to)
    target_dir = site.__file__.replace('__init__.py', '')

    packages = []
    package_root_dirs = []

    for root, dirs, files in os.walk(target_dir):
        if all(root not in prd for prd in package_root_dirs):
            if 'package.py' in files:
                package_root_dirs.append(root)

    for prd in package_root_dirs:
        root = prd.replace(target_dir, '').replace('/', '.')
        package = importlib.import_module('%s.%s.package' % (site.__name__, root))
        pkg_attr = getattr(package, '__package')
        packages.append(package)

        if not pkg_attr['bound']:
            for key in ('struct', 'resources'):
                pkg_attr[key] = resolve_module(key, pkg_attr[key])

            for key in ('conf', 'private', 'templates'):
                pkg_attr[key] = resolve_path(key, package.__file__.replace('package.py', ''), pkg_attr[key])

            pkg_attr['bound'] = True
            setattr(package, '__package', pkg_attr)
            setattr(package, '__conf', _conf.load_dir(pkg_attr['conf']))
            pkg_conf = getattr(package, '__conf')

            try:
                pkg_struct = importlib.import_module(pkg_attr['struct'])

                if pkg_conf['urls']['struct'] is None:
                    _struct.bind(pkg_struct, to=caller, url='%s%s/' % ('' if url is None else '%s/' % url.strip('/'),
                                                                       pkg_conf['urls']['root'].strip('/')))
                else:
                    _struct.bind(pkg_struct, to=caller, url='%s%s/%s/' % ('' if url is None else '%s/' % url.strip('/'),
                                                                          pkg_conf['urls']['root'].strip('/'),
                                                                          pkg_conf['urls']['struct'].strip('/')))
            except ModuleNotFoundError:
                pkg_struct = None

            if pkg_struct is not None:
                try:
                    pkg_res = importlib.import_module(pkg_attr['resources'])
                    dr_resources.bind(pkg_res, to=pkg_struct)
                except ModuleNotFoundError:
                    pass
                
                key = pkg_conf['urls']['root'].strip('/') if 'urls' in pkg_conf and 'root' in pkg_conf['urls'] else root
                setattr(package, '__struct', {key: pkg_struct})
    
    setattr(caller, 'urlpatterns',
            getattr(caller, 'urlpatterns', []) + [re_path('%s$' % ('' if url is None else '%s/' % url.strip('/')),
                                                          csrf_exempt(partial(walk, root=site)))])
    setattr(site, '__packages', packages)


def link(module: Union[str, ModuleType], *, path: str = None, struct: str = None, resources: str = None,
         conf: str = None, private: str = None,
         templates: str = None) -> None:
    package = _get_module(module)

    if not hasattr(package, '__package'):
        setattr(package, '__package', {'bound': False,
                                       'path': path, 'struct': struct, 'resources': resources,
                                       'conf': conf, 'private': private, 'templates': templates})


def requires(module: Union[str, ModuleType], *, permissions: Union[list, tuple] = None) -> None:
    package = _get_module(module)
    setattr(package, '__permissions', permissions)


def call(branch: str, *, by: Union[str, ModuleType]) -> callable:
    caller = _get_module(by).__name__
    path = caller.split('.')
    root = None

    for i in range(len(path), 0, -1):
        try:
            package = importlib.import_module('%s.package' % '.'.join(path[:i]))
            
            if hasattr(package, '__package'):
                root = '.'.join(package.__name__.split('.')[:-2])

        except ModuleNotFoundError:
            continue
    
    if root is None:
        raise Exception("Function 'packages.call' must be called from within a package")

    branch = branch.split('.')
    return getattr(importlib.import_module('%s.%s' % (root, '.'.join(branch[:-1]))), branch[-1])


@api_view(['GET'])
@permission_classes([AllowAny])
def walk(request: WSGIRequest, root: Union[str, ModuleType]) -> Response:
    site = _get_module(root)
    package_endpoints = {}

    for package in getattr(site, '__packages', []):
        permissions = getattr(package, '__permissions', [])

        if all(permission().has_permission(request, api_view()(walk)) for permission in permissions):
            for key, pkg_struct in getattr(package, '__struct', {}).items():
                package_endpoints[key] = _struct.walk_endpoints(pkg_struct.__name__, 'reduce' in request.GET)

            # print(request.user)
            # print(getattr(package, '__permissions'))
            # print(getattr(package, '__permissions')[0]().has_permission(request, api_view()(walk)))
            # print(api_view()(walk))

    return Response({'packages': package_endpoints}, status=status.HTTP_200_OK)
