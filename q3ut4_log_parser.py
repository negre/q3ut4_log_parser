#!/usr/bin/env python
# -*- coding: utf-8 -*-

import cgi
import os
import re
import sqlite3
import sys


# Patterns
frag_prog = re.compile(r"^ *[0-9]+:[0-9]{2} Kill: [0-9]+ [0-9]+ [0-9]+: (?!<world>)(.*) killed (.*) by (?!MOD_CHANGE_TEAM$|MOD_FALLING$|MOD_WATER$|MOD_LAVA$|UT_MOD_BLED$|UT_MOD_FLAG$)(.*)$")
playerjoins_prog = re.compile(r'^ *([0-9]+):([0-9]+) ClientUserinfo: ([0-9]+) (.*)$')
playerchange_prog = re.compile(r"^ *[0-9]+:[0-9]+ ClientUserinfoChanged: ([0-9]+) (.*)$")
playerquits_prog = re.compile(r"^ *([0-9]+):([0-9]+) ClientDisconnect: ([0-9]+)$")
endgame_prog = re.compile(r"^ *([0-9]+):([0-9]+) ShutdownGame:$")
initround_prog = re.compile(r"^ *([0-9]+):([0-9]+) InitRound: (.*)$")
item_prog = re.compile(r"^ *[0-9]+:[0-9]{2} Item: ([0-9]+) (?!<world>)(.*)$")
flag_prog = re.compile(r"^ *[0-9]+:[0-9]{2} Flag: ([0-9]+) ([0-9]+): (.*)$")
teamscore_prog = re.compile(r"^ *([0-9]+):([0-9]+) red:([0-9]+)[ ]*blue:([0-9]+)$")

# Database connection
db_conn = None


# Create db
def create_db():
	global db_conn
	db_conn = sqlite3.connect(':memory:')
	db_conn.execute('create table frags (fragger text, fragged text, weapon text)')
	db_conn.execute('create table games (player text, start integer, stop integer)')
	db_conn.execute('create table flags (player text, event text)')
	db_conn.execute('create table score (player text, score int)')
	db_conn.commit()


# Read the log and populate db
def parse_log(logpath):
	global db_conn

	idd = {}
	logf = open(logpath, 'r')
	team = {}
    
	while 1:
		logline = logf.readline()
		if (not logline):
			break

		m = frag_prog.match(logline)
		if (m):
			# Update the frags table
			db_conn.execute(
					'''insert into frags values (?, ?, ?)''', 
					(m.group(1), m.group(2), m.group(3)))
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

		m = playerchange_prog.match(logline)
		if (m):
			playerinfos = re.split(r"\\", m.group(2))
			teamNb = int(playerinfos[playerinfos.index('t')+1])
			name = playerinfos[playerinfos.index('n')+1]
			team[m.group(1)] = teamNb
			continue
		
		m = playerquits_prog.match(logline)
		if (m):
			time = int(m.group(1))*60 + int(m.group(2))
			try:
				# Update the games table
				db_conn.execute(
					'''update games set stop=? where player = ? and stop = -1''',
					(time, idd[m.group(3)]))
				# And the players id dictionary
				del idd[m.group(3)]
				del team[m.group(3)]
			except KeyError:
				pass # Somehow, somebody disconnected without begin there in the
				     # first place, ignore it
			continue

		m = initround_prog.match(logline)
		if (m):
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
			team = {}
			continue

		m = item_prog.match(logline)
		if (m):
			if( m.group(2) == "team_CTF_redflag" or m.group(2) == "team_CTF_blueflag" ):
				db_conn.execute(
					'''insert into flags values (?, ?)''', 
					(idd[m.group(1)], "CATCH"))
				pass
			continue
		
		m = flag_prog.match(logline)
		if (m):
			if int(m.group(2)) == 0 :
				db_conn.execute(
					'''insert into flags values (?, ?)''', 
					(idd[m.group(1)], "DROP"))
				pass
			elif int(m.group(2)) == 1 :
				db_conn.execute(
					'''insert into flags values (?, ?)''', 
					(idd[m.group(1)], "RETURN"))
				pass
			elif int(m.group(2)) == 2 :
				db_conn.execute(
					'''insert into flags values (?, ?)''', 
					(idd[m.group(1)], "CAPTURE"))
				pass				
			continue
		m = teamscore_prog.match(logline)
		if(m):
			red_score = int(m.group(3))
			blue_score = int(m.group(4))
			#sys.stderr.write( 'red: ' + str(red_score) + ' blue: '+ str(blue_score) + '\n' )
			for k,v, in team.iteritems():
				#sys.stderr.write( str(k) + ' ' + str(v) + '\n' )
				if( (v == 1 and red_score > blue_score)
					or ( v == 2 and red_score < blue_score ) ):
					# player win
					db_conn.execute(
						'''insert into score values(?,?)''',
						(idd[k], 1))
				elif( (v == 1 and red_score < blue_score)
					  or ( v == 2 and red_score > blue_score ) ):
					# player lose
					db_conn.execute(
						'''insert into score values(?,?)''',
						(idd[k], -1))
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
		hours = int(row[1]) / 3600
		minutes = (int(row[1]) - hours*3600) / 60
		seconds = (int(row[1]) - minutes*60) % 60
		print "      <li>%s (%i:%.2i:%.2i)</li>" % (row[0], hours, minutes, seconds)
	print "    </ol>"

