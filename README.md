# GameBot

A Discord dice bot with metadata-driven board game dice, standard dice with
modifiers, MariaDB roll history, statistics reports, private server setup,
and optional dddice forwarding.

Supported sets include HeroQuest combat and movement, Space Crusade,
Descent, DOOM, Deep Rock Galactic, and OrcQuest. Dice definitions and aliases
live in `dice.json` and reload automatically.

## Getting started

1. Install Python and create a virtual environment.
2. Install `requirements.txt`.
3. Copy `.env.example` to `.env` and supply Discord/database credentials.
4. Generate and preserve an integration encryption key as documented.
5. Run `python init_database.py`, then `python gamebot.py`.

Read [INSTRUCTIONS.md](INSTRUCTIONS.md) for Discord permissions, hosting,
private setup, administrator roles, integrations, and detailed statistics.
See [STATISTICS.md](STATISTICS.md) for the statistics quick reference and
[DATABASE_SETUP.md](DATABASE_SETUP.md) for database details.

```text
!help
!roll 2d6 + 3
!hqroll 3
!rollColor
!stats
```

Only one instance should run for a given Discord token. Never commit `.env`
or share API/encryption keys. Required image assets are included; generated
roll output images and local environments are excluded.

## Tests

```text
python -m unittest discover -s tests -q
```
