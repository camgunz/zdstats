#!/usr/bin/env python

from distutils.core import setup
import py2exe

setup(
    name='ZDStats',
    version='1.0',
    description='ZDaemon Stats Generator',
    author='Charles Gunyon',
    author_email='charles.gunyon@gmail.com',
    console=[ 'zdstats.py' ],
    options={ "py2exe": {} }
)