# 
def favorite_weapons():
	global db_conn
	print "    <a name=\"6\"><h2>Favorite weapons per player</h2></a>"
	curs = db_conn.cursor()
	curs.execute('''
select fragger, weapon, count(*) as frags 
from frags 
group by lower(fragger), lower(weapon) 
order by lower(fragger) asc, count(*) desc
''')
	player = None
	for row in curs:
		if (player != row[0].lower()):
			if (player):
				print "    </table>"
			print """\
    <h3>%s weapons:</h3>
    <table>\
""" % cgi.escape(row[0])
			player = row[0].lower()

		print """\
      <tr>
        <td style="width: 180px;">%s</td>\
""" % cgi.escape(row[1].replace('UT_MOD_', ''))
		
		bar_str = '        <td><span class="ascii-bar">'
		for i in xrange(0, row[2]):
			bar_str = ''.join([bar_str, '| '])
		bar_str = ''.join([bar_str, '</span>&nbsp;', str(row[2]), '</td>'])
		
		print """%s
      </tr>\
""" % bar_str
	print "    </table>"

#
def he_ranking():
	global db_conn
	print """\
    <a name="7"><h2>Bomber ranking</h2></a>
    <ol>\
"""
	curs = db_conn.cursor()
	curs.execute('''
select fragger, count(*) as frags 
from frags 
where weapon = "UT_MOD_HEGRENADE"
group by lower(fragger)
order by count(*) desc, lower(fragger) asc
''')
	for row in curs:
		print "      <li>%s (%s)</li>" % (row[0], row[1])
	print "    </ol>"

#
def sr8_ranking():
	global db_conn
	print """\
    <a name="8"><h2>Sniper ranking</h2></a>
    <ol>\
"""
	curs = db_conn.cursor()
	curs.execute('''
select fragger, count(*) as frags 
from frags 
where weapon = "UT_MOD_SR8"
group by lower(fragger)
order by count(*) desc, lower(fragger) asc
''')
	for row in curs:
		print "      <li>%s (%s)</li>" % (row[0], row[1])
	print "    </ol>"

def capture_ranking():
	global db_conn
	print """\
    <a name="9"><h2>Capture ranking</h2></a>
    <ol>\
"""
	curs = db_conn.cursor()
	curs.execute('''
select player, count(*) as flags
from flags
where event = "CAPTURE"
group by lower(player)
order by count(*) desc, lower(player) asc
''')
	for row in curs:
		print "      <li>%s (%s)</li>" % (row[0], row[1])
	print "    </ol>"

def attack_ranking():
	global db_conn
	print """\
    <a name="10"><h2>Attack ranking</h2></a>
	<paragraph> Number of flags catched </paragraph>
    <ol>\
"""
	curs = db_conn.cursor()
	curs.execute('''
select player, count(*) as flags
from flags
where event = "CATCH"
group by lower(player)
order by count(*) desc, lower(player) asc
''')
	for row in curs:
		print "      <li>%s (%s)</li>" % (row[0], row[1])
	print "    </ol>"

def defense_ranking():
	global db_conn
	print """\
    <a name="11"><h2>Defense ranking</h2></a>
	<paragraph> Number of flags returned </paragraph>
    <ol>\
"""
	curs = db_conn.cursor()
	curs.execute('''
select player, count(*) as flags
from flags
where event = "RETURN"
group by lower(player)
order by count(*) desc, lower(player) asc
''')
	for row in curs:
		print "      <li>%s (%s)</li>" % (row[0], row[1])
	print "    </ol>"

def score_ranking():
	global db_conn
	print """\
    <a name="12"><h2>Score ranking</h2></a>
    <ol>\
"""
	curs = db_conn.cursor()
	curs.execute('''
select player, COALESCE(win,0), COALESCE(lost,0), COALESCE(win,0) - COALESCE(lost,0)  as score
from
score
left outer join
(
  select player as player1, count(*) as win
  from score
  where score > 0
  group by lower(player)
) t1
on score.player=t1.player1
left outer join
(
  select player as player2, count(*) as lost
  from score
  where score < 0
  group by lower(player)
) t2
on score.player = t2.player2
group by lower(player1)
order by score desc, lower(player1) asc
''')
	for row in curs:
		print "      <li>%s : %s victories - %s defeats = <b>%s</b></li>" % (row[0], row[1], row[2], row[3])
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
      <li><a href="#12">Score ranking</a></li>	  
      <li><a href="#9">Capture ranking</a></li>	  
      <li><a href="#10">Attack ranking</a></li>	  
      <li><a href="#11">Defense ranking</a></li>	  
      <li><a href="#3">Frags/Deaths ratio-based ranking</a></li>
      <li><a href="#1">Frags repartition per player</a></li>
      <li><a href="#2">Deaths repartition per player</a></li>
      <li><a href="#4">Frag-based ranking</a></li>
      <li><a href="#5">Presence-based ranking</a></li>
      <li><a href="#6">Favorite weapons per player</a></li>	  
      <li><a href="#7">Bomber ranking</a></li>	  
      <li><a href="#8">Sniper ranking</a></li>	  
    </ul>\
"""
	score_ranking()
	capture_ranking()
	attack_ranking()
	defense_ranking()
	frags_repartition()
	death_repartition()
	fdratio_ranking()
	frag_ranking()
	presence_ranking()
	favorite_weapons()
	he_ranking()
	sr8_ranking()

	db_conn.close()

	print """\
    <hr>
  </body>
</html>\
"""


if __name__ == '__main__':
	main()
