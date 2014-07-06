# Export your LiveJournal blog data

[Livejournal provides a method to export your texts as 
XML](http://www.livejournal.com/export.bml). However 
this has to be done manually for every month of your blog. 
Also it does not export comments. I used this set of tools
to help me at least with the first task. 

## download_xmls.py

This script will download your entries in XML for all the years
you specify. I took the simple way and did authentication by cookies
taken from my browser. You will have to repeat the same for 
your cookies.

## lj_xml_to_md.py

This script will convert the entries from HTML wrapped in XML 
to markdown files suitable to use in many 
[static sites generators](http://staticsitegenerators.net/) 
like [metalsmith](https://github.com/segmentio/metalsmith).
The metadata like title, date, UTX tags will be saved in the
front-matter in these files. It needs 
[`html2text`](https://github.com/html2text/html2text/) to work.