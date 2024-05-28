# -*- coding: utf-8 -*-

name = 'hdr_merge'

version = '1.0.3'

requires = [
    'oiio',
    'exifread',
    'blender-2',
    'python-3.10'
]

def commands():
    env.PATH.append('{root}/bin')
    env.PYTHONPATH.append('{root}/python')
    env.PYTHONPATH.append('{root}/blender')

timestamp = 1716861976

format_version = 2
