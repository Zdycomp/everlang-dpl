#!/usr/bin/env python3
"""Setup script for everlang package."""

from setuptools import setup, find_packages

setup(
    packages=find_packages(where="."),
    package_data={
        "everlang_standalone": ["py.typed"],
    },
    entry_points={
        "console_scripts": [
            "everlang=everlang_standalone.main:main",
            "everlang-dna=everlang_standalone.everlang.biocomputing.cli:main_dna",
            "everlang-transpile=everlang_standalone.everlang.transpiler.cli:main_transpile",
            "everlang-particles=everlang_standalone.everlang.core.cli:main_particles",
        ],
    },
)
