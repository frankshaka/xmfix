#!/usr/bin/env python

"""
distutils/setuptools install script.
"""

try:
    from setuptools import setup
    setup
except ImportError:
    from distutils.core import setup

setup(
    name='xmfix',
    version="0.0.1",
    description='Utility to fix broken XMind files.',
    long_description=open('README.md').read(),
    author='Frank Shaka',
    author_email='frank@xmind.net',
    url='https://github.com/frankshaka/xmfix',
    scripts=['xmfix'],
    license=open("License.txt").read()
)
