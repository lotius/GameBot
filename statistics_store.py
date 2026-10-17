"""Server-scoped statistics queries with shared filters and bounded output."""
import json
from datetime import datetime, timedelta, timezone


class StatisticsStore:
    def __init__(self, connection_factory):
        self.connection_factory = connection_factory

    def query(self, guild_id, options):
        clauses, args = ['r.guild_id=%s'], [guild_id]
        for option, column in [('game', 'game_key'), ('user', 'user_id'), ('channel', 'channel_id')]:
            if options.get(option) is not None:
                clauses.append(f'r.{column}=%s')
                args.append(options[option])
        for option, operator in [('since', '>='), ('until', '<')]:
            if options.get(option) is not None:
                clauses.append(f'r.rolled_at {operator} %s')
                args.append(options[option])
        if options.get('dice_type'):
            clauses.append('d.dice_type=%s')
            args.append(options['dice_type'])
        where = ' AND '.join(clauses)
        base = ' FROM gamebot_rolls r JOIN gamebot_roll_results d ON d.roll_id=r.id WHERE ' + where
        view = options['view']
        with self.connection_factory() as c:
            with c.cursor() as q:
                q.execute('SELECT COUNT(DISTINCT r.id),COUNT(*),COUNT(DISTINCT r.user_id),MIN(r.rolled_at),MAX(r.rolled_at)' + base, args)
                summary = q.fetchone()
                if view == 'leaderboard':
                    q.execute('SELECT r.user_id,COUNT(DISTINCT r.id),COUNT(*)' + base + ' GROUP BY r.user_id ORDER BY COUNT(DISTINCT r.id) DESC,r.user_id LIMIT 25', args)
                    return summary, q.fetchall()
                if view == 'daily':
                    q.execute('SELECT DATE(r.rolled_at),COUNT(DISTINCT r.id),COUNT(*)' + base + ' GROUP BY DATE(r.rolled_at) ORDER BY DATE(r.rolled_at) DESC LIMIT 90', args)
                    return summary, q.fetchall()
                if view in ('recent', 'export'):
                    limit = 20 if view == 'recent' else 1000
                    q.execute('SELECT r.id,r.rolled_at,r.user_id,r.channel_id,r.game_key,r.modifier,d.die_index,d.dice_type,d.face_id,d.face_values' + base + ' ORDER BY r.rolled_at DESC,r.id DESC,d.die_index LIMIT %s', args + [limit])
                    return summary, q.fetchall()
                if view == 'overview':
                    q.execute('SELECT r.game_key,COUNT(DISTINCT r.id),COUNT(*)' + base + ' GROUP BY r.game_key ORDER BY COUNT(DISTINCT r.id) DESC,r.game_key', args)
                    return summary, q.fetchall()
                # Group numeric values in SQL rather than loading every historical die.
                q.execute('SELECT r.game_key,d.dice_type,d.face_id,d.face_values,COUNT(*)' + base + ' GROUP BY r.game_key,d.dice_type,d.face_id,d.face_values ORDER BY r.game_key,d.dice_type,d.face_id LIMIT 5001', args)
                groups = q.fetchall()
                if len(groups) > 5000:
                    raise ValueError('Too many distinct result definitions. Choose a game and shorter date range.')
                if view == 'compare':
                    q.execute('SELECT r.game_key,d.dice_type,r.definition_snapshot,COUNT(*)' + base + ' GROUP BY r.game_key,d.dice_type,r.definition_snapshot LIMIT 5001', args)
                    definitions = q.fetchall()
                    if len(definitions) > 5000:
                        raise ValueError('Too many historical definitions. Choose a shorter date range.')
                    expected = {}
                    for game, kind, snapshot, count in definitions:
                        data = json.loads(snapshot)
                        if game == 'standard':
                            faces = [{'id': str(value), 'numOfFaces': 1} for value in range(1, data['sides'] + 1)]
                        else:
                            faces = data['diceTypes'][kind]['faces']
                        total = sum(face['numOfFaces'] for face in faces)
                        for face in faces:
                            key = (game, kind, face.get('id', face.get('face')))
                            expected[key] = expected.get(key, 0) + count * face['numOfFaces'] / total
                    return summary, (groups, expected)
                return summary, groups
