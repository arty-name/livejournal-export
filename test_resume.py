"""Offline checks for retaining completed months across interrupted exports."""

import contextlib
from datetime import datetime
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import download_posts
from utilities import ExportError


def month_xml(item_id):
    return (
        '<livejournal><entry>'
        f'<itemid>{item_id}</itemid><logtime>2009-03-01 12:00:00</logtime>'
        '<subject>Sample post</subject><event>Sample body</event>'
        '</entry></livejournal>'
    )


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = self.enterContext(tempfile.TemporaryDirectory())
        self.previous_cwd = Path.cwd()
        os.chdir(self.temporary)
        self.addCleanup(os.chdir, self.previous_cwd)
        Path('posts-xml').mkdir()
        Path('posts-json').mkdir()
        self.output = io.StringIO()
        self.enterContext(contextlib.redirect_stdout(self.output))
        self.months = self.enterContext(patch.object(
            download_posts, 'get_months', return_value=(
                datetime(2009, 3, 1), datetime(2009, 4, 1))))
        self.fetch = self.enterContext(patch.object(download_posts, 'fetch_month_posts'))
        self.bind = self.enterContext(patch.object(download_posts, 'bind_export_account'))

    def cache(self, month, xml):
        path = Path(f'posts-xml/{month}.xml')
        path.write_text(xml, encoding='utf-8')
        return path

    def assert_no_temporary_files(self):
        self.assertEqual(list(Path('.').rglob('*.tmp')), [])

    def test_resume_uses_completed_month_and_downloads_only_missing_month(self):
        path = self.cache('2009-03', month_xml(1))
        original = path.read_bytes()
        self.fetch.return_value = month_xml(2)

        posts = download_posts.download_posts(resume=True)

        self.bind.assert_called_once_with(resume=True)
        self.fetch.assert_called_once_with(2009, 4)
        self.assertEqual([post['id'] for post in posts], [1, 2])
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(json.loads(Path('posts-json/all.json').read_text()), posts)
        self.assertEqual(Path('posts-xml/2009-04.xml').read_text(), month_xml(2))
        self.assert_no_temporary_files()

    def test_all_cached_months_are_included_without_network_calls(self):
        self.cache('2009-03', month_xml(1))
        self.cache('2009-04', month_xml(2))

        posts = download_posts.download_posts(resume=True)

        self.fetch.assert_not_called()
        self.assertEqual([post['id'] for post in posts], [1, 2])

    def test_empty_month_is_a_valid_cache(self):
        self.cache('2009-03', '<livejournal/>')
        self.cache('2009-04', month_xml(2))

        posts = download_posts.download_posts(resume=True)

        self.fetch.assert_not_called()
        self.assertEqual([post['id'] for post in posts], [2])

    def test_invalid_cache_stops_without_replacing_it_or_aggregate(self):
        invalid_samples = (
            '<livejournal>',
            '<html><body>private sample</body></html>',
            '<livejournal><error>private sample</error></livejournal>',
            '<livejournal>private sample</livejournal>',
            '<response><entry/></response>',
        )
        for xml in invalid_samples:
            with self.subTest(xml=xml):
                path = self.cache('2009-03', xml)
                aggregate = Path('posts-json/all.json')
                aggregate.write_text('previous complete aggregate')

                with self.assertRaises(ExportError) as caught:
                    download_posts.download_posts(resume=True)

                self.fetch.assert_not_called()
                self.assertEqual(path.read_text(), xml)
                self.assertEqual(aggregate.read_text(), 'previous complete aggregate')
                self.assertIn('existing file was kept', str(caught.exception))
                self.assertNotIn('private sample', str(caught.exception))
                self.assert_no_temporary_files()

    def test_account_mismatch_stops_before_reading_or_downloading_months(self):
        path = self.cache('2009-03', month_xml(1))
        original = path.read_bytes()
        self.bind.side_effect = ExportError('Different account')

        with self.assertRaisesRegex(ExportError, 'Different account'):
            download_posts.download_posts(resume=True)

        self.fetch.assert_not_called()
        self.assertEqual(path.read_bytes(), original)
        self.assertFalse(Path('posts-json/all.json').exists())

    def test_invalid_new_month_is_never_saved(self):
        self.fetch.return_value = '<livejournal><error>private sample</error></livejournal>'

        with self.assertRaises(ExportError):
            download_posts.download_posts(resume=True)

        self.assertFalse(Path('posts-xml/2009-03.xml').exists())
        self.assertFalse(Path('posts-json/all.json').exists())
        self.assert_no_temporary_files()

    def test_interruption_during_publish_retains_previous_completed_month(self):
        original = self.cache('2009-03', month_xml(1)).read_bytes()
        self.fetch.return_value = month_xml(2)
        with patch.object(download_posts.os, 'link', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                download_posts.download_posts(resume=True)

        self.assertEqual(Path('posts-xml/2009-03.xml').read_bytes(), original)
        self.assertFalse(Path('posts-xml/2009-04.xml').exists())
        self.assert_no_temporary_files()

    def test_aggregate_publication_failure_keeps_previous_aggregate_and_new_month(self):
        self.cache('2009-03', month_xml(1))
        self.fetch.return_value = month_xml(2)
        aggregate = Path('posts-json/all.json')
        aggregate.write_text('previous complete aggregate')
        with patch.object(download_posts.os, 'replace', side_effect=OSError('disk full')):
            with self.assertRaises(ExportError):
                download_posts.download_posts(resume=True)

        self.assertEqual(aggregate.read_text(), 'previous complete aggregate')
        self.assertEqual(Path('posts-xml/2009-04.xml').read_text(), month_xml(2))
        self.assert_no_temporary_files()

    def test_new_cache_publication_never_clobbers_a_concurrent_file(self):
        path = Path('posts-xml/2009-04.xml')
        path.write_text('written by another export')

        with self.assertRaises(ExportError):
            download_posts._atomic_write(path, month_xml(2), replace=False)

        self.assertEqual(path.read_text(), 'written by another export')
        self.assert_no_temporary_files()

    def test_default_mode_downloads_range_again(self):
        self.cache('2009-03', month_xml(1))
        self.cache('2009-04', month_xml(2))
        self.fetch.side_effect = [month_xml(3), month_xml(4)]

        posts = download_posts.download_posts()

        self.bind.assert_called_once_with(resume=False)
        self.assertEqual([post['id'] for post in posts], [3, 4])
        self.assertEqual(self.fetch.call_count, 2)
        self.assertEqual(Path('posts-xml/2009-03.xml').read_text(), month_xml(3))
        self.assertEqual(Path('posts-xml/2009-04.xml').read_text(), month_xml(4))
        self.assert_no_temporary_files()


if __name__ == '__main__':
    unittest.main()
