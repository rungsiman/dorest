"""The generic architecture

The generic mechanism forwards API calls to a preconfigured set of backend functions.
An basic use case is when an API should support multiple database backends.
For example, the following packages provides connectors for databases 'dba' and 'dbb':
~~~~~~~~~~~~~~~~~~~~~~~
    + gen
    |- __init__.py
    |- connector.py
    + db
    | + dba
    | |- __init__.py
    | |- connector.py
    | + dbb
    | |- __init__.py
    | |- connector.py
    ...
~~~~~~~~~~~~~~~~~~~~~~~

To make package 'gen' generic, import 'register' function from this module and implement it in 'gen/__init__.py':
---
    generic.register('db', to=__name__, using='dba')
---
The first parameter indicates the root package of the backends, and the 'using' parameter indicates which backend is being used.

Suppose there is a function defined in 'gen/connector.py' that inserts data to a database and returns record ID:
---
    def insert(title: str, article: str, author: str) -> str:
        return generic.resolve(insert)(title, article, author, datetime.now())
---
Once received an API call, the 'generic.resolve' function will look for the registered configuration ('generic.register')
in the same and parent packages, then match the caller ('gen.connector.insert') to the backend ('db.dba.connector.insert').

Thus, the 'insert' function in 'db/dba/connector.py' should be:
---
    def insert(title: str, article: str, author: str, created: datetime) -> str:
        return dba_client.insert({'title': title, 'article': article, 'author': author, 'created': created})
---

The Dorest project
:copyright: (c) 2020 Ichise Laboratory at NII & AIST
:author: Rungsiman Nararatwong
"""


import importlib
import sys
from typing import Union
from types import ModuleType


def _get_module(module: Union[str, ModuleType]) -> ModuleType:
    return getattr(sys.modules, module, importlib.import_module(module)) if isinstance(module, str) else module


def _locate_package(branch: str) -> Union[str, None]:
    path = branch.split('.')

    for i in range(len(path) - 1, 0, -1):
        active_path = '.'.join(path[:i])

        try:
            package = importlib.import_module('%s.package' % active_path)

            if hasattr(package, '__package'):
                return package.__name__[:-8]

        except ModuleNotFoundError:
            continue

    return None


def bind(backend: Union[str, ModuleType], *, to: Union[str, ModuleType], using: str,
         bypass_package: bool = False) -> None:
    """Register a backends' package by setting the attribute '__interface' to the module

    :param backend: The backends' package
    :param to: The root of the interface package (usually __name__)
    :param using: The selected backend
    :param bypass_package: Only locate backends in PYTHONPATH
    :return: None
    """

    package = _locate_package(_get_module(to).__name__)

    if isinstance(backend, str) and package is not None and not bypass_package:
        backend = '%s.%s' % (package, backend)

    setattr(_get_module(to), '__interface', {'package': _get_module(backend), 'driver': using})


def resolve(caller: Union[callable, str, ModuleType]) -> callable:
    """Call the preconfigured backend that matches the caller

    :param caller: The caller function or a branch indicating the function
    :return: The backend function
    """

    if callable(caller):
        branch = '%s.%s' % (caller.__module__, caller.__name__)
    else:
        branch = getattr(sys.modules, caller, importlib.import_module(caller)).__name__ \
            if isinstance(caller, str) else caller.__name__

    path = branch.split('.')
    depth, target = None, None

    # Locate the registered configuration ('interfaces.bind') in the same and parent packages
    for i in range(len(path) - 1, 0, -1):
        active_path = '.'.join(path[:i])
        module = getattr(sys.modules, active_path, importlib.import_module(active_path))

        if hasattr(module, '__interface'):
            depth, target = i, getattr(module, '__interface')

    return getattr(importlib.import_module('%s.%s.%s' % (target['package'].__name__, target['driver'],
                                                         '.'.join(path[depth:-1]))), path[-1])
