# Export your LiveJournal blog data

[Livejournal provides a method to export your posts as 
XML](http://www.livejournal.com/export.bml). However 
this has to be done manually for every month of your blog. 
Also [comments are exported separately](http://www.livejournal.com/developer/exporting.bml).
I wrote this tool to make exporting more convenient.

You will need Python 3.12 or newer to use it.

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

## Network errors and historical XML

Login and export share an HTTPS session. Read-only post/comment downloads retry
transient connection failures, incomplete chunked responses, HTTP 502/503/504,
and malformed or non-export responses up to four total attempts, waiting 2, 4,
and 8 seconds. Requests have 15-second connection and 60-second read timeouts.
Login is not retried, and TLS certificate verification remains enabled.

Unexpected responses are saved privately under `diagnostics/` after the final
attempt, with safe metadata describing the failure and XML error position.
These files can contain private post text and are excluded from Git. Request
headers, cookies, and credentials are not logged. XML-forbidden literal control
characters are replaced with U+FFFD only if the complete result then passes
strict parsing; the original response is preserved and the repair is reported.
Other malformed XML is never silently accepted as an empty month.

Historical comment exports can declare UTF-8 while containing Windows-1251
subjects/bodies alongside newer UTF-8 comments. Text fields are decoded
independently: valid UTF-8 is preserved; otherwise the entire field is decoded
strictly as Windows-1251. This automatic fallback assumes one encoding per field
and Windows-1251 for legacy text; it does not detect arbitrary legacy encodings.
Only subject/body payloads are converted. The original bytes are retained and
the complete result must pass strict XML parsing. No bytes are silently dropped.

## Tests

Install the requirements below, then run `python -m unittest discover -v`.
Tests use synthetic fixtures and require no LiveJournal credentials or network.

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
