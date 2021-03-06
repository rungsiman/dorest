#!/bin/bash

rm -r build
rm -r dist
rm -r dorest.egg-info

python3 -m pip install --user --upgrade setuptools wheel
python3 setup.py sdist bdist_wheel
python3 -m pip install --user --upgrade twine
python3 -m twine upload dist/*
