#!/usr/bin/env python
# -*- coding: utf-8 -*-

import cgi
import os
import re
import sqlite3
import sys


# Patterns
frag_prog = re.compile(r"^ *[0-9]+:[0-9]{2} Kill: [0-9]+ [0-9]+ [0-9]+: (?!<world>)(.*) killed (.*) by (?!MOD_CHANGE_TEAM$|MOD_FALLING$|MOD_WATER$|MOD_LAVA$|UT_MOD_BLED$|UT_MOD_FLAG$)(.*)$")
playerjoins_prog = re.compile(r'^ *([0-9]+):([0-9]+) ClientUserinfo: ([1-9]+) (.*)$')
playerquits_prog = re.compile(r"^ *([0-9]+):([0-9]+) ClientDisconnect: ([1-9]+)$")
endgame_prog = re.compile(r"^ *([0-9]+):([0-9]+) ShutdownGame:$")

# Database connection
db_conn = None


# Create db
def create_db():
	global db_conn
	db_conn = sqlite3.connect(':memory:')
	db_conn.execute('create table frags (fragger text, fragged text)')
	db_conn.execute('create table games (player text, start integer, stop integer)')
	db_conn.commit()


# Read the log and populate db
def parse_log(logpath):
	global db_conn

	idd = {}
	logf = open(logpath, 'r')

	while 1:
		logline = logf.readline()
		if (not logline):
			break

		m = frag_prog.match(logline)
		if (m):
			# Update the frags table
			db_conn.execute(
					'''insert into frags values (?, ?)''', 
					(m.group(1), m.group(2)))
			continue

		m = playerjoins_prog.match(logline)
		if (m):
			if (m.group(3) not in idd):
				playerinfos = re.split(r"\\", m.group(4))
				playername = playerinfos[playerinfos.index('name')+1]
				time = int(m.group(1))*60 + int(m.group(2))
				# Update the players id dictionary
				idd[m.group(3)] = playername
				# And the player games table
				db_conn.execute(
					'''insert into games values (?, ?, -1)''',
					(playername, time))
			continue

		m = playerquits_prog.match(logline)
		if (m):
			time = int(m.group(1))*60 + int(m.group(2))
			# Update the games table
			db_conn.execute(
				'''update games set stop=? where player = ? and stop = -1''',
				(time, idd[m.group(3)]))
			# And the players id dictionary
			del idd[m.group(3)]
			continue

		m = endgame_prog.match(logline)
		if (m):
			time = int(m.group(1))*60 + int(m.group(2))
			# New game, make everybody quits
			for k,v in idd.iteritems():
				db_conn.execute(
					'''update games set stop=? where player = ? and stop = -1''',
					(time, v))
				pass
			idd = {}
			continue

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
def fdratio_ranking():
	global db_conn
	print """\
    <a name="3"><h2>Frag/death ratio-based ranking</h2></a>
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


#
def frag_ranking():
	global db_conn
	print """\
    <a name="4"><h2>Frag-based ranking</h2></a>
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
def presence_ranking():
	global db_conn
	print """\
    <a name="5"><h2>Presence-based ranking</h2></a>
    <ol>\
"""
	curs = db_conn.cursor()
	curs.execute('''
select player, sum(stop-start) as frags 
from games
group by lower(player)
order by sum(stop-start) desc
''')
	for row in curs:
		print "      <li>%s (%i:%i:%i)</li>" % (row[0], int(row[1]) / 3600, int(row[1]) / 60, int(row[1]) % 60)
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
      <li><a href="#3">Frags/Deaths ratio-based ranking</a></li>
      <li><a href="#4">Frag-based ranking</a></li>
      <li><a href="#5">Presence-based ranking</a></li>
    </ul>\
"""

	frags_repartition()
	death_repartition()
	fdratio_ranking()
	frag_ranking()
	presence_ranking()

	db_conn.close()

	print """\
    <hr>
  </body>
</html>\
"""


if __name__ == '__main__':
	main()
