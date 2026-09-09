import contextlib
from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import authentication
import download_comments
import download_posts
from utilities import ExportError


class AccountBindingTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(contextlib.chdir(folder))
        self.enterContext(patch.object(authentication, 'cachedUsername', 'fixture-user'))
        self.enterContext(patch.object(authentication, 'authenticated_request_params',
                                      return_value={'cookies': {'session': 'private-test-cookie'}}))

    def test_binding_stores_only_username_and_accepts_same_account(self):
        authentication.bind_export_account(resume=True)
        manifest = Path('posts-xml/.account.json')
        self.assertEqual(json.loads(manifest.read_text()), {'username': 'fixture-user'})
        self.assertEqual(manifest.stat().st_mode & 0o777, 0o600)
        authentication.bind_export_account(resume=True)

    def test_other_account_stops_and_keeps_manifest(self):
        authentication.bind_export_account(resume=True)
        manifest = Path('posts-xml/.account.json')
        original = manifest.read_bytes()
        with patch.object(authentication, 'cachedUsername', 'another-user'):
            with self.assertRaises(ExportError):
                authentication.bind_export_account(resume=True)
        self.assertEqual(manifest.read_bytes(), original)

    def test_invalid_manifest_stops_without_overwriting_it(self):
        Path('posts-xml').mkdir()
        manifest = Path('posts-xml/.account.json')
        manifest.write_text('invalid-json')
        with self.assertRaises(ExportError):
            authentication.bind_export_account(resume=True)
        self.assertEqual(manifest.read_text(), 'invalid-json')

    def test_first_ordinary_run_adopts_legacy_cache_without_changing_it(self):
        Path('posts-xml').mkdir()
        legacy = Path('posts-xml/2009-03.xml')
        legacy.write_bytes(b'<livejournal/>')

        authentication.bind_export_account()

        self.assertEqual(legacy.read_bytes(), b'<livejournal/>')
        self.assertEqual(json.loads(Path('posts-xml/.account.json').read_text()),
                         {'username': 'fixture-user'})

    def _existing_export(self):
        authentication.bind_export_account()
        files = {
            'posts-xml/2009-03.xml': '<livejournal/>',
            'posts-json/all.json': '["previous posts"]',
            'comments-xml/comment_meta-0.xml': '<livejournal/>',
            'comments-xml/comment_body-1.xml': '<livejournal/>',
            'comments-json/usermap.json': '{"10": "previous-reader"}',
            'comments-json/all.json': '["previous comments"]',
        }
        for name, content in files.items():
            path = Path(name)
            path.parent.mkdir(exist_ok=True)
            path.write_text(content, encoding='utf-8')
        return {path: path.read_bytes() for path in Path('.').rglob('*') if path.is_file()}

    def _allow_manifest_read_only(self):
        read_text = Path.read_text

        def checked_read(path, *args, **kwargs):
            self.assertEqual(path, Path('posts-xml/.account.json'),
                             'An export cache was read before account validation')
            return read_text(path, *args, **kwargs)

        return patch.object(Path, 'read_text', checked_read)

    def test_account_mismatch_blocks_post_refresh_and_resume_without_cache_changes(self):
        original = self._existing_export()
        for resume in (False, True):
            with self.subTest(resume=resume), \
                    patch.object(authentication, 'cachedUsername', 'another-user'), \
                    patch.object(download_posts, 'get_months', return_value=(
                        datetime(2009, 3, 1), datetime(2009, 3, 1))), \
                    patch.object(download_posts, 'fetch_month_posts') as fetch, \
                    patch.object(download_posts, '_atomic_write') as save, \
                    patch.object(download_posts.os, 'makedirs') as mkdir, \
                    self._allow_manifest_read_only():
                with self.assertRaisesRegex(ExportError, 'another account'):
                    download_posts.download_posts(resume=resume)
                fetch.assert_not_called()
                save.assert_not_called()
                mkdir.assert_not_called()
            self.assertEqual(
                {path: path.read_bytes() for path in Path('.').rglob('*') if path.is_file()},
                original)

    def test_account_mismatch_blocks_standalone_comment_refresh_and_resume(self):
        original = self._existing_export()
        for resume in (False, True):
            with self.subTest(resume=resume), \
                    patch.object(authentication, 'cachedUsername', 'another-user'), \
                    patch.object(download_comments, 'fetch_xml') as fetch, \
                    patch.object(download_comments, '_atomic_write') as save, \
                    patch.object(download_comments.os, 'makedirs') as mkdir, \
                    self._allow_manifest_read_only():
                with self.assertRaisesRegex(ExportError, 'another account'):
                    download_comments.download_comments(resume=resume)
                fetch.assert_not_called()
                save.assert_not_called()
                mkdir.assert_not_called()
            self.assertEqual(
                {path: path.read_bytes() for path in Path('.').rglob('*') if path.is_file()},
                original)


class AuthenticationReuseTests(unittest.TestCase):
    def test_repeated_account_checks_reuse_authenticated_session(self):
        with tempfile.TemporaryDirectory() as folder, contextlib.chdir(folder), \
                patch.object(authentication, 'cachedUsername', 'fixture-user'), \
                patch.object(authentication, 'cachedCookies', None), \
                patch.object(authentication, 'get_authenticated_cookies',
                             return_value={'session': 'private-test-cookie'}) as login:
            authentication.bind_export_account()
            authentication.bind_export_account(resume=True)
            authentication.bind_export_account()

            login.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
