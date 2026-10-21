"""Tests for scan_leaks.py. Run: python3 -m unittest test_scan_leaks.py"""

import base64
import contextlib
import io
import json
import os
import tempfile
import unittest

import scan_leaks

TEMPLATE = (
    'You are a senior product photographer. Light the product with a soft key from the '
    'upper left, a warm rim light behind it, and a seamless gradient backdrop that '
    'fades from charcoal to slate. Keep reflections crisp and never crop the logo.'
)
TEMPLATE_ZH = '你是一名资深的商业摄影师。请使用左上方的柔光作为主光，在产品背后加一盏暖色轮廓光，背景使用从炭灰到石板灰的无缝渐变。'


class ScanLeaksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.secrets = self.write('secrets/stylist.txt', TEMPLATE + '\n\n' + TEMPLATE_ZH)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, rel, text):
        path = os.path.join(self.dir, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(text)
        return path

    def run_cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = scan_leaks.main(['--json', '--secrets', self.secrets] + list(args))
        return code, json.loads(out.getvalue())

    def test_plain_bundle_string_is_found(self):
        bundle = self.write('static/chunk.js', 'var a="x";const P=%s;export{P};' % json.dumps(TEMPLATE))
        code, result = self.run_cli(bundle)
        self.assertEqual(code, 1)
        self.assertGreater(result['hits'][0]['matched'], 10)

    def test_double_escaped_rsc_payload_is_found(self):
        inner = json.dumps({'template': TEMPLATE.replace('. ', '.\n')})
        page = self.write('page.html', '<script>self.__next_f.push([1,%s])</script>' % json.dumps('5:' + inner))
        code, result = self.run_cli(page)
        self.assertEqual(code, 1)
        # every fingerprint matches, including those spanning the escaped line breaks
        whole = len(set(scan_leaks.shingles(scan_leaks.tokens(TEMPLATE), 8)))
        self.assertEqual(result['hits'][0]['matched'], whole)

    def test_html_entities_and_unicode_escapes_are_decoded(self):
        escaped = ''.join('\\u%04x' % ord(c) for c in TEMPLATE_ZH)
        page = self.write('zh.json', '{"p":"%s"}' % escaped)
        self.assertEqual(self.run_cli(page)[0], 1)
        page2 = self.write('ent.html', '<div title="%s"></div>' % TEMPLATE.replace("'", '&#39;').replace(' ', '&#32;'))
        self.assertEqual(self.run_cli(page2)[0], 1)

    def test_har_base64_response_names_the_request(self):
        body = base64.b64encode(json.dumps({'result': 'ok', 'debug': {'prompt': TEMPLATE}}).encode()).decode()
        har = {'log': {'entries': [
            {'request': {'method': 'GET', 'url': 'https://app.test/api/health'}, 'response': {'content': {'text': '{"ok":true}'}}},
            {'request': {'method': 'POST', 'url': 'https://app.test/api/generate', 'postData': {'text': '{"skillId":"stylist"}'}},
             'response': {'content': {'text': body, 'encoding': 'base64'}}},
        ]}}
        path = self.write('session.har', json.dumps(har))
        code, result = self.run_cli(path)
        self.assertEqual(code, 1)
        self.assertEqual(len(result['hits']), 1)
        self.assertIn('POST https://app.test/api/generate (response body)', result['hits'][0]['target'])

    def test_unrelated_text_with_shared_words_is_clean(self):
        page = self.write('static/app.js', 'Upload a product photo. The photographer can light the logo, '
                                           'then crop the backdrop. A soft key and a warm rim are both options.')
        code, result = self.run_cli(page)
        self.assertEqual((code, result['hits']), (0, []))

    def test_code_secret_fingerprints_only_string_literals(self):
        self.secrets = self.write('server/registry.ts',
                                  "import 'server-only'\nexport function composePrompt(choices, userRequest) {\n"
                                  "  return `%s ${userRequest}`\n}\n" % TEMPLATE)
        same_code = self.write('static/client.js', 'export function composePrompt(choices, userRequest) { return api(choices, userRequest) }')
        self.assertEqual(self.run_cli(same_code)[0], 0)
        leaked = self.write('static/leak.js', 'const t=`%s`' % TEMPLATE)
        self.assertEqual(self.run_cli(leaked)[0], 1)

    def test_short_secret_matches_whole(self):
        code, _ = self.run_cli('--secret-text', 'charcoal slate gradient, no lens flare', '--text', 'neg: Charcoal  slate gradient, no lens-flare!')
        self.assertEqual(code, 1)

    def test_canary_and_text_inputs(self):
        self.assertEqual(self.run_cli('--canary', 'cnry-7f3a', '--text', 'hello cnry-7f3a')[0], 1)
        self.assertEqual(self.run_cli('--text', 'nothing secret here at all, just a reply about photos')[0], 0)

    def test_server_build_dir_and_secret_files_are_skipped_by_default(self):
        self.write('.next/server/app/page.js', 'const T=%s' % json.dumps(TEMPLATE))
        self.write('.next/static/chunks/main.js', 'console.log("hi")')
        code, result = self.run_cli(os.path.join(self.dir, '.next'))
        self.assertEqual(code, 0, result)
        self.assertEqual(self.run_cli(self.dir)[0], 0)  # the secret file itself is never a target
        code, result = self.run_cli('--no-default-excludes', self.dir)
        self.assertEqual(code, 1)
        self.assertEqual([h['target'] for h in result['hits']], [os.path.join(self.dir, '.next/server/app/page.js')])


if __name__ == '__main__':
    unittest.main()
