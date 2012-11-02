=======================================================
rt2to3: Runtime 2to3 conversion (for Python developers)
=======================================================

Overview
========

The standard development process for Python 2/3 code is to write
Python 2 compatible code and rely on `2to3` to convert the code to a
Python 3 compatible syntax. This is cumbersome, often requiring a call
to ``python3 setup.py build`` after any change.

`rt2to3` avoids this by modifying the standard Python import
mechanisms to optionally call `2to3` at runtime. Specifically,
`rt2to3` injects a path hook into `sys.path_hooks`. When importing a
file whose path matches a predicate, often a subdirectory test, a
custom file loader is used to process the module source through
`2to3` before it is compiled. For speed, the results of the `2to3`
conversion are cached in the ``__pycache__`` directory.


Requirements
============

`rt2to3` requires Python 3.2 or later.


Examples
========

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

For permanent behavior, add to your ``sitecustomize.py``::

    import sys
    from rt2to3 import Runtime2to3Installer

    IPY = '/home/user/projects/ipython'
    nofix = ['apply', 'except', 'has_key', 'next', 'repr', 'tuple_params']

    sys.path.insert(0, IPY)
    Runtime2to3Installer(nofix=nofix).install(IPY)

Or use a ``*.pth`` file::

    /home/user/projects/ipython
    import rt2to3; rt2to3.Runtime2to3Installer(nofix=['apply', 'except', 'has_key', 'next', 'repr', 'tuple_params']).install('/home/user/projects/ipython')


Caveats
=======

This module only affects *imported* code. Code which is run as a
script or using `execfile` is not processed by `2to3`. In addition,
any spawned Python processes (e.g., via `subprocess.Popen`) will *not*
inherit the runtime `2to3` configuration.  You can work around this
by using the ``sitecustomize.py`` file as suggested above.

Byte code is not cached for modules loaded using the runtime 2to3
importer. This is because the default cache tag does not know about
the specific 2to3 settings (i.e., which fixers were or were not used),
and so we cannot properly detect stale ``.pyc`` files.

Source inspection tools might not properly detect the 2to3 converted
source, if they try to open ``module.__file__`` directly, rather than
use ``module.__loader__.get_data(module.__name__)``. The path to the
2to3 converted source is available in ``module.__rt2to3__``.
