#!/usr/bin/env python
# -*- coding: utf-8 -*-

import cgi
import os
import re
import sqlite3
import sys


# Patterns
frag_prog = re.compile(r"^[ ]*[0-9]+:[0-9]{2} Kill: [0-9]+ [0-9]+ [0-9]+: (?!<world>)(.*) killed (.*) by (?!MOD_CHANGE_TEAM$|MOD_FALLING$|MOD_WATER$|MOD_LAVA$|UT_MOD_BLED$|UT_MOD_FLAG$)(.*)$")
fall_prog = re.compile(r"^[ ]*[0-9]+:[0-9]{2} Kill: [0-9]+ [0-9]+ [0-9]+: <non-client> killed (.*) by MOD_FALLING$")
bled_prog = re.compile(r"^[ ]*[0-9]+:[0-9]{2} Kill: [0-9]+ [0-9]+ [0-9]+: <non-client> killed (.*) by UT_MOD_BLED$")

# Database connection
db_conn = None


# Create db
def create_db():
	global db_conn
	db_conn = sqlite3.connect(':memory:')
	db_conn.execute('create table frags (fragger text, fragged text)')
	db_conn.commit()


# Read the log and populate db
def parse_log(logpath):
	global db_conn
	logf = open(logpath, 'r')
	while 1:
		logline = logf.readline()
		if (not logline):
			break

		m = frag_prog.match(logline)
		if (m != None):
			# Update the frags
			frag_tuple = (m.group(1), m.group(2))
			db_conn.execute(
					'''insert into frags values (?, ?)''', 
					frag_tuple)
	db_conn.commit()
	logf.close()


# 
def frags_repartition():
	global db_conn
	print "    <a name=\"1\"><h2>Frags repartition per player</h2></a>"
	curs = db_conn.cursor()
	curs.execute('''
select fragger, fragged, count(*) as frags 
from frags 
group by lower(fragger), lower(fragged) 
order by lower(fragger) asc, count(*) desc
''')
	player = None
	for row in curs:
		if (player != row[0].lower()):
			if (player):
				print "    </table>"
			print """\
    <h3>%s fragged:</h3>
    <table>\
""" % cgi.escape(row[0])
			player = row[0].lower()

		print """\
      <tr>
        <td style="width: 180px;">%s</td>\
""" % cgi.escape(row[1])
		
		bar_str = '        <td><span class="ascii-bar">'
		for i in xrange(0, row[2]):
			bar_str = ''.join([bar_str, '| '])
		bar_str = ''.join([bar_str, '</span>&nbsp;', str(row[2]), '</td>'])
		
		print """%s
      </tr>\
""" % bar_str
	print "    </table>"


# 
def death_repartition():
	global db_conn
	print """\
    <a name=\"2\"><h2>Deaths repartition per player</h2></a>
    <table>
"""
	curs = db_conn.cursor()
	curs.execute('''
select fragged, fragger, count(*) 
from frags 
group by lower(fragged), lower(fragger)
order by lower(fragged) asc, count(*) desc
''')
	player = None
	for row in curs:
		if (player != row[0].lower()):
			if (player):
				print "    </table>"
			print """\
    <h3>%s has been fragged by:</h3>
    <table>\
""" % cgi.escape(row[0])
			player = row[0].lower()

		print """\
      <tr>
        <td style="width: 180px;">%s</td>
""" % cgi.escape(row[1])
		
		bar_str = '        <td><span class="ascii-bar">'
		for i in xrange(0, row[2]):
			bar_str = ''.join([bar_str, '| '])
		bar_str = ''.join([bar_str, '</span>&nbsp;', str(row[2]), '</td>'])
		
		print """%s
      </tr>\
""" % bar_str
	print "    </table>"


#
def frag_ranking():
	global db_conn
	print """\
    <a name="#3"><h2>Frag-based ranking</h2></a>
    <ol>\
"""
	curs = db_conn.cursor()
	curs.execute('''
select fragger, count(*) as frags 
from frags 
where fragger != fragged
group by lower(fragger)
order by count(*) desc, lower(fragger) asc
''')
	for row in curs:
		print "      <li>%s (%s)</li>" % (row[0], row[1])
	print "    </ol>"


#
def fdratio_ranking():
	global db_conn
	print """\
    <a name="#4"><h2>Frag/death ratio-based ranking</h2></a>
    <ol>\
"""
	players_curs = db_conn.cursor()
	players_curs.execute('''
select fragger
from frags
group by lower(fragger)
''')

	ratios = []
	for players_row in players_curs:
		tuple = (players_row[0],)

		frags_curs = db_conn.cursor()
		frags_curs.execute('''
select count(*)
from frags
where lower(fragger) = lower(?)
	and fragger != fragged
''', tuple)
		frags_row = frags_curs.fetchone()

		deaths_curs = db_conn.cursor()
		deaths_curs.execute('''
select count(*)
from frags
where lower(fragged) = lower(?)
''', tuple)
		deaths_row = deaths_curs.fetchone()

		try:
			ratios.append((players_row[0], float(frags_row[0]) / float(deaths_row[0])))
		except ZeroDivisionError:
			ratios.append((players_row[0], 666.0))

	ratios.sort(key=lambda ratio: ratio[1], reverse=True)
	for r in ratios:
		print "      <li>%s (%f)</li>" % (cgi.escape(r[0]), r[1])

	print "    </ol>"


# Main function
def main():
	global db_conn

	if (len(sys.argv) < 2):
		sys.exit(1)

	create_db()

	if os.path.isdir(sys.argv[1]):
		for logrpath in os.listdir(sys.argv[1]):
			logfpath = ''.join([sys.argv[1], '/', logrpath])
			parse_log(logfpath)
	else:
		parse_log(sys.argv[1])

	print """\
<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">
<html lang="en-US">
  <head>
    <title>UrbT stats page</title>
    <meta http-equiv="Content-Type" content="text/html; charset=utf-8">
    <style>
      h2 {
        border-bottom: 1px solid grey;
      }
      span.ascii-bar {
        background: #EFA21E;
        color: #EFA21E;
		font-size: xx-small;
      }
    </style>
  </head>
  <body>
    <h1>Urban Terror statistics webpage</h1>
    <hr>
    <ul>Available stats:
      <li><a href="#1">Frags repartition per player</a></li>
      <li><a href="#2">Deaths repartition per player</a></li>
      <li><a href="#3">Frag-based ranking</a></li>
      <li><a href="#4">Frags/Deaths ratio-based ranking</a></li>
    </ul>\
"""

	frags_repartition()
	death_repartition()
	frag_ranking()
	fdratio_ranking()

	db_conn.close()

	print """\
    <hr>
  </body>
</html>\
"""


if __name__ == '__main__':
	main()
