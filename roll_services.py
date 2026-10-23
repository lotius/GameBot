"""Post-send history and opt-in dddice forwarding."""
import asyncio
import logging
import os
import time
from collections import deque

from cryptography.fernet import Fernet
import requests


def encrypt_key(key):
    secret = os.getenv('INTEGRATION_ENCRYPTION_KEY')
    if not secret:
        raise ValueError('Integration encryption key is not configured on the host.')
    return Fernet(secret.encode()).encrypt(key.encode()).decode()


def dddice_payload(roll, destination):
    dice = []
    for result in roll['results']:
        mapping = result.get('dddice')
        if not mapping:
            continue
        dice.append({'type': mapping['type'], 'theme': mapping['theme'], 'value': str(mapping['value'])})
    if not dice:
        return None
    return {'room': destination, 'dice': dice, 'label': f"{roll['game']} roll (modifier {roll['modifier']:+d})"}


def integration_key(policy):
    if policy.get('encrypted_key'):
        key = Fernet(os.environ['INTEGRATION_ENCRYPTION_KEY'].encode()).decrypt(policy['encrypted_key'].encode()).decode()
    else:
        key = os.getenv('DDDICE_API_KEY')
    if not key:
        raise ValueError('No dddice API key configured.')
    return key


def test_dddice_connection(policy):
    try:
        key = integration_key(policy)
    except Exception:
        return 'API key missing or could not be decrypted. Save it again with /dddice-key and check the host encryption key.'
    headers = {'Authorization': 'Bearer ' + key, 'Accept': 'application/json'}
    def check(path):
        response = requests.get('https://dddice.com/api/1.0/' + path, headers=headers,
                                timeout=10, allow_redirects=False)
        errors = {401: 'API key rejected or expired.', 403: 'Access denied: check the key permissions and room membership.',
                  404: 'Room not found or not accessible.', 429: 'dddice rate limit reached; retry later.'}
        if response.status_code in errors:
            return errors[response.status_code]
        if not response.ok:
            return f'dddice request failed (HTTP {response.status_code}).'
        if not isinstance(response.json(), (dict, list)):
            return 'dddice returned an unexpected response.'
        return None
    try:
        error = check('room')
        if error:
            return error
        destination = policy.get('destination') or policy.get('default_destination')
        if not destination:
            return 'API key accepted. No room configured; select a default or channel-specific room.'
        from urllib.parse import quote
        error = check('room/' + quote(destination, safe=''))
        if error:
            return 'API key accepted. ' + error
        return ('Connection successful: API key accepted and selected room readable. '
                'No roll was sent. This read-only test does not verify roll-write permission or theme compatibility.')
    except requests.Timeout:
        return 'dddice connection timed out; retry later.'
    except requests.RequestException:
        return 'Could not connect to dddice; check host network access.'
    except (ValueError, TypeError):
        return 'dddice returned an unexpected response.'


def forward_dddice(policy, roll):
    destination = policy['destination'] or policy['default_destination']
    payload = dddice_payload(roll, destination)
    if payload is None:
        return
    if not destination:
        raise ValueError('dddice needs an API key and destination room.')
    key = integration_key(policy)
    response = requests.post('https://dddice.com/api/1.0/roll', json=payload,
        headers={'Authorization': 'Bearer ' + key, 'Accept': 'application/json'}, timeout=15)
    if not response.ok:
        # Do not expose response bodies or Authorization headers in logs.
        raise RuntimeError(f'dddice returned HTTP {response.status_code}.')


class RollServices:
    def __init__(self, store):
        self.store = store
        self.cache = {}
        self.retry_after = 0
        self.refresh_after = {}
        self.buckets = {}

    async def policy(self, message):
        key = (message.guild.id, message.channel.id)
        now = time.monotonic()
        if now >= self.retry_after and key in self.cache and now < self.refresh_after.get(key, 0):
            return self.cache[key]
        if now >= self.retry_after:
            try:
                policy = await asyncio.to_thread(self.store.policy, *key)
                if len(self.cache) >= 10000:
                    self.cache.clear()
                    self.refresh_after.clear()
                self.cache[key] = policy
                self.refresh_after[key] = now + 15
                return policy
            except Exception:
                logging.warning('Database settings unavailable; using cached/default roll policy.')
                self.retry_after = now + 30
        policy = dict(self.cache.get(key, dict(rolls_enabled=True, spam_enabled=True,
                       spam_limit=5, spam_window_seconds=10)))
        policy.update(logging_enabled=False, dddice_enabled=False, integration_enabled=False,
                      database_unavailable=True)
        return policy

    def admit(self, message, policy):
        if not policy.get('spam_enabled', True):
            return True
        now = time.monotonic()
        window = policy.get('spam_window_seconds', 10)
        limit = policy.get('spam_limit', 5)
        # Drop inactive users instead of retaining a bucket forever.
        if len(self.buckets) > 10000:
            self.buckets = {key: value for key, value in self.buckets.items()
                            if value and now - value[-1] < 3600}
        key = (message.guild.id, message.author.id)
        bucket = self.buckets.setdefault(key, deque())
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    def invalidate(self):
        self.cache.clear()
        self.refresh_after.clear()
        self.retry_after = 0

    async def completed(self, message, roll, policy):
        if policy.get('database_unavailable'):
            await message.channel.send('Database unavailable: this roll was not recorded in statistics or forwarded to dddice.')
            return
        if policy['logging_enabled']:
            try:
                await asyncio.to_thread(self.store.record_roll, message, roll)
            except Exception:
                logging.exception('Roll logging failed for message %s.', message.id)
                await message.channel.send('Your roll succeeded, but its statistics could not be saved.')
        if policy['dddice_enabled'] and policy['integration_enabled']:
            try:
                await asyncio.to_thread(forward_dddice, policy, roll)
            except Exception as error:
                logging.error('dddice forwarding failed for message %s (%s).', message.id, type(error).__name__)
                await message.channel.send('Your roll succeeded, but dddice forwarding failed. Ask a moderator to check the integration settings and dice theme.')
