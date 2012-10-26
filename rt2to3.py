"""rt2to3: Python runtime 2to3 conversion (for developers)

Launch IPython from within the source directory::

  $ git clone https://github.com/ipython/ipython.git
  $ cd ipython
  $ python3 -m rt2to3 ipython.py

Launch IPython from another directory::

  $ IPY=/home/user/projects/ipython
  $ python -m rt2to3 -d $IPY $IPY/ipython.py

Or specify a module to load::

  $ PYTHONPATH=$IPY python3 -m rt2to3 -d $IPY \
    -m IPython.frontend.terminal.ipapp

Custom usage::

    import os
    import sys
    import rt2to3
    from lib2to3 import refactor

    fixer_names = {'lib2to3.fixes.fix_exec', ...}
    refactoring_tool = refactor.RefactoringTool(fixer_names)

    directory = '/path/to/python2module'
    def predicate(path):
        return path == directory or path.startswith(directory + os.path.sep)

    path_hook = rt2to3.Runtime2to3FileFinder.predicated_path_hook(
        predicate, refactoring_tool)
    sys.path_hooks.insert(0, path_hook)
    sys.import_path_cache.clear()
"""

#-----------------------------------------------------------------------------
#  Copyright (C) 2012 Bradley Froehle <brad.froehle@gmail.com>

#  Distributed under the terms of the BSD License.  The full license is in
#  the file COPYING, distributed as part of this software.
#-----------------------------------------------------------------------------

__version__ = '0.1'

#-----------------------------------------------------------------------------
# Imports
#-----------------------------------------------------------------------------

import collections
import errno
import logging
import os
import sys
import warnings

try:
    from importlib.machinery import FileFinder, SourceFileLoader, \
         SOURCE_SUFFIXES
except ImportError:
    # Python <= 3.2
    from importlib._bootstrap import _FileFinder as FileFinder, \
         _SourceFileLoader as SourceFileLoader, _suffix_list
    import imp
    SOURCE_SUFFIXES = _suffix_list(imp.PY_SOURCE)

# Python 3.2 wants an object, Python 3.3 wants a tuple.
FileFinderDetail = collections.namedtuple(
    'FileFinderDetail',
    'loader suffixes')
FileFinderDetail.supports_packages = True

#-----------------------------------------------------------------------------
# Classes
#-----------------------------------------------------------------------------

__all__ = [
    'Runtime2to3FileFinder',
    'Runtime2to3SourceFileLoader',
    ]

class Runtime2to3FileFinder(FileFinder):
    """File finder for source types ('.py') which automatically
    runs the 2to3 refactoring tool on import.

    To enable, run::

        path_hook = Runtime2to3FileFinder.predicated_path_hook(
            predicate, refactoring_tool)
        sys.path_hooks.insert(0, path_hook)
        sys.import_path_cache.clear()

    Parameters
    ----------
    predicate : callable, as predicate(path)
        The 2to3 file finder restricts its operations only to directories
        for which the predicate is satisfied (i.e., `predicate(path)`
        evalates to True).
    refactoring_tool : instance of `lib2to3.refactor.RefactoringTool`
        The 2to3 refactoring tool passed to `Runtime2to3SourceFileLoader`.
    """

    @classmethod
    def predicated_path_hook(cls, predicate, *a, **kw):
        """A class method whch returns a closure to use on sys.path_hook."""
        def predicated_path_hook_for_FileFinder(path):
            """path hook for FileFinder"""
            if not os.path.isdir(path):
                raise ImportError("only directories are supported")
            if not predicate(path):
                raise ImportError("predicate not satisfied")
            return cls(path, *a, **kw)
        return predicated_path_hook_for_FileFinder

    def __init__(self, path, refactoring_tool, tag='rt2to3'):
        logger = logging.getLogger('Runtime2to3FileFinder')
        logger.debug("Processing %s" % path)
        auto2to3 = FileFinderDetail(
            Runtime2to3SourceFileLoader.loader(refactoring_tool, tag),
            SOURCE_SUFFIXES)
        super().__init__(path, auto2to3)

    def __repr__(self):
        return "%s(%r)" % (self.__class__.__name__, self.path)

