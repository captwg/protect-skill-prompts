#!/usr/bin/env python3
"""Find fragments of secret prompts in anything a browser can receive.

Fingerprints each secret as overlapping runs of words ("shingles", 8 words by
default; CJK characters count as half a word) and looks for those runs in build
output, HTML, API responses, HAR exports, storage dumps or plain text. Escapes are
decoded first (JSON/JS string escapes, \\uXXXX, HTML entities, nested several times
for React Server Component payloads), so a prompt is found even when it was
serialized inside a string inside a string.

Exit codes: 0 clean, 1 leak found, 2 usage error.

Examples:
  scan_leaks.py --secrets server/skills .next/static
  scan_leaks.py --secrets prompts/ --url http://localhost:5173/ session.har
  scan_leaks.py --secrets prompts/ --text "$(pbpaste)"
  some-command | scan_leaks.py --secrets prompts/ --stdin

Python 3.8+, standard library only.
"""

import argparse
import base64
import fnmatch
import gzip
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request

CODE_EXTS = {'.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.py', '.rb', '.go', '.java', '.kt', '.php', '.vue', '.svelte'}
DEFAULT_EXCLUDES = ['*/node_modules/*', '*/.git/*', '*/.next/server/*', '*/.next/cache/*', '*/.nuxt/*', '*/.svelte-kit/output/server/*']
CJK = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]')
TOKEN = re.compile(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af\uf900-\ufaff]|[^\W_]+', re.UNICODE)
STRING_LITERAL = re.compile(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`', re.S)
# Template placeholders: fingerprints never span one, since the filled-in value differs.
PLACEHOLDER = re.compile(r'\$\{[^}]*\}|\{\{[^}]*\}\}|\{[A-Za-z_][\w.]*\}|%\(\w+\)s|%s')
ESCAPES = [
    (re.compile(r'\\u([0-9a-fA-F]{4})'), lambda m: chr(int(m.group(1), 16))),
    (re.compile(r'\\x([0-9a-fA-F]{2})'), lambda m: chr(int(m.group(1), 16))),
    (re.compile(r'\\[nrt]'), lambda m: ' '),
    (re.compile(r'\\(["\'`/\\])'), lambda m: m.group(1)),
]


def decode(text):
    """Undo string escaping and HTML entities until the text stops changing."""
    for _ in range(4):
        before = text
        for pattern, repl in ESCAPES:
            text = pattern.sub(repl, text)
        text = html.unescape(text)
        if text == before:
            break
    return text


def tokens(text):
    return TOKEN.findall(decode(text).lower())


def shingles(toks, words):
    """Yield runs starting at every token, long enough to weigh `words` (a CJK char weighs 0.5)."""
    weights = [0.5 if CJK.fullmatch(t) else 1.0 for t in toks]
    for start in range(len(toks)):
        total, end = 0.0, start
        while end < len(toks) and total < words:
            total += weights[end]
            end += 1
        if total < words:
            break
        yield ' '.join(toks[start:end])


def walk(path):
    if os.path.isfile(path):
        return [path]
    return [os.path.join(root, f) for root, dirs, names in os.walk(path) if not dirs.sort() for f in sorted(names)]


class Secret:
    def __init__(self, name, text, words):
        self.name = name
        self.shingles, self.short_lengths = set(), set()
        for part in PLACEHOLDER.split(text):
            toks = tokens(part)
            found = set(shingles(toks, words))
            if not found and len(toks) >= 4:  # shorter than one shingle: match it whole
                found = {' '.join(toks)}
                self.short_lengths.add(len(toks))
            self.shingles |= found


def secret_texts(path):
    """Yield (name, text). Code files contribute only their string literals."""
    for file in walk(path):
        try:
            with open(file, encoding='utf-8') as fh:
                text = fh.read()
        except (UnicodeDecodeError, OSError):
            continue
        if os.path.splitext(file)[1].lower() in CODE_EXTS:
            for i, lit in enumerate(m.group(0)[1:-1] for m in STRING_LITERAL.finditer(text)):
                yield '%s#string%d' % (file, i + 1), lit
        else:
            yield file, text


def har_items(label, raw):
    data = json.loads(raw)
    for i, entry in enumerate(data.get('log', {}).get('entries', [])):
        req, res = entry.get('request', {}), entry.get('response', {})
        where = '%s#%d %s %s' % (label, i, req.get('method', ''), req.get('url', ''))
        yield where + ' (url)', req.get('url', '')
        body = (req.get('postData') or {}).get('text')
        if body:
            yield where + ' (request body)', body
        content = res.get('content') or {}
        text = content.get('text')
        if text and content.get('encoding') == 'base64':
            try:
                text = base64.b64decode(text).decode('utf-8', 'ignore')
            except ValueError:
                pass
        if text:
            yield where + ' (response body)', text
        for j, msg in enumerate(entry.get('_webSocketMessages') or []):
            yield '%s (websocket %s #%d)' % (where, msg.get('type', ''), j), msg.get('data', '')


