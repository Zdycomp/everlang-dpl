#!/usr/bin/env python3
"""Complete language compatibility matrix.

This is an honest adapter contract: every requested language gets a stable
identity, file extensions, detection, inspection, and toolchain probe. Native
emission is marked only where an emitter exists; portable manifest generation
works for every language without pretending to compile unavailable toolchains.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

LANGUAGES = (
    'C', 'C#', 'C++', 'Clojure', 'CSS', 'Dart', 'Dockerfile', 'Elixir',
    'Emacs Lisp', 'Go', 'Haskell', 'HTML', 'Java', 'JavaScript', 'Julia',
    'Jupyter Notebook', 'Kotlin', 'Lua', 'MATLAB', 'Objective-C', 'Perl',
    'PHP', 'PowerShell', 'Python', 'R', 'Ruby', 'Rust', 'Scala', 'Shell',
    'Swift', 'TeX', 'TypeScript', 'Vue',
)


@dataclass(frozen=True)
class LanguageAdapter:
    name: str
    extensions: Tuple[str, ...]
    commands: Tuple[str, ...]
    native_backend: Optional[str]
    role: str

    @property
    def installed(self) -> bool:
        return all(shutil.which(command) for command in self.commands)

    @property
    def status(self) -> str:
        if self.native_backend:
            return 'native-emitter' if self.installed else 'native-emitter-unavailable'
        return 'inspector-and-manifest'


ADAPTERS: Dict[str, LanguageAdapter] = {
    'C': LanguageAdapter('C', ('.c', '.h'), ('gcc',), None, 'foundation'),
    'C#': LanguageAdapter('C#', ('.cs',), ('dotnet',), None, 'compatibility'),
    'C++': LanguageAdapter('C++', ('.cc', '.cpp', '.hpp'), ('g++',), None, 'phase'),
    'Clojure': LanguageAdapter('Clojure', ('.clj', '.cljs'), ('clojure',), None, 'compatibility'),
    'CSS': LanguageAdapter('CSS', ('.css',), (), None, 'interface'),
    'Dart': LanguageAdapter('Dart', ('.dart',), ('dart',), None, 'compatibility'),
    'Dockerfile': LanguageAdapter('Dockerfile', ('Dockerfile',), ('docker',), None, 'packaging'),
    'Elixir': LanguageAdapter('Elixir', ('.ex', '.exs'), ('elixir',), None, 'compatibility'),
    'Emacs Lisp': LanguageAdapter('Emacs Lisp', ('.el',), ('emacs',), None, 'compatibility'),
    'Go': LanguageAdapter('Go', ('.go',), ('go',), 'go', 'finality'),
    'Haskell': LanguageAdapter('Haskell', ('.hs',), ('ghc',), None, 'compatibility'),
    'HTML': LanguageAdapter('HTML', ('.html', '.htm'), (), None, 'interface'),
    'Java': LanguageAdapter('Java', ('.java',), ('javac',), None, 'runtime'),
    'JavaScript': LanguageAdapter('JavaScript', ('.js', '.mjs'), ('node',), 'js', 'runtime'),
    'Julia': LanguageAdapter('Julia', ('.jl',), ('julia',), None, 'compatibility'),
    'Jupyter Notebook': LanguageAdapter('Jupyter Notebook', ('.ipynb',), ('jupyter',), None, 'notebook'),
    'Kotlin': LanguageAdapter('Kotlin', ('.kt', '.kts'), ('kotlinc',), 'kotlin', 'runtime'),
    'Lua': LanguageAdapter('Lua', ('.lua',), ('lua',), None, 'compatibility'),
    'MATLAB': LanguageAdapter('MATLAB', ('.m',), ('matlab',), None, 'compatibility'),
    'Objective-C': LanguageAdapter('Objective-C', ('.m', '.mm'), ('clang',), None, 'compatibility'),
    'Perl': LanguageAdapter('Perl', ('.pl', '.pm'), ('perl',), None, 'compatibility'),
    'PHP': LanguageAdapter('PHP', ('.php',), ('php',), None, 'compatibility'),
    'PowerShell': LanguageAdapter('PowerShell', ('.ps1', '.psm1'), ('pwsh',), None, 'compatibility'),
    'Python': LanguageAdapter('Python', ('.py',), ('python3',), None, 'reference'),
    'R': LanguageAdapter('R', ('.r', '.R'), ('Rscript',), None, 'compatibility'),
    'Ruby': LanguageAdapter('Ruby', ('.rb',), ('ruby',), None, 'dsl'),
    'Rust': LanguageAdapter('Rust', ('.rs',), ('rustc',), 'rust', 'finality'),
    'Scala': LanguageAdapter('Scala', ('.scala',), ('scala',), None, 'compatibility'),
    'Shell': LanguageAdapter('Shell', ('.sh', '.bash'), ('bash',), None, 'automation'),
    'Swift': LanguageAdapter('Swift', ('.swift',), ('swiftc',), None, 'compatibility'),
    'TeX': LanguageAdapter('TeX', ('.tex',), ('pdflatex',), None, 'documentation'),
    'TypeScript': LanguageAdapter('TypeScript', ('.ts', '.tsx'), ('tsc',), None, 'compatibility'),
    'Vue': LanguageAdapter('Vue', ('.vue',), (), None, 'interface'),
}


def adapter(name: str) -> LanguageAdapter:
    return ADAPTERS[name]


def manifest() -> Iterable[dict]:
    for name in LANGUAGES:
        item = adapter(name)
        yield {
            'language': item.name,
            'extensions': list(item.extensions),
            'commands': list(item.commands),
            'native_backend': item.native_backend,
            'role': item.role,
            'status': item.status,
        }


def detect_path(path: Path) -> Optional[LanguageAdapter]:
    if path.name == 'Dockerfile':
        return adapter('Dockerfile')
    for item in ADAPTERS.values():
        if path.suffix in item.extensions:
            return item
    return None