class Runtime2to3SourceFileLoader(SourceFileLoader):
    """Source file loader which runs source code through 2to3.

    Initial source loading will be _very_ slow, but results are cached
    so future imports will be faster.

    The cached source code is stored in the `__pycache__` directory with
    a `.<TAG>.py` suffix.
    """

    @classmethod
    def loader(cls, *a, **kw):
        """A class method returning a closure for use as a loader."""
        def loader_for_Runtime2to3SourceFileLoader(fullname, path):
            return cls(fullname, path, *a, **kw)
        return loader_for_Runtime2to3SourceFileLoader

    def __init__(self, fullname, path, refactoring_tool, tag):
        """Initialize the source file loader.

         - fullname and path are as in SourceFileLoader.
         - refactoring_tool is an instance of lib2to3.RefactoringTool
         """
        super().__init__(fullname, path)
        self.original_path = path
        self.refactoring_tool = refactoring_tool
        self.tag = tag
        self.logger = logging.getLogger('Runtime2to3SourceFileLoader')
        self.logger.debug('Initialize: %s (%s)' % (fullname, path))

    def _2to3_cache_path(self, path):
        """Path to the cache file (PACKAGE/__pycache__/NAME.TAG.py)"""
        head, tail = os.path.split(path)
        base_filename, sep, tail = tail.partition('.')
        filename = ''.join([base_filename, sep, self.tag, sep, tail])
        return os.path.join(head, '__pycache__', filename)

    def _refactor_2to3(self, path):
        """Run the module through 2to3, returning a string of code and encoding."""
        # self.logger.debug('Refactoring: %s' % path)
        source, encoding = self.refactoring_tool._read_python_source(path)

        source += '\n' # Silence certain parse errors.
        tree = self.refactoring_tool.refactor_string(source, path)
        return str(tree)[:-1], encoding # Take off the '\n' added earlier.

    def _load_cached_2to3(self, path, cache):
        """Load the cached 2to3 source.

        Returns None if the cache is stale or missing.
        """
        try:
            cache_stats = os.stat(cache)
            source_stats = os.stat(path)
        except OSError as e:
            if e.errno == errno.ENOENT: # FileNotFoundError
                self.logger.debug('Cache miss: %s' % cache)
                return None
            else:
                raise

        if cache_stats.st_mtime <= source_stats.st_mtime:
            self.logger.debug('Cache miss (stale): %s' % cache)
            return None

        self.logger.debug("Cache hit: %s" % cache)
        return super().get_data(cache)

    def get_data(self, path):
        """Load a file from disk, running source code through 2to3."""

        if path == self.original_path:
            cache = self._2to3_cache_path(path)
            data = self._load_cached_2to3(path, cache)
            if data is None:
                output, encoding = self._refactor_2to3(path)
                data = bytearray(output, encoding or sys.getdefaultencoding())
                self.set_data(cache, data)
            return data

        else:
            return super().get_data(path)

    def load_module(self, fullname):
        """Load the module."""
        self.logger.debug('Loading module: %s' % fullname)
        path = self.get_filename(fullname)
        module = self._load_module(fullname, sourceless=True)
        module.__file__ = self._2to3_cache_path(path)
        return module


#-----------------------------------------------------------------------------
# Run
#-----------------------------------------------------------------------------

if __name__ == "__main__":

    import argparse
    import hashlib
    import runpy
    import textwrap
    from lib2to3 import refactor

    parser = argparse.ArgumentParser(description="Runtime 2to3 conversion")
    parser.add_argument("-f", "--fix", action="append", default=[],
                        help="Each FIX specifies a transformation; default: all")
    parser.add_argument("-x", "--nofix", action="append", default=[],
                        help="Prevent a transformation from being run")
    parser.add_argument("-d", dest='directory', action="append", default=[],
                        help="Directory to apply transformations; default: current")

    group = parser.add_argument_group('code to run')
    subgroup = group.add_mutually_exclusive_group(required=True)
    subgroup.add_argument('-m', dest='module', metavar='MOD',
                       help="run library module as a script")
    subgroup.add_argument('file', nargs='?', metavar='FILE',
                       help="program read from script file")

    group.add_argument("args", nargs=argparse.REMAINDER, metavar="...", help=
                       "additional arguments for the script or module; separate with "
                       "-- to prevent accidentally parsing these options")

    options = parser.parse_args()

    # Build list of fixers.
    # Taken from lib2to3.main:
    fixer_pkg = 'lib2to3.fixes'
    avail_fixes = set(refactor.get_fixers_from_package(fixer_pkg))
    unwanted_fixes = set(fixer_pkg + ".fix_" + fix for fix in options.nofix)
    explicit = set()
    if options.fix:
        all_present = False
        for fix in options.fix:
            if fix == "all":
                all_present = True
            else:
                explicit.add(fixer_pkg + ".fix_" + fix)
        requested = avail_fixes.union(explicit) if all_present else explicit
    else:
        requested = avail_fixes.union(explicit)
    fixer_names = requested.difference(unwanted_fixes)

    # Build the refactoring tool.
    refactoring_tool = refactor.RefactoringTool(fixer_names)

    # For cache purposes, develop a tag which is unique to the
    # refactoring tool.
    key = tuple(sorted(fixer_names))
    tag = 'rt2to3-' + hashlib.md5(str(key).encode('utf-8')).hexdigest()[:6]

    # Build a function which matches the target directories.
    directories = []
    for d in options.directory or ['.']:
        directories.append(os.path.abspath(d))

    def predicate(path):
        """Match any directory or subdirectory of `directories`."""
        p = os.path.abspath(path)
        return any(p == d or p.startswith(d + os.path.sep)
                   for d in directories)

    # Add our custom path hook to the list of system imports.
    path_hook = Runtime2to3FileFinder.predicated_path_hook(
        predicate, refactoring_tool, tag)
    sys.path_hooks.insert(0, path_hook)
    sys.path_importer_cache.clear()

    if options.module:
        mod_name = options.module
        sys.argv = [mod_name] + options.args
        runpy.run_module(mod_name, run_name="__main__")

    elif options.file:
        file_name = options.file
        sys.argv = [file_name] + options.args
        runpy.run_path(file_name, run_name="__main__")

    else:
        raise NotImplementedError("Unknown run option.")
