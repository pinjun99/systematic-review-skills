#!/usr/bin/env python3
# Copyright 2026 Ooi Pin Jun
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Check local documentation links using only the standard library."""

from html import unescape
from pathlib import Path
import re
import tempfile
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[3]
DESTINATION = r'<[^<>\n]+>|(?:\\.|[^\s()\\]|\((?:\\.|[^\s()\\])*\))+'
DEFINITION = re.compile(
    rf'^ {{0,3}}\[([^\]\n]+)\]:[ \t]*(?:\n[ \t]*)?({DESTINATION})', re.M
)
LINK = re.compile(
    rf'(?<!\\)\[([^\[\]\n]*)\](?:\(\s*({DESTINATION})'
    r'''(?:\s+(?:"[^"\n]*"|'[^'\n]*'|\([^\n]*?\)))?\s*\)|\[([^\]\n]*)\])?'''
)


def blank(match):
    """Mask examples without losing line numbers."""
    return re.sub(r'[^\n]', ' ', match.group())


def without_fences(text):
    lines = []
    fence = None
    for line in text.splitlines(keepends=True):
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)', line)
        if fence:
            lines.append(re.sub(r'[^\n]', ' ', line))
            if (marker and marker[1][0] == fence[0]
                    and len(marker[1]) >= len(fence) and not marker[2].strip()):
                fence = None
        elif marker and not (marker[1][0] == '`' and '`' in marker[2]):
            fence = marker[1]
            lines.append(re.sub(r'[^\n]', ' ', line))
        else:
            lines.append(line)
    return ''.join(lines)


def normalize_label(label):
    return ' '.join(label.split()).casefold()


def links(text):
    text = without_fences(text)
    text = re.sub(r'(?<!`)(`+)(?!`)([\s\S]*?)(?<!`)\1(?!`)', blank, text)
    definitions = {}
    for match in DEFINITION.finditer(text):
        definitions.setdefault(normalize_label(match[1]), match[2])
    text = DEFINITION.sub(blank, text)
    for match in LINK.finditer(text):
        target = match[2]
        if target is None:
            target = definitions.get(normalize_label(match[3] or match[1]))
        if target is not None:
            target = re.sub(r'\\([!"#$%&\'()*+,\-./:;<=>?@\[\]\\^_`{|}~])', r'\1', target)
            yield text.count('\n', 0, match.start()) + 1, unescape(target.strip('<>'))


def heading_anchors(text):
    """GitHub-style heading slugs, including suffixes for duplicate headings."""
    anchors = set()
    lines = without_fences(text).splitlines()
    for index, line in enumerate(lines):
        atx = re.match(r'^ {0,3}#{1,6}(?:[ \t]+(.*?)|[ \t]*)$', line)
        if atx:
            heading = re.sub(r'[ \t]+#+[ \t]*$', '', atx[1] or '')
        elif (line.strip() and index + 1 < len(lines)
              and re.fullmatch(r' {0,3}(?:=+|-+)[ \t]*', lines[index + 1])):
            heading = line.strip()
        else:
            continue
        # Formatting markers and link destinations are not rendered heading text.
        heading = LINK.sub(lambda match: match[1], heading)
        heading = re.sub(r'<[^>]*>', '', heading)
        heading = re.sub(r'(`+)(.*?)\1', lambda match: match[2], heading)
        slug = re.sub(r'[^\w\- ]', '', unescape(heading).lower()).replace(' ', '-')
        anchor, suffix = slug, 0
        while anchor in anchors:
            suffix += 1
            anchor = f'{slug}-{suffix}'
        anchors.add(anchor)
    return anchors


def markdown_files(root):
    return sorted(set(root.glob('*.md')) | set((root / 'docs').rglob('*.md'))
                  | set((root / '.agents' / 'skills').rglob('*.md')))


def missing_links(paths):
    failures = []
    anchor_cache = {}
    for source in paths:
        for line, target in links(source.read_text(encoding='utf-8')):
            url = urlsplit(target)
            if url.scheme or url.netloc or not url.path:
                continue
            destination = (source.parent / unquote(url.path)).resolve()
            if not destination.exists():
                failures.append(f'{source}:{line}: missing target: {target}')
            elif url.fragment and destination.suffix.lower() == '.md':
                if destination not in anchor_cache:
                    anchor_cache[destination] = heading_anchors(
                        destination.read_text(encoding='utf-8')
                    )
                if unquote(url.fragment) not in anchor_cache[destination]:
                    failures.append(f'{source}:{line}: missing heading: {target}')
    return failures


class MarkdownLinkTests(unittest.TestCase):
    def test_repository_links(self):
        failures = missing_links(markdown_files(ROOT))
        self.assertEqual([], failures, '\n' + '\n'.join(failures))

    def test_reports_every_missing_file_and_heading(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'exists.md').write_text('# Present\n', encoding='utf-8')
            source = root / 'source.md'
            source.write_text(
                '[inline](missing.md)\n[reference][absent]\n'
                '[absent]: also-missing.md\n[heading](exists.md#absent)\n',
                encoding='utf-8',
            )
            self.assertEqual([
                f'{source}:1: missing target: missing.md',
                f'{source}:2: missing target: also-missing.md',
                f'{source}:4: missing heading: exists.md#absent',
            ], missing_links([source]))

    def test_relative_paths_queries_fragments_and_reference_forms(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'docs').mkdir()
            (root / 'guide (new).md').write_text(
                '# Hello, World!\n# Hello, World!\nSetext heading\n---\n',
                encoding='utf-8',
            )
            source = root / 'docs' / 'source.md'
            source.write_text(
                '[inline](../guide%20(new).md?view=1#hello-world)\n'
                '[named][Mixed CASE]\n[collapsed][]\n[shortcut]\n'
                '[mixed case]: <../guide (new).md#hello-world-1> "Title"\n'
                '[collapsed]: ../guide%20(new).md#setext-heading\n'
                '[shortcut]: ../guide%20(new).md\n', encoding='utf-8',
            )
            self.assertEqual(4, len(list(links(source.read_text(encoding='utf-8')))))
            self.assertEqual([], missing_links([source]))

    def test_ignores_external_links_anchors_and_code(self):
        text = '''[web](https://example.test/a.md#absent)
[web](http://example.test/)
[email](mailto:reader@example.test)
[local anchor](#absent)
`[inline code](missing.md)` and ``[code with `](missing.md)``
```markdown
[fenced](missing.md)
````
   ~~~
[tilde fence][missing]
[missing]: missing.md
   ~~~
[real](present.md)
'''
        self.assertEqual(['https://example.test/a.md#absent', 'http://example.test/',
                          'mailto:reader@example.test', '#absent', 'present.md'],
                         [target for _, target in links(text)])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'present.md').touch()
            source = root / 'source.md'
            source.write_text(text, encoding='utf-8')
            self.assertEqual([], missing_links([source]))

    def test_heading_slug_rules(self):
        self.assertEqual(
            {'hello-world', 'hello-world-1', 'hello-world-1-1',
             'a-hyphen-and_under-score', 'café--code', 'linked-text', 'setext'},
            heading_anchors('# Hello, World!\n# Hello, World!\n# Hello World-1\n'
                            '# A-hyphen and_under-score\n# Café & `code`\n'
                            '# [Linked text](guide.md) ###\nSetext\n===\n'
                            '```\n# Not a heading\n```\n'
                            '~~~\n# Also not a heading\n~~~\n'),
        )

    def test_discovers_all_requested_locations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            names = ['README.md', 'CONTRIBUTING.md', 'docs/nested/guide.md',
                     '.agents/skills/example/SKILL.md',
                     '.agents/skills/example/references/guide.md']
            for name in names + ['unrelated/ignored.md']:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            self.assertEqual(sorted(root / name for name in names), markdown_files(root))


if __name__ == '__main__':
    unittest.main()
