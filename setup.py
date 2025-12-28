from setuptools import setup, Extension
import pybind11
import sys

# Configuration spécifique selon la plateforme
if sys.platform == 'win32':
    extra_compile_args = ['/std:c++14']
    extra_link_args = []
else:
    extra_compile_args = ['-std=c++14']
    extra_link_args = []

ext_modules = [
    Extension(
        'mine_module',
        ['mine_pow.cpp'],
        include_dirs=[pybind11.get_include()],
        language='c++',
        extra_compile_args=extra_compile_args,
        extra_link_args=extra_link_args,
    ),
]

setup(
    name='mine_module',
    ext_modules=ext_modules,
)