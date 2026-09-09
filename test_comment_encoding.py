import contextlib
import io
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import requests

from xml_responses import ExportResponseError, parse_response, save_response


def response(raw):
    result = requests.Response()
    result.status_code = 200
    result._content = raw
    result._content_consumed = True
    return result


def envelope(fields):
    return b'<?xml version="1.0" encoding="utf-8"?><livejournal><comments>' + fields + b'</comments></livejournal>'


class CommentEncodingTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(contextlib.chdir(folder))
        self.stderr = self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def test_mixed_encodings_preserve_each_field_and_raw_response(self):
        old = 'Точно Р°: старый комментарий'
        modern = 'И новый комментарий 😀'
        raw = envelope(b'<comment id="1"><subject>' + 'Тема'.encode('cp1251')
                       + b'</subject><body>' + old.encode('cp1251') + b'</body></comment>'
                       + b'<comment id="2"><body>' + modern.encode('utf-8')
                       + b'</body></comment><comment id="3" state="D"/>')
        xml = parse_response(response(raw), '/export_comments.bml', {})
        root = ET.fromstring(xml)
        self.assertEqual([x.text for x in root.iter('body')], [old, modern])
        self.assertEqual(root.find('.//subject').text, 'Тема')
        self.assertEqual(len(list(root.iter('comment'))), 3)
        self.assertNotIn('\ufffd', xml)
        saved = next(Path('diagnostics').glob('*.response.bin'))
        self.assertEqual(saved.read_bytes(), raw)
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(old, self.stderr.getvalue())

    def test_subject_and_body_can_use_different_encodings(self):
        raw = envelope(b'<comment id="1"><subject>' + 'Старая'.encode('cp1251')
                       + b'</subject><body>' + 'Новая И'.encode('utf-8') + b'</body></comment>')
        root = ET.fromstring(parse_response(response(raw), '/export_comments.bml', {}))
        self.assertEqual(root.find('.//subject').text, 'Старая')
        self.assertEqual(root.find('.//body').text, 'Новая И')

    def test_cdata_and_numeric_entities_keep_meaning(self):
        raw = envelope(b'<comment id="1"><subject>' + 'Тема'.encode('cp1251')
                       + b' &#1048;</subject><body><![CDATA[' + 'Текст <tag>'.encode('cp1251')
                       + b']]></body></comment>')
        root = ET.fromstring(parse_response(response(raw), '/export_comments.bml', {}))
        self.assertEqual(root.find('.//subject').text, 'Тема И')
        self.assertEqual(root.find('.//body').text, 'Текст <tag>')

    def test_bad_bytes_outside_known_fields_are_not_guessed(self):
        raw = envelope(b'<comment id="1" posterid="\xff"><body>'
                       + 'Текст'.encode('cp1251') + b'</body></comment>')
        with self.assertRaises(ExportResponseError):
            parse_response(response(raw), '/export_comments.bml', {})

    def test_legacy_field_with_control_character_preserves_both_repairs(self):
        raw = envelope(b'<comment id="1"><body>' + 'Привет'.encode('cp1251')
                       + b'\x01' + ' мир'.encode('cp1251') + b'</body></comment>')
        parsed = parse_response(response(raw), '/export_comments.bml', {})
        self.assertEqual(ET.fromstring(parsed).find('.//body').text, 'Привет\ufffd мир')
        self.assertEqual(next(Path('diagnostics').glob('*.response.bin')).read_bytes(), raw)
        self.assertIn('Windows-1251', self.stderr.getvalue())
        self.assertIn('U+FFFD', self.stderr.getvalue())

    def test_undefined_legacy_byte_is_not_replaced(self):
        raw = envelope(b'<comment id="1"><body>\xff\x98</body></comment>')
        with self.assertRaises(ExportResponseError):
            parse_response(response(raw), '/export_comments.bml', {})

    def test_existing_failed_response_can_be_repaired_without_rewriting_original(self):
        raw = envelope(b'<comment id="1"><body>' + 'Текст'.encode('cp1251') + b'</body></comment>')
        r = response(raw)
        saved = save_response(r, '/export_comments.bml', {}, 'original encoding failure')
        before = saved.stat().st_mtime_ns
        parsed = parse_response(r, '/export_comments.bml', {})
        self.assertEqual(ET.fromstring(parsed).find('.//body').text, 'Текст')
        self.assertEqual(saved.read_bytes(), raw)
        self.assertEqual(saved.stat().st_mtime_ns, before)

    def test_legacy_fallback_is_not_used_for_post_exports(self):
        raw = b'<livejournal><entry><event>' + 'Текст'.encode('cp1251') + b'</event></entry></livejournal>'
        with self.assertRaises(ExportResponseError):
            parse_response(response(raw), '/export_do.bml', {})


if __name__ == '__main__':
    unittest.main()
