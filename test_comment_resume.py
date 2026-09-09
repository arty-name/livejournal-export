"""Offline checks for continuing comment batches after an interrupted export."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import download_comments
from utilities import ExportError


def metadata_xml(max_id, next_id=None, user_id=10):
    next_tag = '' if next_id is None else f'<nextid>{next_id}</nextid>'
    return (f'<livejournal><maxid>{max_id}</maxid>{next_tag}'
            f'<usermaps><usermap id="{user_id}" user="reader-{user_id}"/></usermaps>'
            '<comments/></livejournal>')


def body_xml(*ids):
    comments = ''.join(
        f'<comment id="{comment_id}" jitemid="7" posterid="10">'
        f'<body>Comment {comment_id}</body></comment>' for comment_id in ids)
    return f'<livejournal><comments>{comments}</comments></livejournal>'


class CommentResumeTests(unittest.TestCase):
    def setUp(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(contextlib.chdir(folder))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        Path('comments-xml').mkdir()
        Path('comments-json').mkdir()
        self.fetch = self.enterContext(patch.object(download_comments, 'fetch_xml'))
        self.bind = self.enterContext(patch.object(download_comments, 'bind_export_account'))

    def cache(self, kind, start_id, xml):
        path = Path(f'comments-xml/{kind}-{start_id}.xml')
        path.write_text(xml, encoding='utf-8')
        return path

    def assert_no_temporary_files(self):
        self.assertEqual(list(Path('.').rglob('*.tmp')), [])

    def test_all_cached_pages_rebuild_aggregate_without_network(self):
        paths = [
            self.cache('comment_meta', 0, metadata_xml(3, 2)),
            self.cache('comment_meta', 2, metadata_xml(3, user_id=11)),
            self.cache('comment_body', 1, body_xml(1, 2)),
            self.cache('comment_body', 3, body_xml(3)),
        ]
        originals = {path: path.read_bytes() for path in paths}

        comments = download_comments.download_comments(resume=True)

        self.bind.assert_called_once_with(resume=True)
        self.fetch.assert_not_called()
        self.assertEqual([comment['id'] for comment in comments], [1, 2, 3])
        self.assertEqual(comments[0]['author'], 'reader-10')
        self.assertEqual(json.loads(Path('comments-json/all.json').read_text()), comments)
        self.assertEqual(json.loads(Path('comments-json/usermap.json').read_text()),
                         {'10': 'reader-10', '11': 'reader-11'})
        self.assertEqual({path: path.read_bytes() for path in paths}, originals)
        self.assert_no_temporary_files()

    def test_only_missing_body_batch_is_downloaded(self):
        self.cache('comment_meta', 0, metadata_xml(3))
        first = self.cache('comment_body', 1, body_xml(1, 2))
        original = first.read_bytes()
        self.fetch.return_value = body_xml(3)

        comments = download_comments.download_comments(resume=True)

        self.fetch.assert_called_once_with({'get': 'comment_body', 'startid': 3})
        self.assertEqual([comment['id'] for comment in comments], [1, 2, 3])
        self.assertEqual(first.read_bytes(), original)
        self.assertEqual(Path('comments-xml/comment_body-3.xml').read_text(), body_xml(3))
        self.assert_no_temporary_files()

    def test_invalid_metadata_cache_is_preserved_without_network(self):
        invalid_samples = (
            '<livejournal>',
            '<html><body>private sample</body></html>',
            '<livejournal><error>private sample</error></livejournal>',
            '<livejournal><comments/></livejournal>',
            '<livejournal><maxid>not a number</maxid><comments/></livejournal>',
            '<livejournal><maxid>3</maxid><comments/><comments/></livejournal>',
        )
        for xml in invalid_samples:
            with self.subTest(xml=xml):
                path = self.cache('comment_meta', 0, xml)
                aggregate = Path('comments-json/all.json')
                aggregate.write_text('previous aggregate')

                with self.assertRaises(ExportError) as caught:
                    download_comments.download_comments(resume=True)

                self.fetch.assert_not_called()
                self.assertEqual(path.read_text(), xml)
                self.assertEqual(aggregate.read_text(), 'previous aggregate')
                self.assertIn('existing file was kept', str(caught.exception))
                self.assertNotIn('private sample', str(caught.exception))
                self.assert_no_temporary_files()

    def test_invalid_body_cache_is_preserved_without_network(self):
        self.cache('comment_meta', 0, metadata_xml(3))
        invalid_samples = (
            '<livejournal><maxid>3</maxid><comments/></livejournal>',
            '<livejournal><comments><error>private sample</error></comments></livejournal>',
            '<livejournal><comments><comment id="1"/></comments></livejournal>',
            '<livejournal><comments><comment id="1" jitemid="7" posterid="bad"/></comments></livejournal>',
        )
        for xml in invalid_samples:
            with self.subTest(xml=xml):
                path = self.cache('comment_body', 1, xml)
                aggregate = Path('comments-json/all.json')
                aggregate.write_text('previous aggregate')

                with self.assertRaises(ExportError) as caught:
                    download_comments.download_comments(resume=True)

                self.fetch.assert_not_called()
                self.assertEqual(path.read_text(), xml)
                self.assertEqual(aggregate.read_text(), 'previous aggregate')
                self.assertNotIn('private sample', str(caught.exception))

    def test_unreadable_encoding_cache_is_preserved(self):
        self.cache('comment_meta', 0, metadata_xml(3))
        path = Path('comments-xml/comment_body-1.xml')
        path.write_bytes(b'\xff')

        with self.assertRaisesRegex(ExportError, 'encoding and permissions'):
            download_comments.download_comments(resume=True)

        self.fetch.assert_not_called()
        self.assertEqual(path.read_bytes(), b'\xff')

    def test_empty_new_batch_stops_without_saving_or_overwriting_aggregate(self):
        self.cache('comment_meta', 0, metadata_xml(3))
        self.fetch.return_value = body_xml()
        aggregate = Path('comments-json/all.json')
        aggregate.write_text('previous aggregate')

        with self.assertRaisesRegex(ExportError, 'made no progress') as caught:
            download_comments.download_comments(resume=True)

        self.fetch.assert_called_once_with({'get': 'comment_body', 'startid': 1})
        self.assertIn('--resume', str(caught.exception))
        self.assertFalse(Path('comments-xml/comment_body-1.xml').exists())
        self.assertEqual(aggregate.read_text(), 'previous aggregate')
        self.assert_no_temporary_files()

    def test_nonadvancing_cached_batch_stops_and_preserves_file(self):
        self.cache('comment_meta', 0, metadata_xml(3))
        self.cache('comment_body', 1, body_xml(1, 2))
        path = self.cache('comment_body', 3, body_xml(1, 2))

        with self.assertRaisesRegex(ExportError, 'made no progress') as caught:
            download_comments.download_comments(resume=True)

        self.fetch.assert_not_called()
        self.assertIn(str(path), str(caught.exception))
        self.assertIn('existing file was kept', str(caught.exception))
        self.assertEqual(path.read_text(), body_xml(1, 2))
        self.assertFalse(Path('comments-json/all.json').exists())

    def test_nonadvancing_metadata_stops_before_body_download(self):
        path = self.cache('comment_meta', 0, metadata_xml(3, 0))

        with self.assertRaisesRegex(ExportError, 'non-advancing next ID'):
            download_comments.download_comments(resume=True)

        self.fetch.assert_not_called()
        self.assertEqual(path.read_text(), metadata_xml(3, 0))
        self.assertFalse(Path('comments-json/all.json').exists())

    def test_zero_comments_creates_valid_empty_aggregate(self):
        self.cache('comment_meta', 0, metadata_xml(0))

        self.assertEqual(download_comments.download_comments(resume=True), [])

        self.fetch.assert_not_called()
        self.assertEqual(json.loads(Path('comments-json/all.json').read_text()), [])

    def test_default_mode_downloads_batches_again(self):
        self.cache('comment_meta', 0, metadata_xml(3))
        self.cache('comment_body', 1, body_xml(1, 2, 3))
        self.fetch.side_effect = [metadata_xml(1), body_xml(1)]

        comments = download_comments.download_comments()

        self.bind.assert_called_once_with(resume=False)
        self.assertEqual(self.fetch.call_count, 2)
        self.assertEqual([comment['id'] for comment in comments], [1])
        self.assertEqual(Path('comments-xml/comment_body-1.xml').read_text(), body_xml(1))
        self.assert_no_temporary_files()

    def test_new_batch_is_kept_if_aggregate_publication_fails(self):
        self.cache('comment_meta', 0, metadata_xml(1))
        self.fetch.return_value = body_xml(1)
        aggregate = Path('comments-json/all.json')
        aggregate.write_text('previous aggregate')
        real_write = download_comments._atomic_write

        def fail_aggregate(path, content, *, replace):
            if str(path) == 'comments-json/all.json':
                raise ExportError('Could not publish aggregate')
            return real_write(path, content, replace=replace)

        with patch.object(download_comments, '_atomic_write', side_effect=fail_aggregate):
            with self.assertRaisesRegex(ExportError, 'publish aggregate'):
                download_comments.download_comments(resume=True)

        self.assertEqual(Path('comments-xml/comment_body-1.xml').read_text(), body_xml(1))
        self.assertEqual(aggregate.read_text(), 'previous aggregate')
        self.assert_no_temporary_files()


if __name__ == '__main__':
    unittest.main()
