# Export your LiveJournal blog data

[Livejournal provides a method to export your posts as 
XML](http://www.livejournal.com/export.bml). However 
this has to be done manually for every month of your blog. 
Also [comments are exported separately](http://www.livejournal.com/developer/exporting.bml).
I wrote this tool to make exporting more convenient.

You will need Python 3 to use it.

## export.py

This script will do the exporting. Run it after you 
have provided cookies and years as described below.
You will end up with full blog contents in several 
formats. `posts-html` folder will contain basic HTML
of posts and comments. `posts-markdown` will contain
posts in Markdown format with HTML comments and metadata 
necessary to [generate a static blog with Pelican](http://docs.getpelican.com/).
`posts-json` will contain posts with nested comments 
in JSON format should you want to process them further.

## auth.py

First of all you will have to log into Livejournal 
and copy values of cookies `ljloggedin` and `ljmastersession` 
to the file auth.py.

## download_posts.py

Edit this file to specify the range of years you want to export.
This script will download your posts in XML into `posts-xml` 
folder. Also it will create `posts-json/all.json` file with all 
the same data in JSON format for convenient processing.

## download_comments.py

This script will download comments from your blog as `comments-xml/*.xml`
files. Also it will create `comments-json/all.json` with all the 
comments data in JSON format for convenient processing.

## Requirements

* `html2text`
* `markdown`
* `beautifulsoup4`
* `requests`

## Processing exported data separately

In the last lines of `export.py` there's a condition `if True:`.
Change `True` to `False` to skip the downloading step and go
directly to the processing of already downloaded data.

