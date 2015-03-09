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
chat_prog = re.compile(r"^ *[0-9]+:[0-9]{2} (say|sayteam): [0:9]+ (?!<world>)(.*): (.*)$")

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
	db_conn.execute('create table chats (player text, phrase text)')
	db_conn.execute('create table rounds (id int, winner text, red_score int, blue_score int)')
	db_conn.execute('create table teams (round_id int, player text, color text)')
	db_conn.commit()


# Read the log and populate db
def parse_log(logpath):
	global db_conn

	idd = {}
	logf = open(logpath, 'r')
	team = {}
	round_id = 0;
    
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
			round_id = round_id + 1
			db_conn.execute('''insert into rounds values(?, ?, ?, ?)''', (round_id,'', 0, 0))
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

			winner = ''
			if red_score > blue_score:
				winner = 'RED'
			if blue_score > red_score:
				winner = 'BLUE'
			db_conn.execute('''update rounds set winner=?, red_score=?, blue_score=? where id = ?''', (winner, red_score, blue_score, round_id))
			
			for k,v, in team.iteritems():
				player = idd[k]
				color = ''
				if v==1:
					color = 'RED'
				if v==2:
					color = 'BLUE'
				db_conn.execute('''insert into teams values(?,?,?)''', (round_id, player, color))
				
				#sys.stderr.write( player + ' ' + str(round_id) + ' ' + color + '\n' )
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
		m = chat_prog.match(logline)
		if(m):
			#print(m.group(2), m.group(3))
			db_conn.execute(
					'''insert into chats values (?, ?)''',
					(m.group(2), m.group(3)))
			continue
	db_conn.commit()
	logf.close()

def filter_db( ratio ):
	global db_conn

	curs = db_conn.cursor()
	curs.execute('''
select player, sum(stop-start) as presence 
from games
group by lower(player)
order by sum(stop-start) desc
''')
	playtime = []
	
	for pt in curs:
		playtime.append(pt)
		
	max_time = playtime[0][1]
	
	for pt in playtime:
		if pt[1] < ratio * max_time:
			sys.stderr.write(pt[0]+' removed from database\n')
			db_conn.execute('''delete from frags where fragger = (?)''', (pt[0],))
			db_conn.execute('''delete from games where player = (?)''', (pt[0],))
			db_conn.execute('''delete from flags where player = (?)''', (pt[0],))
			db_conn.execute('''delete from score where player = (?)''', (pt[0],))
			db_conn.execute('''delete from chats where player = (?)''', (pt[0],))

	db_conn.execute('''delete from frags where fragger not in (select player from games)
	                                           or fragged not in (select player from games)''')
	db_conn.execute('''delete from flags where player not in (select player from games)''')
	db_conn.execute('''delete from score where player not in (select player from games)''')
	db_conn.execute('''delete from chats where player not in (select player from games)''')
	db_conn.execute('''delete from teams where player not in (select player from games)''')
	
	db_conn.commit()
	
	#player, max_time = playtime[0]	
	#sys.stderr.write(player + ' ' + str(max_time)+'\n')
	
			

# 
def frags_repartition():
	global db_conn
	print "    <a name=\"11\"><h2>Frags repartition per player</h2></a>"
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
    <a name=\"12\"><h2>Deaths repartition per player</h2></a>
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
    <a name="7"><h2>Frag/death ratio-based ranking</h2></a>
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
    <a name="8"><h2>Frag-based ranking</h2></a>
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
    <a name="9"><h2>Presence-based ranking</h2></a>
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
	print "    <a name=\"13\"><h2>Favorite weapons per player</h2></a>"
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
    <a name="5"><h2>Bomber ranking</h2></a>
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
def sniper_ranking():
	global db_conn
	print """\
    <a name="6"><h2>Sniper ranking</h2></a>
    <ol>\
"""
	curs = db_conn.cursor()
	curs.execute('''
select fragger, count(*) as frags 
from frags 
where weapon = "UT_MOD_SR8" or weapon = "UT_MOD_PSG1"
group by lower(fragger)
order by count(*) desc, lower(fragger) asc
''')
	for row in curs:
		print "      <li>%s (%s)</li>" % (row[0], row[1])
	print "    </ol>"

