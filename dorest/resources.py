"""Structured API endpoints resource manager

This manager associates structured API endpoints with their resources, which must also be structured according to the API structure.

For example, suppose there is a function 'bar' in a module 'foo', which is located in 'api_root_pkg.subpkg' (the actual path would be
'.../api_root_pkg/subpkg/foo.py').

Function 'bar' needs to access an input file 'input.txt'. To use this resource manager, the 'input.txt' must be stored as
'.../res_root/subpkg/foo/bar/input.txt', with '.../res_root' registered as the root directory of the structured API endpoints.

Once 'input.txt' is stored in the directory, calling 'resolve' with 'bar' and 'input.txt' as its parameters will return the path to the file:
---
    def bar(...):
        with open(resources.resolve(bar, 'input.txt), 'r') as file:
            ...
---

The Dorest project
:copyright: (c) 2020 Ichise Laboratory at NII & AIST
:author: Rungsiman Nararatwong
"""

import importlib
import os
import sys
from typing import Union
from types import ModuleType


def _get_module(module: Union[str, ModuleType]) -> ModuleType:
    return getattr(sys.modules, module, importlib.import_module(module)) if isinstance(module, str) else module


def bind(package: Union[str, ModuleType], *, to: Union[str, ModuleType]) -> None:
    """Bind a root resource directory to structured API endpoints

    In general, this function should be called in '__init__.py' of the root package of the structured API endpoints.
    The functions will then add '__resources' attribute to the module for the 'resolve' function to use as reference.

    :param package: The root package of the designated resources in Python's import format
    :param to: The root package of the structured API endpoints
    :return: None
    """

    setattr(_get_module(to), '__resources', _get_module(package))


def resolve(obj: Union[callable, str, ModuleType], path: str = None) -> str:
    """Resolve the path where resources corresponding to the given function or module are stored

    :param obj: The caller function or module
    :param path: A sub-path to the target resource (usually filename) within the resolved path
    :return: A path to the target resource
    """

    if callable(obj):
        branch = '%s.%s' % (obj.__module__, obj.__name__)
    else:
        branch = getattr(sys.modules, obj, importlib.import_module(obj)).__name__ if isinstance(obj, str) else obj.__name__

    levels = branch.split('.')
    res_level, res_module = None, None

    # Find a reference to the root path of the resources registered using the 'register' function
    # starting from the lowest-level package of the 'obj' (function or module)
    for i in range(len(levels) - 1, 0, -1):
        sub_branch = '.'.join(levels[:i])
        attr = getattr(sys.modules, sub_branch, importlib.import_module(sub_branch))

        if hasattr(attr, '__resources'):
            res_level, res_module = i, getattr(attr, '__resources')

    if res_module is None:
        raise ModuleNotFoundError("Cannot locate resource directory of '%s'" % str(obj))

    return '%s/%s%s' % (os.path.dirname(res_module.__file__), '/'.join(levels[res_level:]),
                        '/%s' % path if path is not None else '')
