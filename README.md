xmfix
=====

A utility to fix broken XMind files.

An XMind file is actually a ZIP archive containing multiple components. In some rare cases, e.g. a software crash occurs before XMind finishes saving the file, the ZIP format is broken and you will get a `java.util.zip.ZipException` error when trying to open that file the next time. This tiny command line utility intends to fix this kind of 'broken files' and recover as much as possible contents inside those files.

Requirements
------------

*   Python 2.6+
*   A Unix-like operating system (Linux, Mac OS X recommended; currently no support for Windows platforms)

Installation
------------

Simply run this command:

    sudo python setup.py install

How To Use
----------

Suppose your broken file is at `/path/to/broken/file.xmind`, run this in command line:

    xmfix /path/to/broken/file.xmind

If the fix succeeded, you would see a `file_fixed.xmind` in the same folder.

That's it.
