# Export your LiveJournal blog data

[Livejournal provides a method to export your posts as 
XML](http://www.livejournal.com/export.bml). However 
this has to be done manually for every month of your blog. 
Also [comments are exported separately](http://www.livejournal.com/developer/exporting.bml).
I wrote this tool to make exporting more convenient.

You will need Python 3 to use it.

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

## download_posts.py

This script will download your posts in XML into `posts-xml` 
folder. Also it will create `posts-json/all.json` file with
the same data in JSON format for convenient processing.

## download_comments.py

This script will download comments from your blog as 
`comments-xml/*.xml` files. Also it will create
`comments-json/all.json` with all the comments data in
JSON format for convenient processing.

## Requirements

See [Pipfile](Pipfile) for up-to-date requirements list.

Run `pipenv install && pipenv run ./export.py` to run the script in created virtual enviromnent.

More about `pipenv` can be found [in Pipenv documentation](https://pipenv.pypa.io/en/latest/).

## Processing exported data separately

In the last lines of `export.py` there's a condition `if True:`.
Change `True` to `False` to skip the downloading step and go
directly to the processing of already downloaded data.

