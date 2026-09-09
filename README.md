# Export your LiveJournal blog data

[Livejournal provides a method to export your posts as 
XML](http://www.livejournal.com/export.bml). However 
this has to be done manually for every month of your blog. 
Also [comments are exported separately](http://www.livejournal.com/developer/exporting.bml).
I wrote this tool to make exporting more convenient.

You will need Python 3.4 or newer to use it.

## export.py

This script will do the exporting. You will end up with
full blog contents in several formats. `posts-html` folder
will contain basic HTML of posts and comments.
`posts-markdown` will contain posts in Markdown format
with HTML comments and metadata necessary to
[generate a static blog with Pelican](http://docs.getpelican.com/).
`posts-json` will contain posts with nested comments 
in JSON format should you want to process them further.

This version of the script does not require you to make any
modifications prior to running it. It will prompt you for
the range of months you want to pull, then will ask for your
LiveJournal username and password. It will use that to 
acquire the required session cookies. After this, the
download process will begin.

To continue an interrupted download, run `python export.py --resume` with the
same account and the original full date range. Completed monthly XML files are
validated and reused; both cached and newly downloaded posts are included in the
result. Comments are downloaded after all posts. Resume also reuses validated
comment metadata and body batches, continuing the saved snapshot up to its
recorded maximum comment ID. Without `--resume`, the selected months and comment
batches are downloaded again.

The first run records the authenticated login name in `posts-xml/.account.json`.
Every later run, with or without `--resume`, checks this account before reading or
overwriting saved exports. Passwords and session cookies are not stored. Use
separate working directories for different journals. Existing exports without
an account file are assigned to the account used on their first run with this
version; only resume such a directory with its original account.

Monthly XML, comment batches, and aggregate JSON files are written atomically so
interruptions cannot leave partially written cache files. Invalid cached XML is
kept for inspection and stops the export instead of being silently skipped or
overwritten. Comment pagination stops with an error if the server makes no
progress. After a failure, use `--resume` to continue from completed files.

## download_posts.py

This script will download your posts in XML into `posts-xml` 
folder. Also it will create `posts-json/all.json` file with
the same data in JSON format for convenient processing.

## download_comments.py

This script will download comments from your blog as 
`comments-xml/*.xml` files. Also it will create
`comments-json/all.json` with all the comments data in
JSON format for convenient processing.

## import_ljarchive.py

This script converts the files downloaded by external tool ljarchive (?)
into the format used by `export.py`.

## Requirements

* `dateutil`
* `html2text`
* `markdown`
* `beautifulsoup4`
* `requests`
* `lxml`

## Processing exported data separately

In the last lines of `export.py` there's a condition `if True:`.
Change `True` to `False` to skip the downloading step and go
directly to the processing of already downloaded data.

## Processing archives created by ljarchive

If you have already downloaded your blog data using ljarchive,
place them in the `posts-xml` folder and run `import_ljarchive.py`.
Then follow the steps described in the previous section.
