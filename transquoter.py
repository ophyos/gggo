#!/bin/sh -
"exec" "python" "-Ot" "$0" "$@"
# Under UNIX, the magic incantations above cause the Python interpreter to
# be invoked on this file with the options "-Ot" (optimise and check tabs)

# TQclient.py
# Copyright (c) 2004-2005 Xanadu Australia
# This code will be released under an Open Source license to be determined
# 2004/05/20 Created by Andrew Pam <xanni@xanadu.net>
# 2004/05/26 Added code to run the proxy server in the background
# 2004/05/30 Imported into subversion
# 2004/09/06 Incorporated CSS into HTML header, implemented resolve_URL()
# 2004/09/14 Renamed to TQclient, removed server code
# 2004/09/15 Added client-side locspec=charrange support
# 2004/09/16 Added HTML/SGML/XML markup removal
# 2004/12/08 Changed terminology and URL of home page
# 2005/03/10 Fixed URL schemes that don't support queries
# 2005/03/13 Added IOError handling, line and paragraph breaks, titles
# 2005/03/14 Added non-visible content removal and whitespace compression
# 2005/03/14 Added caching of colours and documents
# 2005/03/16 Improved error handling, added progress indication
# 2005/06/19 Added initial support for images
# 2005/07/03 Replaced breaks hack with "data:" literals
# 2005/07/18 Corrected local URLs to start with "file://"
# 2005/08/29 Change line breaks in emitted HTML to remove whitespace

__version__ = "0.14"
__doc__ = """Transquotation client for Ted Nelson's DeepLit

If invoked with a parameter, opens the named file, processes it as a
"virtual stream list" of URLs by assembling an HTML page concatenating
the results of retrieving the URLs listed, and executes the default
system web browser with the resulting HTML page.

In future, this program will cache requests.  It should also enclose
references to non-textual documents in <object> tags rather than resolving
them.  (For compatibility, image/* MIME-types are enclosed in <img> tags.)
"""

import os, re, sys, tempfile, urllib2, webbrowser, htmlentitydefs

# Define constants
TQhome = "http://www.xanadu.com.au/transquoter/"
classes = ( "red", "green", "blue", "yellow", "magenta", "cyan", "error", "" )
nclasses = len(classes) - 2	# The last two classes are special
css =  """
<style type="text/css"><!--
@media screen {body {background: white; color: black; margin: 20px;}}
:link,:visited {color: black; text-decoration: none;}
a.error {color: red;}
a.red:hover {background: #FF6666;}
a.green:hover {background: #66FF66;}
a.blue:hover {background: #6666FF;}
a.yellow:hover {background: #FFFF66;}
a.magenta:hover {background: #FF66FF;}
a.cyan:hover {background: #66FFFF;}
--></style>
"""
htmlheader1 = """<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN">
<html>
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">
<title>"""
htmlheader2 = "</title>" + css + "</head>\n<body>\n<p>\n"
htmlfooter = "</p>\n</body>\n</html>\n"
content_type = '<meta http-equiv="content-type" content="'
target = 'target="context" rev="original context"'
default_charset = "windows-1252"
magic = "?xuversion=1.0&locspec="
mimetypes = ( "text/html", "text/sgml", "text/xml" )
deletere = re.compile(r"<!--.+?-->|<(head|script|style).+?</(\1)>", \
		      re.DOTALL | re.IGNORECASE)
entityre = re.compile("&(" + \
		      "|".join(htmlentitydefs.name2codepoint.keys()) + ");")

# Initialise global variables
current_colour = -1		# The first document will have no class
colours = {}
documents = {}
titles = {}

def numeric_entity(match):
	"Convert a numeric HTML entity match object into a character."
	return chr(int(match.group(1)))

def decode_entity(match):
	"Convert an HTML entity match object into a Unicode character."
	return unichr(htmlentitydefs.name2codepoint[match.group(1)])

def decode_hexpair(match):
	"Convert a pair of hex digits into a character."
	return chr(int(match.group(1),16))

def between(s, start, finish):
	"""
	Return all characters from s between the first
	(case insignificant) instances of start and finish.
	"""
	l = s.lower()
	r = ""			# Result string
	i = l.find(start)
	if i >= 0:
		i += len(start)
		r = s[i : l.find(finish, i)]
	return r

