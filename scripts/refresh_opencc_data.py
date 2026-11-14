#!/usr/bin/env python3
"""Refresh OpenCC dictionaries from an opencc-js release.

The plugin converts with opencc-python-reimplemented 0.1.7 (last release, stale
data). The Chinese Learning App uses opencc-js. This script takes the opencc-js
dictionaries (STPhrases, STCharacters, TWPhrases, TWVariants and their reverses)
and writes them in the Python library's `key<TAB>first value` format so both
projects convert from the same data.

Usage:
  refresh_opencc_data.py <opencc-js package dir> [--out DIR] [--install DIR]

  <opencc-js package dir>  e.g. .../node_modules/opencc-js (needs dist/esm-lib/dict)
  --out DIR      where to write the .txt files (default: opencc_data/)
  --install DIR  also copy them into an opencc/dictionary dir (e.g. the pip
                 install used by setup_plugin.py)

Writes OPENCC_JS_VERSION next to the dictionaries; then run
tests/test_conversion_golden.py and read the diff before shipping.
"""
import argparse
import json
import os
import re
import shutil
import sys

DICTS = ['STPhrases', 'STCharacters', 'TSPhrases', 'TSCharacters',
         'TWPhrases', 'TWPhrasesRev', 'TWVariants', 'TWVariantsRev',
         'TWVariantsRevPhrases']


def read_js_dict(path):
    """opencc-js dict modules are `export default "k v|k v|..."`."""
    src = open(path, encoding='utf-8').read()
    m = re.search(r'export\s+default\s+("(?:[^"\\]|\\.)*")', src, re.S)
    if not m:
        raise ValueError('unrecognised dict module: %s' % path)
    return json.loads(m.group(1))


def convert(blob):
    """'k v1 v2|k2 v' -> sorted 'k\\tv1' lines (first value only)."""
    lines = []
    for entry in blob.split('|'):
        parts = entry.split(' ')
        if len(parts) >= 2 and parts[0]:
            lines.append('%s\t%s' % (parts[0], parts[1]))
    return sorted(set(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('pkg')
    ap.add_argument('--out', default='opencc_data')
    ap.add_argument('--install')
    a = ap.parse_args()

    dict_dir = os.path.join(a.pkg, 'dist', 'esm-lib', 'dict')
    if not os.path.isdir(dict_dir):
        sys.exit('not an opencc-js package dir (no dist/esm-lib/dict): ' + a.pkg)
    version = json.load(open(os.path.join(a.pkg, 'package.json')))['version']

    os.makedirs(a.out, exist_ok=True)
    for name in DICTS:
        src = os.path.join(dict_dir, name + '.js')
        if not os.path.exists(src):
            print('skip (missing in this release):', name)
            continue
        lines = convert(read_js_dict(src))
        with open(os.path.join(a.out, name + '.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        print('%-22s %6d entries' % (name, len(lines)))
    with open(os.path.join(a.out, 'OPENCC_JS_VERSION'), 'w') as f:
        f.write(version + '\n')
    print('opencc-js', version, '->', a.out)

    if a.install:
        for name in os.listdir(a.out):
            if name.endswith('.txt'):
                shutil.copy(os.path.join(a.out, name), os.path.join(a.install, name))
        print('installed into', a.install)


if __name__ == '__main__':
    main()
