#!/usr/bin/env python

"""This module provides `XMindFileFixer` class to fix a broken XMind file.
"""

__version__ = "0.0.1"
__author__ = "Frank Shaka"

import os
import os.path
import zipfile
import subprocess
import logging
import re


class ZipSource(object):
    def __init__(self, file_path):
        self.file_path = file_path

    def __enter__(self):
        self._zipfile = zipfile.ZipFile(self.file_path, "r")
        return self

    def __exit__(self, exc_type, exception, traceback):
        self._zipfile.close()
        self._zipfile = None

    def entries(self):
        if not hasattr(self, "_zipfile"):
            raise KeyError("Should use 'with' before calling this function.")
        for zipinfo in self._zipfile.infolist():
            yield zipinfo.filename

    def read(self, entry_name):
        if not hasattr(self, "_zipfile"):
            raise KeyError("Should use 'with' before calling this function.")
        return self._zipfile.read(entry_name)

    def entry_size(self, entry_name):
        if not hasattr(self, "_zipfile"):
            raise KeyError("Should use 'with' before calling this function.")
        info = self._zipfile.getinfo(entry_name)
        return info.file_size if info else 0


class DirSource(object):
    def __init__(self, file_path):
        self.file_path = file_path

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exception, traceback):
        pass

    def entries(self):
        return self._walk(self.file_path, "")

    def _walk(self, parent, base):
        for name in os.listdir(parent):
            path = os.path.join(parent, name)
            entry = os.path.join(base, name)
            if os.path.isdir(path):
                yield entry + "/"
                for subentry in self._walk(path, entry):
                    yield subentry
            else:
                yield entry

    def read(self, entry_name):
        if entry_name.endswith("/"):
            return ""
        with open(os.path.join(self.file_path, entry_name), "r") as f:
            return f.read()

    def entry_size(self, entry_name):
        return os.stat(os.path.join(self.file_path, entry_name)).st_size


class ZipTarget(object):
    def __init__(self, file_path, compressed=False):
        self.file_path = file_path
        self.compressed = compressed

    def __enter__(self):
        self._zipfile = zipfile.ZipFile(self.file_path, "w", zipfile.ZIP_DEFLATED if self.compressed else zipfile.ZIP_STORED)
        return self

    def __exit__(self, exc_type, exception, traceback):
        self._zipfile.close()
        self._zipfile = None

    def write(self, entry_name, content):
        if not hasattr(self, "_zipfile"):
            raise KeyError("Should use 'with' before calling this function.")
        self._zipfile.writestr(entry_name, content)


class DirTarget(object):
    def __init__(self, file_path):
        self.file_path = file_path

    def __enter__(self):
        mkdirs(self.file_path)
        return self

    def __exit__(self, exc_type, exception, traceback):
        pass

    def write(self, entry_name, content):
        path = os.path.join(self.file_path, entry_name)
        if not mkdirs(os.dirname(path)):
            raise IOError("Directory can not be created to write file: " + path)
        if entry_name.endswith("/"):
            os.mkdir(path)
        else:
            with open(path, "w") as f:
                f.write(content)


revision_file_pattern = re.compile(r"rev-(\d+)-\d+\.xml")
revision_content_pattern = re.compile(r"<xmap-revision-content[^>]+>(<sheet[^>]+>.*</sheet>)</xmap-revision-content>")

