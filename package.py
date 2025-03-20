# -*- coding: utf-8 -*-

name = 'hdr_merge'

version = '1.0.4'

requires = [
    'oiio',
    'exifread',
    'blender',
    'python-3.11'
]

def commands():
    env.PATH.append('{root}/bin')
    env.PYTHONPATH.append('{root}/python')
    env.PYTHONPATH.append('{root}/blender')

timestamp = 1716861976

format_version = 2