def resolve(URL):
	"""
	Resolve a URL into a tuple containing a Unicode string and a
	title (if any).  If the string begins with a space, it contains
	an error message.
	"""
	
	h = None	# Headers
	title = ""
	print "Resolving " + URL
	try:
		rf = urllib2.urlopen(URL)

		try:
			h = rf.info()
			# Don't bother reading non-text media types for now
			# Change this once ranges are supported for other types
			if not h or h.type.startswith("text/"):
				data = rf.read()
		finally:
			rf.close()

		if h and h.type in mimetypes:
			c = between(data, content_type, '"')
			if not c:
				c = h["Content-Type"]
			match = re.search("charset=([^;]+)", c.lower())
			data = re.sub("&#(\d+);", numeric_entity, data)
			if match:
				data = data.decode(match.group(1))
			else:
				data = data.decode(default_charset)
			title = between(data, "<title>", "</title>")
			data = deletere.sub("", data)
			data = re.sub("<[^>]*>", "", data)
			data = entityre.sub(decode_entity, data)

		if not h or h.type.startswith("text/"):
			data = re.sub(r"\s+", " ", data).strip()
		elif h.type.startswith("image/"):
			data = '<img src="' + URL + '">'
		else:
			data = " " + h.type
	except EnvironmentError:
		data = " " + URL
	except LookupError:
		data = " Unable to decode charset " + c
	return (data, title)

def transclude(URL):
	"""
	Resolve a URL into a Unicode string of HTML containing
	the transcluded content enclosed in a context link.
	"""
	global current_colour, colours, documents, titles
	baseurl = URL
	u = URL
	l = -1		# The default character range is the entire document

	try:
		# Is this a Xanadu character range selection URL
		m = u.rfind(magic + "charrange:")
		if m >= 0:
			baseurl = u[ : m]
			# If the scheme is not http or similar (shttp, https)
			# or the URL contains a query string
			if "http" not in u.split(":")[0] or u.count("?") > 1:
				u = baseurl
			# Get the start and length of the character range
			(s, l) = URL[m + len(magic) + 10 : ].split("/")
			s = int(s)
			l = int(l)
		if baseurl in documents:
			data = documents[baseurl]
		else:
			data, titles[baseurl] = resolve(u)
			if u == baseurl or len(data) > l:
				documents[baseurl] = data
	except:
		print "Invalid range " + URL
		data = " " + URL

	if data[0] == " ":		# Error
		data = data[1 : ]
		colours[baseurl] = -2
	else:
		if baseurl not in colours:
			colours[baseurl] = current_colour
			current_colour = (current_colour + 1) % nclasses
		if m >= 0:
			if len(data) > l:	# Extract requested portion
				data = data[s : s + l]
			if u.find(magic + "charrange:") >= 0:
				u += "&mode=context"
		if u.find(magic + "area:") >= 0:
			u += "&mode=human"

	# Start a context link
	content = '<a\nhref="' + u.replace("&", "&amp;") + '"'
	if baseurl in colours:
		css_class = classes[colours[baseurl]]
		if css_class:
			content += ' class="' + css_class + '"'
	if baseurl in titles:
		content += ' title="' + titles[baseurl] + '"'
	content += ' ' + target + '>' + data + "</a>"
	return content.encode("UTF-8")

def literal(URL):
	"""
	Resolve a 'data:' URL into a string of HTML.
	Currently only handles text/html and text/plain MIME-types
	and does not handle character sets or base64 encoding.
	"""

	(t, s) = URL[len("data:") : ].split(",")
	t = t.lower()
	s = re.sub("%([\da-fA-F][\da-fA-F])", decode_hexpair, s)
	if t == "text/html":
		return s
	elif t == "" or t == "text/plain":
		return "<pre>" + s + "</pre>"
	else:
		return '<a\nhref="' + URL + '" class="error" ' + \
			target + '>' + t + "</a>"

def main():
	"Construct a TQHTML file from the EDL, then open in a web browser."
	# Default to the TransQuoter home page
	URL = TQhome
	if len(sys.argv) > 1:	# If a file was named as a parameter
		# Open the file with universal newline support
		f = file(sys.argv[1], "U")
		# Now construct and write an HTML page
		(fd, URL) = tempfile.mkstemp(prefix = "TQ", suffix = ".html",
			text = True)
		URL = "file://" + URL
		os.write(fd, htmlheader1 + os.path.basename(sys.argv[1]) +
			     htmlheader2)
		for line in f:
			line = line.strip()
			if line and line[0] != "#":
				if line.lower().startswith("data:"):
					os.write(fd, literal(line))
				else:
					os.write(fd, transclude(line))
		os.write(fd, htmlfooter)
		os.close(fd)
	print "Viewing " + URL
	webbrowser.open(URL, autoraise=1)
	return

if __name__ == '__main__':
	main()