class XMindFileFixer(object):
    def __init__(self, file_path):
        self.source_path = file_path
        (self.source_dir, self.source_name) = os.path.split(file_path)
        (self.source_prefix, self.source_suffix) = os.path.splitext(self.source_name)
        self.unzipped_dir = file_path if os.path.isdir(file_path) else None
        self.recovered_path = None
        self.force_recovered_path = None
        self.rebuilt_zip_path = None
        self.target_path = None

    def fix(self):
        try:
            if not self.unzipped_dir:
                self.unzip()
            else:
                logging.info("[xmfix] Fixing XMind file from directory: %s", self.unzipped_dir)
            if self.unzipped_dir:
                self.rebuild_content()
                self.rebuild_manifest()
                self.rebuild_zip()
                self.build_target()
        except:
            logging.error("[xmfix] Failed to fix XMind file: %s", self.source_path, exc_info=True)
        finally:
            self.clear()

        return self.target_path

    def clear(self):
        logging.info("[xmfix] Clearing temporary files/dirs:")
        if self.unzipped_dir and self.unzipped_dir != self.source_path:
            rmall(self.unzipped_dir)
        if self.recovered_path:
            rmall(self.recovered_path)
        if self.force_recovered_path:
            rmall(self.force_recovered_path)
        if self.rebuilt_zip_path:
            rmall(self.rebuilt_zip_path)

    def unzip(self):
        self.unzipped_dir = self.extract_zip(self.source_path)
        if self.unzipped_dir:
            return
        
        self.unzipped_dir = self.recover_and_extract_zip()
        if self.unzipped_dir:
            return

    def extract_zip(self, source_path):
        target_dir = os.path.join(self.source_dir, "xmfix_" + self.source_prefix)
        rmall(target_dir)
        logging.info("[xmfix] Unzipping file: %s -> %s", source_path, target_dir)
        try:
            exitcode = unzip(source_path, target_dir)
        except:
            rmall(target_dir)
            raise
        else:
            if exitcode == 0:
                return target_dir
            rmall(target_dir)
            return None

    def recover_and_extract_zip(self):
        logging.info("[xmfix] Recovering ZIP file: %s", self.source_path)
        self.recovered_path = os.path.join(self.source_dir, "xmfix_" + self.source_prefix + "_recovered.zip")
        exitcode = run("zip", "-FF", self.source_path, "--out", self.recovered_path)
        if exitcode != 0:
            return None
        logging.info("[xmfix] ZIP file recovered: %s", self.recovered_path)
        
        extracted = self.extract_zip(self.recovered_path)
        if extracted:
            return extracted

        logging.info("[xmfix] Force recovering ZIP file: %s", self.source_path)
        self.force_recovered_path = os.path.join(self.source_dir, "xmfix_" + self.source_prefix + "_force_recovered.zip")
        exitcode = run("zip", "-FF", self.recovered_path, "--out", self.force_recovered_path)
        if exitcode != 0:
            return None
        logging.info("[xmfix] ZIP file force recovered: %s", self.force_recovered_path)
    
        return self.extract_zip(self.force_recovered_path)

    def rebuild_content(self):
        content_file = os.path.join(self.unzipped_dir, "content.xml")
        if os.path.exists(content_file) and os.stat(content_file).st_size:
            logging.debug("[xmfix] Content file already exists.")
            return
        
        sheets = []
        revisions_dir = os.path.join(self.unzipped_dir, "Revisions")
        for sheet_id in os.listdir(revisions_dir):
            revision_dir = os.path.join(revisions_dir, sheet_id)
            revision = -1
            sheet = None
            revision_file = None
            for rev_file_name in os.listdir(revision_dir):
                m = revision_file_pattern.match(rev_file_name)
                if m:
                    rev = int(m.group(1))
                    if rev > revision:
                        revision_file = os.path.join(revision_dir, rev_file_name)
                        try:
                            with open(revision_file, "r") as rf:
                                revision_content = rf.read()
                            m = revision_content_pattern.search(revision_content)
                            if m:
                                sheet = m.group(1)
                                revision = rev
                        except:
                            logging.warning("[xmfix] Failed to load revision: %s", revision_file)
            if sheet:
                sheets.append(sheet)
                logging.info("[xmfix] Sheet recovered: %s", revision_file)
        if sheets:
            content = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
                '<xmap-content xmlns="urn:xmind:xmap:xmlns:content:2.0" '
                    'xmlns:fo="http://www.w3.org/1999/XSL/Format" '
                    'xmlns:svg="http://www.w3.org/2000/svg" '
                    'xmlns:xhtml="http://www.w3.org/1999/xhtml" '
                    'xmlns:xlink="http://www.w3.org/1999/xlink" '
                    'version="2.0">') + "".join(sheets) + '</xmap-content>'
            with open(content_file, "w") as cf:
                cf.write(content)
            logging.warning("[xmfix] Content rebuilt from editing history (%s sheets).", len(sheets))
            return
        
        raise RuntimeError("'content.xml' is missing and failed to rebuild it.")

    def rebuild_manifest(self):
        manifest_dir = os.path.join(self.unzipped_dir, "META-INF")
        manifest_file = os.path.join(manifest_dir, "manifest.xml")
        if os.path.exists(manifest_file):
            logging.debug("[xmfix] Manifest file already exists.")
            return
        
        logging.info("[xmfix] Rebuilding manifest from %s ....", self.unzipped_dir)
        logging.debug("[xmfix] Manifest file path: %s", manifest_file)
        entries = []
        with DirSource(self.unzipped_dir) as source:
            for entry in source.entries():
                logging.info("[xmfix] Reading entry: %s", entry)
                # Remove empty XML files to prevent XMind from failing to parse XML:
                if source.entry_size(entry) > 0 or not entry.lower().endswith(".xml"):
                    entries.append('<file-entry full-path="%s" media-type=""/>' % entry)
                else:
                    logging.warning("[xmfix] Empty XML removed: %s", entry)
                    rmall(os.path.join(self.unzipped_dir, entry))
        manifest = ('<?xml version="1.0" encoding="UTF-8" standalone="no"?>'
            '<manifest xmlns="urn:xmind:xmap:xmlns:manifest:1.0">'
            ) + "".join(entries) + (
                '<file-entry full-path="META-INF/" media-type=""/>'
                '<file-entry full-path="META-INF/manifest.xml" media-type="text/xml"/>'
            '</manifest>')
        mkdirs(manifest_dir)
        with open(manifest_file, "w") as mf:
            mf.write(manifest)
        logging.info("[xmfix] Manifest rebuilt: %s", manifest_file)

    def rebuild_zip(self):
        zip_path = os.path.join(self.source_dir, "xmfix_" + self.source_prefix + ".zip")
        logging.info("[xmfix] Rebuilding ZIP archive from %s ....", self.unzipped_dir)
        logging.debug("[xmfix] ZIP archive target file: %s", zip_path)
        with DirSource(self.unzipped_dir) as source:
            with ZipTarget(zip_path) as target:
                for entry in source.entries():
                    logging.info("[xmfix] Archiving %s...", entry)
                    content = source.read(entry)
                    target.write(entry, content)
        logging.info("[xmfix] ZIP archive rebuilt: %s", zip_path)
        self.rebuilt_zip_path = zip_path

    def build_target(self):
        target_path = os.path.join(self.source_dir, self.source_prefix + "_fixed.xmind")
        index = 1
        while os.path.lexists(target_path):
            index += 1
            target_path = os.path.join(self.source_dir, self.source_prefix + ("_fixed (%s).xmind" % index))
        logging.info("[xmfix] Building target: %s -> %s", self.rebuilt_zip_path, target_path)
        os.rename(self.rebuilt_zip_path, target_path)
        logging.info("[xmfix] Target built: %s", target_path)
        self.target_path = target_path


def mkdirs(dirpath):
    logging.debug("[xmfix] Making dirs: %s", dirpath)
    if os.path.isdir(dirpath):
        return True
    if os.path.exists(dirpath): # and not os.path.isdir(dirpath):
        return False
    (parent, name) = os.path.split(dirpath)
    if parent:
        mkdirs(parent)
    if not os.path.isdir(parent):
        return False
    os.mkdir(dirpath)
    return os.path.isdir(dirpath)


def rmall(file_path):
    logging.debug("[xmfix] Deleting: %s", file_path)
    _rmall(file_path)


def _rmall(file_path):
    if os.path.isdir(file_path):
        for name in os.listdir(file_path):
            _rmall(os.path.join(file_path, name))
        os.rmdir(file_path)
    elif os.path.lexists(file_path):
        os.remove(file_path)


def run(*cmdargs, **kwargs):
    logging.debug("[xmfix] Calling: %s", " ".join('"' + arg + '"' for arg in cmdargs))
    return subprocess.call(cmdargs)


def unzip(source_file, target_dir):
    mkdirs(target_dir)
    return run("unzip", source_file, "-d", target_dir)