def capture_ranking():
	global db_conn
	print """\
    <a name="2"><h2>Capture ranking</h2></a>
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
    <a name="3"><h2>Attack ranking</h2></a>
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
    <a name="4"><h2>Defense ranking</h2></a>
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
    <a name="1"><h2>Score ranking</h2></a>
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

def chat_ranking():
	global db_conn
	print """\
    <a name="10"><h2>Chat ranking</h2></a>
    <ol>\
"""
	curs = db_conn.cursor()
	curs.execute('''
select player, count(*) as chats
from chats
group by lower(player)
order by count(*) desc, lower(player) asc
''')
	for row in curs:
		print "      <li>%s (%s)</li>" % (row[0], row[1])
	print "    </ol>"
	
def best_teammates():
	global db_conn
	print """\
    <a name=\"14\"><h2>Best teammates per player</h2></a>
	<ol>\
"""
	curs = db_conn.cursor()
	curs.execute('''\
SELECT DISTINCT player as player
FROM teams
ORDER BY player ASC
''')
	players = []
	for row in curs:
		players.append(row[0])

	for player in players:
		print "<h3>%s :</h3>" % player
		print "<table>"
		curs.execute('''
SELECT name1, teamate, oponent
FROM
(
  SELECT player2 as name1, count(*) as teamate
  FROM
  (
    SELECT player as name11, color, round_id
    FROM teams
    WHERE player=\"%s\" AND color!=\"\"
  ) t1
  LEFT OUTER JOIN
  (
    SELECT player as player2, color, round_id
    FROM teams
    WHERE player!=\"%s\" AND color!=\"\"
  ) t2
  ON t1.color=t2.color AND t1.round_id = t2.round_id
  GROUP BY LOWER(player2)
  ORDER BY count(*) DESC, LOWER(player2) ASC
) tt1
LEFT OUTER JOIN
(
  SELECT player2 as name2, count(*) as oponent
  FROM
  (
    SELECT player as player1, color, round_id
    FROM teams
    WHERE player=\"%s\" AND color!=\"\"
  ) t1
  LEFT OUTER JOIN
  (
    SELECT player as player2, color, round_id
    FROM teams
    WHERE player!=\"%s\" AND color!=\"\"
  ) t2
  ON t1.color!=t2.color AND t1.round_id = t2.round_id
  GROUP BY LOWER(player2)
  ORDER BY count(*) DESC, LOWER(name2) ASC
) tt2
ON tt1.name1=tt2.name2
''' % (player, player, player, player))
		for row in curs:
			print """\
<tr>
<td style="width: 180px;">%s : </td>
<td> %s </td>
<td> %s </td>
</tr>""" % (row[0], row[1], row[2])
	

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
	
	filter_db(0.05)
	
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
      <li><a href="#1">Score ranking</a></li>	  
      <li><a href="#2">Capture ranking</a></li>	  
      <li><a href="#3">Attack ranking</a></li>	  
      <li><a href="#4">Defense ranking</a></li>	  
      <li><a href="#5">Bomber ranking</a></li>	  
      <li><a href="#6">Sniper ranking</a></li>	  
      <li><a href="#7">Frags/Deaths ratio-based ranking</a></li>
      <li><a href="#8">Frag-based ranking</a></li>
      <li><a href="#9">Presence-based ranking</a></li>
      <li><a href="#10">Chat ranking</a></li>
      <li><a href="#11">Frags repartition per player</a></li>
      <li><a href="#12">Deaths repartition per player</a></li>
      <li><a href="#13">Favorite weapons per player</a></li>
    </ul>\
"""
	score_ranking()
	capture_ranking()
	attack_ranking()
	defense_ranking()
	he_ranking()
	sniper_ranking()
	fdratio_ranking()
	frag_ranking()
	presence_ranking()
	chat_ranking()
	frags_repartition()
	death_repartition()
	favorite_weapons()
	best_teammates()
	db_conn.close()

	print """\
    <hr>
  </body>
</html>\
"""


if __name__ == '__main__':
	main()
