# GameBot setup instructions

## 1. Prepare Discord

1. Open [Discord Developer Portal](https://discord.com/developers/applications)
   and select your bot application.
2. Under **Bot**, enable **Message Content Intent**. The bot uses default
   gateway intents plus message content; Server Members and Presence intents
   are not required.
3. Obtain the bot token and save it as `DISCORD_TOKEN` in the host environment.
4. Invite the bot to each server using the `bot` and `applications.commands`
   scopes. Grant **View Channel**, **Send Messages**, and **Attach Files** in
   the channels you intend to use. The bot itself does not need Administrator.
5. Moderators configuring it need **Manage Server** permission or the configured
   bot administrator role. Assigning that role requires Manage Server.

See the [discord.py intent documentation](https://discordpy.readthedocs.io/en/stable/intents.html).

## 2. Prepare MariaDB and the environment

The current database already has all eight tables. For a new deployment:

1. In SparkedHost Apollo, open **Databases**, create/select the database, and
   copy its endpoint, port, username, password, and full database name.
2. Ensure **Connections From** allows the bot host. SparkedHost documents `%`
   as allowing connections from anywhere.
3. Put the following entries in `.env` in the GameBot directory. Use actual
   values instead of the placeholders; never paste secrets into Discord.

```dotenv
DISCORD_TOKEN=your-discord-bot-token
DB_HOST=your-database-hostname
DB_PORT=your-database-port
DB_NAME=your-full-database-name
DB_USER=your-database-user
DB_PASSWORD="your-database-password"
INTEGRATION_ENCRYPTION_KEY=your-existing-encryption-key
DDDICE_API_KEY=
```

Use the hostname alone for `DB_HOST`; specify the port separately. A properly
quoted password is supported. Copy credentials directly from the panel to
avoid confusing similar characters. Restart after environment changes.

An encryption key has already been generated in this project's `.env`.
Preserve that same key across deployments: it decrypts the dddice credentials
in MariaDB. Keep a private backup of it alongside database backups. Do not
regenerate it when restarting or moving the bot. If it is lost, stored API
keys need to be entered again. The optional plaintext host fallback is protected by the private `.env`, rather than stored encrypted in MariaDB.

For an entirely fresh installation without encrypted credentials, generate
an encryption key after installing dependencies:

```text
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Save that output privately as `INTEGRATION_ENCRYPTION_KEY`.

[Official SparkedHost database setup guide](https://help.sparkedhost.com/en/article/how-to-create-a-mysql-database-1yf1ruk/).

## 3. Install and run locally on Windows

Open PowerShell in the GameBot directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe init_database.py
.\.venv\Scripts\python.exe gamebot.py
```

If `.venv` already exists, skip its creation. `init_database.py` is safe to
rerun: it creates missing tables and preserves existing records. If an
existing instruction table has an incompatible schema, review it rather
than deleting it.

Select `.venv\Scripts\python.exe` as the VS Code Python interpreter.
Keep the terminal running. Press **Ctrl+C** to stop the bot.

## 4. Deploy on SparkedHost

1. Stop any local or old hosted instance using the same Discord token.
2. Upload the current Python files, `requirements.txt`, `dice.json`,
   `schema.sql`, and the complete `images/` directory.
3. Set the host environment or upload the private `.env`, including the
   **same encryption key** used locally. Do not publish this file.
4. Use a compatible Python runtime. The local setup has been tested with
   Python 3.14; dependency installation must succeed for the host runtime.
5. Install dependencies in the deployment's interpreter:

   ```text
   python -m pip install -r requirements.txt
   python init_database.py
   ```

6. Configure the Python startup file/command as `gamebot.py` or
   `python gamebot.py`, according to the selected hosting template.
7. Start it from the GameBot directory and check for the connected message.

Do not upload the Windows `.venv` to a Linux host. Install dependencies on
that host instead. Run one active instance per Discord token; two instances
can both respond to the same message.

## 5. First setup for each Discord server

These settings belong to the server where the command is run. Repeat the
setup in each server; no server IDs or channel IDs belong in `.env`.

```text
/setup instructions action:set channel:#announcements
/setup instructions action:status
/setup logging action:on
/setup rolls action:off channel:#general
/setup rolls action:on channel:#games
```

Rolls default to enabled in every channel, so disable every channel where
you do not want rolling. Enabling `#games` does not create an allowlist or
turn off other channels. Help, setup, and statistics remain available when
rolling is disabled.

Instructions default to off. The shared catalog suppresses every already-known
entry, including for newly configured channels. Only new global discoveries
are announced to all currently subscribed servers. An empty catalog is seeded
silently on its first scan. Checks run every 15 minutes. Set up the destination
before expecting announcements.

Test in an enabled dice channel:

```text
!help
!help hqroll
!roll 2d6 + 3
!hqroll 3
!hqroll 1 boss 2 pink
!hqmove 2 fl
!stats roll
!stats hqroll
```

### Optional host-level dddice key

`DDDICE_API_KEY` has been added as an empty entry in `.env`. You may put your
key there privately and restart the bot. It is used only for enabled
integrations/channels where no encrypted per-server key is stored. The same
host key can therefore serve multiple configured servers. For separate server
accounts use `/dddice-key`; those stored keys always take precedence. The host
fallback is not copied into MariaDB or audit records.

## 6. Configure dddice for a server

1. Obtain an API key from your dddice account and identify a room slug that
   the key can access.
2. Run `/dddice-key` in the Discord server. Enter the key in the private
   modal; do not enter it as a public prefix command.
3. Choose a default room and enable the integration:

   ```text
   /setup dddice action:"default your-room-slug"
   /setup dddice action:on
   ```

4. Enable forwarding in each chosen Discord channel:

   ```text
   /setup dddice action:on channel:#campaign
   ```

   Or specify a room for that channel:

   ```text
   /setup dddice action:another-room-slug channel:#campaign
   ```

5. Run `/setup status` in that channel, then test a mapped roll such as
   `!hqroll 2 white`.

Both the server integration and channel forwarding must be on. A
channel-specific room takes priority over the server default. Use the room
slug rather than its URL. Save a replacement key through `/dddice-key` if
credentials change.

HeroQuest combat and movement dice have mappings. Standard `!roll` and other
games without mappings still work in Discord and log statistics, but cannot
yet be forwarded. Every requested dice type in a forwarded roll needs a
matching dddice theme. A missing mapping reports a forwarding failure.

The integration sends the already selected outcomes rather than generating
a second roll. See the [dddice API documentation](https://docs.dddice.com/api/).

## 7. Customize dice and aliases

Edit `dice.json` and put the referenced images in the game's configured
`imageDirectory` under `images/`. HeroQuest uses `images/hqdice/transparent/`.
The bot checks for changed definitions every 30 seconds; no restart is needed
for valid metadata edits. Invalid edits keep the last working definitions
and log the reason. Startup requires valid metadata and existing images.

Add aliases beside a dice type's existing faces and limit, for example:

```json
"aliases": ["p", "rose"]
```

This lets `!hqroll 3 rose` select pink if those aliases are added to pink.
Use lowercase names starting with a letter, followed by letters/numbers.
Keep aliases unique within a game. Aliases normalize to the same type;
`!hqroll 1 pink 1 rose` is rejected as specifying it twice.

Game-level aliases choose the command, such as `hqroll` for `hqdice`.
`defaultDiceType.typeToUse` chooses the type for a count-only request.
`numOfFaces` is a face's probability weight. Per-type limits and the overall
limit are enforced; excess counts are rejected rather than reduced.
Generated help includes aliases, defaults, limits, and randomized examples.

Add numeric `values` to a face to include damage, shields, range, or other
quantities in statistics. Add `dddice` to a type and `dddiceValue` to each
face to map a custom 3D theme, as described below.

## Complete moderator command reference

Ordinary slash setup commands require **Manage Server** or the configured bot administrator role and is scoped to the
server where it is issued. Setup remains available in channels with rolls
disabled and is intentionally omitted from public help. Channel parameters
accept a channel mention or numeric ID from that same server. The bot must
have View Channel and Send Messages there. Settings persist in MariaDB and
changes are audited without storing API keys in the audit log.

Changes normally take effect immediately in the running instance; cached
roll policies can last 15 seconds. Database outages prevent setup changes,
but do not prevent ordinary rolling. `/setup status` is a read-only check.
There is no automatic allowlist: channels allow rolls until explicitly off.

### `/setup instructions action:set channel:#announcements`

**What it does:** Selects this server's HeroQuest instruction announcement destination.

**How and why to use it:** Run `/setup instructions action:set channel:#announcements` to subscribe this server. Use a channel appropriate for news. Checks run every 15 minutes; already-known entries stay silent, including on a newly configured destination.

### `/setup instructions action:off`

**What it does:** Disables instruction announcements for this server.

**How and why to use it:** Use when the server does not want instruction news. Existing catalog and delivery history remain; no other server is affected.

### `/setup instructions action:status`

**What it does:** Shows the selected instruction channel or reports that announcements are off.

**How and why to use it:** Use to verify your destination before waiting for the next poll. It changes nothing.

### `/setup rolls action:on channel:#channel`

**What it does:** Allows standard and board-game rolls in the selected channel.

**How and why to use it:** Example: `/setup rolls action:on channel:#games`. This enables that channel only; it does not disable any others. Attach Files is needed for image dice.

### `/setup rolls action:off channel:#channel`

**What it does:** Silently ignores dice rolls in the selected channel.

**How and why to use it:** Example: `/setup rolls action:off channel:#general`. Use to keep rolling out of conversation channels. Help, statistics, and moderator setup remain available.

### `/setup logging action:on`

**What it does:** Records successful dice rolls and their individual results for this server.

**How and why to use it:** Logging defaults to on. Enable it to collect command counts, face frequencies, and numeric statistics. Failed commands/sends are not recorded.

### `/setup logging action:off`

**What it does:** Stops saving new dice statistics for this server.

**How and why to use it:** Use when history is unwanted. Existing records remain; rolls still work and dddice can still forward them. This does not disable configuration auditing.

### `/setup spam action:"<count> <seconds>"`

**What it does:** Sets a per-user, per-server command allowance.

**How and why to use it:** Example: `/setup spam action:"5 10"` allows five accepted commands per user in a rolling ten-second window across all channels. Count must be 1-100 and seconds 1-3600. This changes limits but does not turn protection on if it is off.

### `/setup spam action:on`

**What it does:** Enables the configured command rate limit for this server.

**How and why to use it:** Defaults to on, at five commands per ten seconds. Use after configuring stricter limits. Excess commands are silently ignored so cooldown responses cannot themselves flood chat. Invalid arguments to a recognized command also consume allowance.

### `/setup spam action:off`

**What it does:** Disables the configurable per-user rate limit for this server.

**How and why to use it:** Use for controlled testing or a trusted server. The limit applies to supported prefix commands except moderator `/setup`; private `/dddice-key` is also outside this limiter. Counters are in memory and reset when the bot restarts.

### `/setup retention action:<days>`

**What it does:** Sets the age threshold for statistics deletion without enabling it.

**How and why to use it:** Example: `/setup retention action:90` keeps ninety days when retention is on. Valid range: 1-36500 days. Set the intended threshold before enabling. Lowering it while retention is already on affects the next purge.

### `/setup retention action:on`

**What it does:** Enables automatic deletion of older roll statistics in this server.

**How and why to use it:** Default is off. The configured default threshold is 90 days. Enabling permanently deletes old roll rows and their individual results when the next maintenance task runs; it does not archive them. Use to bound storage and keep statistics focused on recent activity.

### `/setup retention action:off`

**What it does:** Stops future automatic purges for this server.

**How and why to use it:** Use to preserve all remaining history. Already purged records cannot be recovered without a backup. Instruction delivery history, integration settings, and audit logs are never purged by this feature.

### `/setup dddice action:"default <room-slug>"`

**What it does:** Sets the default dddice destination for this server.

**How and why to use it:** Example: `/setup dddice action:"default my-campaign"`. Use a room slug, not a URL. The key must have access to that room. This does not itself enable forwarding, and a channel override takes precedence.

### `/setup dddice action:<room-slug> channel:#channel`

**What it does:** Sets a channel-specific dddice destination and enables forwarding for that channel.

**How and why to use it:** Example: `/setup dddice action:my-room channel:#campaign`. Use when different Discord channels belong to different campaigns. The server integration must also be on.

### `/setup dddice action:on channel:#channel`

**What it does:** Enables dddice forwarding for the selected channel using its existing override or server default.

**How and why to use it:** Example: `/setup dddice action:on channel:#campaign`. Use after choosing a room and configuring an API key. If no room is configured, a forwarded roll will fail rather than guessing a destination.

### `/setup dddice action:off channel:#channel`

**What it does:** Disables forwarding in the selected channel while preserving its room override.

**How and why to use it:** Example: `/setup dddice action:off channel:#campaign`. Discord rolls and statistics continue normally. Turning it on later reuses the saved override.

### `/setup dddice action:on`

**What it does:** Enables the server-level dddice integration.

**How and why to use it:** Use after configuring a private per-server key or the host fallback key. Only channels with forwarding enabled are affected. Supported dice also need theme mappings.

### `/setup dddice action:off`

**What it does:** Disables dddice forwarding for the entire server.

**How and why to use it:** Use to pause integration without deleting keys, room choices, or individual channel settings. Discord rolls and statistics continue.

### `/dddice-key`

**What it does:** Opens a private modal to save or replace this server's dddice API key.

**How and why to use it:** Requires Manage Server. The key is encrypted before storage and the confirmation is private. It takes precedence over `DDDICE_API_KEY` in the host environment. It does not enable forwarding or verify room access. Never enter a key in a public prefix message.

### `/setup status`

**What it does:** Displays this channel's roll and dddice settings plus server logging, integration, spam, and retention settings.

**How and why to use it:** Run it in the channel you want to inspect. Keys appear only as configured, host fallback, or unset; their values are never shown. Use `/setup instructions action:status` separately for the news destination.

### Retention schedule and scope

Maintenance runs on bot startup and then hourly, deleting up to 1,000 expired
rolls per opted-in server on each run. Large backlogs drain over multiple runs.
A roll expires when its timestamp is older than the configured number of days.
The delete of parent rolls and child results is transactional and scoped to
one server. Purging changes that server's displayed statistics permanently.
Retention remains disabled until a moderator explicitly enables it.

### Database outage behavior

When settings cannot be loaded, the bot uses its last cached channel and spam
policy. If that channel has no cached policy, rolls are allowed with the
default spam protection; a restriction cannot be recovered from an unavailable
database. Logging and dddice forwarding are disabled for outage-mode rolls.
The response states that the roll was not recorded. No retrospective replay
or durable queue is implemented. Connection retries resume after 30 seconds.
If a cached policy was still fresh when a statistics write fails, the bot
reports that the displayed roll could not be saved. Stats/setup commands need
MariaDB and report an unavailable database rather than fabricating results.

### Instruction delivery guarantees

Announcements require both a successful delivery-history lookup and a
committed unique pending delivery reservation before sending to Discord.
If the database is unavailable, nothing is sent. Existing sent or pending
entries are skipped, including after a failed final database update. Definite
Discord rejection (missing channel or permission) releases the reservation if
the database is still available. An uncertain failure or process interruption
leaves the entry pending rather than risking a repeat. This favors preventing
duplicates; a pending message may never have been delivered.

An administrator can inspect pending rows through phpMyAdmin:

```sql
SELECT channel_id, instruction_id, sent_at
FROM gamebot_instruction_deliveries
WHERE delivery_state = 'pending';
```

Check Discord before resolving an entry. If it was delivered, update only
that row to `delivery_state = 'sent'`. If it was not delivered, an administrator can announce it manually. Deleting a
pending row does not trigger replay because the shared catalog suppresses it. Do not reset all delivery
history. Changing channels does not replay catalog entries. The next discovery
scan announces only newly registered global products.

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

## Database tables

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
Pending reservations prevent automatic resends after an uncertain delivery; review them manually if necessary. No live Discord announcements or dddice rolls were sent during testing.

## Troubleshooting

| Symptom | Check |
|---|---|
| `ModuleNotFoundError` | Install requirements with the same interpreter used to start the bot. On Windows use `.venv\Scripts\python.exe`. |
| Duplicate replies or a successful roll followed by an obsolete error | Stop the old/local/hosted duplicate instance. |
| Database connection timeout | Verify endpoint, port, host availability, and allowed connection sources. |
| MariaDB error 1045 | Copy credentials directly into `.env` and test via the database's built-in phpMyAdmin. Local phpMyAdmin access does not establish remote access. |
| Missing tables | Run `python init_database.py` using the deployment interpreter and environment. |
| Bot connects but ignores prefix commands | Check Message Content Intent, channel permissions, and `/setup status`; the channel may have rolls disabled. |
| `/dddice-key` does not appear | Check startup logs for slash command sync errors and that the bot installation includes application command support. Commands may take time to appear. |
| dddice forwarding fails | Check server/channel enablement, room access, theme mappings, and the original encryption key on this host. |
| No instruction announcements | Check `/setup instructions action:status`, destination permissions, polling errors, and existing delivery history. |
| Dice edits do not apply | Wait 30 seconds and check logs for invalid JSON, duplicate aliases, bad limits, or missing images. |
| `bash: sed: command not found` but Discord connects | This is a Git Bash shell issue; use PowerShell to launch the bot. |

After code, dependency, or environment changes, restart the single active
bot instance. Database-backed settings take effect without restart; valid
dice metadata updates take effect on the next reload.

Before upgrading a deployment, stop its bot, install requirements and run
`python init_database.py` to add the new settings/delivery-state columns, then
restart. These migrations preserve existing history and keep retention off
for previously unconfigured servers.

Run the local regression tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -q
```

Messages from bots, webhooks, DMs, system events, or messages with attachments
are ignored. Unknown commands and malformed prefixes are ignored. Prefix
commands must start directly with `!` followed by the command name. Supported
commands with malformed arguments receive usage feedback. Commands longer
than 1,000 characters are rejected. Outgoing bot messages cannot ping users
or roles. Unexpected command failures are logged and contained.

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

## Comprehensive statistics commands and reports

Statistics are available to ordinary server members. They never read another
server's history. Run `!stats` for a friendly overview or use `/stats` for
Discord's guided command fields. `!stats help` lists reports and examples.

### Quick start

```text
!stats
!stats hqroll
!stats me
!stats faces hqroll week
!stats values oqroll month
!stats compare hqroll type:white
!stats leaderboard week
!stats recent me
```

Long reports have Previous/Next buttons, usable by the person who requested
the report. Other users can request their own report. Buttons expire after
three minutes; run the command again to refresh it. Reports show their
filters, command/dice/player counts, average dice per command, and recorded
start/end timestamps. Discord displays timestamps in the viewer's local time.

### Reports

| Command | What it shows | When to use it |
|---|---|---|
| `!stats` / `!stats overview` | Server activity grouped by game | See what everyone is playing |
| `!stats hqroll` / `!stats summary hqroll` | Game totals, averages, and numeric result totals | Get a quick game summary |
| `!stats faces hqroll` | Every recorded face's count and percentage within its dice type | Examine face frequencies |
| `!stats values hqroll` | Symbol totals, average per selected command, average per selected die | Inspect skulls, shields, damage, or other metadata values |
| `!stats compare hqroll` | Actual face percentages, expected percentages, difference in percentage points | Compare recorded results with configured face weights |
| `!stats recent hqroll` | Latest 20 individual results with player, time, dice type, and modifier | Review recent activity |
| `!stats leaderboard` | Top 25 players ranked by recorded command count, plus dice count | Compare activity, not luck |
| `!stats daily` | Command/dice counts by UTC day, newest first, up to 90 dates | See activity over time |
| `!stats export hqroll` | CSV with up to 1,000 newest individual die records | Analyze or save a selection externally |
| `!stats help` | Report/filter instructions and examples | Find a command |

Standard dice use `roll`, `dice`, or `standard`. Board game commands and their
aliases work, for example `hqroll`, `hqdice`, `drgroll`, or `oqroll`.
`hqmove` is a separate movement statistics category. Omit the game for a
server-wide view where appropriate.

### Filters: combine them in any order

| Filter | Meaning | Example |
|---|---|---|
| `me` | Only your rolls | `!stats me month` |
| `@player` | Only that player's rolls in this server | `!stats hqroll @player week` |
| `here` | Only the current channel | `!stats recent here` |
| `#channel` | Only that server channel | `!stats leaderboard #games month` |
| `today` | Since midnight UTC | `!stats today` |
| `week` | Rolling last 7 days | `!stats hqroll week` |
| `month` | Rolling last 30 days | `!stats values hqroll month` |
| `7d`, `30d`, etc. | Rolling last N days (1-9999) | `!stats faces drgroll 14d` |
| `all` | All retained history; this is the default | `!stats hqroll all` |
| `since:YYYY-MM-DD` | From that date at midnight UTC | `!stats hqroll since:2026-10-01` |
| `until:YYYY-MM-DD` | Through the entire selected UTC date | `!stats hqroll until:2026-10-31` |
| `type:white` | Only that dice type, for a selected game | `!stats compare hqroll type:white` |

Use actual Discord mentions for players and channels. Plain display names
are ambiguous and are not accepted. Choose one game, user, channel, and view
per request. Choose a duration OR explicit dates, not both. Dice type aliases
are normalized automatically (for example HeroQuest `type:dew` uses `gen24`).
For standard dice use `type:d6`, `type:d20`, etc. A dice-type filter requires
a game. With this filter, command counts mean commands containing that type,
and dice counts include only matching dice.

Combined examples:

```text
!stats faces hqroll me week type:white
!stats values oqroll @player month
!stats compare drgroll type:red 30d
!stats recent here me
!stats export descentdice since:2026-10-01 until:2026-10-31
```

### Guided slash command

Select `/stats` and choose named fields:

- `view`: overview, summary, faces, values, compare, recent, leaderboard,
  daily, export, or help.
- `game`: a game command such as `hqroll`, or `roll` for standard dice.
- `player`: an optional member picker.
- `channel`: an optional text, voice, stage, or thread channel picker.
- `days`: optional rolling number of days.
- `dice_type`: optional type or alias; choose a game too.
- `private`: set to true to make the report visible only to you.

Examples: `/stats view:faces game:hqroll days:7 dice_type:white` or
`/stats view:summary game:oqroll player:@player private:true`.
Use prefix commands for exact since/until date ranges. Slash reports respect
the configured spam protection. Selecting a game with the default overview
produces that game's summary.

### Understanding the numbers

A command rolling five dice contributes one command and five individual die
results. Face percentages use the selected dice type as the denominator.
Numeric values come from the `values` captured with each die result. Totals
and averages preserve historical values rather than rewriting older rolls
when metadata changes. Missing numeric values in older history are not
backfilled; averages describe recorded values across the selected dice and
commands. Standard numeric result totals exclude the command modifier; the
modifier is included in recent/export records for separate analysis.

Expected percentages in comparison reports use each roll's historical
weight definition. For example, standard white HeroQuest skulls have a 3/6
expected frequency. Different definitions are weighted by how many dice were
actually rolled under each definition. Comparisons include faces with zero
observations. Differences are descriptive; small samples can vary widely
and this report is not a statistical fairness test.

Leaderboard results measure activity, never luck or skill. All reports cover
only this server, only retained history, and only rolls successfully saved.
Disabled logging and database outages create gaps. Retention deletion changes
report totals. A report with no matches explains how to widen the filters.

### CSV exports and limits

Exports require the bot's Attach Files permission. CSV columns include roll
ID, UTC timestamp, current player name, channel ID, game, modifier, die index, dice type,
face ID, and values JSON. Each row is one die, so a capped export may include
only part of its oldest roll. Exports preserve formulas as literal text to
avoid spreadsheet execution. They are capped at 1,000 rows to keep downloads
manageable; narrow filters when more history exists. A private slash export
is visible only to its requester.

Detailed reports aggregate history in MariaDB instead of loading every die.
An unusually large number of historical face/metadata variations asks you
to narrow the game/date filters. Statistics are read-only and never change
settings or send dddice rolls. Database failures return a clear unavailable
message while ordinary rolling can continue.

### Deployment

Restart the bot after updating this code to register `/stats` in connected
servers. Existing database tables are reused; no history migration or
schema change is required for these reports. Refresh Discord if the command
picker is stale. The bot needs Embed Links for the report cards and Attach
Files for CSV exports.


### Detailed walkthrough: server overview

**Commands:** `!stats`, `!stats overview`, or `/stats view:overview`.

Use this first when you do not know which game to investigate. It lists each
game represented in the selected history, ordered by command activity. The
header shows recorded command count, total individual dice, distinct players,
and the average dice per selected command. The range below it describes the
oldest and newest matching records, not necessarily the requested boundaries.

```text
!stats
!stats overview week
!stats me
!stats overview #games month
```

`!stats me` is an overview across your games. `!stats here` is an overview
of the current channel. A game may not appear because nobody rolled it,
logging was off, recording failed, a filter excluded it, or history was purged.
An omitted game does not mean that its dice command is unavailable.

### Detailed walkthrough: game summary

**Commands:** `!stats hqroll`, `!stats summary hqroll`, or
`/stats view:summary game:hqroll`.

Use a summary for totals without a long face-by-face table. In addition to
activity counts, it lists each recorded numeric result key, total, average
per selected command, and average per selected die. HeroQuest can show skulls,
white shields, and black shields; other games use their configured values.

```text
!stats hqroll
!stats summary oqroll me month
!stats summary roll type:d20 week
!stats hqmove here
```

For standard rolls, `value` is the sum of the individual dice before modifiers.
For movement dice, `movement` is the sum of their recorded numeric outcomes.
A summary is not a count of wins, combat hits, or damage actually applied:
the bot does not know game state, target defense, or how a result was used.

### Detailed walkthrough: faces

**Command:** `!stats faces <game>` or `/stats view:faces game:<game>`.

Use this to see how often each pictured result appeared. Results are grouped
by game, dice type, and recorded face ID. Each percentage uses the number of
selected dice of that same type, not all dice in the entire report.

```text
!stats faces hqroll type:white
!stats faces descentdice type:red me 30d
!stats faces roll type:d6
!stats faces oqroll #games week
```

If white HeroQuest dice were rolled 100 times and skull appeared 48 times,
its observed frequency is 48%. Rolling some blue dice does not change that
white-die percentage. Repeated physical sides with the same image are one
result category: three skull sides do not create three separate rows.

The faces view displays observed outcomes. For expected faces that have not
appeared at all, use the comparison report; it includes zero-observation faces.

### Detailed walkthrough: numeric values

**Command:** `!stats values <game>` or `/stats view:values game:<game>`.

Use this to aggregate symbols or quantities rather than image filenames.
The keys come from the `values` saved with each result. A face may contribute
to multiple keys, and a double symbol may contribute 2 rather than 1.

```text
!stats values hqroll type:white me week
!stats values oqroll month
!stats values descentdice 14d
!stats values drgroll here
```

For OrcQuest, the configured keys can combine die colors into result types
such as yellow attack or orange defend. The actual totals follow your current
and historical definitions; the report does not infer missing values from
a filename. A blank result can be counted explicitly if its definition has
a numeric blank key.

Worked example: two recorded HeroQuest commands contain five selected dice
in total, and their recorded results contribute three skulls. The report
shows 3 skulls total, 1.50 skulls per command, and 0.60 skulls per die.

With `type:white`, only white dice contribute to the die denominator and
numeric totals; only commands containing white dice contribute to the command
denominator. Older rolls with missing numeric metadata are not backfilled.
Averages include those records in the denominator, so use dates starting
after metadata was populated if you need a consistently annotated sample.

### Detailed walkthrough: observed versus expected

**Command:** `!stats compare <game>` or `/stats view:compare game:<game>`.

Use this when you want to compare face frequencies with the configured dice
weights. Each row shows observed count/percentage, expected percentage, and
the difference expressed in percentage points. Positive means that face
appeared more often than its weighted expectation; negative means less often.

```text
!stats compare hqroll type:white
!stats compare doomroll type:black month
!stats compare roll type:d20 me 30d
```

Example: expected skull frequency is 50%, observed is 55%, and the displayed
difference is +5 percentage points. It is not a statement that the player
was 5% luckier, nor that the random generator is biased.

The report uses definition snapshots saved with the rolls. If a face's weight
changed, expected counts from the old and new definitions are combined in
proportion to how many selected dice used each version. A 3/6 skull result
and a 4/6 skull result therefore retain their separate historical expectations.

Small samples are noisy. This report supplies descriptive comparisons only;
it does not calculate p-values, confidence intervals, or prove fairness.

### Detailed walkthrough: recent results

**Command:** `!stats recent` or `/stats view:recent`.

Use this to check recent recorded outcomes and identify the player/time.
It returns up to 20 individual dice results, newest commands first. Each
line includes the recorded timestamp, player, game, dice type, face, die
position, and command modifier. A six-dice command can contribute six lines.
The modifier is shown on every line for that command; do not add it once
for every die when reconstructing the command total.

```text
!stats recent
!stats recent me here
!stats recent hqroll @player week
```

The limit is on individual dice, not commands. At the oldest edge, the report
can contain only part of a command. Use an export for a larger result set.
Recent results are database history, not a replay of Discord messages.

### Detailed walkthrough: leaderboard

**Command:** `!stats leaderboard` or `/stats view:leaderboard`.

Use this to see the most active rollers, ranked by recorded command count.
The report includes up to 25 users and shows their selected command and dice
counts. Ties are ordered by user ID; a rank is an activity ranking only.

```text
!stats leaderboard
!stats leaderboard hqroll week
!stats leaderboard here month
```

Filtering a leaderboard to `me` or one player produces a one-person ranking.
For competition across players, leave the player filter empty. Leaderboard entries use current server display names, fetching members when
they are not cached. Users who left are labeled Former member, and lookup
failures are labeled Unavailable member. User IDs are not displayed.

### Detailed walkthrough: daily activity

**Command:** `!stats daily` or `/stats view:daily`.

Use this to see how activity is distributed over calendar dates. It lists
up to 90 dates with matching records, newest first, with command and dice
counts for each UTC date. Zero-activity dates are not inserted into the table.

```text
!stats daily week
!stats daily hqroll me month
!stats daily since:2026-10-01 until:2026-10-31
```

A UTC date can differ from your local calendar date near midnight. Individual
Discord timestamps elsewhere in a report still display in your viewer's
local timezone. `week` is a rolling seven-day interval, not the current
Monday-to-Sunday calendar week; `month` is a rolling thirty-day interval.

### Detailed walkthrough: CSV export

**Command:** `!stats export <game>` or `/stats view:export`.

Use an export for a spreadsheet, backup of a selection, or external analysis.
It creates a UTF-8 CSV attachment with up to 1,000 newest individual dice.
This is a filtered data export, not a full database backup.

```text
!stats export hqroll me week
!stats export roll type:d20 #games
!stats export oqroll since:2026-10-01 until:2026-10-31
```

| CSV column | Meaning |
|---|---|
| `roll_id` | Database command record ID; group matching IDs into one command |
| `time_utc` | Recorded command timestamp in UTC |
| `player_name` | Current server display name of the roller, or a departed/unavailable member label |
| `channel_id` | Discord channel ID where the roll occurred |
| `game` | Canonical game key, such as hqdice or standard |
| `modifier` | Command-level modifier; count it once per roll_id |
| `die_index` | Zero-based position of the individual die within the command |
| `dice_type` | Canonical dice type after resolving aliases |
| `face` | Recorded face ID, normally the image filename or numeric face |
| `values_json` | JSON object containing that die's recorded statistic values |

A five-dice command has five rows sharing `roll_id`. To count commands in a
spreadsheet, count distinct roll IDs rather than CSV rows. To reconstruct a
standard final total, sum its individual `value` fields and add the shared
modifier once. A capped export's oldest command may be incomplete: narrow
the date filters if you need the entire command at that boundary.

Exports carry current player names and channel IDs from the selected server. Use
`/stats view:export private:true` if you do not want the attachment posted
for other channel members. CSV formula-looking cells are prefixed so a
spreadsheet treats them as literal text.

### Detailed walkthrough: help

**Commands:** `!stats help`, `/stats view:help`, or `!help stats`.

Use the first two for the full quick reference. `!help stats` gives a short
pointer to the reports. No game, player, or date filter is needed for help.
The slash help view ignores optional report filters.

### Troubleshooting statistics

| Symptom | What to do |
|---|---|
| No recorded rolls match | Remove player/channel/type filters, try all retained history, and verify logging was enabled when the rolls occurred |
| A familiar face has no numeric values | Historical metadata may have omitted values; add values for future rolls and filter to a consistently annotated date range |
| Totals shrank | A moderator may have enabled retention or shortened its age threshold |
| Plain player/channel name is rejected | Use a real Discord mention or the slash command's picker |
| A dice type is rejected | Choose a game and use one of its current canonical types or aliases |
| Invalid date or conflicting dates | Use YYYY-MM-DD; choose either a duration or since/until, and make the end date no earlier than the start |
| CSV export fails | Give the bot Attach Files permission in the response channel |
| Cards have no pagination | Give the bot Embed Links; without it the report falls back to plain text |
| Buttons no longer respond | They expire after three minutes; request the report again |
| Someone else cannot use your page buttons | Controls belong to the requester; they can run their own statistics command |
| Database is unavailable | Reports need the database; regular rolling can continue without statistics until it recovers |
| Too many historical definition variations | Choose one game and a shorter date range |
| Slash statistics are rate limited | Wait for the configured spam window or ask a moderator about its settings |
| `/stats` is missing | Restart the updated bot, refresh Discord, and check its command registration logs |

Reports are read-only: they do not change setup, delete history, send dddice
rolls, or retrieve records from another server. Prefix reports are public in
the response channel; the slash command is public by default and becomes
private only when `private:true` is selected. No Manage Server permission or
bot admin role is required to view statistics.

Leaderboards show current server display names, never user IDs. Uncached
members are looked up through Discord; departed/unavailable members have
a descriptive placeholder rather than a numeric ID.

All command output uses current server display names rather than Discord
user IDs, including player filters, recent results, leaderboards, and CSV
exports. CSV uses the `player_name` column. The database keeps IDs internally
for accurate matching, but they are never included in user-facing player
labels or exports. Departed/unavailable members get a descriptive label.
Names are resolved when the report is requested and may change between
exports; people with identical display names are not distinguished by ID.
