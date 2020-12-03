"""Configuration manager

The 'resolve' function reads all YAML and JSON configurations in the directory specified in a Django project's setting file.
The function returns a dictionary of a tree with configuration file names as the first level.

For example, suppose there is a file named 'foo.yaml' with the following content:
---
greet:
    message: Hello!
---
Calling 'configs.resolve("foo.greet")' would return a dictionary '{message: "Hello!"}',
and calling 'configs.resolve("foo.greet.message")' would return a string "Hello!".

The path to the configuration directory is stored in 'DOREST["CONFIGS"]["PATH"]' in Django project's setting file.

The Dorest project
:copyright: (c) 2020 Ichise Laboratory at NII & AIST
:author: Rungsiman Nararatwong
"""

import importlib
import json
import re
import sys
from os import listdir
from os.path import isfile, join
from typing import Any, Dict, List, Union
from types import ModuleType

import yaml
from django.conf import settings

from .exceptions import UnsupportedFileTypeError


SUPPORTED_FILE_TYPES = ['yml', 'yaml', 'json']


def _get_module(module: Union[str, ModuleType]) -> ModuleType:
    return getattr(sys.modules, module, importlib.import_module(module)) if isinstance(module, str) else module


def _load(path: str) -> dict:
    """Select appropriate loader (YAML or JSON) based on file type

    :param path: Path to the configuration file
    :return: An unprocessed configuration dictionary
    """

    if re.search(r'\.(yml|yaml)$', path):
        return yaml.safe_load(open(path, 'r'))

    elif re.search(r'\.json$', path):
        return json.load(path)

    else:
        raise UnsupportedFileTypeError(path, SUPPORTED_FILE_TYPES)


def _traverse(tree: Dict[str, Any], active_branch: List[str]) -> Any:
    """Traverse the tree-structure configuration dictionary

    :param tree: The configuration dictionary
    :param active_branch: A list of node names in the branch of interest
    :return: A subtree or value of a leaf
    """
    if len(active_branch) > 1:
        return _traverse(tree[active_branch[0]], active_branch[1:])
    else:
        return tree[active_branch[0]]


def _resolve_package(module: Union[str, ModuleType]) -> Any:
    package_branch = _get_module(module).__name__.split('.')
    pkg = None

    for i in range(len(package_branch) - 1, 0, -1):
        sub_branch = '.'.join(package_branch[:i])

        try:
            module = importlib.import_module('%s.package' % sub_branch)

            if hasattr(module, '__package'):
                pkg = module
        except ModuleNotFoundError:
            continue

    return getattr(pkg, '__conf')


def load_dir(path: str) -> dict:
    """Load configurations from YAML or JSON files in a directory

    :param path: Path to the configuration directory
    :return: An unprocessed configuration dictionary
    """
    return {re.sub(r'\.(%s)$' % '|'.join(SUPPORTED_FILE_TYPES), '', file): _load(join(path, file)) for file in listdir(path)
            if isfile(join(path, file)) and re.search(r'\.(%s)$' % '|'.join(SUPPORTED_FILE_TYPES), file)}


def resolve(branch: str = None, at: Union[str, ModuleType] = None) -> Any:
    """Retrieve a subtree or value of specified node or leaf within the tree-structure configuration dictionary

    If 'package' is None then return the API's common configuration; otherwise, return the package's configuration

    :param at: A module (usually where the caller function belongs) which is part of a package
               In case the module contains the caller function, pass '__name__' to this argument
    :param branch: A branch to node or leaf of interest
    :return: A subtree or value of a leaf
    """
    if at is None:
        return _traverse(_conf, branch.split('.')) if branch is not None else _conf
    else:
        pkg_conf = _resolve_package(at)
        return _traverse(pkg_conf, branch.split('.')) if branch is not None else pkg_conf


_conf = load_dir(settings.DOREST['CONFIGS']['PATH'])
