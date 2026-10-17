# GameBot database and setup

Install dependencies with `python -m pip install -r requirements.txt`, then
run `python init_database.py`. Tables already created on the connected host
can be reused. The migration preserves existing records.

The host environment contains `DISCORD_TOKEN`, `DB_HOST`, `DB_PORT`,
`DB_NAME`, `DB_USER`, `DB_PASSWORD`, and `INTEGRATION_ENCRYPTION_KEY`.
The encryption key was generated in the local `.env`. Copy that key along
with the database credentials to SparkedHost. Preserve it across restarts
and deployments: changing or losing it makes stored integration API keys
unreadable. Do not commit `.env` or share its contents.

## Moderator commands

Setup commands require Manage Server permission or the configured bot administrator role. They work in every
server channel, including channels where rolls are disabled. Setup is
intentionally absent from the public `!help` output.

```text
/setup instructions action:set channel:#announcements
/setup instructions action:off
/setup instructions action:status
/setup rolls action:off channel:#general
/setup rolls action:on channel:#games
/setup logging action:on
/setup logging action:off
/setup dddice action:"default <room-slug>"
/setup dddice action:<room-slug> channel:#campaign
/setup dddice action:on channel:#campaign
/setup dddice action:off channel:#campaign
/setup dddice action:on
/setup dddice action:off
/setup status
```

Channels allow rolls unless explicitly disabled. Logging defaults to on.
Instructions and dddice default to off. `/setup status` displays the current
channel's roll/integration settings and the server's logging/integration
status; keys are never displayed.

Use `/dddice-key` to enter the server's dddice API key in a private modal.
Keys are encrypted before storage. This slash command is registered at
startup; the bot installation needs application command support. Runtime
permission checks apply even if command permissions are changed in Discord.

To enable forwarding, save a key, enable dddice for the server, and enable
it in each desired Discord channel. A channel-specific room overrides the
server's default room. Use the room slug rather than the room URL. Keys
must have access to the selected room.

## Dice metadata and dddice

HeroQuest combat and movement themes use the mappings from the supplied
MentorBot reference. Other game types can opt in by adding to each dice type:

```json
"dddice": {"type": "d6", "theme": "your-theme-slug"}
```

Each face can include `dddiceValue` matching that face's value in the custom
3D theme and `values` containing numeric outcomes, for example:

```json
{"face": "skull.png", "numOfFaces": 3, "dddiceValue": 1,
 "values": {"skulls": 1}}
```

The theme's physical face order must match those values. Without an explicit
value the first weighted slot for the face is used. All results in a roll
must have theme mappings; otherwise forwarding reports a failure rather
than sending incorrect dice. Standard numeric dice currently log statistics
but have no dddice theme mapping. The original local outcome is sent to
DDDICE, so it does not reroll the dice. Modifiers appear in the roll label.

Metadata is reloaded every 30 seconds. Numeric `values` currently populate
HeroQuest combat and movement results; other games still provide face counts
and average dice per command, and can add numeric values in `dice.json`.

## History and statistics

```text
!stats roll
!stats hqroll
!stats hqmove
!stats descentdice
```

Statistics are scoped to the current Discord server. They show command
counts, dice counts, average dice per command, counts/percentages by dice
type and face, and totals/averages per command for configured numeric values.
Regular dice include each die's numeric value. Board game aliases resolve to
the same canonical game. Definition snapshots preserve historical weights
and result values when metadata changes.

Successful Discord sends are recorded as one roll with individual die
results in a single transaction. Invalid requests and failed Discord sends
are not recorded. Discord message IDs prevent duplicate history. Turning
logging off leaves existing history intact. Database or dddice failures
produce an explanatory message; statistics writes are not durably queued,
so an outage can leave a displayed roll unrecorded. This does not suppress
an older duplicate bot running elsewhere: deploy one active instance.

## Tables

- `found_instructions`: global instruction catalog.
- `gamebot_instruction_deliveries`: announcement history per destination.
- `gamebot_guild_settings`: instruction channel and roll logging preference.
- `gamebot_channel_settings`: per-channel dice permission and dddice room.
- `gamebot_guild_integrations`: encrypted per-server dddice credentials.
- `gamebot_configuration_audit`: moderator changes; key changes record only
  whether a key was configured, never plaintext or ciphertext.
- `gamebot_rolls`: per-command history, identity, and definition snapshot.
- `gamebot_roll_results`: exact individual faces and numeric outcomes.

Instruction checks run every 15 minutes. Product-ID/title marker files in
`found_instructions/` are imported without resending. Changing channels or
adding a server never replays products already in the shared catalog.
Pending delivery reservations suppress uncertain retries; review pending entries manually. No live Discord announcements or dddice rolls were sent during testing.

See INSTRUCTIONS.md for the complete current spam/retention controls,
outage behavior, instruction reservations, and DDDICE_API_KEY host fallback.
Run init_database.py before restarting to migrate those columns. Retention
is disabled by default; instruction send reservations suppress automatic
retries after uncertain delivery.

Instruction discovery runs once per poll, even without subscribed servers.
The 14 currently visible Hasbro entries were registered silently as the
baseline. Newly discovered products are distributed to the destinations from
that poll; they are not replayed automatically after outages or a restart.


## Private setup interface

