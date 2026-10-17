# Dice statistics guide

Statistics are available to ordinary server members. They never read another
server's history. Run `!stats` for a friendly overview or use `/stats` for
Discord's guided command fields. `!stats help` lists reports and examples.

## Quick start

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

## Reports

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

## Filters: combine them in any order

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

## Guided slash command

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

## Understanding the numbers

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

## CSV exports and limits

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

## Deployment

Restart the bot after updating this code to register `/stats` in connected
servers. Existing database tables are reused; no history migration or
schema change is required for these reports. Refresh Discord if the command
picker is stale. The bot needs Embed Links for the report cards and Attach
Files for CSV exports.

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
# Shared outcomes across dice variants

Game-wide face and comparison reports combine matching outcomes across dice
variants. For example, HeroQuest skull faces from white, black, and green dice
appear in one skull row. Percentages use all selected dice for that game;
expected frequencies are weighted by the variants actually rolled.

Use `!stats faces hqroll type:black` to inspect a specific variant. Variant
names appear once in these labels. Double-symbol faces remain separate faces;
`!stats values hqroll` and the game summary count their full symbol values
across all colors. Recorded dice types and raw CSV exports are preserved.

