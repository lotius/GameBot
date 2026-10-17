"""Discover game instructions and persist successful announcements."""
import asyncio
from dataclasses import dataclass
import logging
from pathlib import Path
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests
import discord

from database import connect

log = logging.getLogger(__name__)
URL = 'https://instructions.hasbro.com/en-us/all-instructions?search=heroquest&page=1&limit=50&sort=newest'


@dataclass(frozen=True)
class Instruction:
    id: str
    title: str
    page_url: str


def parse_instructions(html):
    soup = BeautifulSoup(html, 'html.parser')
    results = {}
    for link in soup.find_all('a', href=True):
        if 'View Details' not in link.get_text(' ', strip=True):
            continue
        # The supplied Hasbro layout places title, product ID, then a third
        # paragraph before each details link. Skip incomplete cards safely.
        paragraphs = list(link.find_all_previous('p', limit=3))
        if len(paragraphs) < 3:
            continue
        title = paragraphs[2].get_text(' ', strip=True)
        product_id = re.search(r'\(([^()]+)\)', paragraphs[1].get_text(' ', strip=True))
        page_url = urljoin(URL, link['href'])
        if not title or not product_id or urlparse(page_url).hostname != 'instructions.hasbro.com':
            continue
        identifier = product_id.group(1).strip()
        if identifier and identifier not in results:
            results[identifier] = Instruction(identifier, title, page_url)
    return list(results.values())


def fetch_instructions():
    response = requests.get(URL, timeout=30)
    response.raise_for_status()
    return parse_instructions(response.text)


class InstructionStore:
    def __init__(self, connection_factory=connect):
        self.connection_factory = connection_factory
        self._initialized = False

    def initialize(self):
        if self._initialized:
            return
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""CREATE TABLE IF NOT EXISTS found_instructions (
                    instruction_id VARCHAR(191) PRIMARY KEY,
                    title TEXT NOT NULL,
                    page_url TEXT NOT NULL,
                    found_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
                cursor.execute('SHOW COLUMNS FROM found_instructions')
                columns = {row[0] for row in cursor.fetchall()}
                required = {'instruction_id', 'title', 'page_url'}
                if not required <= columns:
                    raise RuntimeError('Existing found_instructions schema needs review; '
                                       'required columns: instruction_id, title, page_url. '
                                       'No existing records were changed.')
                cursor.execute("""CREATE TABLE IF NOT EXISTS gamebot_instruction_deliveries (
                    channel_id BIGINT UNSIGNED NOT NULL,
                    instruction_id VARCHAR(191) NOT NULL,
                    sent_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    delivery_state VARCHAR(16) NOT NULL DEFAULT 'sent',
                    PRIMARY KEY (channel_id, instruction_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")
            connection.commit()
        self._initialized = True

    def discover(self, entries):
        """Register global discoveries once; an empty catalog is a silent baseline."""
        self.initialize()
        with self.connection_factory() as c:
            with c.cursor() as q:
                q.execute('SELECT 1 FROM found_instructions LIMIT 1')
                baseline = q.fetchone() is None
                new = []
                for entry in entries:
                    q.execute('INSERT IGNORE INTO found_instructions (instruction_id,title,page_url) VALUES (%s,%s,%s)', (entry.id,entry.title,entry.page_url))
                    if q.rowcount == 1 and not baseline:
                        new.append(entry)
            c.commit()
        return new

    def was_sent(self, channel_id, instruction):
        self.initialize()
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1 FROM gamebot_instruction_deliveries '
                               'WHERE channel_id=%s AND instruction_id=%s',
                               (channel_id, instruction.id))
                return cursor.fetchone() is not None

    def record_sent(self, channel_id, instruction):
        self.initialize()
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute('INSERT INTO found_instructions (instruction_id, title, page_url) '
                               'VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE instruction_id=instruction_id',
                               (instruction.id, instruction.title, instruction.page_url))
                cursor.execute('INSERT INTO gamebot_instruction_deliveries (channel_id, instruction_id) '
                               'VALUES (%s, %s) ON DUPLICATE KEY UPDATE channel_id=channel_id',
                               (channel_id, instruction.id))
            connection.commit()


    def reserve(self, channel_id, instruction):
        """Commit a unique pending delivery before contacting Discord."""
        self.initialize()
        with self.connection_factory() as c:
            with c.cursor() as q:
                q.execute('INSERT INTO found_instructions (instruction_id,title,page_url) VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE instruction_id=instruction_id', (instruction.id,instruction.title,instruction.page_url))
                q.execute("INSERT IGNORE INTO gamebot_instruction_deliveries (channel_id,instruction_id,delivery_state) VALUES (%s,%s,'pending')", (channel_id,instruction.id))
                claimed = q.rowcount == 1
            c.commit()
        return claimed

    def finish(self, channel_id, instruction):
        with self.connection_factory() as c:
            with c.cursor() as q:
                q.execute("UPDATE gamebot_instruction_deliveries SET delivery_state='sent', sent_at=CURRENT_TIMESTAMP WHERE channel_id=%s AND instruction_id=%s", (channel_id,instruction.id))
            c.commit()

    def release(self, channel_id, instruction):
        with self.connection_factory() as c:
            with c.cursor() as q:
                q.execute("DELETE FROM gamebot_instruction_deliveries WHERE channel_id=%s AND instruction_id=%s AND delivery_state='pending'", (channel_id,instruction.id))
            c.commit()


async def check_instructions(channel, store, marker_directory=None, entries=None):
    if channel is None:
        return
    if entries is None:
        fetched = await asyncio.to_thread(fetch_instructions)
        entries = await asyncio.to_thread(store.discover, fetched)
    for instruction in entries:
        if await asyncio.to_thread(store.was_sent, channel.id, instruction):
            continue
        # Preserve locally recorded history on the first database-backed run.
        # Both the older title markers and MentorBot's product-ID markers work.
        markers = Path(marker_directory) if marker_directory else None
        previously_sent = markers is not None and any(
            (markers / (key + '.txt')).is_file()
            for key in [instruction.id, instruction.title]
            if Path(key).name == key and '/' not in key and '\\' not in key
        )
        if previously_sent:
            await asyncio.to_thread(store.record_sent, channel.id, instruction)
            continue
        if not await asyncio.to_thread(store.reserve, channel.id, instruction):
            continue
        try:
            await channel.send(
                f"Hey everyone! A new PDF for **{instruction.title}** is now available "
                f"on the Hasbro Instructions webpage!\n{instruction.page_url}"
            )
        except (discord.Forbidden, discord.NotFound):
            # Definitive rejection: no message was delivered. Other failures keep
            # the pending reservation because delivery may have succeeded.
            await asyncio.to_thread(store.release, channel.id, instruction)
            raise
        await asyncio.to_thread(store.finish, channel.id, instruction)