All setup now uses slash commands. Public prefix setup messages are ignored and
are no longer supported. Select `/setup` in Discord and choose a subcommand;
Discord will present named fields. The required `action` field accepts the
setting value, and the optional `channel` field chooses a Discord text
channel. Both command responses and status output are ephemeral, visible only
to the moderator running them. Runtime checks require Manage Server or the configured bot administrator
role. Command names may be visible to others; execution and responses remain
protected. Discord Integration permissions can further restrict visibility. Discord administrators
can still see command names; names are not secrets.

Examples using the named Discord fields:

| Command | Fields | Purpose |
|---|---|---|
| `/setup instructions` | `action: set`, `channel: #announcements` | Select announcement channel |
| `/setup instructions` | `action: off` or `action: status` | Disable or inspect announcements |
| `/setup rolls` | `action: on` or `off`, `channel: #games` | Configure dice access |
| `/setup logging` | `action: on` or `off` | Configure roll statistics |
| `/setup spam` | `action: 5 10` | Five commands per ten seconds |
| `/setup spam` | `action: on` or `off` | Enable/disable spam protection |
| `/setup retention` | `action: 90` | Set retention days |
| `/setup retention` | `action: on` or `off` | Enable/disable purging |
| `/setup dddice` | `action: default my-room` | Set default room |
| `/setup dddice` | `action: my-room`, `channel: #campaign` | Set room override and enable channel |
| `/setup dddice` | `action: on` or `off`, `channel: #campaign` | Enable/disable channel forwarding |
| `/setup dddice` | `action: on` or `off`, no channel | Enable/disable server integration |
| `/setup status` | No fields | Inspect current channel/server settings |
| `/dddice-key` | Private modal | Save a per-server key |

Values with spaces are entered as one action field (without surrounding
quotes in the Discord field). Restart the bot to register these commands in
its connected servers. Refresh Discord if its picker shows stale entries.


## Per-server bot administrator role

Use a normal Discord role to delegate bot management without granting Manage
Server. A member may configure the bot if they have **Manage Server OR the
configured bot administrator role** in that server. No role is configured by
default. The role ID is saved in MariaDB; changing a role name does not affect
access. Removing the role from a member revokes their delegated access.

Only Manage Server users can use these private commands:

| Command | How to use it | Why |
|---|---|---|
| `/setup admin-role` | `action: set`, `role: @Bot Admin` | Delegate bot configuration to members of that regular role |
| `/setup admin-role` | `action: status` | Inspect the saved role |
| `/setup admin-role` | `action: clear` | Remove delegation; Manage Server access remains |

`@everyone`, managed integration roles, and roles from another server cannot
be assigned. Changes are audited. Delegated administrators cannot replace,
clear, or inspect the delegation setting through this command, so they cannot
expand their own authority.

Delegated administrators can change channel settings, statistics retention,
spam controls, announcements, dddice destinations, and dddice API keys. They
can therefore enable destructive statistics purging and replace integration
credentials. Key permission is checked again when the private modal is
submitted. A database outage denies role-based configuration until permissions
can be verified; Manage Server access does not depend on that role lookup.

Discord's fixed default Manage Server restriction has been removed from the
setup group and key command so role-only administrators can invoke them.
Runtime permission checks protect every operation. To also hide command names
from ordinary members, use **Server Settings > Integrations > the bot** and
allow `/setup` and `/dddice-key` for the delegated role and administrators,
while denying other roles. Keep the delegated role allowance current if you
change the configured role. Inputs, replies, and denials remain ephemeral.

Restart the bot to register `/setup admin-role` and updated command permissions.
The database migration has already been applied locally; run
`python init_database.py` when deploying this code elsewhere.


## Private dddice connection test

Use `/setup dddice-test` to check the key and room configured for the current
channel, or select the optional `channel` field to test another channel in
this server. Manage Server or the bot administrator role is required.
Responses are private. The test uses the saved per-server key first, then
the host fallback, and checks authenticated room-list and selected-room reads.
It does not send a roll, change settings, or expose the API key.

Errors distinguish missing/decryption-failed keys, rejected keys, inaccessible
rooms, rate limits, timeouts, and database problems. A successful result proves
authentication and room readability, not roll-write permission or 3D theme
compatibility. Test an ordinary mapped roll separately when ready. Restart
the bot to register the new slash subcommand.

API reference: https://docs.dddice.com/api/


## Dice-channel defaults and voice text chats

Rolls are enabled in all channels by default, including newly created
channels. This is an explicit-disable policy, not an allowlist. Configure
exceptions privately with:

```text
/setup rolls action:off channel:#general
/setup rolls action:off channel:<voice channel>
/setup rolls action:on channel:<voice channel>
```

The channel picker accepts text channels, voice-channel text chats, stage
channels, and threads. Settings apply to the selected channel ID. A thread
has its own channel ID; disabling its parent does not automatically disable
that thread. To disable a channel, the bot does not need permission to post
there; enabling requires the appropriate view/send permissions. Attachment
permission is additionally needed when rolling image dice. Thread replies
use Send Messages in Threads permission.

Public prefix setup is no longer supported. Use the private `/setup rolls`
command, with Manage Server or the configured bot administrator role.
Restart to refresh the expanded slash-command channel picker.


## Comprehensive statistics reports

Use `!stats` for an overview, `!stats help` for examples, or `/stats` for
guided game/player/channel/date/type fields and optional private results.
Reports include summaries, faces, values, historical comparisons, recent
results, activity leaderboards, daily activity, and CSV exports. See
[STATISTICS.md](STATISTICS.md) for every command, filter, example, and limit.
Restart to register `/stats`; no database schema migration is needed.
