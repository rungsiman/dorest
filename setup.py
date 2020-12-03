import setuptools

with open('README.md', 'r') as fh:
    long_description = fh.read()

setuptools.setup(
    name='dorest',
    version='0.1.0',
    author_email='rungsiman@gmail.com',
    description="API manager extension for Django REST Framework",
    long_description=long_description,
    url='https://github.com/rungsiman/dorest',
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