def file_items(path, excludes, max_bytes, skip):
    for file in walk(path):
        norm = '/' + os.path.abspath(file).replace(os.sep, '/')
        if any(fnmatch.fnmatch(norm, pat) for pat in excludes) or os.path.abspath(file) in skip:
            continue
        try:
            if os.path.getsize(file) > max_bytes:
                print('skipped (larger than --max-bytes): %s' % file, file=sys.stderr)
                continue
            with open(file, 'rb') as fh:
                raw = fh.read()
        except OSError:
            continue
        if file.endswith('.gz'):
            try:
                raw = gzip.decompress(raw)
            except OSError:
                pass
        text = raw.decode('utf-8', 'ignore')
        if file.endswith('.har'):
            try:
                yield from har_items(file, text)
                continue
            except ValueError:
                pass
        yield file, text


def url_items(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'scan-leaks/1.0'})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            yield url, res.read().decode('utf-8', 'ignore')
    except urllib.error.HTTPError as err:  # error pages leak too
        yield url + ' (HTTP %d)' % err.code, err.read().decode('utf-8', 'ignore')
    except (urllib.error.URLError, OSError) as err:
        sys.exit('could not fetch %s: %s' % (url, err))


def scan(label, text, secrets, index, canaries):
    """index = (all secret shingles, token lengths of secrets shorter than one shingle, words)."""
    every, short_lengths, words = index
    toks = tokens(text)
    found = {sh for sh in shingles(toks, words) if sh in every}
    for n in short_lengths:
        found |= {sh for sh in (' '.join(toks[i:i + n]) for i in range(len(toks) - n + 1)) if sh in every}
    hits = []
    for secret in secrets:
        matched = secret.shingles & found
        if matched:
            hits.append({'target': label, 'secret': secret.name, 'matched': len(matched),
                         'total': len(secret.shingles), 'sample': min(matched, key=len)})
    decoded = decode(text)
    for canary in canaries:
        if canary in text or canary in decoded:
            hits.append({'target': label, 'secret': 'canary:' + canary, 'matched': 1, 'total': 1, 'sample': canary})
    return hits


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('targets', nargs='*', help='files or directories to scan (.har files are parsed)')
    p.add_argument('--secrets', action='append', default=[], metavar='PATH', help='file or directory holding secret prompts (repeatable)')
    p.add_argument('--secret-text', action='append', default=[], metavar='TEXT', help='a secret given inline')
    p.add_argument('--canary', action='append', default=[], metavar='STRING', help='exact marker string planted in a prompt')
    p.add_argument('--url', action='append', default=[], help='fetch and scan a page or API response')
    p.add_argument('--text', action='append', default=[], help='scan this text')
    p.add_argument('--stdin', action='store_true', help='scan text from standard input')
    p.add_argument('--words', type=float, default=8, help='shingle length in words (default 8)')
    p.add_argument('--exclude', action='append', default=[], metavar='GLOB', help='skip matching paths')
    p.add_argument('--no-default-excludes', action='store_true', help='also scan node_modules, .git and server build dirs')
    p.add_argument('--max-bytes', type=int, default=25 * 1024 * 1024, help='skip larger files (default 25 MB)')
    p.add_argument('--json', action='store_true', help='print hits as JSON')
    args = p.parse_intermixed_args(argv)

    secrets = [Secret(name, text, args.words) for path in args.secrets for name, text in secret_texts(path)]
    secrets += [Secret('--secret-text #%d' % (i + 1), t, args.words) for i, t in enumerate(args.secret_text)]
    secrets = [s for s in secrets if s.shingles]
    if not secrets and not args.canary:
        p.error('no usable secrets: pass --secrets/--secret-text with at least a few words, or --canary')
    if not (args.targets or args.url or args.text or args.stdin):
        p.error('nothing to scan: pass targets, --url, --text or --stdin')

    excludes = args.exclude + ([] if args.no_default_excludes else DEFAULT_EXCLUDES)
    skip = {os.path.abspath(f) for s in args.secrets for f in walk(s)}
    items = []
    for target in args.targets:
        if not os.path.exists(target):
            p.error('not found: %s' % target)
        items.append(file_items(target, excludes, args.max_bytes, skip))
    items += [url_items(u) for u in args.url]
    items.append(('<text #%d>' % (i + 1), t) for i, t in enumerate(args.text))
    if args.stdin:
        items.append([('<stdin>', sys.stdin.read())])

    every = set().union(*(s.shingles for s in secrets))
    index = (every, set().union(*(s.short_lengths for s in secrets)), args.words)
    hits, scanned = [], 0
    for group in items:
        for label, text in group:
            scanned += 1
            hits += scan(label, text, secrets, index, args.canary)

    if args.json:
        print(json.dumps({'scanned': scanned, 'secrets': len(secrets), 'hits': hits}, ensure_ascii=False, indent=2))
    elif hits:
        print('LEAK: %d hit(s) in %d scanned item(s)\n' % (len(hits), scanned))
        for h in hits:
            print('  %s\n    secret:  %s\n    matched: %d of %d fingerprints (%.0f%%)\n    sample:  "%s"\n' % (
                h['target'], h['secret'], h['matched'], h['total'], 100.0 * h['matched'] / h['total'], h['sample'][:160]))
    else:
        print('clean: %d item(s) scanned against %d secret(s)%s' % (
            scanned, len(secrets), ' and %d canary(ies)' % len(args.canary) if args.canary else ''))
    return 1 if hits else 0


if __name__ == '__main__':
    sys.exit(main())
