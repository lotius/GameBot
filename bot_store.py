"""Transactional configuration, auditing, and dice history."""
import json
from database import connect


class BotStore:
    def __init__(self, connection_factory=connect):
        self.connection_factory = connection_factory

    def get_admin_role(self, guild_id):
        with self.connection_factory() as c:
            with c.cursor() as q:
                q.execute('SELECT bot_admin_role_id FROM gamebot_guild_settings WHERE guild_id=%s', (guild_id,))
                row = q.fetchone()
                return row[0] if row else None

    def policy(self, guild_id, channel_id):
        with self.connection_factory() as c:
            with c.cursor() as q:
                q.execute('SELECT roll_logging_enabled, spam_enabled, spam_limit, spam_window_seconds, retention_enabled, retention_days FROM gamebot_guild_settings WHERE guild_id=%s', (guild_id,))
                row = q.fetchone()
                logging_enabled = bool(row[0]) if row else True
                moderation = dict(spam_enabled=bool(row[1]), spam_limit=row[2], spam_window_seconds=row[3], retention_enabled=bool(row[4]), retention_days=row[5]) if row else dict(spam_enabled=True, spam_limit=5, spam_window_seconds=10, retention_enabled=False, retention_days=90)
                q.execute('SELECT rolls_enabled, dddice_enabled, dddice_destination FROM gamebot_channel_settings WHERE guild_id=%s AND channel_id=%s', (guild_id, channel_id))
                row = q.fetchone()
                channel = {'rolls_enabled': bool(row[0]), 'dddice_enabled': bool(row[1]), 'destination': row[2]} if row else {'rolls_enabled': True, 'dddice_enabled': False, 'destination': None}
                q.execute("SELECT encrypted_api_key, default_destination, enabled FROM gamebot_guild_integrations WHERE guild_id=%s AND integration='dddice'", (guild_id,))
                row = q.fetchone()
                channel.update(logging_enabled=logging_enabled, encrypted_key=row[0] if row else None,
                               default_destination=row[1] if row else None, integration_enabled=bool(row[2]) if row else False)
                channel.update(moderation)
                return channel

    def change(self, guild_id, actor_id, setting, value, channel_id=None):
        fields = {
            'admin-role': ('gamebot_guild_settings', 'bot_admin_role_id'),
            'instructions': ('gamebot_guild_settings', 'instruction_channel_id'),
            'spam-enabled': ('gamebot_guild_settings', 'spam_enabled'),
            'spam-limit': ('gamebot_guild_settings', 'spam_limit'),
            'spam-window': ('gamebot_guild_settings', 'spam_window_seconds'),
            'retention-enabled': ('gamebot_guild_settings', 'retention_enabled'),
            'retention-days': ('gamebot_guild_settings', 'retention_days'),
            'logging': ('gamebot_guild_settings', 'roll_logging_enabled'),
            'rolls': ('gamebot_channel_settings', 'rolls_enabled'),
            'dddice-channel': ('gamebot_channel_settings', 'dddice_enabled'),
            'dddice-room': ('gamebot_channel_settings', 'dddice_destination'),
            'dddice-default': ('gamebot_guild_integrations', 'default_destination'),
            'dddice-enabled': ('gamebot_guild_integrations', 'enabled'),
            'dddice-key': ('gamebot_guild_integrations', 'encrypted_api_key'),
        }
        table, field = fields[setting]  # Only these identifiers enter SQL.
        if table == 'gamebot_channel_settings':
            if channel_id is None:
                raise ValueError('Channel required')
            keys, args = 'guild_id, channel_id', (guild_id, channel_id)
            where = 'guild_id=%s AND channel_id=%s'
        elif table == 'gamebot_guild_integrations':
            keys, args = 'guild_id, integration', (guild_id, 'dddice')
            where = 'guild_id=%s AND integration=%s'
        else:
            keys, args = 'guild_id', (guild_id,)
            where = 'guild_id=%s'
        with self.connection_factory() as c:
            with c.cursor() as q:
                q.execute(f'INSERT IGNORE INTO {table} ({keys}) VALUES ({", ".join(["%s"] * len(args))})', args)
                q.execute(f'SELECT {field} FROM {table} WHERE {where} FOR UPDATE', args)
                old = q.fetchone()[0]
                q.execute(f'UPDATE {table} SET {field}=%s WHERE {where}', (value,) + args)
                # Never put credentials or ciphertext into audit values.
                old_audit = bool(old) if setting == 'dddice-key' else old
                new_audit = bool(value) if setting == 'dddice-key' else value
                q.execute('INSERT INTO gamebot_configuration_audit (guild_id,actor_id,setting_name,channel_id,old_value,new_value) VALUES (%s,%s,%s,%s,%s,%s)',
                          (guild_id, actor_id, setting, channel_id, json.dumps(old_audit), json.dumps(new_audit)))
            c.commit()

    def record_roll(self, message, roll):
        with self.connection_factory() as c:
            with c.cursor() as q:
                # Lock/claim by Discord message ID; duplicate handling never adds results.
                q.execute('INSERT INTO gamebot_rolls (message_id,guild_id,channel_id,user_id,game_key,command_name,dice_count,modifier,definition_snapshot) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id)',
                          (message.id, message.guild.id, message.channel.id, message.author.id, roll['game'], roll['command'], len(roll['results']), roll['modifier'], json.dumps(roll['definition'])))
                if q.rowcount != 1:
                    c.rollback()
                    return False
                roll_id = q.lastrowid
                q.executemany('INSERT IGNORE INTO gamebot_roll_results (roll_id,die_index,dice_type,face_id,face_values) VALUES (%s,%s,%s,%s,%s)',
                              [(roll_id, index, result['dice_type'], result['face_id'], json.dumps(result['values'])) for index, result in enumerate(roll['results'])])
            c.commit()

    def purge_expired(self):
        """Purge only opted-in guilds, in bounded transactions."""
        deleted = 0
        with self.connection_factory() as c:
            with c.cursor() as q:
                q.execute('SELECT guild_id,retention_days FROM gamebot_guild_settings WHERE retention_enabled=TRUE')
                guilds = q.fetchall()
            for guild_id, days in guilds:
                with c.cursor() as q:
                    # Lock the setting so an off command cannot race the purge.
                    q.execute('SELECT retention_enabled,retention_days FROM gamebot_guild_settings WHERE guild_id=%s FOR UPDATE', (guild_id,))
                    current = q.fetchone()
                    if not current or not current[0]:
                        c.commit()
                        continue
                    q.execute('SELECT id FROM gamebot_rolls WHERE guild_id=%s AND rolled_at < UTC_TIMESTAMP() - INTERVAL %s DAY ORDER BY id LIMIT 1000 FOR UPDATE', (guild_id, current[1]))
                    ids = [row[0] for row in q.fetchall()]
                    if ids:
                        placeholders = ','.join(['%s'] * len(ids))
                        q.execute(f'DELETE FROM gamebot_roll_results WHERE roll_id IN ({placeholders})', ids)
                        q.execute(f'DELETE FROM gamebot_rolls WHERE id IN ({placeholders})', ids)
                        deleted += q.rowcount
                c.commit()
        return deleted
