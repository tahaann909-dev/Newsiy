"""
================================================================================
  DISCORD SECURITY & UTILITY BOT  -  SINGLE FILE EDITION
================================================================================

  Prefix: "+"   (changeable per server with +setprefix)

  QUICK START (PyCharm)
  ---------------------
   1. pip install discord.py aiosqlite python-dotenv
   2. Create a file named  .env  next to this script containing:
          DISCORD_TOKEN=your_token_here
      (or just paste your token into TOKEN below)
   3. Discord Developer Portal -> your app -> Bot -> Privileged Gateway Intents:
          [x] SERVER MEMBERS INTENT
          [x] MESSAGE CONTENT INTENT
      The bot will not work without both of these.
   4. Run this file.
   5. In your server: +setup     then     +permcheck

  WHAT IS INSIDE
  --------------
   * Anti-raid   : join-flood detection, account-age screening, auto lockdown
   * Automod     : spam, duplicates, mass mentions, invites, zalgo, caps
   * Anti-nuke   : strips roles on mass channel deletion
   * Tickets     : dropdown panel, persistent buttons, HTML transcripts
   * Moderation  : ban/tempban/softban/kick/mute/warn/purge/lock/nuke/roles
   * Cases       : every action logged and searchable per user
   * Welcome     : join & leave messages, placeholders, autorole, DM welcome
   * Stats       : -u profile card, leaderboards, achievements
   * Fun         : consent-gated claim, 8ball, ship, poll, roll, remind
   * Scheduler   : temp bans/mutes expire correctly even after a restart

  NOTE ON  +ls
  ------------
   +ls is an alias of +claim. It renames the target to "soumise de <you>" exactly
   as intended, but it sends them an Accept / No thanks button first and only
   renames them if they accept. +uncollar undoes it at any time.
   Without that gate the command is a bullying tool: whoever is being picked on
   gets renamed to somebody's property on demand, over and over, and your mods
   spend the week resetting nicknames. The button costs people who are in on the
   joke two seconds. Change the label freely:  +claim @user chaton

================================================================================
"""

import asyncio
import datetime
import html as htmllib
import io
import json
import logging
import os
import platform
import random
import re
import sys
import time
import traceback
from collections import defaultdict, deque

import aiosqlite
import discord
from discord.ext import commands, tasks

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")


# ==============================================================================
#  SECTION 1 - CONFIGURATION
#  Everything you might want to tweak lives here.
# ==============================================================================


# ---------------------------------------------------------------- credentials
# Put your token in a .env file or an environment variable. NEVER hardcode it
# and never commit it to git.
TOKEN = os.getenv("DISCORD_TOKEN", "")

# ---------------------------------------------------------------- basics
PREFIX = "+"           # commandes de base : clear, ping, profil...
ELEVATED_PREFIX = "&"  # commandes de rang supérieur : blacklist, sanctions...
DB_PATH = "data/bot.sqlite3"
OWNER_IDS = {  # users who bypass every permission check
    # 123456789012345678,
}

# ---------------------------------------------------------------- appearance
COLOR_PRIMARY = 0x2B2D31   # dark, se fond dans le theme sombre (minimaliste)
COLOR_SUCCESS = 0x57F287   # green
COLOR_WARN = 0xFEE75C      # yellow
COLOR_ERROR = 0xED4245     # red
COLOR_MUTED = 0x2B2D31     # dark

EMOJI = {
    "ok": "\u2705",
    "no": "\u274c",
    "warn": "\u26a0\ufe0f",
    "shield": "\U0001f6e1\ufe0f",
    "ticket": "\U0001f3ab",
    "wave": "\U0001f44b",
    "hammer": "\U0001f528",
    "mute": "\U0001f507",
    "clock": "\U0001f552",
    "star": "\u2b50",
    "chart": "\U0001f4ca",
    "lock": "\U0001f512",
    "unlock": "\U0001f513",
    "boom": "\U0001f4a5",
    "crown": "\U0001f451",
}

# ---------------------------------------------------------------- anti-raid
# These are *defaults*. Each guild can override them with -antiraid set.
ANTIRAID_DEFAULTS = {
    "enabled": 1,
    # join-flood detection
    "join_threshold": 8,        # this many joins...
    "join_window": 10,          # ...within this many seconds = raid
    "min_account_age_days": 3,  # les comptes plus récents sont suspects
    # message-spam detection
    "msg_threshold": 30,         # this many messages...
    "msg_window": 7,            # ...in this many seconds = spam
    "dupe_threshold": 4,        # identical messages in a row
    "mention_limit": 6,         # mass-mention ceiling per message
    # what to do
    "raid_action": "lockdown",  # lockdown | kick | ban | alert
    "spam_action": "mute",      # mute | kick | ban | delete
    "mute_minutes": 10,
    "lockdown_minutes": 15,
    "log_channel": None,
    "alert_role": None,
    "quarantine_role": None,
}

TICKET_DEFAULTS = {
    "category": None,
    "staff_role": None,
    "log_channel": None,
    "transcript": 1,
    "max_open_per_user": 2,
    "ping_staff": 1,
}

WELCOME_DEFAULTS = {
    "welcome_channel": None,
    "welcome_message": "{mention} vient d'arriver sur **{server}** ! Nous sommes maintenant {count}.",
    "goodbye_channel": None,
    "goodbye_message": "**{user}** a quitté le serveur. Nous sommes maintenant {count}.",
    "autorole": None,
    "dm_welcome": 0,
    "dm_message": "Salut {user}, bienvenue sur {server} ! Lis les règles et amuse-toi bien.",
}

# ---------------------------------------------------------------- misc
COOLDOWN_RATE = 3
COOLDOWN_PER = 8.0

# ---------------------------------------------------------------- nettoyage auto
# Les réponses du bot aux commandes s'effacent après ce délai (en secondes).
# Mets None pour désactiver et garder toutes les réponses.
AUTO_DELETE_SECONDS = 30
# Supprimer aussi le message de commande de l'utilisateur ("+ban @x", etc.)
DELETE_INVOKING_MESSAGE = True
DELETE_INVOKING_DELAY = 3

# Words that will be auto-flagged. Keep it light; the automod is more useful
# as a scaffold you extend than as a shipped blocklist.
DEFAULT_BLOCKED_PATTERNS = [
    r"discord\.gg/\w+",
    r"discordapp\.com/invite/\w+",
]


# ------------------------------------------------------------------------------
# Because this is a single file, the original `config.X` and `h.X` references
# from the multi-file version resolve to this same module. Nothing to change.
# ------------------------------------------------------------------------------
config = h = sys.modules[__name__]




# ==============================================================================
#  SECTION 2 - HELPERS
# ==============================================================================




# --------------------------------------------------------------------- time

DURATION_RE = re.compile(
    r"(?:(?P<weeks>\d+)\s*w)?"
    r"(?:(?P<days>\d+)\s*d)?"
    r"(?:(?P<hours>\d+)\s*h)?"
    r"(?:(?P<minutes>\d+)\s*m)?"
    r"(?:(?P<seconds>\d+)\s*s)?",
    re.IGNORECASE,
)


def parse_duration(text: str) -> int | None:
    """
    '1h30m' -> 5400.  '2d' -> 172800.  '45' -> 45 (bare numbers = seconds).
    Returns None if nothing parseable was found.
    """
    if not text:
        return None
    text = text.strip().replace(" ", "")
    if text.isdigit():
        return int(text)
    m = DURATION_RE.fullmatch(text)
    if not m or not any(m.groupdict().values()):
        return None
    parts = {k: int(v) for k, v in m.groupdict().items() if v}
    total = (
        parts.get("weeks", 0) * 604800
        + parts.get("days", 0) * 86400
        + parts.get("hours", 0) * 3600
        + parts.get("minutes", 0) * 60
        + parts.get("seconds", 0)
    )
    return total or None


def human_duration(seconds: int) -> str:
    if seconds <= 0:
        return "0s"
    units = [("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]
    out = []
    for label, size in units:
        if seconds >= size:
            qty, seconds = divmod(seconds, size)
            out.append(f"{qty}{label}")
    return " ".join(out[:3])


def ts(dt: datetime.datetime | int, style: str = "R") -> str:
    """Discord relative/absolute timestamp markup."""
    if isinstance(dt, datetime.datetime):
        dt = int(dt.timestamp())
    return f"<t:{int(dt)}:{style}>"


def now() -> int:
    return int(time.time())


# --------------------------------------------------------------------- embeds

def base_embed(title=None, description=None, color=config.COLOR_PRIMARY) -> discord.Embed:
    # Interface minimaliste : pas de timestamp, couleur sombre neutre.
    return discord.Embed(title=title, description=description, color=color)


def ok_embed(description, title=None):
    # Minimaliste : texte brut, fine bordure verte, pas d'emoji.
    return base_embed(title, description, config.COLOR_SUCCESS)


def err_embed(description, title=None):
    return base_embed(title, description, config.COLOR_ERROR)


def warn_embed(description, title=None):
    return base_embed(title, description, config.COLOR_WARN)


def progress_bar(value: int, total: int, length: int = 16) -> str:
    if total <= 0:
        total = 1
    filled = int(length * min(value, total) / total)
    return "\u2588" * filled + "\u2591" * (length - filled)


# --------------------------------------------------------------------- checks

def is_owner_or(**perms):
    """Vérification des permissions that owners in config always pass."""
    async def predicate(ctx: commands.Context):
        if ctx.author.id in config.OWNER_IDS:
            return True
        if ctx.guild is None:
            return False
        if ctx.author.id == ctx.guild.owner_id:
            return True
        has = ctx.author.guild_permissions
        return all(getattr(has, name, False) == value for name, value in perms.items())
    return commands.check(predicate)


def hierarchy_ok(actor: discord.Member, target: discord.Member) -> tuple[bool, str]:
    """
    Returns (allowed, reason_if_not). Prevents moderators from acting on people
    at or above their own role position, and protects the guild owner.
    """
    if actor.id == target.id:
        return False, "Tu ne peux pas l'utiliser sur toi-même."
    if target.id == actor.guild.owner_id:
        return False, "C'est le propriétaire du serveur."
    if actor.id == actor.guild.owner_id:
        return True, ""
    if target.top_role >= actor.top_role:
        return False, "Le rôle le plus haut de ce membre est égal ou supérieur au tien."
    return True, ""


def bot_can_act(me: discord.Member, target: discord.Member) -> tuple[bool, str]:
    if target.top_role >= me.top_role:
        return False, "Mon rôle n'est pas assez haut pour agir sur ce membre."
    return True, ""


# --------------------------------------------------------------------- misc

def clean(text: str, limit: int = 1000) -> str:
    """Strip mass mentions and truncate."""
    text = (text or "").replace("@everyone", "@\u200beveryone").replace(
        "@here", "@\u200bhere"
    )
    return text[:limit]


def format_user(user) -> str:
    return f"{user} (`{user.id}`)"


async def safe_dm(user: discord.abc.User, embed: discord.Embed) -> bool:
    try:
        await user.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


def chunk(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


async def resolve_member(guild, texte):
    """
    Résout un membre depuis une mention (<@123>) ou un ID brut.
    Interroge l'API si le membre n'est pas en cache (indispensable sur les gros
    serveurs où tout n'est pas mis en cache). Renvoie (membre, erreur_ou_None).
    """
    uid = str(texte).strip().strip("<@!>")
    if not uid.isdigit():
        return None, "Donne une mention ou un ID valide."
    membre = guild.get_member(int(uid))
    if membre is not None:
        return membre, None
    try:
        membre = await guild.fetch_member(int(uid))
        return membre, None
    except discord.NotFound:
        return None, "Ce membre n'est pas sur le serveur."
    except discord.HTTPException:
        return None, "ID introuvable."


# ==============================================================================
#  SECTION 3 - DATABASE
# ==============================================================================




SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id        INTEGER PRIMARY KEY,
    prefix          TEXT    DEFAULT '-',
    mod_log         INTEGER,
    mute_role       INTEGER,
    created_at      INTEGER
);

CREATE TABLE IF NOT EXISTS antiraid (
    guild_id            INTEGER PRIMARY KEY,
    enabled             INTEGER DEFAULT 1,
    join_threshold      INTEGER DEFAULT 8,
    join_window         INTEGER DEFAULT 10,
    min_account_age_days INTEGER DEFAULT 3,
    msg_threshold       INTEGER DEFAULT 30,
    msg_window          INTEGER DEFAULT 7,
    dupe_threshold      INTEGER DEFAULT 4,
    mention_limit       INTEGER DEFAULT 6,
    raid_action         TEXT    DEFAULT 'lockdown',
    spam_action         TEXT    DEFAULT 'mute',
    mute_minutes        INTEGER DEFAULT 10,
    lockdown_minutes    INTEGER DEFAULT 15,
    log_channel         INTEGER,
    alert_role          INTEGER,
    quarantine_role     INTEGER
);

CREATE TABLE IF NOT EXISTS tickets_config (
    guild_id            INTEGER PRIMARY KEY,
    category            INTEGER,
    staff_role          INTEGER,
    log_channel         INTEGER,
    transcript          INTEGER DEFAULT 1,
    max_open_per_user   INTEGER DEFAULT 2,
    ping_staff          INTEGER DEFAULT 1,
    panel_message       INTEGER
);

CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    owner_id    INTEGER NOT NULL,
    topic       TEXT,
    claimed_by  INTEGER,
    open        INTEGER DEFAULT 1,
    opened_at   INTEGER,
    closed_at   INTEGER,
    closed_by   INTEGER
);

CREATE TABLE IF NOT EXISTS welcome (
    guild_id        INTEGER PRIMARY KEY,
    welcome_channel INTEGER,
    welcome_message TEXT,
    goodbye_channel INTEGER,
    goodbye_message TEXT,
    autorole        INTEGER,
    dm_welcome      INTEGER DEFAULT 0,
    dm_message      TEXT
);

CREATE TABLE IF NOT EXISTS cases (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    mod_id      INTEGER NOT NULL,
    action      TEXT NOT NULL,
    reason      TEXT,
    duration    INTEGER,
    created_at  INTEGER
);

CREATE TABLE IF NOT EXISTS temp_actions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    action      TEXT NOT NULL,      -- 'mute' | 'ban' | 'quarantine'
    expires_at  INTEGER NOT NULL,
    payload     TEXT,               -- json, e.g. roles removed on mute
    done        INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS stats (
    guild_id        INTEGER NOT NULL,
    user_id         INTEGER NOT NULL,
    messages        INTEGER DEFAULT 0,
    characters      INTEGER DEFAULT 0,
    commands        INTEGER DEFAULT 0,
    attachments     INTEGER DEFAULT 0,
    reactions_given INTEGER DEFAULT 0,
    voice_seconds   INTEGER DEFAULT 0,
    first_seen      INTEGER,
    last_seen       INTEGER,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS command_usage (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    command     TEXT NOT NULL,
    uses        INTEGER DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, command)
);

CREATE TABLE IF NOT EXISTS mod_notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    mod_id      INTEGER,
    note        TEXT,
    created_at  INTEGER
);

CREATE TABLE IF NOT EXISTS afk (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    reason      TEXT,
    since       INTEGER,
    old_nick    TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS tags (
    guild_id    INTEGER NOT NULL,
    name        TEXT NOT NULL,
    content     TEXT,
    owner_id    INTEGER,
    uses        INTEGER DEFAULT 0,
    created_at  INTEGER,
    PRIMARY KEY (guild_id, name)
);

CREATE TABLE IF NOT EXISTS giveaways (
    message_id  INTEGER PRIMARY KEY,
    channel_id  INTEGER NOT NULL,
    guild_id    INTEGER NOT NULL,
    host_id     INTEGER,
    prize       TEXT,
    winners     INTEGER DEFAULT 1,
    ends_at     INTEGER,
    ended       INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sticky (
    channel_id  INTEGER PRIMARY KEY,
    guild_id    INTEGER NOT NULL,
    content     TEXT,
    last_id     INTEGER
);

CREATE TABLE IF NOT EXISTS media_channels (
    channel_id  INTEGER PRIMARY KEY,
    guild_id    INTEGER NOT NULL,
    mute_minutes INTEGER DEFAULT 10
);

CREATE TABLE IF NOT EXISTS stat_channels (
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    kind        TEXT NOT NULL,      -- members|online|voice|bots|boosts|humans
    template    TEXT,               -- ex: "\U0001f465 • Membres : {count}"
    PRIMARY KEY (channel_id)
);

CREATE TABLE IF NOT EXISTS log_config (
    guild_id        INTEGER PRIMARY KEY,
    log_text        INTEGER,        -- messages supprimés / édités
    log_mod         INTEGER,        -- bans / kicks / mutes / rôles
    log_voice       INTEGER,        -- arrivées / départs / déplacements vocaux
    log_join        INTEGER,        -- arrivées / départs de membres
    enabled         INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS rules (
    guild_id    INTEGER PRIMARY KEY,
    channel_id  INTEGER,
    message_id  INTEGER,
    role_id     INTEGER,
    content     TEXT,
    accepted    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS hardbans (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    mod_id      INTEGER,
    reason      TEXT,
    name        TEXT,           -- pseudo au moment du hardban, pour la détection d'alt
    created_at  INTEGER,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS hardban_config (
    guild_id        INTEGER PRIMARY KEY,
    autoban_alts    INTEGER DEFAULT 1,   -- bannir auto les alts suspects
    max_account_age INTEGER DEFAULT 7,   -- compte plus jeune que X jours = suspect
    log_channel     INTEGER
);

CREATE TABLE IF NOT EXISTS bot_blacklist (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    reason      TEXT,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS automod_whitelist (
    guild_id    INTEGER NOT NULL,
    role_id     INTEGER NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS tempvoice_config (
    guild_id        INTEGER PRIMARY KEY,
    hub_channel     INTEGER,
    category        INTEGER,
    name_template   TEXT DEFAULT 'Salon de {user}',
    default_limit   INTEGER DEFAULT 0,
    send_panel      INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS temp_voice (
    channel_id  INTEGER PRIMARY KEY,
    guild_id    INTEGER NOT NULL,
    owner_id    INTEGER NOT NULL,
    created_at  INTEGER
);

CREATE TABLE IF NOT EXISTS jails (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    roles       TEXT,               -- json list of role ids taken away
    mod_id      INTEGER,
    reason      TEXT,
    jailed_at   INTEGER,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS collars (
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    owner_id    INTEGER NOT NULL,
    old_nick    TEXT,
    created_at  INTEGER,
    PRIMARY KEY (guild_id, user_id)
);


CREATE TABLE IF NOT EXISTS selfroles (
    guild_id    INTEGER NOT NULL,
    role_id     INTEGER NOT NULL,
    label       TEXT,
    emoji       TEXT,
    description TEXT,
    added_at    INTEGER,
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS selfrole_panel (
    guild_id    INTEGER PRIMARY KEY,
    channel_id  INTEGER,
    message_id  INTEGER,
    title       TEXT,
    description TEXT,
    placeholder TEXT,
    multiple    INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_cases_user ON cases(guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_temp_pending ON temp_actions(done, expires_at);
CREATE INDEX IF NOT EXISTS idx_tickets_owner ON tickets(guild_id, owner_id, open);
"""


class Database:
    def __init__(self, path: str = config.DB_PATH):
        self.path = path
        self.conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------ lifecycle
    async def connect(self):
        self.conn = await aiosqlite.connect(self.path)
        self.conn.row_factory = aiosqlite.Row
        await self.conn.executescript(SCHEMA)
        await self.conn.commit()
        await self.migrate()

    async def migrate(self):
        """
        Add columns that were introduced after the first release.
        SQLite has no 'ADD COLUMN IF NOT EXISTS', so we inspect the table first.
        Safe to run on every startup.
        """
        wanted = {
            "guild_settings": {
                "jail_role": "INTEGER",
                "jail_channel": "INTEGER",
            },
            "welcome": {
                "welcome_image": "TEXT",
                "goodbye_image": "TEXT",
            },
        }
        for table, columns in wanted.items():
            existing = {
                r["name"] for r in await self.fetchall(f"PRAGMA table_info({table})")
            }
            for name, kind in columns.items():
                if name not in existing:
                    await self.conn.execute(
                        f"ALTER TABLE {table} ADD COLUMN {name} {kind}"
                    )
        # Relève l'ancien seuil anti-flood (7) vers le nouveau (30) sur les
        # serveurs déjà configurés, sans écraser un réglage volontairement élevé.
        await self.conn.execute(
            "UPDATE antiraid SET msg_threshold=30 WHERE msg_threshold < 30"
        )
        await self.conn.execute(
            "UPDATE antiraid SET msg_window=7 WHERE msg_window < 7"
        )
        await self.conn.commit()

    async def close(self):
        if self.conn:
            await self.conn.close()

    # ------------------------------------------------------------ helpers
    async def fetchone(self, q, args=()):
        async with self.conn.execute(q, args) as cur:
            return await cur.fetchone()

    async def fetchall(self, q, args=()):
        async with self.conn.execute(q, args) as cur:
            return await cur.fetchall()

    async def execute(self, q, args=()):
        await self.conn.execute(q, args)
        await self.conn.commit()

    async def _ensure_row(self, table: str, guild_id: int):
        await self.conn.execute(
            f"INSERT OR IGNORE INTO {table} (guild_id) VALUES (?)", (guild_id,)
        )
        await self.conn.commit()

    # ------------------------------------------------------------ settings
    async def guild_settings(self, guild_id: int):
        await self._ensure_row("guild_settings", guild_id)
        return await self.fetchone(
            "SELECT * FROM guild_settings WHERE guild_id=?", (guild_id,)
        )

    async def set_guild(self, guild_id: int, key: str, value):
        await self._ensure_row("guild_settings", guild_id)
        await self.execute(
            f"UPDATE guild_settings SET {key}=? WHERE guild_id=?", (value, guild_id)
        )

    async def antiraid(self, guild_id: int):
        await self._ensure_row("antiraid", guild_id)
        return await self.fetchone("SELECT * FROM antiraid WHERE guild_id=?", (guild_id,))

    async def set_antiraid(self, guild_id: int, key: str, value):
        await self._ensure_row("antiraid", guild_id)
        await self.execute(
            f"UPDATE antiraid SET {key}=? WHERE guild_id=?", (value, guild_id)
        )

    async def tickets_config(self, guild_id: int):
        await self._ensure_row("tickets_config", guild_id)
        return await self.fetchone(
            "SELECT * FROM tickets_config WHERE guild_id=?", (guild_id,)
        )

    async def set_ticket(self, guild_id: int, key: str, value):
        await self._ensure_row("tickets_config", guild_id)
        await self.execute(
            f"UPDATE tickets_config SET {key}=? WHERE guild_id=?", (value, guild_id)
        )

    async def welcome(self, guild_id: int):
        row = await self.fetchone("SELECT * FROM welcome WHERE guild_id=?", (guild_id,))
        if row is None:
            d = config.WELCOME_DEFAULTS
            await self.execute(
                "INSERT INTO welcome (guild_id, welcome_message, goodbye_message, dm_message)"
                " VALUES (?,?,?,?)",
                (guild_id, d["welcome_message"], d["goodbye_message"], d["dm_message"]),
            )
            row = await self.fetchone(
                "SELECT * FROM welcome WHERE guild_id=?", (guild_id,)
            )
        return row

    async def set_welcome(self, guild_id: int, key: str, value):
        await self.welcome(guild_id)
        await self.execute(
            f"UPDATE welcome SET {key}=? WHERE guild_id=?", (value, guild_id)
        )

    # ------------------------------------------------------------ cases
    async def add_case(self, guild_id, user_id, mod_id, action, reason, duration=None):
        cur = await self.conn.execute(
            "INSERT INTO cases (guild_id,user_id,mod_id,action,reason,duration,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (guild_id, user_id, mod_id, action, reason, duration, int(time.time())),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def user_cases(self, guild_id, user_id, limit=25):
        return await self.fetchall(
            "SELECT * FROM cases WHERE guild_id=? AND user_id=?"
            " ORDER BY id DESC LIMIT ?",
            (guild_id, user_id, limit),
        )

    async def case_count(self, guild_id, user_id):
        row = await self.fetchone(
            "SELECT COUNT(*) c FROM cases WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )
        return row["c"] if row else 0

    # ------------------------------------------------------------ temp actions
    async def schedule(self, guild_id, user_id, action, expires_at, payload=None):
        await self.execute(
            "INSERT INTO temp_actions (guild_id,user_id,action,expires_at,payload)"
            " VALUES (?,?,?,?,?)",
            (guild_id, user_id, action, expires_at, json.dumps(payload or {})),
        )

    async def due_actions(self, now: int):
        return await self.fetchall(
            "SELECT * FROM temp_actions WHERE done=0 AND expires_at<=?", (now,)
        )

    async def complete_action(self, action_id: int):
        await self.execute("UPDATE temp_actions SET done=1 WHERE id=?", (action_id,))

    async def cancel_actions(self, guild_id, user_id, action):
        await self.execute(
            "UPDATE temp_actions SET done=1 WHERE guild_id=? AND user_id=? AND action=? AND done=0",
            (guild_id, user_id, action),
        )

    # ------------------------------------------------------------ stats
    async def bump_stat(self, guild_id, user_id, field, amount=1):
        now = int(time.time())
        await self.conn.execute(
            "INSERT INTO stats (guild_id,user_id,first_seen,last_seen) VALUES (?,?,?,?)"
            " ON CONFLICT(guild_id,user_id) DO NOTHING",
            (guild_id, user_id, now, now),
        )
        await self.conn.execute(
            f"UPDATE stats SET {field}={field}+?, last_seen=? WHERE guild_id=? AND user_id=?",
            (amount, now, guild_id, user_id),
        )
        await self.conn.commit()

    async def get_stats(self, guild_id, user_id):
        row = await self.fetchone(
            "SELECT * FROM stats WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )
        return row

    async def bump_command(self, guild_id, user_id, command):
        await self.conn.execute(
            "INSERT INTO command_usage (guild_id,user_id,command,uses) VALUES (?,?,?,1)"
            " ON CONFLICT(guild_id,user_id,command) DO UPDATE SET uses=uses+1",
            (guild_id, user_id, command),
        )
        await self.conn.commit()

    async def top_commands(self, guild_id, user_id, limit=5):
        return await self.fetchall(
            "SELECT command, uses FROM command_usage WHERE guild_id=? AND user_id=?"
            " ORDER BY uses DESC LIMIT ?",
            (guild_id, user_id, limit),
        )

    async def total_commands(self, guild_id, user_id):
        row = await self.fetchone(
            "SELECT COALESCE(SUM(uses),0) t FROM command_usage WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )
        return row["t"] if row else 0

    async def leaderboard(self, guild_id, field="messages", limit=10):
        return await self.fetchall(
            f"SELECT user_id, {field} v FROM stats WHERE guild_id=?"
            f" ORDER BY {field} DESC LIMIT ?",
            (guild_id, limit),
        )

    async def rank_of(self, guild_id, user_id, field="messages"):
        row = await self.fetchone(
            f"SELECT COUNT(*)+1 r FROM stats WHERE guild_id=? AND {field} >"
            f" (SELECT {field} FROM stats WHERE guild_id=? AND user_id=?)",
            (guild_id, guild_id, user_id),
        )
        return row["r"] if row else 1

    # ------------------------------------------------------------ tickets
    async def open_ticket(self, guild_id, channel_id, owner_id, topic):
        cur = await self.conn.execute(
            "INSERT INTO tickets (guild_id,channel_id,owner_id,topic,opened_at)"
            " VALUES (?,?,?,?,?)",
            (guild_id, channel_id, owner_id, topic, int(time.time())),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def ticket_by_channel(self, channel_id):
        return await self.fetchone(
            "SELECT * FROM tickets WHERE channel_id=?", (channel_id,)
        )

    async def open_count(self, guild_id, owner_id):
        row = await self.fetchone(
            "SELECT COUNT(*) c FROM tickets WHERE guild_id=? AND owner_id=? AND open=1",
            (guild_id, owner_id),
        )
        return row["c"] if row else 0

    async def close_ticket(self, channel_id, closed_by):
        await self.execute(
            "UPDATE tickets SET open=0, closed_at=?, closed_by=? WHERE channel_id=?",
            (int(time.time()), closed_by, channel_id),
        )

    async def claim_ticket(self, channel_id, mod_id):
        await self.execute(
            "UPDATE tickets SET claimed_by=? WHERE channel_id=?", (mod_id, channel_id)
        )

    # ------------------------------------------------------------ salons média uniquement
    async def add_media_channel(self, channel_id, guild_id, mute_minutes):
        await self.execute(
            "INSERT OR REPLACE INTO media_channels (channel_id,guild_id,mute_minutes)"
            " VALUES (?,?,?)",
            (channel_id, guild_id, mute_minutes),
        )

    async def get_media_channel(self, channel_id):
        return await self.fetchone(
            "SELECT * FROM media_channels WHERE channel_id=?", (channel_id,)
        )

    async def remove_media_channel(self, channel_id):
        await self.execute(
            "DELETE FROM media_channels WHERE channel_id=?", (channel_id,)
        )

    async def all_media_channels(self, guild_id):
        return await self.fetchall(
            "SELECT * FROM media_channels WHERE guild_id=?", (guild_id,)
        )

    # ------------------------------------------------------------ salons compteurs
    async def add_stat_channel(self, guild_id, channel_id, kind, template):
        await self.execute(
            "INSERT OR REPLACE INTO stat_channels (guild_id,channel_id,kind,template)"
            " VALUES (?,?,?,?)",
            (guild_id, channel_id, kind, template),
        )

    async def stat_channels(self, guild_id):
        return await self.fetchall(
            "SELECT * FROM stat_channels WHERE guild_id=?", (guild_id,)
        )

    async def all_stat_channels(self):
        return await self.fetchall("SELECT * FROM stat_channels")

    async def remove_stat_channel(self, channel_id):
        await self.execute(
            "DELETE FROM stat_channels WHERE channel_id=?", (channel_id,)
        )

    # ------------------------------------------------------------ logs
    async def log_config(self, guild_id):
        await self._ensure_row("log_config", guild_id)
        return await self.fetchone("SELECT * FROM log_config WHERE guild_id=?", (guild_id,))

    async def set_log(self, guild_id, key, value):
        await self._ensure_row("log_config", guild_id)
        await self.execute(
            f"UPDATE log_config SET {key}=? WHERE guild_id=?", (value, guild_id)
        )

    # ------------------------------------------------------------ règlement
    async def rules(self, guild_id):
        await self._ensure_row("rules", guild_id)
        return await self.fetchone("SELECT * FROM rules WHERE guild_id=?", (guild_id,))

    async def set_rules(self, guild_id, key, value):
        await self._ensure_row("rules", guild_id)
        await self.execute(
            f"UPDATE rules SET {key}=? WHERE guild_id=?", (value, guild_id)
        )

    async def bump_rules_accepted(self, guild_id):
        await self.execute(
            "UPDATE rules SET accepted=accepted+1 WHERE guild_id=?", (guild_id,)
        )

    # ------------------------------------------------------------ hardban
    async def add_hardban(self, guild_id, user_id, mod_id, reason, name):
        await self.execute(
            "INSERT OR REPLACE INTO hardbans"
            " (guild_id,user_id,mod_id,reason,name,created_at) VALUES (?,?,?,?,?,?)",
            (guild_id, user_id, mod_id, reason, name, int(time.time())),
        )

    async def get_hardban(self, guild_id, user_id):
        return await self.fetchone(
            "SELECT * FROM hardbans WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )

    async def remove_hardban(self, guild_id, user_id):
        await self.execute(
            "DELETE FROM hardbans WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )

    async def all_hardbans(self, guild_id):
        return await self.fetchall(
            "SELECT * FROM hardbans WHERE guild_id=? ORDER BY created_at DESC",
            (guild_id,),
        )

    async def hardban_config(self, guild_id):
        await self._ensure_row("hardban_config", guild_id)
        return await self.fetchone(
            "SELECT * FROM hardban_config WHERE guild_id=?", (guild_id,)
        )

    async def set_hardban_config(self, guild_id, key, value):
        await self._ensure_row("hardban_config", guild_id)
        await self.execute(
            f"UPDATE hardban_config SET {key}=? WHERE guild_id=?", (value, guild_id)
        )

    # ------------------------------------------------------------ notes de modération
    async def add_note(self, guild_id, user_id, mod_id, note):
        cur = await self.conn.execute(
            "INSERT INTO mod_notes (guild_id,user_id,mod_id,note,created_at)"
            " VALUES (?,?,?,?,?)",
            (guild_id, user_id, mod_id, note, int(time.time())),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_notes(self, guild_id, user_id):
        return await self.fetchall(
            "SELECT * FROM mod_notes WHERE guild_id=? AND user_id=? ORDER BY id DESC",
            (guild_id, user_id),
        )

    async def del_note(self, note_id, guild_id):
        await self.execute(
            "DELETE FROM mod_notes WHERE id=? AND guild_id=?", (note_id, guild_id)
        )

    # ------------------------------------------------------------ afk
    async def set_afk(self, guild_id, user_id, reason, old_nick):
        await self.execute(
            "INSERT OR REPLACE INTO afk (guild_id,user_id,reason,since,old_nick)"
            " VALUES (?,?,?,?,?)",
            (guild_id, user_id, reason, int(time.time()), old_nick),
        )

    async def get_afk(self, guild_id, user_id):
        return await self.fetchone(
            "SELECT * FROM afk WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )

    async def remove_afk(self, guild_id, user_id):
        await self.execute(
            "DELETE FROM afk WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )

    # ------------------------------------------------------------ tags
    async def set_tag(self, guild_id, name, content, owner_id):
        await self.execute(
            "INSERT OR REPLACE INTO tags (guild_id,name,content,owner_id,uses,created_at)"
            " VALUES (?,?,?,?,COALESCE((SELECT uses FROM tags WHERE guild_id=? AND name=?),0),?)",
            (guild_id, name, content, owner_id, guild_id, name, int(time.time())),
        )

    async def get_tag(self, guild_id, name):
        return await self.fetchone(
            "SELECT * FROM tags WHERE guild_id=? AND name=?", (guild_id, name)
        )

    async def del_tag(self, guild_id, name):
        await self.execute(
            "DELETE FROM tags WHERE guild_id=? AND name=?", (guild_id, name)
        )

    async def list_tags(self, guild_id):
        return await self.fetchall(
            "SELECT name, uses FROM tags WHERE guild_id=? ORDER BY uses DESC", (guild_id,)
        )

    async def bump_tag(self, guild_id, name):
        await self.execute(
            "UPDATE tags SET uses=uses+1 WHERE guild_id=? AND name=?", (guild_id, name)
        )

    # ------------------------------------------------------------ giveaways
    async def add_giveaway(self, message_id, channel_id, guild_id, host_id,
                           prize, winners, ends_at):
        await self.execute(
            "INSERT OR REPLACE INTO giveaways"
            " (message_id,channel_id,guild_id,host_id,prize,winners,ends_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (message_id, channel_id, guild_id, host_id, prize, winners, ends_at),
        )

    async def get_giveaway(self, message_id):
        return await self.fetchone(
            "SELECT * FROM giveaways WHERE message_id=?", (message_id,)
        )

    async def due_giveaways(self, now):
        return await self.fetchall(
            "SELECT * FROM giveaways WHERE ended=0 AND ends_at<=?", (now,)
        )

    async def end_giveaway(self, message_id):
        await self.execute(
            "UPDATE giveaways SET ended=1 WHERE message_id=?", (message_id,)
        )

    async def active_giveaways(self, guild_id):
        return await self.fetchall(
            "SELECT * FROM giveaways WHERE guild_id=? AND ended=0 ORDER BY ends_at",
            (guild_id,),
        )

    # ------------------------------------------------------------ sticky
    async def set_sticky(self, channel_id, guild_id, content):
        await self.execute(
            "INSERT OR REPLACE INTO sticky (channel_id,guild_id,content,last_id)"
            " VALUES (?,?,?,NULL)",
            (channel_id, guild_id, content),
        )

    async def get_sticky(self, channel_id):
        return await self.fetchone(
            "SELECT * FROM sticky WHERE channel_id=?", (channel_id,)
        )

    async def sticky_last(self, channel_id, message_id):
        await self.execute(
            "UPDATE sticky SET last_id=? WHERE channel_id=?", (message_id, channel_id)
        )

    async def del_sticky(self, channel_id):
        await self.execute("DELETE FROM sticky WHERE channel_id=?", (channel_id,))

    # ------------------------------------------------------------ listes
    async def blacklist_add(self, guild_id, user_id, reason):
        await self.execute(
            "INSERT OR REPLACE INTO bot_blacklist (guild_id,user_id,reason)"
            " VALUES (?,?,?)",
            (guild_id, user_id, reason),
        )

    async def blacklist_remove(self, guild_id, user_id):
        await self.execute(
            "DELETE FROM bot_blacklist WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )

    async def is_blacklisted(self, guild_id, user_id):
        row = await self.fetchone(
            "SELECT 1 FROM bot_blacklist WHERE guild_id=? AND user_id=?",
            (guild_id, user_id),
        )
        return row is not None

    async def blacklist_all(self, guild_id):
        return await self.fetchall(
            "SELECT * FROM bot_blacklist WHERE guild_id=?", (guild_id,)
        )

    async def whitelist_add(self, guild_id, role_id):
        await self.execute(
            "INSERT OR REPLACE INTO automod_whitelist (guild_id,role_id) VALUES (?,?)",
            (guild_id, role_id),
        )

    async def whitelist_remove(self, guild_id, role_id):
        await self.execute(
            "DELETE FROM automod_whitelist WHERE guild_id=? AND role_id=?",
            (guild_id, role_id),
        )

    async def whitelist_all(self, guild_id):
        rows = await self.fetchall(
            "SELECT role_id FROM automod_whitelist WHERE guild_id=?", (guild_id,)
        )
        return [r["role_id"] for r in rows]

    # ------------------------------------------------------------ salons vocaux temporaires
    async def tempvoice_config(self, guild_id: int):
        await self._ensure_row("tempvoice_config", guild_id)
        return await self.fetchone(
            "SELECT * FROM tempvoice_config WHERE guild_id=?", (guild_id,)
        )

    async def set_tempvoice(self, guild_id: int, key: str, value):
        await self._ensure_row("tempvoice_config", guild_id)
        await self.execute(
            f"UPDATE tempvoice_config SET {key}=? WHERE guild_id=?", (value, guild_id)
        )

    async def add_temp_voice(self, channel_id, guild_id, owner_id):
        await self.execute(
            "INSERT OR REPLACE INTO temp_voice (channel_id,guild_id,owner_id,created_at)"
            " VALUES (?,?,?,?)",
            (channel_id, guild_id, owner_id, int(time.time())),
        )

    async def get_temp_voice(self, channel_id):
        return await self.fetchone(
            "SELECT * FROM temp_voice WHERE channel_id=?", (channel_id,)
        )

    async def set_temp_voice_owner(self, channel_id, owner_id):
        await self.execute(
            "UPDATE temp_voice SET owner_id=? WHERE channel_id=?", (owner_id, channel_id)
        )

    async def remove_temp_voice(self, channel_id):
        await self.execute("DELETE FROM temp_voice WHERE channel_id=?", (channel_id,))

    async def all_temp_voice(self, guild_id):
        return await self.fetchall(
            "SELECT * FROM temp_voice WHERE guild_id=?", (guild_id,)
        )

    # ------------------------------------------------------------ jails
    async def add_jail(self, guild_id, user_id, role_ids, mod_id, reason):
        await self.execute(
            "INSERT OR REPLACE INTO jails"
            " (guild_id,user_id,roles,mod_id,reason,jailed_at) VALUES (?,?,?,?,?,?)",
            (guild_id, user_id, json.dumps(role_ids), mod_id, reason, int(time.time())),
        )

    async def get_jail(self, guild_id, user_id):
        return await self.fetchone(
            "SELECT * FROM jails WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )

    async def remove_jail(self, guild_id, user_id):
        await self.execute(
            "DELETE FROM jails WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )

    async def all_jails(self, guild_id):
        return await self.fetchall(
            "SELECT * FROM jails WHERE guild_id=? ORDER BY jailed_at DESC", (guild_id,)
        )

    # ------------------------------------------------------------ collars
    async def set_collar(self, guild_id, user_id, owner_id, old_nick):
        await self.execute(
            "INSERT OR REPLACE INTO collars (guild_id,user_id,owner_id,old_nick,created_at)"
            " VALUES (?,?,?,?,?)",
            (guild_id, user_id, owner_id, old_nick, int(time.time())),
        )

    async def get_collar(self, guild_id, user_id):
        return await self.fetchone(
            "SELECT * FROM collars WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )

    async def remove_collar(self, guild_id, user_id):
        await self.execute(
            "DELETE FROM collars WHERE guild_id=? AND user_id=?", (guild_id, user_id)
        )

    async def collars_of(self, guild_id, owner_id):
        return await self.fetchall(
            "SELECT * FROM collars WHERE guild_id=? AND owner_id=?", (guild_id, owner_id)
        )

    # ------------------------------------------------------------ self-roles
    async def add_selfrole(self, guild_id, role_id, label, emoji, description):
        await self.execute(
            "INSERT OR REPLACE INTO selfroles"
            " (guild_id,role_id,label,emoji,description,added_at)"
            " VALUES (?,?,?,?,?,?)",
            (guild_id, role_id, label, emoji, description, int(time.time())),
        )

    async def remove_selfrole(self, guild_id, role_id):
        await self.execute(
            "DELETE FROM selfroles WHERE guild_id=? AND role_id=?",
            (guild_id, role_id),
        )

    async def selfroles(self, guild_id):
        return await self.fetchall(
            "SELECT * FROM selfroles WHERE guild_id=? ORDER BY added_at",
            (guild_id,),
        )

    async def selfrole_panel(self, guild_id):
        await self._ensure_row("selfrole_panel", guild_id)
        return await self.fetchone(
            "SELECT * FROM selfrole_panel WHERE guild_id=?", (guild_id,)
        )

    async def set_selfrole_panel(self, guild_id, key, value):
        await self._ensure_row("selfrole_panel", guild_id)
        await self.execute(
            f"UPDATE selfrole_panel SET {key}=? WHERE guild_id=?", (value, guild_id)
        )


# ==============================================================================
#  SECTION 4 - MODERATION
# ==============================================================================






class Moderation(commands.Cog):
    """Garder le serveur en un seul morceau."""

    def __init__(self, bot):
        self.bot = bot

    # ================================================================ internals

    async def log_case(self, guild, case_id, action, target, mod, reason,
                       duration=None, color=config.COLOR_WARN):
        row = await self.bot.db.guild_settings(guild.id)
        channel_id = row["mod_log"] if row else None
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        e = h.base_embed(f"Dossier #{case_id} — {action.title()}", color=color)
        e.add_field(name="Membre", value=f"{target.mention}\n`{target.id}`", inline=True)
        e.add_field(name="Modérateur", value=f"{mod.mention}\n`{mod.id}`", inline=True)
        if duration:
            e.add_field(name="Durée", value=h.human_duration(duration), inline=True)
        e.add_field(name="Raison", value=h.clean(reason or "Aucune raison donnée"), inline=False)
        e.set_thumbnail(url=target.display_avatar.url)
        try:
            await channel.send(embed=e)
        except discord.HTTPException:
            pass

    async def notify(self, target, guild, action, reason, duration=None):
        e = h.base_embed(
            f"Tu as été {action} sur {guild.name}",
            color=config.COLOR_ERROR,
        )
        e.add_field(name="Raison", value=h.clean(reason or "Aucune raison donnée"), inline=False)
        if duration:
            e.add_field(name="Durée", value=h.human_duration(duration), inline=False)
        e.set_footer(text="Si tu penses que c'est une erreur, contacte le staff.")
        return await h.safe_dm(target, e)

    async def preflight(self, ctx, member: discord.Member) -> str | None:
        """Renvoie un message d'erreur, ou None si l'action peut se faire."""
        allowed, why = h.hierarchy_ok(ctx.author, member)
        if not allowed:
            return why
        allowed, why = h.bot_can_act(ctx.guild.me, member)
        if not allowed:
            return why
        return None

    async def get_mute_role(self, guild) -> discord.Role | None:
        """
        Fetch (or create) the fallback mute role. Only used when native timeouts
        can't be applied — e.g. durations over 28 days, or a target the bot can't
        time out.
        """
        row = await self.bot.db.guild_settings(guild.id)
        if row and row["mute_role"]:
            role = guild.get_role(row["mute_role"])
            if role:
                return role
        role = discord.utils.get(guild.roles, name="Muet")
        if role is None:
            try:
                role = await guild.create_role(
                    name="Muet",
                    colour=discord.Colour.dark_grey(),
                    reason="Automatic mute role creation",
                )
            except discord.Forbidden:
                return None
            for channel in guild.channels:
                try:
                    await channel.set_permissions(
                        role,
                        send_messages=False,
                        add_reactions=False,
                        speak=False,
                        send_messages_in_threads=False,
                        create_public_threads=False,
                        reason="Mute role setup",
                    )
                except discord.HTTPException:
                    continue
        await self.bot.db.set_guild(guild.id, "mute_role", role.id)
        return role

    # ================================================================ ban family

    @commands.command(name="ban", help="Bannir un membre. -ban @membre 7d spam")
    @commands.guild_only()
    @h.is_owner_or(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx, user: discord.User, *, rest: str = ""):
        duration = None
        reason = rest
        first = rest.split(" ", 1)[0] if rest else ""
        parsed = h.parse_duration(first)
        if parsed:
            duration = parsed
            reason = rest.split(" ", 1)[1] if " " in rest else ""

        member = ctx.guild.get_member(user.id)
        if member:
            problem = await self.preflight(ctx, member)
            if problem:
                return await ctx.reply(embed=h.err_embed(problem), mention_author=False)
            await self.notify(member, ctx.guild, "banni", reason, duration)

        try:
            await ctx.guild.ban(
                user,
                reason=f"{ctx.author} ({ctx.author.id}): {reason or 'aucune raison'}",
                delete_message_days=0,
            )
        except discord.NotFound:
            return await ctx.reply(embed=h.err_embed("Utilisateur introuvable."), mention_author=False)

        case_id = await self.bot.db.add_case(
            ctx.guild.id, user.id, ctx.author.id, "ban", reason, duration
        )
        if duration:
            await self.bot.db.schedule(
                ctx.guild.id, user.id, "ban", h.now() + duration
            )

        e = h.ok_embed(
            f"**{user}** a été banni"
            + (f" pour **{h.human_duration(duration)}**." if duration else ".")
            + f"\nDossier `#{case_id}`"
        )
        await ctx.reply(embed=e, mention_author=False)
        await self.log_case(ctx.guild, case_id, "ban", user, ctx.author, reason,
                            duration, config.COLOR_ERROR)

    @commands.command(name="softban", help="Bannit puis débannit aussitôt pour purger les messages.")
    @commands.guild_only()
    @h.is_owner_or(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def softban(self, ctx, member: discord.Member, *, reason: str = ""):
        problem = await self.preflight(ctx, member)
        if problem:
            return await ctx.reply(embed=h.err_embed(problem), mention_author=False)
        await self.notify(member, ctx.guild, "softban (messages supprimés)", reason)
        await ctx.guild.ban(member, reason=f"softban by {ctx.author}: {reason}",
                            delete_message_days=1)
        await ctx.guild.unban(member, reason="softban release")
        case_id = await self.bot.db.add_case(
            ctx.guild.id, member.id, ctx.author.id, "softban", reason
        )
        await ctx.reply(embed=h.ok_embed(f"Softban de **{member}**. Dossier `#{case_id}`"),
                        mention_author=False)
        await self.log_case(ctx.guild, case_id, "softban", member, ctx.author, reason)

    @commands.command(name="unban", help="Débannir via l'ID du membre.")
    @commands.guild_only()
    @h.is_owner_or(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: int, *, reason: str = ""):
        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=f"{ctx.author}: {reason}")
        except discord.NotFound:
            return await ctx.reply(
                embed=h.err_embed("Ce membre n'est pas banni ici."), mention_author=False
            )
        await self.bot.db.cancel_actions(ctx.guild.id, user_id, "ban")
        case_id = await self.bot.db.add_case(
            ctx.guild.id, user_id, ctx.author.id, "unban", reason
        )
        await ctx.reply(embed=h.ok_embed(f"**{user}** débanni. Dossier `#{case_id}`"),
                        mention_author=False)
        await self.log_case(ctx.guild, case_id, "unban", user, ctx.author, reason,
                            color=config.COLOR_SUCCESS)

    @commands.command(name="kick")
    @commands.guild_only()
    @h.is_owner_or(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx, member: discord.Member, *, reason: str = ""):
        problem = await self.preflight(ctx, member)
        if problem:
            return await ctx.reply(embed=h.err_embed(problem), mention_author=False)
        await self.notify(member, ctx.guild, "expulsé", reason)
        await member.kick(reason=f"{ctx.author}: {reason}")
        case_id = await self.bot.db.add_case(
            ctx.guild.id, member.id, ctx.author.id, "kick", reason
        )
        await ctx.reply(embed=h.ok_embed(f"**{member}** expulsé. Dossier `#{case_id}`"),
                        mention_author=False)
        await self.log_case(ctx.guild, case_id, "kick", member, ctx.author, reason)

    # ================================================================ mutes

    @commands.command(name="mute", aliases=["timeout", "tempmute"],
                      help="+mute @membre 30m comportement perturbateur")
    @commands.guild_only()
    @h.is_owner_or(moderate_members=True)
    async def mute(self, ctx, member: discord.Member, duration: str = "10m", *, reason: str = ""):
        problem = await self.preflight(ctx, member)
        if problem:
            return await ctx.reply(embed=h.err_embed(problem), mention_author=False)

        seconds = h.parse_duration(duration)
        if seconds is None:
            # They probably typed the reason where the duration goes.
            reason = f"{duration} {reason}".strip()
            seconds = 600
        seconds = max(30, min(seconds, 60 * 60 * 24 * 28))

        await self.notify(member, ctx.guild, "rendu muet", reason, seconds)

        used_native = False
        if ctx.guild.me.guild_permissions.moderate_members:
            try:
                until = discord.utils.utcnow() + datetime.timedelta(seconds=seconds)
                await member.timeout(until, reason=f"{ctx.author}: {reason}")
                used_native = True
            except discord.HTTPException:
                used_native = False

        if not used_native:
            role = await self.get_mute_role(ctx.guild)
            if role is None:
                return await ctx.reply(
                    embed=h.err_embed("Je ne peux ni exclure temporairement ni créer un rôle muet ici."),
                    mention_author=False,
                )
            await member.add_roles(role, reason=f"mute by {ctx.author}")
            await self.bot.db.schedule(
                ctx.guild.id, member.id, "mute", h.now() + seconds,
                {"role": role.id},
            )

        case_id = await self.bot.db.add_case(
            ctx.guild.id, member.id, ctx.author.id, "mute", reason, seconds
        )
        e = h.ok_embed(
            f"**{member}** est muet pendant **{h.human_duration(seconds)}**"
            f" (fin {h.ts(h.now() + seconds)}).\nDossier `#{case_id}`"
        )
        await ctx.reply(embed=e, mention_author=False)
        await self.log_case(ctx.guild, case_id, "mute", member, ctx.author, reason, seconds)

    @commands.command(name="unmute", aliases=["untimeout"])
    @commands.guild_only()
    @h.is_owner_or(moderate_members=True)
    async def unmute(self, ctx, member: discord.Member, *, reason: str = ""):
        cleared = False
        if member.is_timed_out():
            try:
                await member.timeout(None, reason=f"{ctx.author}: {reason}")
                cleared = True
            except discord.HTTPException:
                pass
        role = discord.utils.get(member.roles, name="Muet")
        row = await self.bot.db.guild_settings(ctx.guild.id)
        if row and row["mute_role"]:
            role = member.get_role(row["mute_role"]) or role
        if role:
            await member.remove_roles(role, reason=f"unmute by {ctx.author}")
            cleared = True

        await self.bot.db.cancel_actions(ctx.guild.id, member.id, "mute")
        if not cleared:
            return await ctx.reply(embed=h.warn_embed("Ce membre n'était pas muet."),
                                   mention_author=False)
        case_id = await self.bot.db.add_case(
            ctx.guild.id, member.id, ctx.author.id, "unmute", reason
        )
        await ctx.reply(embed=h.ok_embed(f"**{member}** n'est plus muet. Dossier `#{case_id}`"),
                        mention_author=False)
        await self.log_case(ctx.guild, case_id, "unmute", member, ctx.author, reason,
                            color=config.COLOR_SUCCESS)

    # ================================================================ jail

    async def get_jail_role(self, guild) -> discord.Role | None:
        """
        Fetch or build the jail role. Unlike a mute (which only blocks talking),
        jail hides every channel except the jail channel, so the member is stuck
        in one room until staff deal with them.
        """
        row = await self.bot.db.guild_settings(guild.id)
        if row and row["jail_role"]:
            role = guild.get_role(row["jail_role"])
            if role:
                return role

        role = discord.utils.get(guild.roles, name="Prison")
        if role is None:
            try:
                role = await guild.create_role(
                    name="Prison",
                    colour=discord.Colour.from_rgb(60, 60, 65),
                    reason="Automatic jail role creation",
                )
            except discord.Forbidden:
                return None

        # Hide everything from the role.
        for channel in guild.channels:
            try:
                await channel.set_permissions(
                    role,
                    view_channel=False,
                    send_messages=False,
                    speak=False,
                    connect=False,
                    add_reactions=False,
                    reason="Jail role setup",
                )
            except discord.HTTPException:
                continue
            await asyncio.sleep(0.2)

        await self.bot.db.set_guild(guild.id, "jail_role", role.id)
        return role

    async def get_jail_channel(self, guild, role) -> discord.TextChannel | None:
        """The one channel jailed members can still see."""
        row = await self.bot.db.guild_settings(guild.id)
        if row and row["jail_channel"]:
            channel = guild.get_channel(row["jail_channel"])
            if channel:
                return channel

        channel = discord.utils.get(guild.text_channels, name="jail")
        if channel is None:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                role: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                ),
                guild.me: discord.PermissionOverwrite(
                    view_channel=True, send_messages=True
                ),
            }
            try:
                channel = await guild.create_text_channel(
                    "jail",
                    overwrites=overwrites,
                    topic="Tu es en prison. Attends un modérateur.",
                    reason="Jail channel setup",
                )
            except discord.Forbidden:
                return None
        else:
            try:
                await channel.set_permissions(
                    role, view_channel=True, send_messages=True,
                    read_message_history=True, reason="Jail channel setup",
                )
            except discord.HTTPException:
                pass

        await self.bot.db.set_guild(guild.id, "jail_channel", channel.id)
        return channel

    @commands.command(name="jail", help="+jail @membre 2h raison — retire les rôles et enferme dans #jail")
    @commands.guild_only()
    @h.is_owner_or(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def jail(self, ctx, member: discord.Member, duration: str = None, *, reason: str = ""):
        problem = await self.preflight(ctx, member)
        if problem:
            return await ctx.reply(embed=h.err_embed(problem), mention_author=False)

        existing = await self.bot.db.get_jail(ctx.guild.id, member.id)
        if existing:
            return await ctx.reply(
                embed=h.warn_embed(
                    f"**{member}** est déjà emprisonné (depuis {h.ts(existing['jailed_at'])})."
                ),
                mention_author=False,
            )

        seconds = h.parse_duration(duration) if duration else None
        if duration and seconds is None:
            # They typed the reason where the duration goes — treat it as reason.
            reason = f"{duration} {reason}".strip()

        async with ctx.typing():
            role = await self.get_jail_role(ctx.guild)
            if role is None:
                return await ctx.reply(
                    embed=h.err_embed("Je n'ai pas pu créer le rôle de prison — vérifie mes permissions."),
                    mention_author=False,
                )
            channel = await self.get_jail_channel(ctx.guild, role)

            # Only strip roles we can actually give back later.
            removable = [
                r for r in member.roles
                if r != ctx.guild.default_role
                and not r.managed
                and r < ctx.guild.me.top_role
            ]
            kept = [r for r in member.roles
                    if r != ctx.guild.default_role and r not in removable]

            await self.notify(member, ctx.guild, "emprisonné", reason, seconds)

            try:
                await member.edit(
                    roles=kept + [role],
                    reason=f"Jailed by {ctx.author}: {reason or 'aucune raison'}",
                )
            except discord.Forbidden:
                return await ctx.reply(
                    embed=h.err_embed(
                        "Discord a refusé — mon rôle doit être au-dessus du sien."
                    ),
                    mention_author=False,
                )

        await self.bot.db.add_jail(
            ctx.guild.id, member.id, [r.id for r in removable], ctx.author.id, reason
        )
        if seconds:
            await self.bot.db.schedule(
                ctx.guild.id, member.id, "jail", h.now() + seconds, {"role": role.id}
            )

        case_id = await self.bot.db.add_case(
            ctx.guild.id, member.id, ctx.author.id, "jail", reason, seconds
        )

        e = h.ok_embed(
            f"**{member}** a été emprisonné"
            + (f" pour **{h.human_duration(seconds)}** "
               f"(libération {h.ts(h.now() + seconds)})" if seconds else " pour une durée indéterminée")
            + f".\n**{len(removable)}** rôle(s) retirés et sauvegardés.\n"
            f"Dossier `#{case_id}`"
        )
        if channel:
            e.description += f"\nIl ne voit plus que {channel.mention}."
        if kept:
            e.set_footer(text=f"{len(kept)} rôle(s) non touchés (gérés par une intégration ou au-dessus de moi)")
        await ctx.reply(embed=e, mention_author=False)
        await self.log_case(ctx.guild, case_id, "jail", member, ctx.author, reason,
                            seconds, config.COLOR_ERROR)

        if channel:
            try:
                await channel.send(
                    content=member.mention,
                    embed=h.base_embed(
                        "Tu as été emprisonné",
                        f"**Raison :** {h.clean(reason) or 'aucune'}\n"
                        + (f"**Libération :** {h.ts(h.now() + seconds)}\n" if seconds
                           else "**Libération :** quand un modérateur le décidera\n")
                        + "\nExplique-toi ici. Le staff te lira.",
                        config.COLOR_ERROR,
                    ),
                )
            except discord.HTTPException:
                pass

    @commands.command(name="unjail", aliases=["free", "libere"],
                      help="Libérer un membre et lui rendre ses rôles.")
    @commands.guild_only()
    @h.is_owner_or(moderate_members=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unjail(self, ctx, member: discord.Member, *, reason: str = ""):
        row = await self.bot.db.get_jail(ctx.guild.id, member.id)
        if not row:
            return await ctx.reply(embed=h.warn_embed(f"**{member}** n'est pas emprisonné."),
                                   mention_author=False)

        import json as _json
        role_ids = _json.loads(row["roles"] or "[]")
        restore = [
            r for r in (ctx.guild.get_role(i) for i in role_ids)
            if r is not None and r < ctx.guild.me.top_role
        ]
        settings = await self.bot.db.guild_settings(ctx.guild.id)
        jail_role = ctx.guild.get_role(settings["jail_role"]) if settings["jail_role"] else None

        keep = [r for r in member.roles
                if r != ctx.guild.default_role and r != jail_role]
        try:
            await member.edit(
                roles=list(set(keep + restore)),
                reason=f"Unjailed by {ctx.author}: {reason or 'aucune raison'}",
            )
        except discord.Forbidden:
            return await ctx.reply(
                embed=h.err_embed("Je ne peux pas modifier ses rôles — mon rôle est trop bas."),
                mention_author=False,
            )

        await self.bot.db.remove_jail(ctx.guild.id, member.id)
        await self.bot.db.cancel_actions(ctx.guild.id, member.id, "jail")
        case_id = await self.bot.db.add_case(
            ctx.guild.id, member.id, ctx.author.id, "unjail", reason
        )
        served = h.now() - (row["jailed_at"] or h.now())
        await ctx.reply(
            embed=h.ok_embed(
                f"**{member}** libéré après **{h.human_duration(served)}**.\n"
                f"**{len(restore)}** rôle(s) restaurés. Dossier `#{case_id}`"
            ),
            mention_author=False,
        )
        await self.log_case(ctx.guild, case_id, "unjail", member, ctx.author, reason,
                            color=config.COLOR_SUCCESS)

    @commands.command(name="emprisonné", aliases=["jaillist"], help="Lister les membres actuellement emprisonnés.")
    @commands.guild_only()
    @h.is_owner_or(moderate_members=True)
    async def jailed(self, ctx):
        rows = await self.bot.db.all_jails(ctx.guild.id)
        if not rows:
            return await ctx.reply(embed=h.base_embed(description="Personne n'est emprisonné."),
                                   mention_author=False)
        lines = []
        for r in rows[:25]:
            m = ctx.guild.get_member(r["user_id"])
            mod = ctx.guild.get_member(r["mod_id"])
            who = m.mention if m else f"`{r['user_id']}` (a quitté le serveur)"
            by = mod.display_name if mod else "unknown"
            lines.append(
                f"• {who} — {h.ts(r['jailed_at'])} by {by}\n"
                f"  \u21b3 {h.clean(r['reason'] or 'aucune raison', 100)}"
            )
        await ctx.reply(
            embed=h.base_embed(f"Membres emprisonnés ({len(rows)})", "\n".join(lines)[:4000]),
            mention_author=False,
        )

    @commands.command(name="jailsetup",
                      help="Créer/réparer le rôle et le salon de prison, ou pointer vers des existants.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def jailsetup(self, ctx, role: discord.Role = None,
                        channel: discord.TextChannel = None):
        async with ctx.typing():
            if role:
                await self.bot.db.set_guild(ctx.guild.id, "jail_role", role.id)
            if channel:
                await self.bot.db.set_guild(ctx.guild.id, "jail_channel", channel.id)
            jrole = await self.get_jail_role(ctx.guild)
            if jrole is None:
                return await ctx.reply(
                    embed=h.err_embed("Impossible de créer le rôle de prison."),
                    mention_author=False,
                )
            jchannel = await self.get_jail_channel(ctx.guild, jrole)
        await ctx.reply(
            embed=h.ok_embed(
                f"Prison prête.\n**Rôle :** {jrole.mention}\n"
                f"**Salon :** {jchannel.mention if jchannel else '*aucun*'}\n\n"
                f"Les permissions ont été réappliquées sur tous les salons."
            ),
            mention_author=False,
        )

    # ================================================================ warnings

    @commands.command(name="warn")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def warn(self, ctx, member: discord.Member, *, reason: str = ""):
        problem = await self.preflight(ctx, member)
        if problem:
            return await ctx.reply(embed=h.err_embed(problem), mention_author=False)
        case_id = await self.bot.db.add_case(
            ctx.guild.id, member.id, ctx.author.id, "warn", reason
        )
        total = await self.bot.db.case_count(ctx.guild.id, member.id)
        delivered = await self.notify(member, ctx.guild, "averti", reason)
        e = h.ok_embed(
            f"**{member}** averti. Dossier `#{case_id}` — il a maintenant **{total}** "
            f"dossier(s) au total."
            + ("" if delivered else "\n*(MP fermés — il n'a pas été prévenu.)*")
        )
        await ctx.reply(embed=e, mention_author=False)
        await self.log_case(ctx.guild, case_id, "warn", member, ctx.author, reason)

    @commands.command(name="cases", aliases=["history", "modlogs", "warnings", "sanction", "sanctions", "casier"])
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def cases(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        rows = await self.bot.db.user_cases(ctx.guild.id, member.id)
        if not rows:
            return await ctx.reply(
                embed=h.base_embed(description=f"**{member}** a un casier vierge."),
                mention_author=False,
            )
        e = h.base_embed(f"Historique des dossiers — {member}", color=config.COLOR_WARN)
        e.set_thumbnail(url=member.display_avatar.url)
        for row in rows[:15]:
            mod = ctx.guild.get_member(row["mod_id"])
            dur = f" · {h.human_duration(row['duration'])}" if row["duration"] else ""
            e.add_field(
                name=f"#{row['id']} · {row['action']}{dur}",
                value=(
                    f"{h.clean(row['reason'] or 'Aucune raison', 200)}\n"
                    f"by {mod.mention if mod else row['mod_id']} · {h.ts(row['created_at'])}"
                ),
                inline=False,
            )
        e.set_footer(text=f"{len(rows)} dossier(s) affiché(s)")
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="delcase", aliases=["delsanction", "delwarn"])
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def delcase(self, ctx, case_id: int):
        await self.bot.db.execute(
            "DELETE FROM cases WHERE id=? AND guild_id=?", (case_id, ctx.guild.id)
        )
        await ctx.reply(embed=h.ok_embed(f"Dossier `#{case_id}` supprimé."),
                        mention_author=False)

    # ================================================================ purge

    @commands.group(name="purge", aliases=["clear", "prune"], invoke_without_command=True,
                    help="+clear 500  |  -clear all  (vide tout le salon)")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx, amount: str = "10"):
        # ---- "all": clone the channel instead of deleting message by message.
        # Deleting 10k messages through the API takes minutes. Cloning is one
        # API call and is effectively instant, at the cost of a new channel ID.
        if amount.lower() in ("all", "tout", "max", "tout"):
            return await self._clear_all(ctx)

        if not amount.isdigit():
            return await ctx.reply(
                embed=h.err_embed("Donne-moi un nombre, ou `all`."), mention_author=False
            )

        amount = max(1, min(int(amount), 10000))
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        status = None
        if amount > 200:
            status = await ctx.send(
                embed=h.base_embed("Purge", f"Traitement de **{amount:,}** messages...")
            )

        total = 0
        remaining = amount
        while remaining > 0:
            batch = min(remaining, 100)
            try:
                deleted = await ctx.channel.purge(limit=batch, bulk=True)
            except discord.HTTPException:
                break
            if not deleted:
                break  # nothing older left to delete
            total += len(deleted)
            remaining -= len(deleted)
            if status and total % 500 == 0:
                try:
                    await status.edit(
                        embed=h.base_embed("Purge", f"**{total:,}** supprimés pour l'instant...")
                    )
                except discord.HTTPException:
                    pass

        note = ""
        if total < amount:
            note = ("\n*Arrêt anticipé — soit le salon est vide, soit le reste "
                    "a plus de 14 jours. Discord interdit la suppression groupée au-delà ; "
                    "utilise `+clear all` pour un salon aussi ancien.*")

        e = h.ok_embed(f"**{total:,}** messages supprimés.{note}")
        if status:
            await status.edit(embed=e, delete_after=10)
        else:
            await ctx.send(embed=e, delete_after=8)

    async def _clear_all(self, ctx):
        """
        Empty the channel for real: loop bulk-deletes until nothing is left.
        No cloning, so the channel keeps its ID, pins targets and history links.
        """
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        status = await ctx.send(
            embed=h.base_embed("Nettoyage", "Vidage du salon en cours...")
        )

        total = 0
        stalled = 0
        while True:
            try:
                deleted = await ctx.channel.purge(
                    limit=100, bulk=True, check=lambda m: m.id != status.id
                )
            except discord.HTTPException:
                break

            if not deleted:
                # Nothing came back — either we're done, or the remainder is old
                # enough that Discord is refusing. Retry once before giving up.
                stalled += 1
                if stalled >= 2:
                    break
                await asyncio.sleep(1)
                continue

            stalled = 0
            total += len(deleted)

            if total % 300 < len(deleted):
                try:
                    await status.edit(
                        embed=h.base_embed("Nettoyage", f"**{total:,}** supprimés...")
                    )
                except discord.HTTPException:
                    pass

            if total >= 50000:  # hard stop so a runaway loop can't spin forever
                break

        try:
            await status.edit(
                embed=h.ok_embed(f"Salon vidé — **{total:,}** messages supprimés."),
                delete_after=6,
            )
        except discord.HTTPException:
            pass

    @purge.command(name="user")
    @h.is_owner_or(manage_messages=True)
    async def purge_user(self, ctx, member: discord.Member, amount: int = 50):
        amount = max(1, min(amount, 500))
        deleted = await ctx.channel.purge(
            limit=amount, check=lambda m: m.author.id == member.id
        )
        await ctx.send(
            embed=h.ok_embed(f"**{len(deleted)}** messages de {member.mention} supprimés."),
            delete_after=6,
        )

    @purge.command(name="bots")
    @h.is_owner_or(manage_messages=True)
    async def purge_bots(self, ctx, amount: int = 50):
        deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author.bot)
        await ctx.send(embed=h.ok_embed(f"**{len(deleted)}** messages de bots supprimés."),
                       delete_after=6)

    @purge.command(name="links")
    @h.is_owner_or(manage_messages=True)
    async def purge_links(self, ctx, amount: int = 50):
        pat = re.compile(r"https?://")
        deleted = await ctx.channel.purge(
            limit=amount, check=lambda m: bool(pat.search(m.content))
        )
        await ctx.send(embed=h.ok_embed(f"**{len(deleted)}** liens supprimés."),
                       delete_after=6)

    @purge.command(name="contains")
    @h.is_owner_or(manage_messages=True)
    async def purge_contains(self, ctx, word: str, amount: int = 50):
        deleted = await ctx.channel.purge(
            limit=amount, check=lambda m: word.lower() in m.content.lower()
        )
        await ctx.send(
            embed=h.ok_embed(f"**{len(deleted)}** messages contenant `{word}` supprimés."),
            delete_after=6,
        )

    # ================================================================ channels

    @commands.command(name="slowmode", aliases=["slow"])
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmode(self, ctx, duration: str = "0"):
        seconds = h.parse_duration(duration) or 0
        seconds = min(seconds, 21600)
        await ctx.channel.edit(slowmode_delay=seconds,
                               reason=f"slowmode by {ctx.author}")
        if seconds:
            await ctx.reply(
                embed=h.ok_embed(f"Mode lent réglé sur **{h.human_duration(seconds)}**."),
                mention_author=False,
            )
        else:
            await ctx.reply(embed=h.ok_embed("Mode lent désactivé."), mention_author=False)

    @commands.command(name="lock")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def lock(self, ctx, channel: discord.TextChannel = None, *, reason: str = ""):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = False
        await channel.set_permissions(
            ctx.guild.default_role, overwrite=overwrite,
            reason=f"lock by {ctx.author}: {reason}",
        )
        await channel.send(
            embed=h.base_embed(
                f"{config.EMOJI['lock']} Salon verrouillé",
                h.clean(reason) or "Un modérateur a verrouillé ce salon.",
                config.COLOR_WARN,
            )
        )

    @commands.command(name="unlock")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def unlock(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        overwrite = channel.overwrites_for(ctx.guild.default_role)
        overwrite.send_messages = None
        await channel.set_permissions(
            ctx.guild.default_role, overwrite=overwrite,
            reason=f"unlock by {ctx.author}",
        )
        await channel.send(
            embed=h.base_embed(
                f"{config.EMOJI['unlock']} Salon déverrouillé",
                "Vous pouvez de nouveau écrire.",
                config.COLOR_SUCCESS,
            )
        )

    @commands.command(name="lockdown", help="Verrouiller tous les salons écrits d'un coup.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def lockdown(self, ctx, state: str = "on"):
        turning_on = state.lower() in ("on", "true", "yes", "enable", "1")
        changed = 0
        async with ctx.typing():
            for channel in ctx.guild.text_channels:
                ow = channel.overwrites_for(ctx.guild.default_role)
                if turning_on and ow.send_messages is False:
                    continue
                ow.send_messages = False if turning_on else None
                try:
                    await channel.set_permissions(
                        ctx.guild.default_role, overwrite=ow,
                        reason=f"server lockdown by {ctx.author}",
                    )
                    changed += 1
                except discord.HTTPException:
                    continue
                await asyncio.sleep(0.3)  # stay friendly with the rate limiter
        verb = "verrouillés" if turning_on else "déverrouillés"
        await ctx.reply(embed=h.ok_embed(f"**{changed}** salons {verb}."),
                        mention_author=False)

    @commands.command(name="nuke", help="Clone et supprime un salon — efface tout l'historique.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def nuke(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        confirm = await ctx.reply(
            embed=h.warn_embed(
                f"Ceci supprime **tout l'historique** de {channel.mention}. "
                f"Tape `confirm` dans les 20 secondes."
            ),
            mention_author=False,
        )
        try:
            reply = await self.bot.wait_for(
                "message",
                timeout=20,
                check=lambda m: m.author == ctx.author
                and m.channel == ctx.channel
                and m.content.lower() == "confirm",
            )
        except asyncio.TimeoutError:
            try:
                await confirm.delete()
            except discord.HTTPException:
                pass
            return await ctx.send(embed=h.err_embed("Annulé."), delete_after=5)

        for msg in (reply, confirm, ctx.message):
            try:
                await msg.delete()
            except discord.HTTPException:
                pass

        position = channel.position
        new = await channel.clone(reason=f"nuke by {ctx.author}")
        await channel.delete(reason=f"nuke by {ctx.author}")
        await new.edit(position=position)
        await new.send(
            embed=h.base_embed(
                f"{config.EMOJI['boom']} Salon réinitialisé",
                f"Nouveau départ, offert par {ctx.author.mention}.",
                config.COLOR_WARN,
            ),
            delete_after=6,
        )

    # ================================================================ roles & nicks

    @commands.command(name="role", help="+role @membre @rôle — ajoute ou retire le rôle.")
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def role(self, ctx, member: discord.Member, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.reply(embed=h.err_embed("Ce rôle est au-dessus du mien."),
                                   mention_author=False)
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.reply(embed=h.err_embed("Ce rôle est au-dessus du tien."),
                                   mention_author=False)
        if role in member.roles:
            await member.remove_roles(role, reason=f"by {ctx.author}")
            await ctx.reply(embed=h.ok_embed(f"{role.mention} retiré à {member.mention}."),
                            mention_author=False)
        else:
            await member.add_roles(role, reason=f"by {ctx.author}")
            await ctx.reply(embed=h.ok_embed(f"{role.mention} donné à {member.mention}."),
                            mention_author=False)

    @commands.command(name="nick", help="Changer ou réinitialiser le pseudo d'un membre.")
    @commands.guild_only()
    @h.is_owner_or(manage_nicknames=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def nick(self, ctx, member: discord.Member, *, nickname: str = None):
        allowed, why = h.bot_can_act(ctx.guild.me, member)
        if not allowed:
            return await ctx.reply(embed=h.err_embed(why), mention_author=False)
        await member.edit(nick=nickname, reason=f"by {ctx.author}")
        if nickname:
            await ctx.reply(embed=h.ok_embed(f"Pseudo changé en **{h.clean(nickname, 32)}**."),
                            mention_author=False)
        else:
            await ctx.reply(embed=h.ok_embed("Pseudo réinitialisé."), mention_author=False)

    @commands.command(name="setmodlog")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def setmodlog(self, ctx, channel: discord.TextChannel):
        await self.bot.db.set_guild(ctx.guild.id, "mod_log", channel.id)
        await ctx.reply(embed=h.ok_embed(f"Journal de modération réglé sur {channel.mention}."),
                        mention_author=False)

    @commands.command(name="setprefix")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def setprefix(self, ctx, prefix: str):
        if len(prefix) > 5:
            return await ctx.reply(embed=h.err_embed("5 caractères maximum."),
                                   mention_author=False)
        await self.bot.db.set_guild(ctx.guild.id, "prefix", prefix)
        self.bot.prefix_cache[ctx.guild.id] = prefix
        await ctx.reply(embed=h.ok_embed(f"Le préfixe est maintenant `{prefix}`"), mention_author=False)


# ==============================================================================
#  SECTION 5 - ANTI-RAID / AUTOMOD / ANTI-NUKE
# ==============================================================================





INVITE_RE = re.compile(r"(?:discord\.(?:gg|io|me|li)|discord(?:app)?\.com/invite)/[\w-]+",
                       re.IGNORECASE)
LINK_RE = re.compile(r"https?://\S+")
ZALGO_RE = re.compile(r"[\u0300-\u036f\u0489]{4,}")


class AntiRaid(commands.Cog):
    """Protection automatique contre les raids, le spam et les nukes."""

    def __init__(self, bot):
        self.bot = bot
        # guild_id -> deque[timestamp]
        self.joins: dict[int, deque] = defaultdict(lambda: deque(maxlen=200))
        # (guild_id, user_id) -> deque[(timestamp, content_hash)]
        self.messages: dict[tuple, deque] = defaultdict(lambda: deque(maxlen=80))
        # guild_id -> unix timestamp when raid mode ends
        self.raid_until: dict[int, float] = {}
        # rate-limit our own alerts
        self.last_alert: dict[int, float] = defaultdict(float)
        self.strikes: dict[tuple, int] = defaultdict(int)

    # ================================================================ helpers

    async def settings(self, guild_id):
        return await self.bot.db.antiraid(guild_id)

    def in_raid(self, guild_id) -> bool:
        return self.raid_until.get(guild_id, 0) > time.time()

    async def alert(self, guild, title, description, color=config.COLOR_ERROR,
                    force=False):
        cfg = await self.settings(guild.id)
        channel_id = cfg["log_channel"]
        if not channel_id:
            row = await self.bot.db.guild_settings(guild.id)
            channel_id = row["mod_log"] if row else None
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if not channel:
            return
        if not force and time.time() - self.last_alert[guild.id] < 3:
            return
        self.last_alert[guild.id] = time.time()

        e = h.base_embed(f"{config.EMOJI['shield']} {title}", description, color)
        content = None
        if cfg["alert_role"]:
            role = guild.get_role(cfg["alert_role"])
            if role:
                content = role.mention
        try:
            await channel.send(
                content=content,
                embed=e,
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        except discord.HTTPException:
            pass

    def is_exempt(self, member: discord.Member) -> bool:
        """Le staff, les bots et tout rôle au-dessus du bot ne sont jamais sanctionnés."""
        if member.bot:
            return True
        if member.id in config.OWNER_IDS:
            return True
        if member.guild.owner_id == member.id:
            return True
        p = member.guild_permissions
        return p.administrator or p.manage_guild or p.manage_messages or p.ban_members

    # ================================================================ join flood

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        cfg = await self.settings(guild.id)
        if not cfg["enabled"]:
            return

        now = time.time()
        window = self.joins[guild.id]
        window.append(now)
        recent = [t for t in window if now - t <= cfg["join_window"]]

        account_age_days = (discord.utils.utcnow() - member.created_at).days
        young = account_age_days < cfg["min_account_age_days"]

        # --- already in raid mode: screen every newcomer hard
        if self.in_raid(guild.id):
            if young:
                await self.handle_suspicious_join(member, cfg, account_age_days)
            return

        # --- raid trigger
        if len(recent) >= cfg["join_threshold"]:
            self.raid_until[guild.id] = now + 60
            await self.trigger_raid(guild, cfg, len(recent))
            return

        # --- lone suspicious account outside raid mode: just log it
        if young:
            await self.alert(
                guild,
                "Nouveau compte arrivé",
                f"{member.mention} `{member.id}`\n"
                f"Compte créé {h.ts(member.created_at)} "
                f"(**{account_age_days}j** — le seuil est de "
                f"{cfg['min_account_age_days']}j).",
                config.COLOR_WARN,
            )

    async def handle_suspicious_join(self, member, cfg, age_days):
        action = cfg["raid_action"]
        reason = f"Anti-raid: account {age_days}d old, joined during active raid"
        try:
            if action == "ban":
                await member.ban(reason=reason, delete_message_days=1)
                verb = "banni"
            elif action == "kick":
                await member.kick(reason=reason)
                verb = "expulsé"
            elif cfg["quarantine_role"]:
                role = member.guild.get_role(cfg["quarantine_role"])
                if role:
                    await member.add_roles(role, reason=reason)
                    verb = "quarantined"
                else:
                    verb = "flagged"
            else:
                verb = "flagged"
        except discord.HTTPException:
            verb = "flagged (action failed)"

        await self.bot.db.add_case(
            member.guild.id, member.id, self.bot.user.id, f"antiraid-{verb}", reason
        )
        await self.alert(
            member.guild,
            f"Arrivée suspecte : {verb}",
            f"{member} `{member.id}` — âge du compte : **{age_days}j**.",
        )

    async def trigger_raid(self, guild, cfg, count):
        await self.alert(
            guild,
            "RAID DÉTECTÉ",
            f"**{count}** arrivées en **{cfg['join_window']}s** "
            f"(seuil {cfg['join_threshold']}).\n"
            f"Réponse : `{cfg['raid_action']}`.\n"
            f"Le mode raid est actif pour les 60 prochaines secondes.",
            config.COLOR_ERROR,
            force=True,
        )

        if cfg["raid_action"] == "lockdown":
            await self.lockdown(guild, cfg["lockdown_minutes"])
        elif cfg["raid_action"] in ("kick", "ban"):
            # Sweep everyone who joined inside the window.
            cutoff = discord.utils.utcnow().timestamp() - cfg["join_window"]
            targets = [
                m for m in guild.members
                if m.joined_at and m.joined_at.timestamp() >= cutoff
                and not self.is_exempt(m)
            ]
            done = 0
            for m in targets:
                try:
                    if cfg["raid_action"] == "ban":
                        await m.ban(reason="Anti-raid sweep", delete_message_days=1)
                    else:
                        await m.kick(reason="Anti-raid sweep")
                    done += 1
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.4)
            await self.alert(
                guild, "Nettoyage du raid terminé",
                f"**{done}/{len(targets)}** comptes traités.", force=True
            )

    async def lockdown(self, guild, minutes: int):
        locked = []
        for channel in guild.text_channels:
            ow = channel.overwrites_for(guild.default_role)
            if ow.send_messages is False:
                continue
            ow.send_messages = False
            try:
                await channel.set_permissions(
                    guild.default_role, overwrite=ow, reason="Anti-raid lockdown"
                )
                locked.append(channel.id)
            except discord.HTTPException:
                continue
            await asyncio.sleep(0.25)

        await self.alert(
            guild, "Serveur verrouillé",
            f"**{len(locked)}** salons verrouillés. Déverrouillage auto dans **{minutes}min** "
            f"({h.ts(h.now() + minutes * 60)}).",
            force=True,
        )
        await asyncio.sleep(minutes * 60)

        for channel_id in locked:
            channel = guild.get_channel(channel_id)
            if not channel:
                continue
            ow = channel.overwrites_for(guild.default_role)
            ow.send_messages = None
            try:
                await channel.set_permissions(
                    guild.default_role, overwrite=ow, reason="Lockdown expired"
                )
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.25)

        await self.alert(guild, "Verrouillage levé", "Salons rouverts.",
                         config.COLOR_SUCCESS, force=True)

    # ================================================================ spam

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        if self.is_exempt(message.author):
            return
        # Rôles ajoutés manuellement à la liste blanche de l'automod.
        try:
            exemptes = await self.bot.db.whitelist_all(message.guild.id)
            if exemptes and any(r.id in exemptes for r in message.author.roles):
                return
        except Exception:
            pass

        cfg = await self.settings(message.guild.id)
        if not cfg["enabled"]:
            return

        key = (message.guild.id, message.author.id)
        now = time.time()
        self.messages[key].append((now, message.content.strip().lower()))
        recent = [x for x in self.messages[key] if now - x[0] <= cfg["msg_window"]]

        violation = None
        contenu = message.content.strip()

        # rate : trop de messages trop vite (vrai spam)
        if len(recent) >= cfg["msg_threshold"]:
            violation = f"{len(recent)} messages en {cfg['msg_window']}s"
        # doublons : on exige des messages NON triviaux (≥ 8 caractères) pour ne
        # pas punir les "ok", "mdr", "ptdr" répétés en discussion normale, et un
        # seuil plus élevé.
        elif len(recent) >= max(cfg["dupe_threshold"], 5):
            tail = [c for _, c in recent[-max(cfg["dupe_threshold"], 5):]]
            if tail[0] and len(tail[0]) >= 8 and len(set(tail)) == 1:
                violation = f"a répété le même message {len(tail)} fois"
        # mention de masse
        mentions = len(message.mentions) + len(message.role_mentions)
        if not violation and mentions >= cfg["mention_limit"]:
            violation = f"mention de masse ({mentions} mentions)"
        # invitations
        if not violation and INVITE_RE.search(message.content):
            if not message.author.guild_permissions.manage_guild:
                violation = "a posté une invitation de serveur"
        # zalgo / abus unicode
        if not violation and ZALGO_RE.search(message.content):
            violation = "a posté du texte zalgo"
        # majuscules : bien plus tolérant — texte long (≥ 40) et quasi tout en
        # majuscules (> 90 %), pour ne pas punir un simple "MERCI TOUT LE MONDE".
        if not violation and len(contenu) >= 40:
            letters = [c for c in contenu if c.isalpha()]
            if letters and sum(c.isupper() for c in letters) / len(letters) > 0.9:
                violation = "majuscules excessives"

        if violation:
            await self.punish_spam(message, cfg, violation)

    async def punish_spam(self, message, cfg, violation):
        member = message.author
        key = (message.guild.id, member.id)
        self.strikes[key] += 1
        strikes = self.strikes[key]

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        # Premier avertissement : on supprime juste le message et on prévient,
        # SANS mute. La sanction n'arrive qu'en cas de récidive immédiate.
        if strikes < 2:
            try:
                await message.channel.send(
                    embed=h.warn_embed(
                        f"{member.mention}, doucement — évite le spam. "
                        f"(prochaine fois = sanction)"
                    ),
                    delete_after=6,
                )
            except discord.HTTPException:
                pass
            await self.alert(
                message.guild, "Automod — avertissement",
                f"{member.mention} `{member.id}` — {violation} (1er, non sanctionné)",
                config.COLOR_WARN,
            )
            # L'avertissement retombe vite pour ne pas s'accumuler à tort.
            await asyncio.sleep(60)
            self.strikes[key] = max(0, self.strikes[key] - 1)
            return

        action = cfg["spam_action"]
        # Escalade pour les vrais récidivistes.
        if strikes >= 6 and action == "mute":
            action = "kick"
        if strikes >= 9:
            action = "ban"

        applied = "message supprimé"
        try:
            if action == "mute":
                until = discord.utils.utcnow() + datetime.timedelta(
                    minutes=cfg["mute_minutes"]
                )
                await member.timeout(until, reason=f"Automod: {violation}")
                applied = f"rendu muet {cfg['mute_minutes']}min"
            elif action == "kick":
                await member.kick(reason=f"Automod: {violation}")
                applied = "expulsé"
            elif action == "ban":
                await member.ban(reason=f"Automod: {violation}", delete_message_days=1)
                applied = "banni"
        except discord.HTTPException:
            applied = "aucune action (permissions manquantes)"

        await self.bot.db.add_case(
            message.guild.id, member.id, self.bot.user.id, f"automod-{action}", violation
        )
        await self.alert(
            message.guild,
            "Automod déclenché",
            f"{member.mention} `{member.id}` in {message.channel.mention}\n"
            f"**Infraction :** {violation}\n"
            f"**Avertissement n° :** {strikes}\n"
            f"**Sanction :** {applied}",
            config.COLOR_WARN,
        )
        # Strikes decay so an old offender isn't punished forever.
        await asyncio.sleep(300)
        self.strikes[key] = max(0, self.strikes[key] - 1)

    # ================================================================ nuke guard

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        """
        Cheap anti-nuke: if a non-exempt member deletes 3+ channels in a minute,
        strip their roles and shout about it.
        """
        guild = channel.guild
        if not guild.me.guild_permissions.view_audit_log:
            return
        try:
            async for entry in guild.audit_logs(
                limit=5, action=discord.AuditLogAction.channel_delete
            ):
                if (discord.utils.utcnow() - entry.created_at).total_seconds() > 10:
                    continue
                actor = guild.get_member(entry.user.id)
                if not actor or self.is_exempt(actor):
                    return
                key = (guild.id, actor.id, "chdel")
                self.strikes[key] += 1
                if self.strikes[key] >= 3:
                    try:
                        await actor.edit(roles=[], reason="Anti-nuke: mass channel delete")
                    except discord.HTTPException:
                        pass
                    await self.alert(
                        guild, "ANTI-NUKE DÉCLENCHÉ",
                        f"{actor.mention} a supprimé plusieurs salons très vite. "
                        f"Tous ses rôles ont été retirés.",
                        force=True,
                    )
                return
        except discord.HTTPException:
            return

    # ================================================================ commands

    @commands.group(name="antiraid", aliases=["ar"], invoke_without_command=True)
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def antiraid(self, ctx):
        cfg = await self.settings(ctx.guild.id)
        state = "ACTIVÉ" if cfg["enabled"] else "DÉSACTIVÉ"
        color = config.COLOR_SUCCESS if cfg["enabled"] else config.COLOR_MUTED
        e = h.base_embed(f"{config.EMOJI['shield']} Anti-raid — {state}", color=color)
        e.add_field(
            name="Vague d'arrivées",
            value=(
                f"Seuil : **{cfg['join_threshold']}** arrivées / "
                f"**{cfg['join_window']}s**\n"
                f"Âge minimum du compte : **{cfg['min_account_age_days']}j**\n"
                f"Action : `{cfg['raid_action']}`\n"
                f"Durée du verrouillage : **{cfg['lockdown_minutes']}min**"
            ),
            inline=False,
        )
        e.add_field(
            name="Spam de messages",
            value=(
                f"Seuil : **{cfg['msg_threshold']}** msgs / **{cfg['msg_window']}s**\n"
                f"Doublons : **{cfg['dupe_threshold']}**\n"
                f"Limite de mentions : **{cfg['mention_limit']}**\n"
                f"Action : `{cfg['spam_action']}` "
                f"(muet = {cfg['mute_minutes']}min)"
            ),
            inline=False,
        )
        log_ch = ctx.guild.get_channel(cfg["log_channel"]) if cfg["log_channel"] else None
        alert_role = ctx.guild.get_role(cfg["alert_role"]) if cfg["alert_role"] else None
        e.add_field(
            name="Destinations",
            value=(
                f"Journal : {log_ch.mention if log_ch else '*non défini*'}\n"
                f"Rôle alerté : {alert_role.mention if alert_role else '*non défini*'}"
            ),
            inline=False,
        )
        e.set_footer(text=f"{ctx.prefix}antiraid set <key> <value> · clés listées dans "
                          f"{ctx.prefix}antiraid keys")
        await ctx.reply(embed=e, mention_author=False)

    @antiraid.command(name="on")
    @h.is_owner_or(administrator=True)
    async def ar_on(self, ctx):
        await self.bot.db.set_antiraid(ctx.guild.id, "enabled", 1)
        await ctx.reply(embed=h.ok_embed("Anti-raid activé."), mention_author=False)

    @antiraid.command(name="off")
    @h.is_owner_or(administrator=True)
    async def ar_off(self, ctx):
        await self.bot.db.set_antiraid(ctx.guild.id, "enabled", 0)
        await ctx.reply(embed=h.warn_embed("Anti-raid désactivé."), mention_author=False)

    @antiraid.command(name="keys")
    @h.is_owner_or(administrator=True)
    async def ar_keys(self, ctx):
        keys = {
            "join_threshold": "arrivées nécessaires pour déclencher un raid",
            "join_window": "fenêtre en secondes du compteur d'arrivées",
            "min_account_age_days": "les comptes plus récents sont suspects",
            "msg_threshold": "messages nécessaires pour détecter du spam",
            "msg_window": "fenêtre en secondes du compteur de messages",
            "dupe_threshold": "messages identiques d'affilée avant sanction",
            "mention_limit": "mentions dans un message avant sanction",
            "raid_action": "lockdown | kick | ban | alert",
            "spam_action": "mute | kick | ban | delete",
            "mute_minutes": "durée du mute automod",
            "lockdown_minutes": "durée du verrouillage auto",
        }
        e = h.base_embed("Clés de l'anti-raid")
        e.description = "\n".join(f"`{k}` — {v}" for k, v in keys.items())
        e.set_footer(text=f"Exemple : {ctx.prefix}antiraid set join_threshold 12")
        await ctx.reply(embed=e, mention_author=False)

    @antiraid.command(name="set")
    @h.is_owner_or(administrator=True)
    async def ar_set(self, ctx, key: str, *, value: str):
        numeric = {
            "join_threshold", "join_window", "min_account_age_days",
            "msg_threshold", "msg_window", "dupe_threshold", "mention_limit",
            "mute_minutes", "lockdown_minutes",
        }
        textual = {"raid_action": {"lockdown", "kick", "ban", "alert"},
                   "spam_action": {"mute", "kick", "ban", "delete"}}

        key = key.lower()
        if key in numeric:
            if not value.isdigit():
                return await ctx.reply(embed=h.err_embed("Cette clé attend un nombre."),
                                       mention_author=False)
            await self.bot.db.set_antiraid(ctx.guild.id, key, int(value))
        elif key in textual:
            if value.lower() not in textual[key]:
                opts = " | ".join(sorted(textual[key]))
                return await ctx.reply(embed=h.err_embed(f"Valeurs possibles : `{opts}`"),
                                       mention_author=False)
            await self.bot.db.set_antiraid(ctx.guild.id, key, value.lower())
        else:
            return await ctx.reply(
                embed=h.err_embed(f"Clé inconnue. Voir `{ctx.prefix}antiraid keys`."),
                mention_author=False,
            )
        await ctx.reply(embed=h.ok_embed(f"`{key}` réglé sur `{value}`."),
                        mention_author=False)

    @antiraid.command(name="logchannel")
    @h.is_owner_or(administrator=True)
    async def ar_log(self, ctx, channel: discord.TextChannel):
        await self.bot.db.set_antiraid(ctx.guild.id, "log_channel", channel.id)
        await ctx.reply(embed=h.ok_embed(f"Les alertes vont dans {channel.mention}."),
                        mention_author=False)

    @antiraid.command(name="alertrole")
    @h.is_owner_or(administrator=True)
    async def ar_role(self, ctx, role: discord.Role):
        await self.bot.db.set_antiraid(ctx.guild.id, "alert_role", role.id)
        await ctx.reply(embed=h.ok_embed(f"{role.mention} sera mentionné en cas de raid."),
                        mention_author=False)

    @antiraid.command(name="panic", help="Forcer manuellement le mode raid + verrouillage.")
    @h.is_owner_or(administrator=True)
    async def ar_panic(self, ctx, minutes: int = 15):
        self.raid_until[ctx.guild.id] = time.time() + minutes * 60
        await ctx.reply(
            embed=h.warn_embed(f"Mode panique pour **{minutes}min**. Verrouillage en cours."),
            mention_author=False,
        )
        await self.lockdown(ctx.guild, minutes)

    @antiraid.command(name="status")
    async def ar_status(self, ctx):
        active = self.in_raid(ctx.guild.id)
        recent = len([t for t in self.joins[ctx.guild.id] if time.time() - t < 60])
        e = h.base_embed(
            "État en direct",
            f"Mode raid : **{'ACTIF' if active else 'repos'}**\n"
            f"Arrivées dans les 60 dernières secondes : **{recent}**\n"
            f"Compteurs de spam suivis : **{len(self.messages)}**",
            config.COLOR_ERROR if active else config.COLOR_SUCCESS,
        )
        await ctx.reply(embed=e, mention_author=False)


# ==============================================================================
#  SECTION 6 - TICKETS
# ==============================================================================





CATEGORIES = [
    ("Aide générale", "Questions, aide, tout le reste", "\U0001f4ac"),
    ("Signaler un membre", "Signaler un comportement contraire aux règles", "\U0001f6a8"),
    ("Contester une sanction", "Contester un mute ou un ban", "\u2696\ufe0f"),
    ("Partenariat", "Demandes de partenariat ou professionnelles", "\U0001f91d"),
    ("Signaler un bug", "Quelque chose ne fonctionne pas", "\U0001f41b"),
]


# ============================================================ transcripts

async def build_transcript(channel: discord.TextChannel) -> discord.File:
    """Render the channel history to a small self-contained HTML file."""
    rows = []
    async for m in channel.history(limit=2000, oldest_first=True):
        stamp = m.created_at.strftime("%Y-%m-%d %H:%M")
        author = htmllib.escape(str(m.author))
        body = htmllib.escape(m.clean_content) or "<i>(pas de texte)</i>"
        attach = "".join(
            f'<div class="att">\U0001f4ce {htmllib.escape(a.filename)}</div>'
            for a in m.attachments
        )
        embeds = "".join(
            f'<div class="emb">{htmllib.escape(e.title or "")} — '
            f'{htmllib.escape((e.description or "")[:200])}</div>'
            for e in m.embeds
        )
        rows.append(
            f'<div class="msg"><span class="ts">{stamp}</span>'
            f'<span class="au">{author}</span>'
            f'<div class="bd">{body}</div>{attach}{embeds}</div>'
        )

    doc = f"""<!doctype html><meta charset="utf-8">
<title>Transcript — #{htmllib.escape(channel.name)}</title>
<style>
 body{{background:#1e1f22;color:#dbdee1;font:14px/1.5 system-ui,sans-serif;
       margin:0;padding:24px}}
 h1{{color:#fff;font-size:20px;border-bottom:1px solid #3f4147;padding-bottom:12px}}
 .msg{{padding:8px 0;border-bottom:1px solid #2b2d31}}
 .ts{{color:#80848e;font-size:12px;margin-right:10px}}
 .au{{color:#5865f2;font-weight:600}}
 .bd{{margin-top:2px;white-space:pre-wrap;word-break:break-word}}
 .att,.emb{{margin-top:4px;padding:6px 10px;background:#2b2d31;border-radius:6px;
            font-size:13px;color:#b5bac1}}
</style>
<h1>#{htmllib.escape(channel.name)} — {len(rows)} messages</h1>
{''.join(rows)}"""
    return discord.File(io.BytesIO(doc.encode()), filename=f"transcript-{channel.name}.html")


# ============================================================ views

class TicketPanelView(discord.ui.View):
    """The public panel. Persistent."""

    def __init__(self, bot=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(TicketSelect())


class TicketSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=name, description=desc, emoji=emoji, value=name)
            for name, desc, emoji in CATEGORIES
        ]
        super().__init__(
            placeholder="Ouvrir un ticket — choisis une catégorie",
            options=options,
            custom_id="ticket:select",
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        cog = bot.get_cog("Tickets")
        await cog.create_ticket(interaction, self.values[0])


class TicketControlView(discord.ui.View):
    """Buttons inside a ticket channel. Persistent."""

    def __init__(self, bot=None):
        super().__init__(timeout=None)
        self.bot = bot

    async def _staff_check(self, interaction) -> bool:
        bot = interaction.client
        cfg = await bot.db.tickets_config(interaction.guild.id)
        if interaction.user.guild_permissions.manage_guild:
            return True
        if cfg["staff_role"] and interaction.user.get_role(cfg["staff_role"]):
            return True
        await interaction.response.send_message(
            embed=h.err_embed("Réservé au staff."), ephemeral=True
        )
        return False

    @discord.ui.button(label="Prendre en charge", emoji="\U0001f64b",
                       style=discord.ButtonStyle.primary, custom_id="ticket:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._staff_check(interaction):
            return
        bot = interaction.client
        ticket = await bot.db.ticket_by_channel(interaction.channel.id)
        if ticket and ticket["claimed_by"]:
            who = interaction.guild.get_member(ticket["claimed_by"])
            return await interaction.response.send_message(
                embed=h.warn_embed(f"Déjà pris en charge par {who.mention if who else 'quelqu\'un'}."),
                ephemeral=True,
            )
        await bot.db.claim_ticket(interaction.channel.id, interaction.user.id)
        await interaction.response.send_message(
            embed=h.ok_embed(f"{interaction.user.mention} s'occupe de ce ticket.")
        )

    @discord.ui.button(label="Fermer", emoji="\U0001f512",
                       style=discord.ButtonStyle.danger, custom_id="ticket:close")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot = interaction.client
        ticket = await bot.db.ticket_by_channel(interaction.channel.id)
        is_owner = ticket and ticket["owner_id"] == interaction.user.id
        if not is_owner and not await self._staff_check(interaction):
            return
        cog = bot.get_cog("Tickets")
        await interaction.response.send_message(
            embed=h.warn_embed("Fermeture dans 5 secondes...")
        )
        await cog.close_ticket(interaction.channel, interaction.user)

    @discord.ui.button(label="Transcription", emoji="\U0001f4dc",
                       style=discord.ButtonStyle.secondary, custom_id="ticket:transcript")
    async def transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._staff_check(interaction):
            return
        await interaction.response.defer(thinking=True, ephemeral=True)
        file = await build_transcript(interaction.channel)
        await interaction.followup.send(file=file, ephemeral=True)


# ============================================================ cog

class Tickets(commands.Cog):
    """Salons d'assistance privés, avec prise en charge et transcriptions."""

    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------ core
    async def create_ticket(self, interaction: discord.Interaction, topic: str):
        guild = interaction.guild
        cfg = await self.bot.db.tickets_config(guild.id)

        open_now = await self.bot.db.open_count(guild.id, interaction.user.id)
        if open_now >= (cfg["max_open_per_user"] or 2):
            return await interaction.response.send_message(
                embed=h.err_embed(
                    f"Tu as déjà **{open_now}** ticket(s) ouvert(s). "
                    f"Ferme-en un avant d'en ouvrir un autre."
                ),
                ephemeral=True,
            )

        category = guild.get_channel(cfg["category"]) if cfg["category"] else None
        staff_role = guild.get_role(cfg["staff_role"]) if cfg["staff_role"] else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, attach_files=True,
                embed_links=True, read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True,
                manage_messages=True, read_message_history=True,
            ),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_messages=True,
                read_message_history=True,
            )

        safe_name = "".join(
            c for c in interaction.user.name.lower() if c.isalnum() or c == "-"
        )[:20] or "user"

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{safe_name}",
                category=category,
                overwrites=overwrites,
                topic=f"{topic} · opened by {interaction.user} ({interaction.user.id})",
                reason=f"Ticket opened by {interaction.user}",
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=h.err_embed("Je ne peux pas créer de salon ici — vérifie mes permissions."),
                ephemeral=True,
            )

        ticket_id = await self.bot.db.open_ticket(
            guild.id, channel.id, interaction.user.id, topic
        )

        e = h.base_embed(
            f"{config.EMOJI['ticket']} Ticket #{ticket_id} — {topic}",
            (
                f"Salut {interaction.user.mention}, merci de nous avoir contactés.\n\n"
                f"**Décris ton problème avec un maximum de détails.** "
                f"Captures d'écran, IDs et liens vers les messages aident le staff à traiter "
                f"ça plus vite.\n\n"
                f"Un membre du staff va prendre en charge ce ticket."
            ),
        )
        e.set_footer(text=f"Ouvert par {interaction.user}", icon_url=interaction.user.display_avatar.url)

        content = staff_role.mention if (staff_role and cfg["ping_staff"]) else None
        await channel.send(
            content=content,
            embed=e,
            view=TicketControlView(self.bot),
            allowed_mentions=discord.AllowedMentions(roles=True, users=True),
        )
        await interaction.response.send_message(
            embed=h.ok_embed(f"Ticket créé : {channel.mention}"), ephemeral=True
        )

    async def close_ticket(self, channel: discord.TextChannel, closer: discord.Member):
        cfg = await self.bot.db.tickets_config(channel.guild.id)
        ticket = await self.bot.db.ticket_by_channel(channel.id)
        if not ticket:
            return await channel.delete(reason="Untracked ticket closed")

        file = None
        if cfg["transcript"]:
            try:
                file = await build_transcript(channel)
            except discord.HTTPException:
                file = None

        if cfg["log_channel"]:
            log = channel.guild.get_channel(cfg["log_channel"])
            if log:
                owner = channel.guild.get_member(ticket["owner_id"])
                claimer = (channel.guild.get_member(ticket["claimed_by"])
                           if ticket["claimed_by"] else None)
                duration = h.now() - (ticket["opened_at"] or h.now())
                e = h.base_embed(
                    f"Ticket #{ticket['id']} fermé", color=config.COLOR_MUTED
                )
                e.add_field(name="Sujet", value=ticket["topic"] or "—", inline=True)
                e.add_field(
                    name="Ouvert par",
                    value=owner.mention if owner else f"`{ticket['owner_id']}`",
                    inline=True,
                )
                e.add_field(
                    name="Pris en charge par",
                    value=claimer.mention if claimer else "*non pris en charge*",
                    inline=True,
                )
                e.add_field(name="Fermé par", value=closer.mention, inline=True)
                e.add_field(name="Durée d'ouverture", value=h.human_duration(duration), inline=True)
                try:
                    await log.send(embed=e, file=file)
                    file = None
                except discord.HTTPException:
                    pass

        # Send the transcript to the ticket owner too, if we still have it.
        owner = channel.guild.get_member(ticket["owner_id"])
        if owner and file:
            try:
                await owner.send(
                    embed=h.base_embed(
                        "Ton ticket a été fermé",
                        f"Transcription de **{channel.guild.name}** en pièce jointe.",
                    ),
                    file=file,
                )
            except discord.HTTPException:
                pass

        await self.bot.db.close_ticket(channel.id, closer.id)
        await asyncio.sleep(5)
        try:
            await channel.delete(reason=f"Ticket closed by {closer}")
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------ commands

    @commands.group(name="ticket", aliases=["tickets"], invoke_without_command=True)
    @commands.guild_only()
    async def ticket(self, ctx):
        cfg = await self.bot.db.tickets_config(ctx.guild.id)
        cat = ctx.guild.get_channel(cfg["category"]) if cfg["category"] else None
        role = ctx.guild.get_role(cfg["staff_role"]) if cfg["staff_role"] else None
        log = ctx.guild.get_channel(cfg["log_channel"]) if cfg["log_channel"] else None
        e = h.base_embed(f"{config.EMOJI['ticket']} Système de tickets")
        e.description = (
            f"**Catégorie :** {cat.name if cat else '*non définie — les tickets iront à la racine*'}\n"
            f"**Rôle staff :** {role.mention if role else '*non défini*'}\n"
            f"**Salon de logs :** {log.mention if log else '*non défini*'}\n"
            f"**Transcriptions :** {'activées' if cfg['transcript'] else 'désactivées'}\n"
            f"**Max ouverts par membre :** {cfg['max_open_per_user']}\n\n"
            f"`{ctx.prefix}ticket panel` — publier le panneau\n"
            f"`{ctx.prefix}ticket category <channel-category-id>`\n"
            f"`{ctx.prefix}ticket staff @role`\n"
            f"`{ctx.prefix}ticket log #channel`\n"
            f"`{ctx.prefix}ticket add @user` / `remove @user`\n"
            f"`{ctx.prefix}ticket rename <name>`\n"
            f"`{ctx.prefix}ticket close`"
        )
        await ctx.reply(embed=e, mention_author=False)

    @ticket.command(name="panel")
    @h.is_owner_or(manage_guild=True)
    async def ticket_panel(self, ctx, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        e = h.base_embed(
            f"{config.EMOJI['ticket']} Besoin d'aide ?",
            (
                "Choisis la catégorie qui correspond à ton problème dans le menu ci-dessous : "
                "un salon privé s'ouvrira entre toi et le staff.\n\n"
                "**N'ouvre pas un ticket pour demander si tu peux demander** — pose directement ta question. "
                "Donne un maximum de détails dès le départ, tu auras une "
                "réponse bien plus vite."
            ),
        )
        e.set_footer(text=f"{ctx.guild.name} · assistance")
        if ctx.guild.icon:
            e.set_thumbnail(url=ctx.guild.icon.url)
        msg = await channel.send(embed=e, view=TicketPanelView(self.bot))
        await self.bot.db.set_ticket(ctx.guild.id, "panel_message", msg.id)
        if channel != ctx.channel:
            await ctx.reply(embed=h.ok_embed(f"Panneau publié dans {channel.mention}."),
                            mention_author=False)

    @ticket.command(name="category")
    @h.is_owner_or(manage_guild=True)
    async def ticket_category(self, ctx, category: discord.CategoryChannel):
        await self.bot.db.set_ticket(ctx.guild.id, "category", category.id)
        await ctx.reply(embed=h.ok_embed(f"Les tickets s'ouvriront dans **{category.name}**."),
                        mention_author=False)

    @ticket.command(name="staff")
    @h.is_owner_or(manage_guild=True)
    async def ticket_staff(self, ctx, role: discord.Role):
        await self.bot.db.set_ticket(ctx.guild.id, "staff_role", role.id)
        await ctx.reply(embed=h.ok_embed(f"Rôle staff réglé sur {role.mention}."),
                        mention_author=False)

    @ticket.command(name="log")
    @h.is_owner_or(manage_guild=True)
    async def ticket_log(self, ctx, channel: discord.TextChannel):
        await self.bot.db.set_ticket(ctx.guild.id, "log_channel", channel.id)
        await ctx.reply(embed=h.ok_embed(f"Les logs de tickets vont dans {channel.mention}."),
                        mention_author=False)

    @ticket.command(name="transcriptions")
    @h.is_owner_or(manage_guild=True)
    async def ticket_transcripts(self, ctx, state: str):
        on = state.lower() in ("on", "true", "yes", "1", "enable")
        await self.bot.db.set_ticket(ctx.guild.id, "transcript", int(on))
        await ctx.reply(embed=h.ok_embed(f"Transcriptions **{'activées' if on else 'désactivées'}**."),
                        mention_author=False)

    @ticket.command(name="limit")
    @h.is_owner_or(manage_guild=True)
    async def ticket_limit(self, ctx, amount: int):
        amount = max(1, min(amount, 10))
        await self.bot.db.set_ticket(ctx.guild.id, "max_open_per_user", amount)
        await ctx.reply(embed=h.ok_embed(f"Les membres peuvent garder **{amount}** tickets ouverts."),
                        mention_author=False)

    @ticket.command(name="add")
    async def ticket_add(self, ctx, member: discord.Member):
        ticket = await self.bot.db.ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.reply(embed=h.err_embed("Ce salon n'est pas un ticket."),
                                   mention_author=False)
        await ctx.channel.set_permissions(
            member, view_channel=True, send_messages=True, read_message_history=True
        )
        await ctx.reply(embed=h.ok_embed(f"{member.mention} ajouté à ce ticket."),
                        mention_author=False)

    @ticket.command(name="remove")
    async def ticket_remove(self, ctx, member: discord.Member):
        ticket = await self.bot.db.ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.reply(embed=h.err_embed("Ce salon n'est pas un ticket."),
                                   mention_author=False)
        if member.id == ticket["owner_id"]:
            return await ctx.reply(embed=h.err_embed("Tu ne peux pas retirer le propriétaire du ticket."),
                                   mention_author=False)
        await ctx.channel.set_permissions(member, overwrite=None)
        await ctx.reply(embed=h.ok_embed(f"{member.mention} retiré."),
                        mention_author=False)

    @ticket.command(name="rename")
    @h.is_owner_or(manage_channels=True)
    async def ticket_rename(self, ctx, *, name: str):
        ticket = await self.bot.db.ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.reply(embed=h.err_embed("Ce salon n'est pas un ticket."),
                                   mention_author=False)
        await ctx.channel.edit(name=name[:90], reason=f"renamed by {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"Renommé en **{name[:90]}**."),
                        mention_author=False)

    @ticket.command(name="close")
    async def ticket_close(self, ctx):
        ticket = await self.bot.db.ticket_by_channel(ctx.channel.id)
        if not ticket:
            return await ctx.reply(embed=h.err_embed("Ce salon n'est pas un ticket."),
                                   mention_author=False)
        await ctx.reply(embed=h.warn_embed("Fermeture dans 5 secondes..."),
                        mention_author=False)
        await self.close_ticket(ctx.channel, ctx.author)


# ==============================================================================
#  SECTION 7 - WELCOME & GOODBYE
# ==============================================================================




PLACEHOLDERS = (
    "`{mention}` — mentionne le membre\n"
    "`{user}` — nom d'utilisateur complet\n"
    "`{username}` — pseudo affiché\n"
    "`{tag}` — nom#discriminateur\n"
    "`{id}` — ID du membre\n"
    "`{server}` — nom du serveur\n"
    "`{count}` — nombre de membres\n"
    "`{ordinal}` — 1er / 2e / 3e membre\n"
    "`{created}` — date de création du compte\n"
    "`{joined}` — date d'arrivée"
)


def ordinal(n: int) -> str:
    if 11 <= (n % 100) <= 13:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


class Welcome(commands.Cog):
    """Accueillir les arrivées, saluer les départs."""

    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------ formatting
    def render(self, template: str, member: discord.Member) -> str:
        guild = member.guild
        count = guild.member_count or len(guild.members)
        joined = member.joined_at or discord.utils.utcnow()
        return (
            (template or "")
            .replace("{mention}", member.mention)
            .replace("{user}", str(member))
            .replace("{username}", member.display_name)
            .replace("{tag}", str(member))
            .replace("{id}", str(member.id))
            .replace("{server}", guild.name)
            .replace("{count}", str(count))
            .replace("{ordinal}", ordinal(count))
            .replace("{created}", h.ts(member.created_at))
            .replace("{joined}", h.ts(joined))
        )

    def welcome_embed(self, member, text, image_url=None) -> discord.Embed:
        e = h.base_embed(
            f"{config.EMOJI['wave']} Bienvenue !", text, config.COLOR_SUCCESS
        )
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(
            name="Compte créé",
            value=h.ts(member.created_at),
            inline=True,
        )
        e.add_field(
            name="Numéro de membre",
            value=f"#{member.guild.member_count}",
            inline=True,
        )
        # Bannière animée : GIF/image configurée, sinon la bannière du serveur.
        if image_url:
            e.set_image(url=image_url)
        elif member.guild.banner:
            e.set_image(url=member.guild.banner.url)
        e.set_footer(text=str(member), icon_url=member.display_avatar.url)
        return e

    # ------------------------------------------------------------ events
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.guild is None:
            return
        cfg = await self.bot.db.welcome(member.guild.id)

        # autorole
        if cfg["autorole"]:
            role = member.guild.get_role(cfg["autorole"])
            if role and role < member.guild.me.top_role:
                try:
                    await member.add_roles(role, reason="Autorole on join")
                except discord.HTTPException:
                    pass

        # channel greeting
        if cfg["welcome_channel"]:
            channel = member.guild.get_channel(cfg["welcome_channel"])
            if channel:
                text = self.render(cfg["welcome_message"], member)
                try:
                    await channel.send(
                        content=member.mention,
                        embed=self.welcome_embed(member, text, cfg["welcome_image"]),
                        allowed_mentions=discord.AllowedMentions(users=True),
                    )
                except discord.HTTPException:
                    pass

        # DM
        if cfg["dm_welcome"] and cfg["dm_message"]:
            e = h.base_embed(
                f"Bienvenue sur {member.guild.name}",
                self.render(cfg["dm_message"], member),
                config.COLOR_SUCCESS,
            )
            if member.guild.icon:
                e.set_thumbnail(url=member.guild.icon.url)
            await h.safe_dm(member, e)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        cfg = await self.bot.db.welcome(member.guild.id)
        if not cfg["goodbye_channel"]:
            return
        channel = member.guild.get_channel(cfg["goodbye_channel"])
        if not channel:
            return
        text = self.render(cfg["goodbye_message"], member)
        e = h.base_embed("Un membre est parti", text, config.COLOR_MUTED)
        e.set_thumbnail(url=member.display_avatar.url)
        if cfg["goodbye_image"]:
            e.set_image(url=cfg["goodbye_image"])
        elif member.guild.banner:
            e.set_image(url=member.guild.banner.url)
        if member.joined_at:
            stayed = h.now() - int(member.joined_at.timestamp())
            e.add_field(name="Temps passé sur le serveur", value=h.human_duration(stayed))
        try:
            await channel.send(embed=e)
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------ commands

    @commands.group(name="welcome", aliases=["greet"], invoke_without_command=True)
    @commands.guild_only()
    @h.is_owner_or(manage_guild=True)
    async def welcome(self, ctx):
        cfg = await self.bot.db.welcome(ctx.guild.id)
        wc = ctx.guild.get_channel(cfg["welcome_channel"]) if cfg["welcome_channel"] else None
        gc = ctx.guild.get_channel(cfg["goodbye_channel"]) if cfg["goodbye_channel"] else None
        ar = ctx.guild.get_role(cfg["autorole"]) if cfg["autorole"] else None
        e = h.base_embed(f"{config.EMOJI['wave']} Système de bienvenue")
        e.add_field(
            name="Welcome",
            value=f"Salon : {wc.mention if wc else '*désactivé*'}\n"
                  f"```{h.clean(cfg['welcome_message'] or '—', 300)}```",
            inline=False,
        )
        e.add_field(
            name="Au revoir",
            value=f"Salon : {gc.mention if gc else '*désactivé*'}\n"
                  f"```{h.clean(cfg['goodbye_message'] or '—', 300)}```",
            inline=False,
        )
        e.add_field(
            name="Options",
            value=f"Rôle auto : {ar.mention if ar else '*désactivé*'}\n"
                  f"MP à l'arrivée : {'activé' if cfg['dm_welcome'] else 'désactivé'}",
            inline=False,
        )
        e.set_footer(text=f"{ctx.prefix}welcome placeholders · {ctx.prefix}welcome test")
        await ctx.reply(embed=e, mention_author=False)

    @welcome.command(name="config", aliases=["setup", "set"])
    @h.is_owner_or(manage_guild=True)
    async def welcome_config(self, ctx, *, image_url: str = None):
        """
        Active la bienvenue dans le salon courant, avec un message FR par défaut
        et une bannière animée. Joins un GIF au message, colle une URL, ou laisse
        vide pour garder la bannière du serveur.
        """
        message_fr = (
            "Bienvenue {mention} sur **{server}** ! \U0001f389\n"
            "Tu es notre **{ordinal}** membre. Pense à lire le règlement et "
            "amuse-toi bien parmi nous."
        )
        # Priorité : pièce jointe > URL fournie > rien (bannière du serveur)
        image = None
        if ctx.message.attachments:
            image = ctx.message.attachments[0].url
        elif image_url:
            image = image_url.strip("<>")

        await self.bot.db.set_welcome(ctx.guild.id, "welcome_channel", ctx.channel.id)
        await self.bot.db.set_welcome(ctx.guild.id, "welcome_message", message_fr)
        if image:
            await self.bot.db.set_welcome(ctx.guild.id, "welcome_image", image)

        cfg = await self.bot.db.welcome(ctx.guild.id)
        apercu = self.welcome_embed(ctx.author, self.render(message_fr, ctx.author),
                                    cfg["welcome_image"])
        await ctx.send(
            embed=h.ok_embed(f"Bienvenue configurée dans {ctx.channel.mention}. Aperçu :")
        )
        await ctx.send(embed=apercu)

    @welcome.command(name="image", aliases=["banner", "gif"])
    @h.is_owner_or(manage_guild=True)
    async def welcome_image_cmd(self, ctx, *, url: str = None):
        image = None
        if ctx.message.attachments:
            image = ctx.message.attachments[0].url
        elif url:
            image = url.strip("<>")
        await self.bot.db.set_welcome(ctx.guild.id, "welcome_image", image)
        if image:
            await ctx.reply(embed=h.ok_embed("Bannière de bienvenue mise à jour."))
        else:
            await ctx.reply(embed=h.ok_embed("Bannière retirée (retour à celle du serveur)."))

    @welcome.command(name="channel")
    @h.is_owner_or(manage_guild=True)
    async def welcome_channel(self, ctx, channel: discord.TextChannel = None):
        await self.bot.db.set_welcome(
            ctx.guild.id, "welcome_channel", channel.id if channel else None
        )
        msg = f"Les bienvenues vont dans {channel.mention}." if channel else "Bienvenues désactivées."
        await ctx.reply(embed=h.ok_embed(msg), mention_author=False)

    @welcome.command(name="message", aliases=["msg"])
    @h.is_owner_or(manage_guild=True)
    async def welcome_message(self, ctx, *, template: str):
        await self.bot.db.set_welcome(ctx.guild.id, "welcome_message", template[:1500])
        preview = self.render(template, ctx.author)
        await ctx.reply(
            embed=h.ok_embed(f"Enregistré. Aperçu :\n\n{preview}"), mention_author=False
        )

    @welcome.command(name="placeholders", aliases=["vars"])
    async def welcome_vars(self, ctx):
        await ctx.reply(
            embed=h.base_embed("Variables disponibles", PLACEHOLDERS),
            mention_author=False,
        )

    @welcome.command(name="test", aliases=["preview"])
    @h.is_owner_or(manage_guild=True)
    async def welcome_test(self, ctx):
        cfg = await self.bot.db.welcome(ctx.guild.id)
        text = self.render(cfg["welcome_message"], ctx.author)
        await ctx.reply(embed=self.welcome_embed(ctx.author, text), mention_author=False)

    @commands.command(name="autorole", aliases=["autorolemembre"],
                      help="+autorole <@role|nom> — rôle donné auto à chaque arrivée. Sans argument : désactive.")
    @commands.guild_only()
    @h.is_owner_or(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def autorole(self, ctx, *, role: str = None):
        if role is None:
            await self.bot.db.set_welcome(ctx.guild.id, "autorole", None)
            return await ctx.reply(embed=h.ok_embed("Rôle automatique désactivé."))
        # Accepte une mention, un ID ou un nom.
        r = None
        clean_id = role.strip("<@&>")
        if clean_id.isdigit():
            r = ctx.guild.get_role(int(clean_id))
        if r is None:
            r = discord.utils.find(lambda x: x.name.lower() == role.lower(), ctx.guild.roles)
        if r is None:
            r = discord.utils.find(lambda x: role.lower() in x.name.lower(), ctx.guild.roles)
        if r is None:
            return await ctx.reply(
                embed=h.err_embed(f"Aucun rôle nommé « {h.clean(role, 50)} ».")
            )
        if r >= ctx.guild.me.top_role:
            return await ctx.reply(
                embed=h.err_embed(
                    f"Le rôle {r.mention} est au-dessus du mien — je ne pourrai pas "
                    f"l'attribuer. Monte mon rôle plus haut dans les paramètres."
                )
            )
        await self.bot.db.set_welcome(ctx.guild.id, "autorole", r.id)
        await ctx.reply(
            embed=h.ok_embed(
                f"Chaque nouveau membre recevra automatiquement {r.mention} à l'arrivée."
            )
        )

    @welcome.command(name="autorole")
    @h.is_owner_or(manage_guild=True)
    async def welcome_autorole(self, ctx, role: discord.Role = None):
        if role and role >= ctx.guild.me.top_role:
            return await ctx.reply(
                embed=h.err_embed("Ce rôle est au-dessus du mien — je ne peux pas l'attribuer."),
                mention_author=False,
            )
        await self.bot.db.set_welcome(
            ctx.guild.id, "autorole", role.id if role else None
        )
        msg = f"Les nouveaux membres reçoivent {role.mention}." if role else "Rôle automatique désactivé."
        await ctx.reply(embed=h.ok_embed(msg), mention_author=False)

    @welcome.command(name="dm")
    @h.is_owner_or(manage_guild=True)
    async def welcome_dm(self, ctx, state: str, *, template: str = None):
        on = state.lower() in ("on", "true", "yes", "1", "enable")
        await self.bot.db.set_welcome(ctx.guild.id, "dm_welcome", int(on))
        if template:
            await self.bot.db.set_welcome(ctx.guild.id, "dm_message", template[:1500])
        await ctx.reply(
            embed=h.ok_embed(f"MP d'arrivée **{'activés' if on else 'désactivés'}**."),
            mention_author=False,
        )

    @commands.group(name="goodbye", aliases=["leave"], invoke_without_command=True)
    @commands.guild_only()
    @h.is_owner_or(manage_guild=True)
    async def goodbye(self, ctx):
        await ctx.invoke(self.welcome)

    @goodbye.command(name="config", aliases=["setup", "set"])
    @h.is_owner_or(manage_guild=True)
    async def goodbye_config(self, ctx, *, image_url: str = None):
        """Active les au revoir dans le salon courant, message FR + image."""
        message_fr = (
            "**{user}** vient de quitter **{server}**. \U0001f44b\n"
            "Nous sommes maintenant **{count}** membres."
        )
        image = None
        if ctx.message.attachments:
            image = ctx.message.attachments[0].url
        elif image_url:
            image = image_url.strip("<>")

        await self.bot.db.set_welcome(ctx.guild.id, "goodbye_channel", ctx.channel.id)
        await self.bot.db.set_welcome(ctx.guild.id, "goodbye_message", message_fr)
        if image:
            await self.bot.db.set_welcome(ctx.guild.id, "goodbye_image", image)

        cfg = await self.bot.db.welcome(ctx.guild.id)
        e = h.base_embed("Un membre est parti",
                         self.render(message_fr, ctx.author), config.COLOR_MUTED)
        e.set_thumbnail(url=ctx.author.display_avatar.url)
        if cfg["goodbye_image"]:
            e.set_image(url=cfg["goodbye_image"])
        elif ctx.guild.banner:
            e.set_image(url=ctx.guild.banner.url)
        await ctx.send(
            embed=h.ok_embed(f"Au revoir configurés dans {ctx.channel.mention}. Aperçu :")
        )
        await ctx.send(embed=e)

    @goodbye.command(name="image", aliases=["banner", "gif"])
    @h.is_owner_or(manage_guild=True)
    async def goodbye_image_cmd(self, ctx, *, url: str = None):
        image = None
        if ctx.message.attachments:
            image = ctx.message.attachments[0].url
        elif url:
            image = url.strip("<>")
        await self.bot.db.set_welcome(ctx.guild.id, "goodbye_image", image)
        await ctx.reply(embed=h.ok_embed("Image des départs mise à jour."))

    @goodbye.command(name="channel")
    @h.is_owner_or(manage_guild=True)
    async def goodbye_channel(self, ctx, channel: discord.TextChannel = None):
        await self.bot.db.set_welcome(
            ctx.guild.id, "goodbye_channel", channel.id if channel else None
        )
        msg = f"Les au revoir vont dans {channel.mention}." if channel else "Au revoir désactivés."
        await ctx.reply(embed=h.ok_embed(msg), mention_author=False)

    @goodbye.command(name="message", aliases=["msg"])
    @h.is_owner_or(manage_guild=True)
    async def goodbye_message(self, ctx, *, template: str):
        await self.bot.db.set_welcome(ctx.guild.id, "goodbye_message", template[:1500])
        await ctx.reply(
            embed=h.ok_embed(f"Enregistré. Aperçu :\n\n{self.render(template, ctx.author)}"),
            mention_author=False,
        )


# ==============================================================================
#  SECTION 8 - STATS & PROFILES
# ==============================================================================





TITLES = [
    (0, "Fantôme", "\U0001f47b"),
    (50, "Observateur", "\U0001f440"),
    (250, "Habitué", "\U0001f4ac"),
    (1000, "Moulin à paroles", "\U0001f5e3\ufe0f"),
    (5000, "Guerrier du clavier", "\u2328\ufe0f"),
    (15000, "Meuble du serveur", "\U0001f3db\ufe0f"),
    (50000, "Candidat à la sortie dehors", "\U0001f33f"),
]


def title_for(messages: int) -> tuple[str, str]:
    best = TITLES[0]
    for threshold, name, emoji in TITLES:
        if messages >= threshold:
            best = (threshold, name, emoji)
    return best[1], best[2]


class Stats(commands.Cog):
    """Qui parle le plus, et à quel point tu t'es ridiculisé."""

    def __init__(self, bot):
        self.bot = bot
        self.voice_since: dict[tuple, float] = {}

    # ------------------------------------------------------------ collection

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        await self.bot.db.bump_stat(message.guild.id, message.author.id, "messages")
        if message.content:
            await self.bot.db.bump_stat(
                message.guild.id, message.author.id, "characters", len(message.content)
            )
        if message.attachments:
            await self.bot.db.bump_stat(
                message.guild.id, message.author.id, "attachments",
                len(message.attachments),
            )

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot or not reaction.message.guild:
            return
        await self.bot.db.bump_stat(
            reaction.message.guild.id, user.id, "reactions_given"
        )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        key = (member.guild.id, member.id)
        if before.channel is None and after.channel is not None:
            self.voice_since[key] = time.time()
        elif before.channel is not None and after.channel is None:
            started = self.voice_since.pop(key, None)
            if started:
                await self.bot.db.bump_stat(
                    member.guild.id, member.id, "voice_seconds",
                    int(time.time() - started),
                )

    # ------------------------------------------------------------ profile

    @commands.command(name="u", aliases=["stats", "profile", "me", "whois", "userinfo"],
                      help="Ta carte de profil, ou celle d'un autre. -u @membre")
    @commands.guild_only()
    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_PER, commands.BucketType.user)
    async def userstats(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        db = self.bot.db
        row = await db.get_stats(ctx.guild.id, member.id)
        messages = row["messages"] if row else 0
        chars = row["characters"] if row else 0
        attachments = row["attachments"] if row else 0
        reactions = row["reactions_given"] if row else 0
        voice = row["voice_seconds"] if row else 0
        first_seen = row["first_seen"] if row else None
        last_seen = row["last_seen"] if row else None

        cmds_total = await db.total_commands(ctx.guild.id, member.id)
        top_cmds = await db.top_commands(ctx.guild.id, member.id, 5)
        msg_rank = await db.rank_of(ctx.guild.id, member.id, "messages")
        cases = await db.case_count(ctx.guild.id, member.id)
        title, badge = title_for(messages)

        e = h.base_embed(
            f"{badge} {member.display_name} — {title}",
            color=member.color if member.color.value else config.COLOR_PRIMARY,
        )
        e.set_thumbnail(url=member.display_avatar.url)

        # --- activity block
        avg_len = round(chars / messages, 1) if messages else 0
        e.add_field(
            name=f"{config.EMOJI['chart']} Activité",
            value=(
                f"Messages : **{messages:,}** (rang **#{msg_rank}**)\n"
                f"Caractères : **{chars:,}**\n"
                f"Longueur moyenne : **{avg_len}** caractères\n"
                f"Pièces jointes : **{attachments:,}**\n"
                f"Réactions données : **{reactions:,}**\n"
                f"Temps en vocal : **{h.human_duration(voice)}**"
            ),
            inline=True,
        )

        # --- command block
        cmd_lines = "\n".join(
            f"`{r['command']}` \u00d7{r['uses']}" for r in top_cmds
        ) or "*rien pour l'instant*"
        e.add_field(
            name="\u2699\ufe0f Commandes",
            value=f"Total exécutées : **{cmds_total:,}**\n**Favorites :**\n{cmd_lines}",
            inline=True,
        )

        # --- server block
        joined = member.joined_at
        e.add_field(
            name=f"{config.EMOJI['crown']} Serveur",
            value=(
                f"Arrivé : {h.ts(joined) if joined else '?'}\n"
                f"Compte créé : {h.ts(member.created_at)}\n"
                f"Premier suivi : {h.ts(first_seen) if first_seen else '—'}\n"
                f"Vu pour la dernière fois : {h.ts(last_seen) if last_seen else '—'}\n"
                f"Dossiers de modération : **{cases}**\n"
                f"Booster : {'oui ' + config.EMOJI['star'] if member.premium_since else 'non'}"
            ),
            inline=False,
        )

        # --- roles
        roles = [r for r in reversed(member.roles) if r != ctx.guild.default_role]
        if roles:
            shown = ", ".join(r.mention for r in roles[:20])
            if len(roles) > 20:
                shown += f" *+{len(roles) - 20} more*"
        else:
            shown = "*aucun rôle*"
        e.add_field(
            name=f"Rôles ({len(roles)}) — principal : "
                 f"{roles[0].name if roles else 'aucun'}",
            value=shown,
            inline=False,
        )

        # --- key permissions worth surfacing
        p = member.guild_permissions
        notable = [
            name.replace("_", " ").title()
            for name in ("administrator", "manage_guild", "ban_members",
                         "kick_members", "manage_messages", "manage_roles",
                         "moderate_members", "mention_everyone")
            if getattr(p, name)
        ]
        if notable:
            e.add_field(name="Permissions notables", value=", ".join(notable), inline=False)

        # --- progress to next title
        nxt = next((t for t in TITLES if t[0] > messages), None)
        if nxt:
            prev = max(t[0] for t in TITLES if t[0] <= messages)
            span = nxt[0] - prev
            done = messages - prev
            bar = h.progress_bar(done, span, 18)
            e.add_field(
                name=f"Progression vers {nxt[2]} {nxt[1]}",
                value=f"`{bar}` {done:,}/{span:,}",
                inline=False,
            )
        else:
            e.add_field(name="Progression", value="Niveau maximum. Sérieusement, va prendre l'air.",
                        inline=False)

        # --- achievements, entirely for laughs
        ach = []
        if messages and chars / messages > 200:
            ach.append("\U0001f4dc **Essayiste** — personne ne les lit")
        if messages and chars / messages < 8 and messages > 100:
            ach.append("\U0001f4a8 **Monosyllabique** — 'ok'")
        if reactions > messages and messages > 20:
            ach.append("\U0001f440 **Réacteur** — plus d'emojis que de mots")
        if voice > 360000:
            ach.append("\U0001f3a7 **En vocal en permanence**")
        if cases == 0 and messages > 500:
            ach.append("\U0001f607 **Irréprochable** — 500+ messages, zéro dossier")
        if cases >= 5:
            ach.append("\U0001f6a9 **Habitué des sanctions** — les modos connaissent ton nom")
        if member.premium_since:
            ach.append("\U0001f49c **Booster** — merci pour l'argent")
        if msg_rank == 1:
            ach.append("\U0001f947 **Bavard n°1** du serveur")
        if ach:
            e.add_field(name="Succès", value="\n".join(ach[:6]), inline=False)

        e.set_footer(text=f"ID: {member.id}")
        await ctx.reply(embed=e, mention_author=False)

    # ------------------------------------------------------------ leaderboards

    @commands.command(name="leaderboard", aliases=["lb", "top"],
                      help="+lb messages|voice|commands|reactions")
    @commands.guild_only()
    async def leaderboard(self, ctx, field: str = "messages"):
        mapping = {
            "messages": ("messages", "messages", "{:,}"),
            "msg": ("messages", "messages", "{:,}"),
            "voice": ("voice_seconds", "temps en vocal", None),
            "vc": ("voice_seconds", "temps en vocal", None),
            "commands": ("commands", "commandes exécutées", "{:,}"),
            "réactions": ("reactions_given", "réactions", "{:,}"),
            "chars": ("characters", "caractères", "{:,}"),
        }
        key = field.lower()
        if key not in mapping:
            return await ctx.reply(
                embed=h.err_embed(f"Choisis parmi : `{'`, `'.join(sorted(set(mapping)))}`"),
                mention_author=False,
            )
        column, label, fmt = mapping[key]
        rows = await self.bot.db.leaderboard(ctx.guild.id, column, 15)
        if not rows:
            return await ctx.reply(embed=h.warn_embed("Aucune donnée pour l'instant."),
                                   mention_author=False)

        medals = ["\U0001f947", "\U0001f948", "\U0001f949"]
        lines = []
        for i, r in enumerate(rows):
            member = ctx.guild.get_member(r["user_id"])
            name = member.display_name if member else f"user {r['user_id']}"
            value = h.human_duration(r["v"]) if fmt is None else fmt.format(r["v"])
            prefix = medals[i] if i < 3 else f"`{i + 1:>2}.`"
            lines.append(f"{prefix} **{h.clean(name, 30)}** — {value}")

        e = h.base_embed(f"{config.EMOJI['chart']} Classement {label} — {ctx.guild.name}",
                         "\n".join(lines))
        my_rank = await self.bot.db.rank_of(ctx.guild.id, ctx.author.id, column)
        e.set_footer(text=f"Tu es #{my_rank}")
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="serverinfo", aliases=["si", "guild", "member", "membre"])
    @commands.guild_only()
    async def serverinfo(self, ctx):
        g = ctx.guild
        humans = sum(1 for m in g.members if not m.bot)
        bots = g.member_count - humans
        online = sum(1 for m in g.members if m.status is not discord.Status.offline)

        e = h.base_embed(g.name)
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        if g.banner:
            e.set_image(url=g.banner.url)
        e.add_field(
            name="Membres",
            value=(
                f"Total : **{g.member_count:,}**\n"
                f"Humains : **{humans:,}**\nBots : **{bots:,}**\n"
                f"Connectés : **{online:,}**"
            ),
            inline=True,
        )
        e.add_field(
            name="Salons",
            value=(
                f"Écrits : **{len(g.text_channels)}**\n"
                f"Vocaux : **{len(g.voice_channels)}**\n"
                f"Catégories : **{len(g.categories)}**\n"
                f"Fils : **{len(g.threads)}**"
            ),
            inline=True,
        )
        e.add_field(
            name="Divers",
            value=(
                f"Rôles : **{len(g.roles)}**\n"
                f"Émojis : **{len(g.emojis)}**/{g.emoji_limit}\n"
                f"Boosts : **{g.premium_subscription_count}** "
                f"(niveau {g.premium_tier})\n"
                f"Vérification : **{g.verification_level}**"
            ),
            inline=True,
        )
        e.add_field(name="Propriétaire", value=g.owner.mention if g.owner else "?", inline=True)
        e.add_field(name="Créé le", value=h.ts(g.created_at), inline=True)
        e.set_footer(text=f"ID: {g.id}")
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="avatar", aliases=["av", "pfp", "pic", "pp"])
    @commands.guild_only()
    async def avatar(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        e = h.base_embed(f"Avatar de {member.display_name}")
        e.set_image(url=member.display_avatar.url)
        e.description = f"[Ouvrir l'original]({member.display_avatar.url})"
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="roleinfo")
    @commands.guild_only()
    async def roleinfo(self, ctx, *, role: discord.Role):
        e = h.base_embed(f"Rôle — {role.name}", color=role.color)
        e.add_field(name="Membres", value=str(len(role.members)), inline=True)
        e.add_field(name="Couleur", value=str(role.color), inline=True)
        e.add_field(name="Position", value=str(role.position), inline=True)
        e.add_field(name="Mentionnable", value="yes" if role.mentionable else "no",
                    inline=True)
        e.add_field(name="Affiché à part", value="yes" if role.hoist else "no", inline=True)
        e.add_field(name="Créé le", value=h.ts(role.created_at), inline=True)
        perms = [p.replace("_", " ") for p, v in role.permissions if v]
        e.add_field(name=f"Permissions ({len(perms)})",
                    value=h.clean(", ".join(perms) or "aucune", 900), inline=False)
        e.set_footer(text=f"ID: {role.id}")
        await ctx.reply(embed=e, mention_author=False)


# ==============================================================================
#  SECTION 9 - FUN
# ==============================================================================





EIGHT_BALL = [
    "C'est certain.", "Sans aucun doute.", "Oui, absolument.", "Tu peux compter dessus.",
    "Très probablement.", "Tout indique que oui.", "Réponse floue, réessaie.",
    "Redemande plus tard.", "Mieux vaut ne pas te le dire maintenant.", "N'y compte pas.",
    "Ma réponse est non.", "Très douteux.", "Absolument pas.",
    "Pourquoi tu demandes ça à un bot.",
]

SHIPS = [
    (0, "Absolument pas. On frôle l'ordonnance restrictive."),
    (10, "Il n'y a rien ici. Passe à autre chose."),
    (25, "Amis. Et encore."),
    (40, "Un peu de potentiel, en plissant les yeux."),
    (55, "Pas mal, en fait."),
    (70, "Là on parle."),
    (85, "Vraiment solide. Que quelqu'un se lance."),
    (95, "Âmes sœurs. Réservez la salle."),
]

ROASTS = [
    "Tu as la confiance de quelqu'un de bien plus compétent.",
    "Je t'expliquerais bien, mais j'ai oublié mes crayons de couleur.",
    "Tu n'es pas la personne la plus bête au monde, mais espère qu'elle reste en bonne santé.",
    "Tes avis sont comme ton ping — toujours mauvais.",
    "Tu apportes tant de joie à tout le monde... quand tu quittes le vocal.",
    "Si le rire est le meilleur remède, ton visage soigne tout le serveur.",
]

COMPLIMENTS = [
    "C'est grâce à toi que ce serveur vaut le détour.",
    "Ton sens du timing dans les conversations est remarquable.",
    "Quelqu'un a passé une meilleure journée grâce à ce que tu as dit.",
    "Tu expliques bien les choses. C'est plus rare que tu ne crois.",
    "Bon goût. Systématiquement.",
]


class ClaimView(discord.ui.View):
    """The consent prompt. Only the target can press these."""

    def __init__(self, owner: discord.Member, target: discord.Member, label: str):
        super().__init__(timeout=90)
        self.owner = owner
        self.target = target
        self.label = label
        self.result: bool | None = None
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message(
                embed=h.err_embed("Cette demande ne t'est pas destinée."), ephemeral=True
            )
            return False
        return True

    async def on_timeout(self):
        self.result = None
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    embed=h.base_embed(
                        "Pas de réponse",
                        f"{self.target.display_name} n'a pas répondu. Rien ne s'est passé.",
                        config.COLOR_MUTED,
                    ),
                    view=self,
                )
            except discord.HTTPException:
                pass

    @discord.ui.button(label="Accepter", emoji="\u2705", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="Non merci", emoji="\u274c", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.result = False
        await interaction.response.defer()
        self.stop()


class Fun(commands.Cog):
    """Des bêtises, essentiellement."""

    def __init__(self, bot):
        self.bot = bot

    # ================================================================ claim

    @commands.command(
        name="ls",
        aliases=["claim", "collar"],
        help="+ls @user <label> — Verrouille un membre en vocal et le renomme de force.",
    )
    @commands.guild_only()
    @commands.bot_has_permissions(manage_nicknames=True, move_members=True)
    @h.is_owner_or(manage_nicknames=True)
    async def ls(self, ctx, member: discord.Member, *, label: str = "soumise"):
        if member.bot:
            return await ctx.reply(embed=h.err_embed("Les bots ne peuvent pas être verrouillés."),
                                   mention_author=False)
        if member.id == ctx.author.id:
            return await ctx.reply(embed=h.err_embed("Tu ne peux pas te verrouiller toi-même."),
                                   mention_author=False)

        allowed, why = h.bot_can_act(ctx.guild.me, member)
        if not allowed:
            return await ctx.reply(embed=h.err_embed(why), mention_author=False)

        allowed, why = h.hierarchy_ok(ctx.author, member)
        if not allowed:
            return await ctx.reply(embed=h.err_embed(why), mention_author=False)

        if member.voice is None or member.voice.channel is None:
            return await ctx.reply(embed=h.err_embed("Ce membre n'est pas dans un salon vocal."),
                                   mention_author=False)

        label = h.clean(label, 16).strip() or "soumise"
        if any(c in label for c in "@`\\<>"):
            return await ctx.reply(embed=h.err_embed("Le label doit rester du texte simple."),
                                   mention_author=False)

        proposed = f"{label} de {ctx.author.display_name}"[:32]
        old_nick = member.nick
        owner = ctx.author

        try:
            await member.edit(nick=proposed, reason=f"Lock by {ctx.author}")
        except discord.Forbidden:
            return await ctx.reply(embed=h.err_embed("Je ne peux pas renommer ce membre."),
                                   mention_author=False)

        await self.bot.db.set_collar(ctx.guild.id, member.id, ctx.author.id, old_nick)

        guild = ctx.guild

        async def monitor_voice():
            while True:
                await asyncio.sleep(1)
                try:
                    fresh_owner = guild.get_member(owner.id)
                    fresh_target = guild.get_member(member.id)
                    if fresh_owner is None or fresh_target is None:
                        continue
                    owner_vc = fresh_owner.voice
                    if owner_vc is None or owner_vc.channel is None:
                        continue
                    target_vc = fresh_target.voice
                    if target_vc is None or target_vc.channel is None:
                        await fresh_target.move_to(owner_vc.channel)
                    elif target_vc.channel != owner_vc.channel:
                        await fresh_target.move_to(owner_vc.channel)
                except (discord.HTTPException, AttributeError):
                    pass

        if hasattr(self.bot, 'lock_tasks') and member.id in self.bot.lock_tasks:
            self.bot.lock_tasks[member.id].cancel()

        if not hasattr(self.bot, 'lock_tasks'):
            self.bot.lock_tasks = {}

        task = ctx.bot.loop.create_task(monitor_voice())
        self.bot.lock_tasks[member.id] = task

        await ctx.reply(
            embed=h.ok_embed(
                f"**{member.display_name}** est maintenant verrouillé et suit "
                f"{owner.mention} en vocal, renommé **{proposed}**.\n"
                f"Libère-le avec `{ctx.prefix}unls @{member.name}`."
            ),
            mention_author=False,
        )
    @commands.command(
        name="unls",
        aliases=["uncollar", "unclaim", "release"],
        help="+unls @user — Libère un membre verrouillé.",
    )
    @commands.guild_only()
    @commands.bot_has_permissions(manage_nicknames=True, move_members=True)
    @h.is_owner_or(manage_nicknames=True)
    async def unls(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        row = await self.bot.db.get_collar(ctx.guild.id, target.id)
        if not row:
            return await ctx.reply(embed=h.warn_embed("Ce membre n'est pas verrouillé."),
                                   mention_author=False)

        allowed = (
            ctx.author.id == target.id
            or ctx.author.id == row["owner_id"]
            or ctx.author.guild_permissions.manage_nicknames
        )
        if not allowed:
            return await ctx.reply(
                embed=h.err_embed("Seuls l'intéressé, la personne qui l'a verrouillé ou le staff "
                                  "peuvent le libérer."),
                mention_author=False,
            )

        if hasattr(ctx.bot, 'lock_tasks') and target.id in ctx.bot.lock_tasks:
            ctx.bot.lock_tasks[target.id].cancel()
            del ctx.bot.lock_tasks[target.id]

        try:
            await target.edit(nick=row["old_nick"], reason=f"Unlock by {ctx.author}")
        except discord.Forbidden:
            pass

        await self.bot.db.remove_collar(ctx.guild.id, target.id)
        await ctx.reply(embed=h.ok_embed(f"**{target.display_name}** libéré."),
                        mention_author=False
                       )


    @commands.command(name="claims", help="Lister tous ceux qui ont accepté ta réclamation.")
    @commands.guild_only()
    async def claims(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        rows = await self.bot.db.collars_of(ctx.guild.id, member.id)
        if not rows:
            return await ctx.reply(
                embed=h.base_embed(description=f"**{member.display_name}** n'a aucune réclamation."),
                mention_author=False,
            )
        lines = []
        for r in rows:
            m = ctx.guild.get_member(r["user_id"])
            lines.append(
                f"• {m.mention if m else r['user_id']} — since {h.ts(r['created_at'])}"
            )
        await ctx.reply(
            embed=h.base_embed(f"Réclamations de {member.display_name}", "\n".join(lines)),
            mention_author=False,
        )

    # ================================================================ misc fun

    @commands.command(name="8ball", aliases=["8b"])
    async def eightball(self, ctx, *, question: str):
        e = h.base_embed("\U0001f3b1 Boule magique")
        e.add_field(name="Tu as demandé", value=h.clean(question, 250), inline=False)
        e.add_field(name="Réponse", value=random.choice(EIGHT_BALL), inline=False)
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="ship")
    @commands.guild_only()
    async def ship(self, ctx, a: discord.Member, b: discord.Member = None):
        b = b or ctx.author
        seed = (a.id * b.id) % 101
        verdict = SHIPS[0][1]
        for threshold, text in SHIPS:
            if seed >= threshold:
                verdict = text
        name = a.display_name[: len(a.display_name) // 2] + \
            b.display_name[len(b.display_name) // 2:]
        e = h.base_embed(
            f"\U0001f498 {a.display_name} \u00d7 {b.display_name}",
            f"**{seed}%**\n`{h.progress_bar(seed, 100, 20)}`\n\n"
            f"Nom du couple : **{h.clean(name, 32)}**\n{verdict}",
            config.COLOR_ERROR if seed < 40 else config.COLOR_SUCCESS,
        )
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="roast")
    @commands.guild_only()
    async def roast(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        if member.bot:
            return await ctx.reply("Je suis parfait, en fait.", mention_author=False)
        await ctx.reply(f"{member.mention} {random.choice(ROASTS)}", mention_author=False)

    @commands.command(name="compliment", aliases=["nice"])
    @commands.guild_only()
    async def compliment(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        await ctx.reply(f"{member.mention} {random.choice(COMPLIMENTS)}",
                        mention_author=False)

    @commands.command(name="roll", aliases=["dice"], help="+roll 2d20")
    async def roll(self, ctx, dice: str = "1d6"):
        try:
            count, sides = dice.lower().split("d")
            count, sides = int(count or 1), int(sides)
        except ValueError:
            return await ctx.reply(embed=h.err_embed("Format : `2d20`"),
                                   mention_author=False)
        if not (1 <= count <= 25 and 2 <= sides <= 1000):
            return await ctx.reply(embed=h.err_embed("Entre 1 et 25 dés, 2 à 1000 faces."),
                                   mention_author=False)
        rolls = [random.randint(1, sides) for _ in range(count)]
        e = h.base_embed(
            f"\U0001f3b2 {dice}",
            f"{' + '.join(map(str, rolls))}\n\n**Total : {sum(rolls)}**"
            if count > 1 else f"**{rolls[0]}**",
        )
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="coinflip", aliases=["flip", "cf"])
    async def coinflip(self, ctx):
        await ctx.reply(f"\U0001fa99 **{random.choice(['Pile', 'Face'])}**",
                        mention_author=False)

    @commands.command(name="choose", aliases=["pick"], help="+choose pizza | sushi | tacos")
    async def choose(self, ctx, *, options: str):
        parts = [p.strip() for p in options.split("|") if p.strip()]
        if len(parts) < 2:
            return await ctx.reply(embed=h.err_embed("Donne-m'en au moins deux, séparés par `|`."),
                                   mention_author=False)
        await ctx.reply(
            embed=h.base_embed("\U0001f914 Je choisis", f"**{h.clean(random.choice(parts), 200)}**"),
            mention_author=False,
        )

    @commands.command(name="poll", help='-poll "Ta question" option1 | option2')
    @commands.guild_only()
    async def poll(self, ctx, question: str, *, options: str = None):
        digits = ["1\ufe0f\u20e3", "2\ufe0f\u20e3", "3\ufe0f\u20e3", "4\ufe0f\u20e3",
                  "5\ufe0f\u20e3", "6\ufe0f\u20e3", "7\ufe0f\u20e3", "8\ufe0f\u20e3"]
        if not options:
            e = h.base_embed("\U0001f4ca " + h.clean(question, 250),
                             f"Votez ci-dessous.\n\n— {ctx.author.mention}")
            msg = await ctx.send(embed=e)
            await msg.add_reaction("\U0001f44d")
            await msg.add_reaction("\U0001f44e")
            await msg.add_reaction("\U0001f937")
            return
        parts = [p.strip() for p in options.split("|") if p.strip()][:8]
        body = "\n".join(f"{digits[i]} {h.clean(p, 100)}" for i, p in enumerate(parts))
        e = h.base_embed("\U0001f4ca " + h.clean(question, 250),
                         body + f"\n\n— {ctx.author.mention}")
        msg = await ctx.send(embed=e)
        for i in range(len(parts)):
            await msg.add_reaction(digits[i])

    @commands.command(name="say")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def say(self, ctx, *, text: str):
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass
        await ctx.send(h.clean(text, 1900))

    @commands.command(name="remind", aliases=["remindme"], help="+remind 30m sortir les poubelles")
    async def remind(self, ctx, when: str, *, what: str = "sans note"):
        seconds = h.parse_duration(when)
        if not seconds or seconds > 60 * 60 * 24 * 7:
            return await ctx.reply(
                embed=h.err_embed("Donne une durée jusqu'à 7 jours, ex. `2h30m`."),
                mention_author=False,
            )
        await ctx.reply(
            embed=h.ok_embed(f"Je te préviens {h.ts(h.now() + seconds)} pour : "
                             f"{h.clean(what, 200)}"),
            mention_author=False,
        )
        await asyncio.sleep(seconds)
        try:
            await ctx.reply(
                content=ctx.author.mention,
                embed=h.base_embed(f"{config.EMOJI['clock']} Rappel",
                                   h.clean(what, 500)),
                mention_author=True,
            )
        except discord.HTTPException:
            await h.safe_dm(
                ctx.author,
                h.base_embed("Rappel", h.clean(what, 500)),
            )


# ==============================================================================
#  SECTION 10 - MODÉRATION AVANCÉE (op)
# ==============================================================================






class OpMod(commands.Cog):
    """Commandes de modération avancée et actions de masse."""

    def __init__(self, bot):
        self.bot = bot
        # salon_id -> (contenu, auteur, pièces jointes)
        self.snipes: dict[int, tuple] = {}
        self.edit_snipes: dict[int, tuple] = {}

    # ================================================================ snipe

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        self.snipes[message.channel.id] = (
            message.content, message.author, h.now(),
            [a.url for a in message.attachments],
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        self.edit_snipes[before.channel.id] = (
            before.content, after.content, before.author, h.now(), after.jump_url
        )

    @commands.command(name="snipe", help="Affiche le dernier message supprimé du salon.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def snipe(self, ctx):
        data = self.snipes.get(ctx.channel.id)
        if not data:
            return await ctx.reply(embed=h.warn_embed("Rien à récupérer ici."))
        contenu, auteur, quand, fichiers = data
        e = h.base_embed(
            "Message supprimé",
            h.clean(contenu, 2000) or "*aucun texte*",
            config.COLOR_WARN,
        )
        e.set_author(name=str(auteur), icon_url=auteur.display_avatar.url)
        e.add_field(name="Supprimé", value=h.ts(quand), inline=True)
        if fichiers:
            e.add_field(name="Pièces jointes", value=f"{len(fichiers)} (liens expirés)",
                        inline=True)
        await ctx.reply(embed=e)

    @commands.command(name="editsnipe", aliases=["esnipe"],
                      help="Affiche la dernière modification de message du salon.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def editsnipe(self, ctx):
        data = self.edit_snipes.get(ctx.channel.id)
        if not data:
            return await ctx.reply(embed=h.warn_embed("Aucune modification récente."))
        avant, apres, auteur, quand, lien = data
        e = h.base_embed("Message modifié", color=config.COLOR_WARN)
        e.set_author(name=str(auteur), icon_url=auteur.display_avatar.url)
        e.add_field(name="Avant", value=h.clean(avant, 900) or "*vide*", inline=False)
        e.add_field(name="Après", value=h.clean(apres, 900) or "*vide*", inline=False)
        e.add_field(name="Modifié", value=f"{h.ts(quand)} · [aller au message]({lien})",
                    inline=False)
        await ctx.reply(embed=e)

    # ================================================================ actions de masse

    @commands.command(name="massban", help="+massban 123 456 789 raison — bannit plusieurs IDs.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(ban_members=True)
    async def massban(self, ctx, ids: commands.Greedy[int], *, reason: str = ""):
        if not ids:
            return await ctx.reply(
                embed=h.err_embed("Donne au moins un ID. Ex : `+massban 123 456 spam`")
            )
        ids = list(dict.fromkeys(ids))[:100]
        status = await ctx.send(
            embed=h.base_embed("Bannissement de masse", f"0/{len(ids)}...")
        )
        ok, echecs = 0, []
        for i, uid in enumerate(ids, 1):
            try:
                await ctx.guild.ban(
                    discord.Object(id=uid),
                    reason=f"Massban par {ctx.author}: {reason or 'aucune raison'}",
                    delete_message_days=1,
                )
                ok += 1
                await self.bot.db.add_case(
                    ctx.guild.id, uid, ctx.author.id, "massban", reason
                )
            except discord.HTTPException:
                echecs.append(uid)
            if i % 5 == 0:
                try:
                    await status.edit(
                        embed=h.base_embed("Bannissement de masse", f"{i}/{len(ids)}...")
                    )
                except discord.HTTPException:
                    pass
            await asyncio.sleep(0.6)

        e = h.ok_embed(f"**{ok}/{len(ids)}** comptes bannis.")
        if echecs:
            e.description += f"\n**Échecs :** `{', '.join(map(str, echecs[:20]))}`"
        await status.edit(embed=e, delete_after=30)

    @commands.command(name="masskick", help="+masskick 123 456 raison")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(kick_members=True)
    async def masskick(self, ctx, ids: commands.Greedy[int], *, reason: str = ""):
        if not ids:
            return await ctx.reply(embed=h.err_embed("Donne au moins un ID."))
        ok = 0
        async with ctx.typing():
            for uid in list(dict.fromkeys(ids))[:100]:
                membre = ctx.guild.get_member(uid)
                if membre is None:
                    continue
                try:
                    await membre.kick(reason=f"Masskick par {ctx.author}: {reason}")
                    ok += 1
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.5)
        await ctx.reply(embed=h.ok_embed(f"**{ok}** membres expulsés."))

    @commands.command(name="banlist", aliases=["bans", "mutelist"], help="Liste les membres bannis.")
    @commands.guild_only()
    @h.is_owner_or(ban_members=True)
    async def banlist(self, ctx):
        bans = [b async for b in ctx.guild.bans(limit=200)]
        if not bans:
            return await ctx.reply(embed=h.base_embed(description="Aucun banni."))
        lignes = [
            f"`{b.user.id}` — **{b.user}** · {h.clean(b.reason or 'aucune raison', 60)}"
            for b in bans[:40]
        ]
        e = h.base_embed(f"Bannis ({len(bans)})", "\n".join(lignes)[:4000])
        if len(bans) > 40:
            e.set_footer(text=f"40 affichés sur {len(bans)}")
        await ctx.reply(embed=e)

    @commands.command(name="roleall", help="Donne un rôle à TOUS les membres.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def roleall(self, ctx, *, role: discord.Role):
        await self._role_masse(ctx, role, lambda m: True, "tous les membres", True)

    @commands.command(name="rolehumans", help="Donne un rôle à tous les humains.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def rolehumans(self, ctx, *, role: discord.Role):
        await self._role_masse(ctx, role, lambda m: not m.bot, "les humains", True)

    @commands.command(name="rolebots", help="Donne un rôle à tous les bots.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def rolebots(self, ctx, *, role: discord.Role):
        await self._role_masse(ctx, role, lambda m: m.bot, "les bots", True)

    @commands.command(name="removeroleall", aliases=["unroleall"],
                      help="Retire un rôle à tout le monde.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def removeroleall(self, ctx, *, role: discord.Role):
        await self._role_masse(ctx, role, lambda m: True, "tous les membres", False)

    async def _role_masse(self, ctx, role, filtre, description, ajouter):
        if role >= ctx.guild.me.top_role:
            return await ctx.reply(embed=h.err_embed("Ce rôle est au-dessus du mien."))
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.reply(embed=h.err_embed("Ce rôle est au-dessus du tien."))

        cibles = [
            m for m in ctx.guild.members
            if filtre(m) and ((role not in m.roles) if ajouter else (role in m.roles))
        ]
        if not cibles:
            return await ctx.reply(embed=h.warn_embed("Personne à modifier."))

        verbe = "Attribution" if ajouter else "Retrait"
        status = await ctx.send(
            embed=h.base_embed(
                f"{verbe} de {role.name}",
                f"0/{len(cibles)} — environ "
                f"{h.human_duration(int(len(cibles) * 0.6))} nécessaires."
            )
        )
        fait = 0
        for i, membre in enumerate(cibles, 1):
            try:
                if ajouter:
                    await membre.add_roles(role, reason=f"Masse par {ctx.author}")
                else:
                    await membre.remove_roles(role, reason=f"Masse par {ctx.author}")
                fait += 1
            except discord.HTTPException:
                pass
            if i % 10 == 0:
                try:
                    await status.edit(
                        embed=h.base_embed(f"{verbe} de {role.name}",
                                           f"{i}/{len(cibles)}...")
                    )
                except discord.HTTPException:
                    pass
            await asyncio.sleep(0.6)

        action = "attribué à" if ajouter else "retiré à"
        await status.edit(
            embed=h.ok_embed(f"{role.mention} {action} **{fait}** membres ({description})."),
            delete_after=30,
        )

    @commands.command(name="nickall", help="Change le pseudo de tout le monde.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def nickall(self, ctx, *, pseudo: str):
        cibles = [m for m in ctx.guild.members
                  if not m.bot and m.top_role < ctx.guild.me.top_role]
        status = await ctx.send(
            embed=h.base_embed("Renommage de masse", f"0/{len(cibles)}...")
        )
        fait = 0
        for membre in cibles:
            try:
                await membre.edit(nick=pseudo[:32], reason=f"Nickall par {ctx.author}")
                fait += 1
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.6)
        await status.edit(
            embed=h.ok_embed(f"**{fait}** pseudos changés."), delete_after=20
        )

    @commands.command(name="resetnicks", help="Réinitialise tous les pseudos.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_nicknames=True)
    async def resetnicks(self, ctx):
        cibles = [m for m in ctx.guild.members
                  if m.nick and m.top_role < ctx.guild.me.top_role]
        fait = 0
        async with ctx.typing():
            for membre in cibles:
                try:
                    await membre.edit(nick=None, reason=f"Reset par {ctx.author}")
                    fait += 1
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.6)
        await ctx.reply(embed=h.ok_embed(f"**{fait}** pseudos réinitialisés."))

    @commands.command(name="slowmodeall", help="Applique le mode lent à tous les salons.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def slowmodeall(self, ctx, duree: str = "0"):
        secondes = min(h.parse_duration(duree) or 0, 21600)
        fait = 0
        async with ctx.typing():
            for salon in ctx.guild.text_channels:
                try:
                    await salon.edit(slowmode_delay=secondes)
                    fait += 1
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.3)
        texte = h.human_duration(secondes) if secondes else "désactivé"
        await ctx.reply(embed=h.ok_embed(f"Mode lent **{texte}** sur **{fait}** salons."))

    # ================================================================ vocal

    @commands.command(name="voicekick", aliases=["vkick"],
                      help="Déconnecte un membre du vocal.")
    @commands.guild_only()
    @h.is_owner_or(move_members=True)
    async def voicekick(self, ctx, membre: discord.Member, *, reason: str = ""):
        if membre.voice is None:
            return await ctx.reply(embed=h.err_embed("Ce membre n'est pas en vocal."))
        await membre.move_to(None, reason=f"{ctx.author}: {reason}")
        await ctx.reply(embed=h.ok_embed(f"**{membre}** déconnecté du vocal."))

    @commands.command(name="voicemute", aliases=["vmute"], help="Coupe le micro en vocal.")
    @commands.guild_only()
    @h.is_owner_or(mute_members=True)
    async def voicemute(self, ctx, membre: discord.Member, *, reason: str = ""):
        if membre.voice is None:
            return await ctx.reply(embed=h.err_embed("Ce membre n'est pas en vocal."))
        await membre.edit(mute=True, reason=f"{ctx.author}: {reason}")
        await ctx.reply(embed=h.ok_embed(f"Micro de **{membre}** coupé."))

    @commands.command(name="voiceunmute", aliases=["vunmute"])
    @commands.guild_only()
    @h.is_owner_or(mute_members=True)
    async def voiceunmute(self, ctx, membre: discord.Member):
        await membre.edit(mute=False, reason=f"Démute par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"Micro de **{membre}** rétabli."))

    @commands.command(name="deafen", aliases=["vdeaf"], help="Rend un membre sourd en vocal.")
    @commands.guild_only()
    @h.is_owner_or(deafen_members=True)
    async def deafen(self, ctx, membre: discord.Member):
        if membre.voice is None:
            return await ctx.reply(embed=h.err_embed("Ce membre n'est pas en vocal."))
        nouvel_etat = not membre.voice.deaf
        await membre.edit(deafen=nouvel_etat, reason=f"Par {ctx.author}")
        await ctx.reply(
            embed=h.ok_embed(
                f"**{membre}** {'rendu sourd' if nouvel_etat else 'entend de nouveau'}."
            )
        )

    @commands.command(name="moveall", help="+moveall <salon source> <salon cible>")
    @commands.guild_only()
    @h.is_owner_or(move_members=True)
    async def moveall(self, ctx, source: discord.VoiceChannel,
                      cible: discord.VoiceChannel):
        membres = list(source.members)
        if not membres:
            return await ctx.reply(embed=h.warn_embed("Le salon source est vide."))
        fait = 0
        async with ctx.typing():
            for membre in membres:
                try:
                    await membre.move_to(cible, reason=f"Moveall par {ctx.author}")
                    fait += 1
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.3)
        await ctx.reply(
            embed=h.ok_embed(f"**{fait}** membres déplacés vers {cible.mention}.")
        )

    @commands.command(name="disconnectall", aliases=["dcall"],
                      help="Déconnecte tout le monde d'un salon vocal.")
    @commands.guild_only()
    @h.is_owner_or(move_members=True)
    async def disconnectall(self, ctx, salon: discord.VoiceChannel = None):
        salon = salon or (ctx.author.voice.channel if ctx.author.voice else None)
        if salon is None:
            return await ctx.reply(embed=h.err_embed("Indique un salon vocal."))
        fait = 0
        async with ctx.typing():
            for membre in list(salon.members):
                try:
                    await membre.move_to(None, reason=f"Par {ctx.author}")
                    fait += 1
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.3)
        await ctx.reply(embed=h.ok_embed(f"**{fait}** membres déconnectés."))

    # ================================================================ listes

    @commands.group(name="botblacklist", aliases=["botbl"], invoke_without_command=True,
                    help="&bl <@user|ID> [raison] — bloque l'usage du bot. &bl list pour la liste.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def blacklist(self, ctx, cible: str = None, *, reason: str = ""):
        # &bl              -> affiche la liste
        # &bl list         -> affiche la liste
        # &bl <@user|ID>   -> ajoute directement
        if cible is None or cible.lower() in ("list", "liste", "show"):
            return await self._bl_montrer(ctx)

        membre = await self._resoudre_membre(ctx, cible)
        if membre is None:
            return await ctx.reply(
                embed=h.err_embed("Membre introuvable. Donne une mention ou un ID valide.")
            )
        await self._bl_ajouter(ctx, membre, reason)

    async def _resoudre_membre(self, ctx, texte):
        """Accepte une mention (<@123>) ou un ID brut."""
        texte = texte.strip().strip("<@!>")
        if not texte.isdigit():
            return None
        membre = ctx.guild.get_member(int(texte))
        if membre is None:
            try:
                membre = await ctx.guild.fetch_member(int(texte))
            except discord.HTTPException:
                return None
        return membre

    async def _bl_montrer(self, ctx):
        rows = await self.bot.db.blacklist_all(ctx.guild.id)
        if not rows:
            return await ctx.reply(embed=h.base_embed(description="Liste noire vide."))
        lignes = []
        for r in rows[:40]:
            m = ctx.guild.get_member(r["user_id"])
            qui = m.mention if m else f"`{r['user_id']}`"
            lignes.append(f"• {qui} — {h.clean(r['reason'] or 'aucune raison', 60)}")
        await ctx.reply(
            embed=h.base_embed(f"Liste noire ({len(rows)})", "\n".join(lignes))
        )

    async def _bl_ajouter(self, ctx, membre, reason):
        if membre.guild_permissions.administrator:
            return await ctx.reply(
                embed=h.err_embed("On ne met pas un administrateur en liste noire.")
            )
        await self.bot.db.blacklist_add(ctx.guild.id, membre.id, reason)
        await ctx.reply(
            embed=h.ok_embed(
                f"**{membre}** ajouté à la liste noire — il ne peut plus utiliser le bot."
                + (f"\n**Raison :** {h.clean(reason, 200)}" if reason else "")
            )
        )

    @blacklist.command(name="add")
    @h.is_owner_or(administrator=True)
    async def bl_add(self, ctx, membre: discord.Member, *, reason: str = ""):
        await self._bl_ajouter(ctx, membre, reason)

    @blacklist.command(name="list", aliases=["liste"])
    @h.is_owner_or(administrator=True)
    async def bl_list(self, ctx):
        await self._bl_montrer(ctx)

    @blacklist.command(name="remove", aliases=["del"])
    @h.is_owner_or(administrator=True)
    async def bl_remove(self, ctx, membre: discord.Member):
        await self.bot.db.blacklist_remove(ctx.guild.id, membre.id)
        await ctx.reply(embed=h.ok_embed(f"**{membre}** retiré de la liste noire."))

    @commands.group(name="whitelist", aliases=["wl"], invoke_without_command=True,
                    help="Rôles exemptés de l'automod.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def whitelist(self, ctx):
        ids = await self.bot.db.whitelist_all(ctx.guild.id)
        roles = [ctx.guild.get_role(i) for i in ids]
        roles = [r.mention for r in roles if r]
        await ctx.reply(
            embed=h.base_embed(
                "Rôles exemptés de l'automod",
                "\n".join(roles) or "*aucun — seul le staff est exempté par défaut*",
            )
        )

    @whitelist.command(name="add")
    @h.is_owner_or(administrator=True)
    async def wl_add(self, ctx, role: discord.Role):
        await self.bot.db.whitelist_add(ctx.guild.id, role.id)
        await ctx.reply(embed=h.ok_embed(f"{role.mention} est exempté de l'automod."))

    @whitelist.command(name="remove", aliases=["del"])
    @h.is_owner_or(administrator=True)
    async def wl_remove(self, ctx, role: discord.Role):
        await self.bot.db.whitelist_remove(ctx.guild.id, role.id)
        await ctx.reply(embed=h.ok_embed(f"{role.mention} n'est plus exempté."))

    # ================================================================ serveur

    @commands.command(name="verifylevel", help="Change le niveau de vérification du serveur.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def verifylevel(self, ctx, niveau: str):
        niveaux = {
            "aucun": discord.VerificationLevel.none,
            "faible": discord.VerificationLevel.low,
            "moyen": discord.VerificationLevel.medium,
            "eleve": discord.VerificationLevel.high,
            "extreme": discord.VerificationLevel.highest,
        }
        if niveau.lower() not in niveaux:
            return await ctx.reply(
                embed=h.err_embed(f"Choix : `{'`, `'.join(niveaux)}`")
            )
        await ctx.guild.edit(verification_level=niveaux[niveau.lower()],
                             reason=f"Par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"Niveau de vérification : **{niveau}**."))

    @commands.command(name="auditlog", aliases=["audit"],
                      help="Affiche les dernières entrées du journal d'audit.")
    @commands.guild_only()
    @h.is_owner_or(view_audit_log=True)
    @commands.bot_has_permissions(view_audit_log=True)
    async def auditlog(self, ctx, limite: int = 10):
        limite = max(1, min(limite, 25))
        lignes = []
        async for entree in ctx.guild.audit_logs(limit=limite):
            action = str(entree.action).replace("AuditLogAction.", "").replace("_", " ")
            cible = getattr(entree.target, "name", entree.target)
            lignes.append(
                f"**{action}** par {entree.user.mention if entree.user else '?'}\n"
                f"↳ cible : `{cible}` · {h.ts(entree.created_at)}"
            )
        await ctx.reply(
            embed=h.base_embed("Journal d'audit", "\n\n".join(lignes)[:4000])
        )

    @commands.command(name="invites", help="Liste les invitations du serveur.")
    @commands.guild_only()
    @h.is_owner_or(manage_guild=True)
    async def invites(self, ctx):
        invitations = await ctx.guild.invites()
        if not invitations:
            return await ctx.reply(embed=h.base_embed(description="Aucune invitation."))
        invitations.sort(key=lambda i: i.uses or 0, reverse=True)
        lignes = [
            f"`{i.code}` — **{i.uses}** utilisations · "
            f"{i.inviter.mention if i.inviter else '?'} · "
            f"{i.channel.mention if i.channel else '?'}"
            for i in invitations[:25]
        ]
        await ctx.reply(
            embed=h.base_embed(f"Invitations ({len(invitations)})", "\n".join(lignes))
        )

    @commands.command(name="delinvite", help="Supprime une invitation par son code.")
    @commands.guild_only()
    @h.is_owner_or(manage_guild=True)
    async def delinvite(self, ctx, code: str):
        for invitation in await ctx.guild.invites():
            if invitation.code == code:
                await invitation.delete(reason=f"Par {ctx.author}")
                return await ctx.reply(embed=h.ok_embed(f"Invitation `{code}` supprimée."))
        await ctx.reply(embed=h.err_embed("Code introuvable."))

    # ================================================================ communication

    @commands.command(name="announce", aliases=["annonce"],
                      help="+announce #salon Ton message")
    @commands.guild_only()
    @h.is_owner_or(manage_guild=True)
    async def announce(self, ctx, salon: discord.TextChannel, *, message: str):
        e = h.base_embed("\U0001f4e2 Annonce", h.clean(message, 4000))
        e.set_footer(text=f"Par {ctx.author}", icon_url=ctx.author.display_avatar.url)
        await salon.send(embed=e)
        await ctx.reply(embed=h.ok_embed(f"Annonce publiée dans {salon.mention}."))

    @commands.command(name="dm", help="Envoie un MP à un membre au nom du staff.")
    @commands.guild_only()
    @h.is_owner_or(manage_guild=True)
    async def dm(self, ctx, membre: discord.Member, *, message: str):
        e = h.base_embed(f"Message du staff de {ctx.guild.name}", h.clean(message, 3000))
        e.set_footer(text="Tu peux répondre en ouvrant un ticket.")
        if await h.safe_dm(membre, e):
            await ctx.reply(embed=h.ok_embed(f"MP envoyé à **{membre}**."))
        else:
            await ctx.reply(embed=h.err_embed("Ses MP sont fermés."))

    @commands.command(name="embed",
                      help="+embed #salon | Titre | Description | #5865F2")
    @commands.guild_only()
    @h.is_owner_or(manage_guild=True)
    async def embed_cmd(self, ctx, salon: discord.TextChannel, *, reste: str):
        parties = [p.strip() for p in reste.split("|")]
        titre = parties[0] if parties else "Sans titre"
        description = parties[1] if len(parties) > 1 else ""
        couleur = config.COLOR_PRIMARY
        if len(parties) > 2 and parties[2]:
            try:
                couleur = int(parties[2].lstrip("#"), 16)
            except ValueError:
                pass
        e = h.base_embed(h.clean(titre, 250), h.clean(description, 4000), couleur)
        await salon.send(embed=e)
        await ctx.reply(embed=h.ok_embed(f"Embed publié dans {salon.mention}."))

    @commands.command(name="clearwarns", aliases=["clearcases", "delallsanction"],
                      help="Efface tous les dossiers d'un membre.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def clearwarns(self, ctx, membre: discord.Member):
        total = await self.bot.db.case_count(ctx.guild.id, membre.id)
        await self.bot.db.execute(
            "DELETE FROM cases WHERE guild_id=? AND user_id=?",
            (ctx.guild.id, membre.id),
        )
        await ctx.reply(
            embed=h.ok_embed(f"**{total}** dossier(s) effacés pour **{membre}**.")
        )

    @commands.command(name="modstats", aliases=["modinfo"], help="Activité de modération d'un membre du staff.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def modstats(self, ctx, membre: discord.Member = None):
        membre = membre or ctx.author
        rows = await self.bot.db.fetchall(
            "SELECT action, COUNT(*) n FROM cases WHERE guild_id=? AND mod_id=?"
            " GROUP BY action ORDER BY n DESC",
            (ctx.guild.id, membre.id),
        )
        if not rows:
            return await ctx.reply(
                embed=h.base_embed(description=f"**{membre}** n'a aucune action enregistrée.")
            )
        total = sum(r["n"] for r in rows)
        detail = "\n".join(f"`{r['action']}` — **{r['n']}**" for r in rows)
        e = h.base_embed(
            f"Activité de modération — {membre.display_name}",
            f"**{total}** actions au total\n\n{detail}",
        )
        e.set_thumbnail(url=membre.display_avatar.url)
        await ctx.reply(embed=e)



    @commands.command(name="unbotbl", help="Retire de la blacklist-bot. &unbotbl <@user|ID>")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def unbotbl(self, ctx, cible: str):
        membre = await self._resoudre_membre(ctx, cible)
        uid = membre.id if membre else (int(cible.strip("<@!>")) if cible.strip("<@!>").isdigit() else None)
        if uid is None:
            return await ctx.reply(embed=h.err_embed("Mention ou ID invalide."))
        await self.bot.db.blacklist_remove(ctx.guild.id, uid)
        await ctx.reply(embed=h.ok_embed(f"`{uid}` retiré de la liste noire."))

    @commands.command(name="botblinfo", help="Infos blacklist-bot. &botblinfo <@user|ID>")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def botblinfo(self, ctx, cible: str):
        membre = await self._resoudre_membre(ctx, cible)
        uid = membre.id if membre else (int(cible.strip("<@!>")) if cible.strip("<@!>").isdigit() else None)
        if uid is None:
            return await ctx.reply(embed=h.err_embed("Mention ou ID invalide."))
        blackliste = await self.bot.db.is_blacklisted(ctx.guild.id, uid)
        nom = str(membre) if membre else f"`{uid}`"
        e = h.base_embed(
            f"Blacklist — {nom}",
            f"Statut : **{'BLACKLISTÉ' if blackliste else 'non blacklisté'}**",
            config.COLOR_ERROR if blackliste else config.COLOR_SUCCESS,
        )
        await ctx.reply(embed=e)


# ==============================================================================
#  SECTION 11 - STATS VOCALES & VOCAL
# ==============================================================================






class VoiceStats(commands.Cog):
    """Panneau de stats vocales et outils vocaux."""

    def __init__(self, bot):
        self.bot = bot

    # ================================================================ panneau de stats

    def _compter(self, guild: discord.Guild):
        en_ligne = en_vocal = en_stream = camera = 0
        for m in guild.members:
            if m.bot:
                continue
            if m.status is not discord.Status.offline:
                en_ligne += 1
            vs = m.voice
            if vs and vs.channel:
                en_vocal += 1
                if vs.self_stream:
                    en_stream += 1
                if vs.self_video:
                    camera += 1
        return en_ligne, en_vocal, en_stream, camera

    @commands.command(name="vc", aliases=["vcstats", "voicestats", "statsvocal"],
                      help="Panneau de statistiques vocales du serveur.")
    @commands.guild_only()
    @commands.cooldown(config.COOLDOWN_RATE, config.COOLDOWN_PER, commands.BucketType.guild)
    async def vc(self, ctx):
        g = ctx.guild
        en_ligne, en_vocal, en_stream, camera = self._compter(g)
        humains = sum(1 for m in g.members if not m.bot)

        e = h.base_embed(f"\U0001f3c6 {g.name} — Statistiques")
        e.description = (
            f"*Membres :* **{g.member_count:,}**\n"
            f"*En ligne :* **{en_ligne:,}**\n"
            f"*En vocal :* **{en_vocal:,}**\n"
            f"*En stream :* **{en_stream:,}**\n"
            f"*Caméra :* **{camera:,}**\n"
            f"*Boosts :* **{g.premium_subscription_count}** "
            f"(niveau {g.premium_tier})"
        )
        if g.icon:
            e.set_thumbnail(url=g.icon.url)
        if g.banner:
            e.set_image(url=g.banner.url)
        e.set_footer(text=f"{humains:,} humains · {g.member_count - humains:,} bots")
        await ctx.reply(embed=e)

    @commands.command(name="vcusers", aliases=["invc", "envocal"],
                      help="Liste les membres actuellement en vocal.")
    @commands.guild_only()
    async def vcusers(self, ctx):
        blocs = []
        for salon in g_voice(ctx.guild):
            membres = [m for m in salon.members if not m.bot]
            if not membres:
                continue
            noms = ", ".join(m.display_name for m in membres)
            blocs.append(f"**{salon.name}** ({len(membres)})\n{h.clean(noms, 400)}")
        if not blocs:
            return await ctx.reply(embed=h.base_embed(description="Personne en vocal."))
        total = sum(len([m for m in s.members if not m.bot]) for s in g_voice(ctx.guild))
        await ctx.reply(
            embed=h.base_embed(f"En vocal — {total} membre(s)", "\n\n".join(blocs)[:4000])
        )

    # ================================================================ tempban / tempactions

    @commands.command(name="tempban", help="+tempban @membre 2d raison — ban avec fin auto.")
    @commands.guild_only()
    @h.is_owner_or(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def tempban(self, ctx, user: discord.User, duree: str, *, reason: str = ""):
        secondes = h.parse_duration(duree)
        if not secondes:
            return await ctx.reply(
                embed=h.err_embed("Durée invalide. Ex : `+tempban @x 2d spam`.")
            )
        membre = ctx.guild.get_member(user.id)
        if membre:
            allowed, why = h.hierarchy_ok(ctx.author, membre)
            if not allowed:
                return await ctx.reply(embed=h.err_embed(why))
            allowed, why = h.bot_can_act(ctx.guild.me, membre)
            if not allowed:
                return await ctx.reply(embed=h.err_embed(why))
            e = h.base_embed(
                f"Tu as été banni temporairement de {ctx.guild.name}",
                color=config.COLOR_ERROR,
            )
            e.add_field(name="Raison", value=h.clean(reason) or "aucune", inline=False)
            e.add_field(name="Durée", value=h.human_duration(secondes), inline=False)
            await h.safe_dm(membre, e)

        await ctx.guild.ban(
            user, reason=f"Tempban par {ctx.author}: {reason}", delete_message_days=0
        )
        await self.bot.db.schedule(ctx.guild.id, user.id, "ban", h.now() + secondes)
        case_id = await self.bot.db.add_case(
            ctx.guild.id, user.id, ctx.author.id, "tempban", reason, secondes
        )
        await ctx.reply(
            embed=h.ok_embed(
                f"**{user}** banni pour **{h.human_duration(secondes)}** "
                f"(fin {h.ts(h.now() + secondes)}). Dossier `#{case_id}`"
            )
        )

    @commands.command(name="temprole", help="+temprole @membre @role 1h — rôle temporaire.")
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def temprole(self, ctx, membre: discord.Member, role: discord.Role, duree: str):
        secondes = h.parse_duration(duree)
        if not secondes:
            return await ctx.reply(embed=h.err_embed("Durée invalide."))
        if role >= ctx.guild.me.top_role:
            return await ctx.reply(embed=h.err_embed("Ce rôle est au-dessus du mien."))
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.reply(embed=h.err_embed("Ce rôle est au-dessus du tien."))
        await membre.add_roles(role, reason=f"Rôle temporaire par {ctx.author}")
        await self.bot.db.schedule(
            ctx.guild.id, membre.id, "temprole", h.now() + secondes, {"role": role.id}
        )
        await ctx.reply(
            embed=h.ok_embed(
                f"{role.mention} donné à {membre.mention} pour "
                f"**{h.human_duration(secondes)}** (retrait {h.ts(h.now() + secondes)})."
            )
        )

    # ================================================================ vocal courtes

    @commands.command(name="move", help="+move <@user|ID> [salon] — déplace en vocal.")
    @commands.guild_only()
    @h.is_owner_or(move_members=True)
    async def move(self, ctx, cible: str, *, salon: discord.VoiceChannel = None):
        membre, err = await h.resolve_member(ctx.guild, cible)
        if err:
            return await ctx.reply(embed=h.err_embed(err))
        if membre.voice is None:
            return await ctx.reply(embed=h.err_embed("Ce membre n'est pas en vocal."))
        # Sans salon indiqué : on l'amène dans le tien.
        if salon is None:
            if ctx.author.voice is None:
                return await ctx.reply(
                    embed=h.err_embed("Indique un salon, ou sois toi-même en vocal.")
                )
            salon = ctx.author.voice.channel
        await membre.move_to(salon, reason=f"Déplacé par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"**{membre}** déplacé vers {salon.mention}."))

    @commands.command(name="setrole", help="+setrole <@user|ID> <nom du rôle> — donne un rôle par son nom.")
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def setrole(self, ctx, cible: str, *, nom_role: str):
        membre, err = await h.resolve_member(ctx.guild, cible)
        if err:
            return await ctx.reply(embed=h.err_embed(err))
        role = discord.utils.find(
            lambda r: r.name.lower() == nom_role.lower(), ctx.guild.roles
        )
        if role is None:
            role = discord.utils.find(
                lambda r: nom_role.lower() in r.name.lower(), ctx.guild.roles
            )
        if role is None:
            return await ctx.reply(
                embed=h.err_embed(f"Aucun rôle nommé « {h.clean(nom_role, 50)} ».")
            )
        if role >= ctx.guild.me.top_role:
            return await ctx.reply(embed=h.err_embed("Ce rôle est au-dessus du mien."))
        if role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.reply(embed=h.err_embed("Ce rôle est au-dessus du tien."))
        if role in membre.roles:
            await membre.remove_roles(role, reason=f"Par {ctx.author}")
            await ctx.reply(embed=h.ok_embed(f"{role.mention} retiré à {membre.mention}."))
        else:
            await membre.add_roles(role, reason=f"Par {ctx.author}")
            await ctx.reply(embed=h.ok_embed(f"{role.mention} donné à {membre.mention}."))

    @commands.command(name="vcmove", help="+vcmove @membre <salon vocal>")
    @commands.guild_only()
    @h.is_owner_or(move_members=True)
    async def vcmove(self, ctx, membre: discord.Member, *, salon: discord.VoiceChannel):
        if not membre.voice:
            return await ctx.reply(embed=h.err_embed("Ce membre n'est pas en vocal."))
        await membre.move_to(salon, reason=f"Déplacé par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"**{membre}** déplacé vers {salon.mention}."))

    @commands.command(name="summon", aliases=["pull"],
                      help="Tire un membre dans ton salon vocal.")
    @commands.guild_only()
    @h.is_owner_or(move_members=True)
    async def summon(self, ctx, membre: discord.Member):
        if not ctx.author.voice:
            return await ctx.reply(embed=h.err_embed("Tu dois être en vocal."))
        if not membre.voice:
            return await ctx.reply(embed=h.err_embed("Ce membre n'est pas en vocal."))
        await membre.move_to(ctx.author.voice.channel,
                             reason=f"Convoqué par {ctx.author}")
        await ctx.reply(
            embed=h.ok_embed(f"**{membre}** amené dans {ctx.author.voice.channel.mention}.")
        )

    @commands.command(name="vclock", help="Verrouille un salon vocal (personne ne rejoint).")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def vclock(self, ctx, salon: discord.VoiceChannel = None):
        salon = salon or (ctx.author.voice.channel if ctx.author.voice else None)
        if not salon:
            return await ctx.reply(embed=h.err_embed("Indique un salon vocal."))
        ow = salon.overwrites_for(ctx.guild.default_role)
        ow.connect = False
        await salon.set_permissions(ctx.guild.default_role, overwrite=ow,
                                    reason=f"Verrou par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"{salon.mention} verrouillé."))

    @commands.command(name="vcunlock")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def vcunlock(self, ctx, salon: discord.VoiceChannel = None):
        salon = salon or (ctx.author.voice.channel if ctx.author.voice else None)
        if not salon:
            return await ctx.reply(embed=h.err_embed("Indique un salon vocal."))
        ow = salon.overwrites_for(ctx.guild.default_role)
        ow.connect = None
        await salon.set_permissions(ctx.guild.default_role, overwrite=ow,
                                    reason=f"Déverrou par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"{salon.mention} déverrouillé."))

    @commands.command(name="vclimit", help="+vclimit 5 — limite le salon vocal courant.")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def vclimit(self, ctx, nombre: int, salon: discord.VoiceChannel = None):
        salon = salon or (ctx.author.voice.channel if ctx.author.voice else None)
        if not salon:
            return await ctx.reply(embed=h.err_embed("Indique un salon vocal."))
        nombre = max(0, min(nombre, 99))
        await salon.edit(user_limit=nombre)
        texte = "illimitée" if nombre == 0 else f"**{nombre}**"
        await ctx.reply(embed=h.ok_embed(f"Limite de {salon.mention} : {texte}."))

    @commands.command(name="muteall", help="Coupe le micro de tout le vocal.")
    @commands.guild_only()
    @h.is_owner_or(mute_members=True)
    async def muteall(self, ctx, salon: discord.VoiceChannel = None):
        salon = salon or (ctx.author.voice.channel if ctx.author.voice else None)
        if not salon:
            return await ctx.reply(embed=h.err_embed("Indique un salon vocal."))
        fait = 0
        async with ctx.typing():
            for membre in salon.members:
                if membre.bot or membre.id == ctx.author.id:
                    continue
                try:
                    await membre.edit(mute=True, reason=f"Muteall par {ctx.author}")
                    fait += 1
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.3)
        await ctx.reply(embed=h.ok_embed(f"Micro coupé pour **{fait}** membres."))

    @commands.command(name="unmuteall")
    @commands.guild_only()
    @h.is_owner_or(mute_members=True)
    async def unmuteall(self, ctx, salon: discord.VoiceChannel = None):
        salon = salon or (ctx.author.voice.channel if ctx.author.voice else None)
        if not salon:
            return await ctx.reply(embed=h.err_embed("Indique un salon vocal."))
        fait = 0
        async with ctx.typing():
            for membre in salon.members:
                if membre.bot:
                    continue
                try:
                    await membre.edit(mute=False, reason=f"Unmuteall par {ctx.author}")
                    fait += 1
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.3)
        await ctx.reply(embed=h.ok_embed(f"Micro rétabli pour **{fait}** membres."))

    @commands.command(name="followme", aliases=["rassemble"],
                      help="Amène tous les membres d'un rôle dans ton salon vocal.")
    @commands.guild_only()
    @h.is_owner_or(move_members=True)
    async def followme(self, ctx, *, role: discord.Role):
        if not ctx.author.voice:
            return await ctx.reply(embed=h.err_embed("Tu dois être en vocal."))
        cible = ctx.author.voice.channel
        membres = [m for m in role.members if m.voice and m.voice.channel != cible]
        if not membres:
            return await ctx.reply(embed=h.warn_embed("Personne à déplacer."))
        fait = 0
        async with ctx.typing():
            for membre in membres:
                try:
                    await membre.move_to(cible, reason=f"Rassemblement par {ctx.author}")
                    fait += 1
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.3)
        await ctx.reply(
            embed=h.ok_embed(f"**{fait}** membres de {role.mention} amenés dans "
                             f"{cible.mention}.")
        )


def g_voice(guild):
    return guild.voice_channels


# ==============================================================================
#  SECTION 12 - EXTRAS (rôles, salons, émojis, notes)
# ==============================================================================






class Extras(commands.Cog):
    """Gestion avancée : rôles, salons, émojis, notes."""

    def __init__(self, bot):
        self.bot = bot

    # ================================================================ notes de modération

    @commands.command(name="note", help="Ajoute une note interne sur un membre.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def note(self, ctx, membre: discord.Member, *, texte: str):
        note_id = await self.bot.db.add_note(
            ctx.guild.id, membre.id, ctx.author.id, h.clean(texte, 800)
        )
        await ctx.reply(embed=h.ok_embed(f"Note `#{note_id}` ajoutée sur **{membre}**."))

    @commands.command(name="notes", help="Affiche les notes internes d'un membre.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def notes(self, ctx, membre: discord.Member):
        rows = await self.bot.db.get_notes(ctx.guild.id, membre.id)
        if not rows:
            return await ctx.reply(embed=h.base_embed(description=f"Aucune note sur **{membre}**."))
        e = h.base_embed(f"Notes — {membre}", color=config.COLOR_WARN)
        for r in rows[:15]:
            mod = ctx.guild.get_member(r["mod_id"])
            e.add_field(
                name=f"#{r['id']} · {h.ts(r['created_at'])}",
                value=f"{h.clean(r['note'], 300)}\n— {mod.mention if mod else r['mod_id']}",
                inline=False,
            )
        await ctx.reply(embed=e)

    @commands.command(name="delnote", help="Supprime une note par son ID.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def delnote(self, ctx, note_id: int):
        await self.bot.db.del_note(note_id, ctx.guild.id)
        await ctx.reply(embed=h.ok_embed(f"Note `#{note_id}` supprimée."))

    # ================================================================ rôles

    @commands.command(name="createrole", aliases=["addrole", "newrole"],
                      help="&createrole <nom> [#couleur]")
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def createrole(self, ctx, nom: str, couleur: str = None):
        c = discord.Colour.default()
        if couleur:
            try:
                c = discord.Colour(int(couleur.lstrip("#"), 16))
            except ValueError:
                pass
        role = await ctx.guild.create_role(name=nom[:100], colour=c,
                                           reason=f"Créé par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"Rôle {role.mention} créé."))

    @commands.command(name="deleterole", aliases=["delrole"], help="Supprime un rôle.")
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def deleterole(self, ctx, *, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            return await ctx.reply(embed=h.err_embed("Ce rôle est au-dessus du mien."))
        nom = role.name
        await role.delete(reason=f"Supprimé par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"Rôle **{nom}** supprimé."))

    @commands.command(name="rolecolor", aliases=["rolecolour"],
                      help="&rolecolor @role #5865F2")
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def rolecolor(self, ctx, role: discord.Role, couleur: str):
        try:
            c = discord.Colour(int(couleur.lstrip("#"), 16))
        except ValueError:
            return await ctx.reply(embed=h.err_embed("Couleur invalide : `#5865F2`."))
        await role.edit(colour=c, reason=f"Par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"Couleur de {role.mention} changée."))

    @commands.command(name="rolename", help="&rolename @role <nouveau nom>")
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def rolename(self, ctx, role: discord.Role, *, nom: str):
        await role.edit(name=nom[:100], reason=f"Par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"Rôle renommé en **{nom[:100]}**."))

    @commands.command(name="hoist", help="Affiche/masque un rôle dans la liste des membres.")
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def hoist(self, ctx, *, role: discord.Role):
        await role.edit(hoist=not role.hoist, reason=f"Par {ctx.author}")
        await ctx.reply(
            embed=h.ok_embed(f"{role.mention} {'affiché à part' if not role.hoist else 'fusionné'}.")
        )

    @commands.command(name="mentionable", help="Rend un rôle mentionnable ou non.")
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def mentionable(self, ctx, *, role: discord.Role):
        await role.edit(mentionable=not role.mentionable, reason=f"Par {ctx.author}")
        etat = "mentionnable" if not role.mentionable else "non mentionnable"
        await ctx.reply(embed=h.ok_embed(f"{role.mention} est maintenant {etat}."))

    @commands.command(name="roles", aliases=["rolelist"], help="Liste tous les rôles.")
    @commands.guild_only()
    async def roles(self, ctx):
        roles = [r for r in reversed(ctx.guild.roles) if r != ctx.guild.default_role]
        texte = ", ".join(f"{r.mention} ({len(r.members)})" for r in roles[:80])
        await ctx.reply(
            embed=h.base_embed(f"Rôles ({len(roles)})", h.clean(texte, 4000))
        )

    @commands.command(name="roleicon", help="Change l'icône d'un rôle (serveur boosté).")
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def roleicon(self, ctx, role: discord.Role, emoji: discord.PartialEmoji):
        try:
            await role.edit(display_icon=await emoji.read(), reason=f"Par {ctx.author}")
        except discord.HTTPException:
            return await ctx.reply(
                embed=h.err_embed("Échec — le serveur doit être boosté (niveau 2).")
            )
        await ctx.reply(embed=h.ok_embed(f"Icône de {role.mention} changée."))

    # ================================================================ salons

    @commands.command(name="createchannel", aliases=["addchannel", "newchannel"],
                      help="&createchannel <nom> [categorie]")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def createchannel(self, ctx, nom: str, *, categorie: discord.CategoryChannel = None):
        salon = await ctx.guild.create_text_channel(
            nom[:100], category=categorie, reason=f"Créé par {ctx.author}"
        )
        await ctx.reply(embed=h.ok_embed(f"Salon {salon.mention} créé."))

    @commands.command(name="createvoice", aliases=["newvoice"],
                      help="Crée un salon vocal.")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def createvoice(self, ctx, nom: str, *, categorie: discord.CategoryChannel = None):
        salon = await ctx.guild.create_voice_channel(
            nom[:100], category=categorie, reason=f"Créé par {ctx.author}"
        )
        await ctx.reply(embed=h.ok_embed(f"Salon vocal **{salon.name}** créé."))

    @commands.command(name="createcategory", aliases=["newcategory"],
                      help="Crée une catégorie.")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def createcategory(self, ctx, *, nom: str):
        cat = await ctx.guild.create_category(nom[:100], reason=f"Créé par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"Catégorie **{cat.name}** créée."))

    @commands.command(name="allchannelcreate", aliases=["setupserver", "buildserver",
                                                        "createall"],
                      help="Construit toute la structure du serveur : catégories, salons écrits et vocaux.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def allchannelcreate(self, ctx):
        # Chaque salon a un "profil" de permissions pour @everyone :
        #   normal    : écrire, images, fichiers, réactions (salon de discussion)
        #   readonly  : lecture seule (annonces, règlement, rôles)
        #   images    : uniquement des images/fichiers, pas de texte seul
        #   staff     : caché à tout le monde sauf staff
        #   hidden    : caché (logs)
        #   voice     : salon vocal normal
        #   voicelock : salon vocal où on ne peut pas parler (compteurs)
        #
        # Plan : (nom_categorie, profil_categorie, [(nom_salon, profil)], [(nom_vocal, profil)])
        PLAN = [
            ("\U0001f4cb Informations", "readonly", [
                ("règlement", "readonly"), ("annonces", "readonly"),
                ("mises-à-jour", "readonly"), ("rôles", "readonly"),
            ], []),
            ("\U0001f4ac Général", "normal", [
                ("général", "normal"), ("discussion", "normal"),
                ("commandes-bot", "normal"), ("memes", "normal"),
                ("photos", "images"),
            ], [("Général", "voice"), ("Musique", "voice")]),
            ("\U0001f3ae Vocal", "voice", [], [
                ("Vocal 1", "voice"), ("Vocal 2", "voice"),
                ("\u300e+\u300f Créer votre salon", "voice"), ("AFK", "voice"),
            ]),
            ("\U0001f3ab Support", "normal", [
                ("ouvrir-un-ticket", "readonly"),
            ], []),
            ("\U0001f4cb Logs", "hidden", [
                ("logs-textuel", "hidden"), ("logs-moderation", "hidden"),
                ("logs-vocal", "hidden"), ("logs-arrivees", "hidden"),
            ], []),
            ("\U0001f4ca Statistiques", "voicelock", [], [
                ("\U0001f465 \u2022 Membres : 0", "voicelock"),
                ("\U0001f7e2 \u2022 En ligne : 0", "voicelock"),
                ("\U0001f50a \u2022 En vocal : 0", "voicelock"),
            ]),
            ("\U0001f6e0\ufe0f Staff", "staff", [
                ("salon-staff", "staff"), ("logs-staff", "staff"),
                ("sanctions", "staff"),
            ], [("Vocal Staff", "staff")]),
        ]

        everyone = ctx.guild.default_role
        me = ctx.guild.me
        # Rôle staff : on prend le premier rôle nommé "staff" / "modérateur" / "admin".
        staff_role = discord.utils.find(
            lambda r: any(x in r.name.lower() for x in ("staff", "modé", "mod", "admin")),
            ctx.guild.roles,
        )

        def perms_pour(profil):
            """Renvoie le dict d'overwrites pour @everyone (+ staff/bot) selon le profil."""
            ow = {me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, connect=True,
                manage_channels=True, read_message_history=True)}
            if profil == "normal":
                ow[everyone] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, attach_files=True,
                    embed_links=True, add_reactions=True, read_message_history=True)
            elif profil == "readonly":
                ow[everyone] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=False, add_reactions=False,
                    read_message_history=True)
            elif profil == "images":
                # Voir + envoyer + joindre des fichiers ; le filtrage "texte seul
                # interdit" est assuré par le système mediaonly (voir plus bas).
                ow[everyone] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, attach_files=True,
                    embed_links=True, add_reactions=True, read_message_history=True)
            elif profil == "staff":
                ow[everyone] = discord.PermissionOverwrite(view_channel=False)
                if staff_role:
                    ow[staff_role] = discord.PermissionOverwrite(
                        view_channel=True, send_messages=True, connect=True,
                        read_message_history=True)
            elif profil == "hidden":
                ow[everyone] = discord.PermissionOverwrite(view_channel=False)
                if staff_role:
                    ow[staff_role] = discord.PermissionOverwrite(
                        view_channel=True, read_message_history=True)
            elif profil == "voice":
                ow[everyone] = discord.PermissionOverwrite(
                    view_channel=True, connect=True, speak=True)
            elif profil == "voicelock":
                # Salon vitrine (compteurs) : visible mais on ne peut pas s'y connecter.
                ow[everyone] = discord.PermissionOverwrite(
                    view_channel=True, connect=False)
            return ow

        confirm = await ctx.reply(
            embed=h.warn_embed(
                f"Je vais créer **{len(PLAN)}** catégories avec leurs salons, "
                f"**et poser les permissions de chaque salon** selon son usage "
                f"(général = tout ; photos = images ; annonces = lecture seule ; "
                f"staff/logs = cachés).\n\nTape `confirm` sous 20 secondes."
            )
        )
        try:
            await self.bot.wait_for(
                "message", timeout=20,
                check=lambda mm: mm.author == ctx.author and mm.channel == ctx.channel
                and mm.content.lower() == "confirm",
            )
        except asyncio.TimeoutError:
            return await confirm.edit(embed=h.err_embed("Annulé."))

        cats = txt = voc = 0
        salons_images = []  # pour activer le mode "photos uniquement" ensuite
        status = await ctx.send(embed=h.base_embed("Construction", "En cours..."))
        for nom_cat, profil_cat, salons_txt, salons_voc in PLAN:
            try:
                categorie = await ctx.guild.create_category(
                    nom_cat, overwrites=perms_pour(profil_cat),
                    reason=f"allchannelcreate par {ctx.author}",
                )
                cats += 1
            except discord.HTTPException:
                continue
            await asyncio.sleep(0.4)
            for nom_salon, profil in salons_txt:
                try:
                    salon = await ctx.guild.create_text_channel(
                        nom_salon, category=categorie,
                        overwrites=perms_pour(profil),
                        reason=f"allchannelcreate par {ctx.author}",
                    )
                    txt += 1
                    if profil == "images":
                        salons_images.append(salon.id)
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.4)
            for nom_salon, profil in salons_voc:
                try:
                    await ctx.guild.create_voice_channel(
                        nom_salon, category=categorie,
                        overwrites=perms_pour(profil),
                        reason=f"allchannelcreate par {ctx.author}",
                    )
                    voc += 1
                except discord.HTTPException:
                    pass
                await asyncio.sleep(0.4)
            try:
                await status.edit(
                    embed=h.base_embed(
                        "Construction",
                        f"**{cats}** catégories · **{txt}** salons écrits · "
                        f"**{voc}** vocaux...",
                    )
                )
            except discord.HTTPException:
                pass

        # Active automatiquement le mode "photos uniquement" sur les salons images.
        for cid in salons_images:
            try:
                await self.bot.db.add_media_channel(cid, ctx.guild.id, 10)
            except Exception:
                pass

        await status.edit(
            embed=h.ok_embed(
                f"Serveur construit :\n"
                f"**{cats}** catégories · **{txt}** salons écrits · "
                f"**{voc}** salons vocaux.\n\n"
                f"**Permissions posées automatiquement :** général = tout, "
                f"#photos = images uniquement, annonces/règlement = lecture seule, "
                f"staff/logs = cachés, compteurs = verrouillés.\n\n"
                f"Pense à lancer `{ctx.prefix}setlogs`, `{ctx.prefix}compteurs setup` "
                f"et `{ctx.prefix}voice setup` pour relier logs, compteurs et "
                f"salons temporaires."
            )
        )

    @commands.command(name="deletechannel", aliases=["delchannel"],
                      help="Supprime un salon.")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def deletechannel(self, ctx, salon: discord.abc.GuildChannel = None):
        salon = salon or ctx.channel
        nom = salon.name
        await salon.delete(reason=f"Supprimé par {ctx.author}")
        if salon != ctx.channel:
            await ctx.reply(embed=h.ok_embed(f"Salon **{nom}** supprimé."))

    @commands.command(name="renamechannel", aliases=["setname"],
                      help="Renomme un salon.")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def renamechannel(self, ctx, *, nom: str):
        await ctx.channel.edit(name=nom[:100], reason=f"Par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"Salon renommé en **{nom[:100]}**."))

    @commands.command(name="settopic", aliases=["topic"], help="Définit le sujet du salon.")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def settopic(self, ctx, *, sujet: str = ""):
        await ctx.channel.edit(topic=sujet[:1024], reason=f"Par {ctx.author}")
        await ctx.reply(embed=h.ok_embed("Sujet du salon mis à jour."))

    @commands.command(name="nsfw", help="Active/désactive le mode NSFW du salon.")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def nsfw(self, ctx):
        await ctx.channel.edit(nsfw=not ctx.channel.is_nsfw(), reason=f"Par {ctx.author}")
        await ctx.reply(
            embed=h.ok_embed(f"NSFW **{'activé' if not ctx.channel.is_nsfw() else 'désactivé'}**.")
        )

    @commands.command(name="hidechannel", aliases=["hide"], help="Masque le salon à @everyone.")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def hidechannel(self, ctx, salon: discord.TextChannel = None):
        salon = salon or ctx.channel
        ow = salon.overwrites_for(ctx.guild.default_role)
        ow.view_channel = False
        await salon.set_permissions(ctx.guild.default_role, overwrite=ow,
                                    reason=f"Par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"{salon.mention} masqué."))

    @commands.command(name="showchannel", aliases=["unhide"], help="Réaffiche le salon.")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def showchannel(self, ctx, salon: discord.TextChannel = None):
        salon = salon or ctx.channel
        ow = salon.overwrites_for(ctx.guild.default_role)
        ow.view_channel = None
        await salon.set_permissions(ctx.guild.default_role, overwrite=ow,
                                    reason=f"Par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"{salon.mention} de nouveau visible."))

    @commands.command(name="clone", help="Clone le salon courant.")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def clone(self, ctx):
        nouveau = await ctx.channel.clone(reason=f"Cloné par {ctx.author}")
        await nouveau.edit(position=ctx.channel.position + 1)
        await ctx.reply(embed=h.ok_embed(f"Salon cloné : {nouveau.mention}"))

    # ================================================================ épingles

    @commands.command(name="pin", help="Épingle le dernier message (ou par ID).")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def pin(self, ctx, message_id: int = None):
        if message_id:
            msg = await ctx.channel.fetch_message(message_id)
        else:
            historique = [m async for m in ctx.channel.history(limit=2)]
            msg = historique[-1] if historique else None
        if not msg:
            return await ctx.reply(embed=h.err_embed("Message introuvable."))
        await msg.pin(reason=f"Par {ctx.author}")
        await ctx.reply(embed=h.ok_embed("Message épinglé."))

    @commands.command(name="unpin", help="Désépingle un message par ID.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def unpin(self, ctx, message_id: int):
        msg = await ctx.channel.fetch_message(message_id)
        await msg.unpin(reason=f"Par {ctx.author}")
        await ctx.reply(embed=h.ok_embed("Message désépinglé."))

    @commands.command(name="unpinall", help="Désépingle tous les messages du salon.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def unpinall(self, ctx):
        pins = await ctx.channel.pins()
        for msg in pins:
            try:
                await msg.unpin()
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.3)
        await ctx.reply(embed=h.ok_embed(f"**{len(pins)}** messages désépinglés."))

    # ================================================================ émojis & stickers

    @commands.command(name="addemoji", help="&addemoji <nom> (avec une image jointe)")
    @commands.guild_only()
    @h.is_owner_or(manage_expressions=True)
    @commands.bot_has_permissions(manage_expressions=True)
    async def addemoji(self, ctx, nom: str):
        if not ctx.message.attachments:
            return await ctx.reply(embed=h.err_embed("Joins une image au message."))
        octets = await ctx.message.attachments[0].read()
        try:
            emoji = await ctx.guild.create_custom_emoji(
                name=nom[:32], image=octets, reason=f"Par {ctx.author}"
            )
        except discord.HTTPException:
            return await ctx.reply(embed=h.err_embed("Échec (taille ou limite atteinte)."))
        await ctx.reply(embed=h.ok_embed(f"Émoji ajouté : {emoji}"))

    @commands.command(name="delemoji", help="Supprime un émoji du serveur.")
    @commands.guild_only()
    @h.is_owner_or(manage_expressions=True)
    @commands.bot_has_permissions(manage_expressions=True)
    async def delemoji(self, ctx, emoji: discord.Emoji):
        nom = emoji.name
        await emoji.delete(reason=f"Par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"Émoji **{nom}** supprimé."))

    @commands.command(name="renameemoji", help="Renomme un émoji.")
    @commands.guild_only()
    @h.is_owner_or(manage_expressions=True)
    @commands.bot_has_permissions(manage_expressions=True)
    async def renameemoji(self, ctx, emoji: discord.Emoji, nom: str):
        await emoji.edit(name=nom[:32], reason=f"Par {ctx.author}")
        await ctx.reply(embed=h.ok_embed(f"Émoji renommé en `{nom[:32]}`."))

    @commands.command(name="enlarge", aliases=["jumbo", "bigemoji"],
                      help="Agrandit un émoji personnalisé.")
    @commands.guild_only()
    async def enlarge(self, ctx, emoji: discord.PartialEmoji):
        e = h.base_embed(emoji.name)
        e.set_image(url=emoji.url)
        await ctx.reply(embed=e)

    # ================================================================ divers staff

    @commands.command(name="editmsg", help="Modifie un message envoyé par le bot.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def editmsg(self, ctx, message_id: int, *, contenu: str):
        try:
            msg = await ctx.channel.fetch_message(message_id)
        except discord.HTTPException:
            return await ctx.reply(embed=h.err_embed("Message introuvable."))
        if msg.author.id != self.bot.user.id:
            return await ctx.reply(embed=h.err_embed("Je ne peux modifier que mes propres messages."))
        if msg.embeds:
            e = msg.embeds[0]
            e.description = h.clean(contenu, 4000)
            await msg.edit(embed=e)
        else:
            await msg.edit(content=h.clean(contenu, 1900))
        await ctx.reply(embed=h.ok_embed("Message modifié."), delete_after=6)

    @commands.command(name="react", help="&react <message_id> <emoji>")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    @commands.bot_has_permissions(add_reactions=True)
    async def react(self, ctx, message_id: int, emoji: str):
        try:
            msg = await ctx.channel.fetch_message(message_id)
            await msg.add_reaction(emoji)
        except discord.HTTPException:
            return await ctx.reply(embed=h.err_embed("Impossible d'ajouter cette réaction."))
        await ctx.message.delete()

    @commands.command(name="echo", help="Répète ton texte dans un salon.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def echo(self, ctx, salon: discord.TextChannel, *, texte: str):
        await salon.send(h.clean(texte, 1900))
        await ctx.reply(embed=h.ok_embed(f"Envoyé dans {salon.mention}."), delete_after=6)

    @commands.command(name="dmall", help="Envoie un MP à tous les membres d'un rôle.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def dmall(self, ctx, role: discord.Role, *, message: str):
        membres = [m for m in role.members if not m.bot]
        if len(membres) > 50:
            return await ctx.reply(
                embed=h.err_embed("Limité à 50 membres pour éviter le spam massif.")
            )
        confirm = await ctx.reply(
            embed=h.warn_embed(f"Envoyer ce MP à **{len(membres)}** membres ? "
                               f"Tape `confirm` sous 20s.")
        )
        try:
            await self.bot.wait_for(
                "message", timeout=20,
                check=lambda m: m.author == ctx.author and m.channel == ctx.channel
                and m.content.lower() == "confirm",
            )
        except asyncio.TimeoutError:
            return await confirm.edit(embed=h.err_embed("Annulé."))
        envoyes = 0
        e = h.base_embed(f"Message de {ctx.guild.name}", h.clean(message, 3000))
        for membre in membres:
            if await h.safe_dm(membre, e):
                envoyes += 1
            await asyncio.sleep(1)
        await ctx.send(embed=h.ok_embed(f"MP envoyé à **{envoyes}/{len(membres)}**."))

    @commands.command(name="poll3", aliases=["timedpoll"],
                      help="Sondage minuté. -poll3 1h Question")
    @commands.guild_only()
    async def timedpoll(self, ctx, duree: str, *, question: str):
        secondes = h.parse_duration(duree)
        if not secondes or secondes > 86400:
            return await ctx.reply(embed=h.err_embed("Durée entre 1s et 24h."))
        e = h.base_embed("\U0001f4ca " + h.clean(question, 250),
                         f"Vote — fin {h.ts(h.now() + secondes)}\n— {ctx.author.mention}")
        msg = await ctx.send(embed=e)
        await msg.add_reaction("\u2705")
        await msg.add_reaction("\u274c")
        await asyncio.sleep(secondes)
        try:
            msg = await ctx.channel.fetch_message(msg.id)
            oui = discord.utils.get(msg.reactions, emoji="\u2705")
            non = discord.utils.get(msg.reactions, emoji="\u274c")
            po = (oui.count - 1) if oui else 0
            pn = (non.count - 1) if non else 0
            verdict = "Oui l'emporte" if po > pn else "Non l'emporte" if pn > po else "Égalité"
            await ctx.send(
                embed=h.base_embed(
                    "Sondage terminé",
                    f"**{h.clean(question, 250)}**\n\u2705 {po} · \u274c {pn}\n\n**{verdict}**",
                )
            )
        except discord.HTTPException:
            pass

    @commands.command(name="clearreactions", aliases=["clearreacts"],
                      help="Retire toutes les réactions d'un message.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clearreactions(self, ctx, message_id: int):
        msg = await ctx.channel.fetch_message(message_id)
        await msg.clear_reactions()
        await ctx.reply(embed=h.ok_embed("Réactions retirées."))

    @commands.command(name="closeall", aliases=["closeserver", "raidlock"],
                      help="En cas de raid : verrouille TOUS les salons écrits d'un coup.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def closeall(self, ctx):
        status = await ctx.send(embed=h.warn_embed("Verrouillage d'urgence en cours..."))
        verrouilles = 0
        for salon in ctx.guild.text_channels:
            ow = salon.overwrites_for(ctx.guild.default_role)
            if ow.send_messages is False:
                continue
            ow.send_messages = False
            try:
                await salon.set_permissions(ctx.guild.default_role, overwrite=ow,
                                            reason=f"Closeall (raid) par {ctx.author}")
                verrouilles += 1
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.25)
        await status.edit(
            embed=h.ok_embed(
                f"\U0001f512 **{verrouilles}** salons verrouillés.\n"
                f"Rouvre tout avec `{ctx.prefix}openall`."
            )
        )

    @commands.command(name="openall", aliases=["openserver", "raidunlock"],
                      help="Rouvre tous les salons après un closeall.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def openall(self, ctx):
        status = await ctx.send(embed=h.base_embed("Réouverture", "En cours..."))
        ouverts = 0
        for salon in ctx.guild.text_channels:
            ow = salon.overwrites_for(ctx.guild.default_role)
            if ow.send_messages is not False:
                continue
            ow.send_messages = None
            try:
                await salon.set_permissions(ctx.guild.default_role, overwrite=ow,
                                            reason=f"Openall par {ctx.author}")
                ouverts += 1
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.25)
        await status.edit(embed=h.ok_embed(f"\U0001f513 **{ouverts}** salons rouverts."))

    @commands.command(name="msg", aliases=["mp"],
                      help="+msg <userid> <message> — envoie un MP à un membre.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def msg(self, ctx, cible: str, *, message: str):
        uid = cible.strip("<@!>")
        if not uid.isdigit():
            return await ctx.reply(embed=h.err_embed("Donne une mention ou un ID valide."))
        membre = ctx.guild.get_member(int(uid))
        if membre is None:
            try:
                membre = await ctx.guild.fetch_member(int(uid))
            except discord.NotFound:
                return await ctx.reply(
                    embed=h.err_embed("Ce membre n'est pas sur le serveur.")
                )
            except discord.HTTPException:
                return await ctx.reply(embed=h.err_embed("ID introuvable."))
        e = h.base_embed(f"Message de {ctx.guild.name}", h.clean(message, 3000))
        e.set_footer(text=f"Envoyé par le staff · {ctx.author}")
        if await h.safe_dm(membre, e):
            await ctx.reply(embed=h.ok_embed(f"MP envoyé à **{membre}**."), delete_after=8)
        else:
            await ctx.reply(embed=h.err_embed("Ses MP sont fermés."))

    @commands.command(name="rep", aliases=["reply", "repondre"],
                      help="+rep <messageid> <message> — répond à un message.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def rep(self, ctx, message_id: int, *, texte: str):
        try:
            cible = await ctx.channel.fetch_message(message_id)
        except discord.HTTPException:
            return await ctx.reply(
                embed=h.err_embed("Message introuvable dans ce salon.")
            )
        try:
            await cible.reply(h.clean(texte, 1900),
                              allowed_mentions=discord.AllowedMentions(users=True))
        except discord.HTTPException:
            return await ctx.reply(embed=h.err_embed("Impossible de répondre."))
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass


# ==============================================================================
#  SECTION 13 - HARDBAN (anti-retour + anti-alt)
# ==============================================================================


import difflib




def similarite(a: str, b: str) -> float:
    """Ratio 0..1 entre deux pseudos, normalisés (minuscules, sans espaces)."""
    a = "".join(a.lower().split())
    b = "".join(b.lower().split())
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


class HardBan(commands.Cog):
    """Bannissement renforcé anti-retour et anti-alt."""

    def __init__(self, bot):
        self.bot = bot

    async def _log(self, guild, embed):
        cfg = await self.bot.db.hardban_config(guild.id)
        chan_id = cfg["log_channel"]
        if not chan_id:
            row = await self.bot.db.guild_settings(guild.id)
            chan_id = row["mod_log"] if row else None
        if chan_id:
            salon = guild.get_channel(chan_id)
            if salon:
                try:
                    await salon.send(embed=embed)
                except discord.HTTPException:
                    pass

    # ================================================================ commandes

    @commands.command(name="hardban", aliases=["hb", "bl"],
                      help="&hardban <@user|ID> [raison] — ban anti-retour + anti-alt.")
    @commands.guild_only()
    @h.is_owner_or(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def hardban(self, ctx, cible: str, *, reason: str = ""):
        cible_id = cible.strip("<@!>")
        if not cible_id.isdigit():
            return await ctx.reply(embed=h.err_embed("Donne une mention ou un ID valide."))
        cible_id = int(cible_id)

        if cible_id == ctx.author.id:
            return await ctx.reply(embed=h.err_embed("Tu ne peux pas te hardban toi-même."))
        if cible_id == ctx.guild.owner_id:
            return await ctx.reply(embed=h.err_embed("C'est le propriétaire du serveur."))

        membre = ctx.guild.get_member(cible_id)
        if membre:
            allowed, why = h.hierarchy_ok(ctx.author, membre)
            if not allowed:
                return await ctx.reply(embed=h.err_embed(why))
            allowed, why = h.bot_can_act(ctx.guild.me, membre)
            if not allowed:
                return await ctx.reply(embed=h.err_embed(why))
            nom = membre.name
        else:
            try:
                user = await self.bot.fetch_user(cible_id)
                nom = user.name
            except discord.HTTPException:
                nom = "inconnu"

        # Ban Discord + enregistrement du hardban.
        try:
            await ctx.guild.ban(
                discord.Object(id=cible_id),
                reason=f"HARDBAN par {ctx.author}: {reason or 'aucune raison'}",
                delete_message_days=1,
            )
        except discord.HTTPException as exc:
            return await ctx.reply(embed=h.err_embed(f"Échec du ban : {exc}"))

        await self.bot.db.add_hardban(
            ctx.guild.id, cible_id, ctx.author.id, reason, nom
        )
        await self.bot.db.add_case(
            ctx.guild.id, cible_id, ctx.author.id, "hardban", reason
        )

        e = h.ok_embed(
            f"**{nom}** (`{cible_id}`) hardban.\n"
            f"Le retour avec ce compte est bloqué, et tout alt évident "
            f"(compte récent au pseudo proche) sera banni automatiquement à "
            f"l'arrivée."
            + (f"\n**Raison :** {h.clean(reason, 200)}" if reason else "")
        )
        await ctx.reply(embed=e)
        await self._log(
            ctx.guild,
            h.base_embed(
                f"{config.EMOJI['hammer']} Hardban",
                f"**Cible :** {nom} `{cible_id}`\n"
                f"**Par :** {ctx.author.mention}\n"
                f"**Raison :** {h.clean(reason) or 'aucune'}",
                config.COLOR_ERROR,
            ),
        )

    @commands.command(name="unhardban", aliases=["unhb", "unbl"],
                      help="Lève un hardban. &unhardban <ID>")
    @commands.guild_only()
    @h.is_owner_or(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unhardban(self, ctx, user_id: int, *, reason: str = ""):
        row = await self.bot.db.get_hardban(ctx.guild.id, user_id)
        if not row:
            return await ctx.reply(embed=h.warn_embed("Cet ID n'est pas hardban."))
        await self.bot.db.remove_hardban(ctx.guild.id, user_id)
        try:
            await ctx.guild.unban(discord.Object(id=user_id),
                                  reason=f"Unhardban par {ctx.author}: {reason}")
        except discord.NotFound:
            pass
        await self.bot.db.add_case(
            ctx.guild.id, user_id, ctx.author.id, "unhardban", reason
        )
        await ctx.reply(
            embed=h.ok_embed(f"Hardban levé pour `{user_id}`. Le compte peut revenir.")
        )

    @commands.command(name="hardbans", aliases=["hblist", "bls", "bllist"],
                      help="Liste les comptes hardban.")
    @commands.guild_only()
    @h.is_owner_or(ban_members=True)
    async def hardbans(self, ctx):
        rows = await self.bot.db.all_hardbans(ctx.guild.id)
        if not rows:
            return await ctx.reply(embed=h.base_embed(description="Aucun hardban."))
        lignes = [
            f"• `{r['user_id']}` — **{h.clean(r['name'] or '?', 20)}** · "
            f"{h.clean(r['reason'] or 'aucune raison', 50)}"
            for r in rows[:40]
        ]
        e = h.base_embed(f"Hardbans ({len(rows)})", "\n".join(lignes))
        if len(rows) > 40:
            e.set_footer(text=f"40 affichés sur {len(rows)}")
        await ctx.reply(embed=e)

    @commands.group(name="hardbanconfig", aliases=["hbconfig"],
                    invoke_without_command=True,
                    help="Réglages du hardban et de la détection d'alt.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def hbconfig(self, ctx):
        cfg = await self.bot.db.hardban_config(ctx.guild.id)
        log = ctx.guild.get_channel(cfg["log_channel"]) if cfg["log_channel"] else None
        e = h.base_embed(
            f"{config.EMOJI['shield']} Configuration hardban",
            f"**Auto-ban des alts :** "
            f"{'activé' if cfg['autoban_alts'] else 'désactivé'}\n"
            f"**Âge de compte suspect :** moins de **{cfg['max_account_age']}j**\n"
            f"**Salon de logs :** {log.mention if log else '*mod-log par défaut*'}\n\n"
            f"`{ctx.prefix}hbconfig autoban on|off`\n"
            f"`{ctx.prefix}hbconfig age <jours>`\n"
            f"`{ctx.prefix}hbconfig log <#salon>`",
        )
        await ctx.reply(embed=e)

    @hbconfig.command(name="autoban")
    @h.is_owner_or(administrator=True)
    async def hb_autoban(self, ctx, state: str):
        on = state.lower() in ("on", "oui", "true", "1", "yes")
        await self.bot.db.set_hardban_config(ctx.guild.id, "autoban_alts", int(on))
        await ctx.reply(
            embed=h.ok_embed(f"Auto-ban des alts **{'activé' if on else 'désactivé'}**.")
        )

    @hbconfig.command(name="age")
    @h.is_owner_or(administrator=True)
    async def hb_age(self, ctx, jours: int):
        jours = max(0, min(jours, 365))
        await self.bot.db.set_hardban_config(ctx.guild.id, "max_account_age", jours)
        await ctx.reply(
            embed=h.ok_embed(
                f"Un compte de moins de **{jours}j** au pseudo proche d'un hardban "
                f"sera traité comme alt."
            )
        )

    @hbconfig.command(name="log")
    @h.is_owner_or(administrator=True)
    async def hb_log(self, ctx, salon: discord.TextChannel):
        await self.bot.db.set_hardban_config(ctx.guild.id, "log_channel", salon.id)
        await ctx.reply(embed=h.ok_embed(f"Logs hardban dans {salon.mention}."))

    # ================================================================ détection à l'arrivée

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        if not guild.me.guild_permissions.ban_members:
            return

        # 1) Retour direct : l'ID est-il hardban ? (filet si le ban Discord a sauté)
        hb = await self.bot.db.get_hardban(guild.id, member.id)
        if hb:
            try:
                await member.ban(reason="Hardban actif — retour bloqué",
                                 delete_message_days=0)
            except discord.HTTPException:
                return
            await self._log(
                guild,
                h.base_embed(
                    f"{config.EMOJI['shield']} Retour d'un compte hardban bloqué",
                    f"{member} `{member.id}` a tenté de revenir et a été re-banni.",
                    config.COLOR_ERROR,
                ),
            )
            return

        # 2) Détection d'alt
        cfg = await self.bot.db.hardban_config(guild.id)
        if not cfg["autoban_alts"]:
            return

        age_jours = (discord.utils.utcnow() - member.created_at).days
        if age_jours > cfg["max_account_age"]:
            return  # compte trop vieux pour être un alt évident

        hardbans = await self.bot.db.all_hardbans(guild.id)
        if not hardbans:
            return

        meilleur = 0.0
        source = None
        for r in hardbans:
            if not r["name"]:
                continue
            score = max(
                similarite(member.name, r["name"]),
                similarite(member.display_name, r["name"]),
            )
            if score > meilleur:
                meilleur = score
                source = r

        # Seuil : pseudo à 80 % identique + compte récent = alt probable.
        if meilleur >= 0.80 and source:
            try:
                await member.ban(
                    reason=f"Alt probable de {source['name']} "
                           f"({int(meilleur*100)}% de similarité, compte {age_jours}j)",
                    delete_message_days=0,
                )
            except discord.HTTPException:
                return
            await self.bot.db.add_case(
                guild.id, member.id, self.bot.user.id, "autoban-alt",
                f"Alt probable de {source['user_id']}",
            )
            await self._log(
                guild,
                h.base_embed(
                    f"{config.EMOJI['boom']} Alt banni automatiquement",
                    f"**Compte :** {member} `{member.id}`\n"
                    f"**Âge :** {age_jours}j\n"
                    f"**Ressemble à :** {source['name']} `{source['user_id']}` "
                    f"(**{int(meilleur*100)}%**)\n\n"
                    f"Si c'est une erreur : `{config.PREFIX}unban {member.id}`.",
                    config.COLOR_ERROR,
                ),
            )


# ==============================================================================
#  SECTION 14 - RÈGLEMENT (bouton -> rôle membre)
# ==============================================================================




DEFAULT_RULES = (
    "**1.** Respecte tout le monde. Pas d'insultes, de harcèlement ni de haine.\n"
    "**2.** Pas de spam, de publicité ni de liens non sollicités.\n"
    "**3.** Pas de contenu NSFW, choquant ou illégal.\n"
    "**4.** Utilise les salons pour leur usage prévu.\n"
    "**5.** Les décisions du staff sont finales.\n\n"
    "En cliquant sur le bouton ci-dessous, tu confirmes avoir lu et accepté "
    "ce règlement."
)

RULE2_TITLE = "\u22c6-\U00010a5a\u02da\u0b94\u0d94 rules \u02da\u22c6"

RULE2_TEXT = (
    "**1. Respect :** Traitez tous les membres et le personnel avec respect. "
    "Maintenez un environnement amical, mature et approprié.\n\n"
    "**2. Pas de discours de haine :** Le racisme, le sexisme, l'homophobie ou "
    "tout contenu dégradant sont strictement interdits. Soutenir ou adopter un "
    "tel comportement entraînera un bannissement.\n\n"
    "**3. Blagues appropriées :** Les blagues inappropriées sont strictement "
    "interdites.\n\n"
    "**4. Pas de NSFW :** Le contenu ou les discussions NSFW (y compris tout "
    "matériel similaire) ne sont pas autorisés.\n\n"
    "**5. Pas de publicité :** La publicité sur ce serveur est interdite.\n\n"
    "**6. Vie privée :** Ne demandez pas, ne partagez pas et ne divulguez pas "
    "d'informations personnelles. Cela est strictement interdit.\n\n"
    "**7. Utilisation des salons :** Utilisez les salons uniquement pour l'usage "
    "auquel ils sont destinés. Le spam ou la mauvaise utilisation des salons est "
    "interdit.\n\n"
    "**8. Pseudos :** Ne gardez pas de pseudos ou surnoms inappropriés ; ils "
    "seront modérés.\n\n"
    "**9. Filtres :** Tenter de contourner les filtres de mots ou le système "
    "d'auto-modération du serveur est interdit.\n\n"
    "**10. Pas de menaces :** Les menaces de toute nature envers les membres ou "
    "quiconque ne seront pas tolérées.\n\n"
    "**11. Pas de contournement des règles :** N'essayez pas de contourner les "
    "règles du serveur.\n\n"
    "**12. Pas de mendicité :** Demander de manière insistante des objets "
    "gratuits tels que des boosts, des gamepasses ou des produits n'est pas "
    "autorisé."
)


class RulesView(discord.ui.View):
    """Bouton d'acceptation persistant."""

    def __init__(self, bot=None):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="J'accepte le règlement", emoji="\u2705",
                       style=discord.ButtonStyle.success, custom_id="rules:accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot = interaction.client
        row = await bot.db.rules(interaction.guild.id)
        if not row or not row["role_id"]:
            return await interaction.response.send_message(
                embed=h.err_embed("Aucun rôle de membre n'est configuré. Préviens le staff."),
                ephemeral=True,
            )
        role = interaction.guild.get_role(row["role_id"])
        if role is None:
            return await interaction.response.send_message(
                embed=h.err_embed("Le rôle configuré n'existe plus."), ephemeral=True
            )
        if role in interaction.user.roles:
            return await interaction.response.send_message(
                embed=h.base_embed(description="Tu as déjà accepté le règlement."),
                ephemeral=True,
            )
        if role >= interaction.guild.me.top_role:
            return await interaction.response.send_message(
                embed=h.err_embed("Je ne peux pas attribuer ce rôle (il est au-dessus du mien). "
                                  "Préviens le staff."),
                ephemeral=True,
            )
        try:
            await interaction.user.add_roles(role, reason="Règlement accepté")
        except discord.HTTPException:
            return await interaction.response.send_message(
                embed=h.err_embed("Échec de l'attribution du rôle. Préviens le staff."),
                ephemeral=True,
            )
        await bot.db.bump_rules_accepted(interaction.guild.id)
        await interaction.response.send_message(
            embed=h.ok_embed(
                f"Bienvenue ! Tu as reçu le rôle {role.mention} et accès au serveur."
            ),
            ephemeral=True,
        )


class Rules(commands.Cog):
    """Message de règlement avec attribution de rôle."""

    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="rules", aliases=["reglement", "règlement"],
                    invoke_without_command=True,
                    help="Publie le règlement avec bouton d'acceptation.")
    @commands.guild_only()
    @h.is_owner_or(manage_guild=True)
    async def rules(self, ctx):
        row = await self.bot.db.rules(ctx.guild.id)
        if not row or not row["role_id"]:
            return await ctx.reply(
                embed=h.warn_embed(
                    f"Configure d'abord le rôle attribué :\n"
                    f"`{ctx.prefix}rules config @Membre`"
                )
            )
        role = ctx.guild.get_role(row["role_id"])
        if role is None:
            return await ctx.reply(
                embed=h.err_embed(
                    "Le rôle configuré n'existe plus. Reconfigure-le :\n"
                    f"`{ctx.prefix}rules config @Membre`"
                )
            )
        texte = row["content"] or DEFAULT_RULES
        e = h.base_embed(f"\U0001f4dc Règlement — {ctx.guild.name}", texte)
        if ctx.guild.icon:
            e.set_thumbnail(url=ctx.guild.icon.url)
        e.set_footer(text="Clique sur le bouton pour accepter et débloquer le serveur.")
        msg = await ctx.send(embed=e, view=RulesView(self.bot))
        await self.bot.db.set_rules(ctx.guild.id, "channel_id", ctx.channel.id)
        await self.bot.db.set_rules(ctx.guild.id, "message_id", msg.id)

    @rules.command(name="config", aliases=["setup", "set"])
    @h.is_owner_or(manage_guild=True)
    async def rules_config(self, ctx, role: discord.Role, *, texte: str = None):
        if role >= ctx.guild.me.top_role:
            return await ctx.reply(
                embed=h.err_embed(
                    "Ce rôle est au-dessus du mien — je ne pourrai pas l'attribuer. "
                    "Monte mon rôle au-dessus dans les paramètres du serveur."
                )
            )
        await self.bot.db.set_rules(ctx.guild.id, "role_id", role.id)
        if texte:
            await self.bot.db.set_rules(ctx.guild.id, "content", texte[:4000])
        await ctx.reply(
            embed=h.ok_embed(
                f"Rôle d'accès réglé sur {role.mention}."
                + ("" if texte else f"\nRèglement par défaut utilisé — personnalise-le "
                                    f"avec `{ctx.prefix}rules text <ton texte>`.")
                + f"\nPublie le message avec `{ctx.prefix}rules`."
            )
        )

    @rules.command(name="text", aliases=["texte", "message"])
    @h.is_owner_or(manage_guild=True)
    async def rules_text(self, ctx, *, texte: str):
        await self.bot.db.set_rules(ctx.guild.id, "content", texte[:4000])
        await ctx.reply(
            embed=h.ok_embed(f"Texte du règlement enregistré. Publie-le avec "
                             f"`{ctx.prefix}rules`.")
        )

    @rules.command(name="stats")
    @h.is_owner_or(manage_guild=True)
    async def rules_stats(self, ctx):
        row = await self.bot.db.rules(ctx.guild.id)
        role = ctx.guild.get_role(row["role_id"]) if row and row["role_id"] else None
        await ctx.reply(
            embed=h.base_embed(
                "Règlement",
                f"**Rôle d'accès :** {role.mention if role else '*non configuré*'}\n"
                f"**Acceptations :** {row['accepted'] if row else 0}",
            )
        )

    @commands.command(name="rule2", aliases=["rules2", "reglement2"],
                      help="Publie le règlement prédéfini ; le bouton donne le rôle Verified.")
    @commands.guild_only()
    @h.is_owner_or(manage_guild=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def rule2(self, ctx):
        # Rôle Verified : on le récupère ou on le crée.
        role = discord.utils.find(
            lambda r: r.name.lower() == "verified", ctx.guild.roles
        )
        if role is None:
            try:
                role = await ctx.guild.create_role(
                    name="Verified",
                    colour=discord.Colour.from_rgb(88, 101, 242),
                    reason="Rôle d'accès au règlement",
                )
            except discord.Forbidden:
                return await ctx.reply(
                    embed=h.err_embed("Je ne peux pas créer le rôle Verified — "
                                      "vérifie mes permissions.")
                )
        if role >= ctx.guild.me.top_role:
            return await ctx.reply(
                embed=h.err_embed(
                    "Le rôle **Verified** est au-dessus du mien — je ne pourrai pas "
                    "l'attribuer. Monte mon rôle plus haut dans les paramètres."
                )
            )

        await self.bot.db.set_rules(ctx.guild.id, "role_id", role.id)
        await self.bot.db.set_rules(ctx.guild.id, "content", RULE2_TEXT)

        e = h.base_embed(RULE2_TITLE, RULE2_TEXT, config.COLOR_PRIMARY)
        if ctx.guild.icon:
            e.set_thumbnail(url=ctx.guild.icon.url)
        e.set_footer(text="Clique sur le bouton pour accepter et recevoir le rôle Verified.")
        msg = await ctx.send(embed=e, view=RulesView(self.bot))
        await self.bot.db.set_rules(ctx.guild.id, "channel_id", ctx.channel.id)
        await self.bot.db.set_rules(ctx.guild.id, "message_id", msg.id)
        # petit accusé, auto-effacé
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass


# ==============================================================================
#  SECTION 15 - SALONS COMPTEURS DE STATS
# ==============================================================================





# Modèles par défaut. {count} est remplacé par le nombre.
MODELES = {
    "members": "\U0001f465 \u2022 Membres : {count}",
    "humans":  "\U0001f9d1 \u2022 Humains : {count}",
    "bots":    "\U0001f916 \u2022 Bots : {count}",
    "online":  "\U0001f7e2 \u2022 En ligne : {count}",
    "voice":   "\U0001f50a \u2022 En vocal : {count}",
    "boosts":  "\U0001f680 \u2022 Boosts : {count}",
}

DESCRIPTIONS = {
    "members": "nombre total de membres",
    "humans": "membres humains",
    "bots": "nombre de bots",
    "online": "membres connectés",
    "voice": "membres en vocal",
    "boosts": "nombre de boosts",
}


class StatsChannels(commands.Cog):
    """Salons vocaux affichant des compteurs en direct."""

    def __init__(self, bot):
        self.bot = bot
        self.maj.start()

    def cog_unload(self):
        self.maj.cancel()

    def valeur(self, guild: discord.Guild, kind: str) -> int:
        if kind == "members":
            return guild.member_count or len(guild.members)
        if kind == "humans":
            return sum(1 for m in guild.members if not m.bot)
        if kind == "bots":
            return sum(1 for m in guild.members if m.bot)
        if kind == "online":
            return sum(1 for m in guild.members
                       if not m.bot and m.status is not discord.Status.offline)
        if kind == "voice":
            return sum(len(vc.members) for vc in guild.voice_channels)
        if kind == "boosts":
            return guild.premium_subscription_count or 0
        return 0

    # ------------------------------------------------------------ boucle
    @tasks.loop(minutes=15)
    async def maj(self):
        try:
            rows = await self.bot.db.all_stat_channels()
        except Exception:
            return
        for row in rows:
            guild = self.bot.get_guild(row["guild_id"])
            if guild is None:
                continue
            salon = guild.get_channel(row["channel_id"])
            if salon is None:
                await self.bot.db.remove_stat_channel(row["channel_id"])
                continue
            modele = row["template"] or MODELES.get(row["kind"], "{count}")
            nouveau_nom = modele.replace("{count}", f"{self.valeur(guild, row['kind']):,}")
            if salon.name != nouveau_nom:
                try:
                    await salon.edit(name=nouveau_nom, reason="Compteur de stats")
                except discord.HTTPException:
                    pass
                await asyncio.sleep(1.5)  # respecter la limite de renommage

    @maj.before_loop
    async def avant(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------ commandes
    @commands.group(name="statschannels", aliases=["statschannel", "compteurs", "counter"],
                    invoke_without_command=True,
                    help="Salons vocaux affichant des compteurs en direct.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def statschannels(self, ctx):
        rows = await self.bot.db.stat_channels(ctx.guild.id)
        p = ctx.prefix
        if not rows:
            corps = (
                f"Aucun compteur pour l'instant.\n\n"
                f"`{p}compteurs setup` — crée d'un coup Membres / En ligne / Vocal\n"
                f"`{p}compteurs add <type>` — ajoute un compteur\n"
                f"`{p}compteurs remove <#salon>` — supprime\n\n"
                f"**Types :** {', '.join(f'`{k}`' for k in MODELES)}"
            )
        else:
            lignes = []
            for r in rows:
                salon = ctx.guild.get_channel(r["channel_id"])
                lignes.append(f"• {salon.mention if salon else r['channel_id']} — "
                              f"`{r['kind']}`")
            corps = "\n".join(lignes) + (
                f"\n\n`{p}compteurs add <type>` · `{p}compteurs remove <#salon>`"
            )
        await ctx.reply(embed=h.base_embed("\U0001f4ca Salons compteurs", corps))

    @statschannels.command(name="setup", aliases=["config"])
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def sc_setup(self, ctx):
        async with ctx.typing():
            categorie = discord.utils.get(ctx.guild.categories, name="\U0001f4ca Statistiques")
            if categorie is None:
                # Personne ne doit pouvoir se connecter à ces salons vitrine.
                overwrites = {
                    ctx.guild.default_role: discord.PermissionOverwrite(connect=False)
                }
                categorie = await ctx.guild.create_category(
                    "\U0001f4ca Statistiques", overwrites=overwrites,
                    reason="Salons compteurs",
                )
            crees = []
            for kind in ("members", "online", "voice"):
                nom = MODELES[kind].replace("{count}", f"{self.valeur(ctx.guild, kind):,}")
                salon = await ctx.guild.create_voice_channel(
                    nom, category=categorie,
                    overwrites={ctx.guild.default_role:
                                discord.PermissionOverwrite(connect=False)},
                    reason="Salon compteur",
                )
                await self.bot.db.add_stat_channel(
                    ctx.guild.id, salon.id, kind, MODELES[kind]
                )
                crees.append(kind)
                await asyncio.sleep(0.5)
        await ctx.reply(
            embed=h.ok_embed(
                f"Compteurs créés : {', '.join(crees)}.\n"
                f"Ils se mettent à jour toutes les 15 minutes (limite Discord)."
            )
        )

    @statschannels.command(name="add", aliases=["ajouter"])
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def sc_add(self, ctx, kind: str, *, modele: str = None):
        kind = kind.lower()
        if kind not in MODELES:
            return await ctx.reply(
                embed=h.err_embed(f"Type inconnu. Choix : {', '.join(MODELES)}")
            )
        modele = modele or MODELES[kind]
        if "{count}" not in modele:
            modele += " {count}"
        categorie = discord.utils.get(ctx.guild.categories, name="\U0001f4ca Statistiques")
        nom = modele.replace("{count}", f"{self.valeur(ctx.guild, kind):,}")
        salon = await ctx.guild.create_voice_channel(
            nom, category=categorie,
            overwrites={ctx.guild.default_role:
                        discord.PermissionOverwrite(connect=False)},
            reason="Salon compteur",
        )
        await self.bot.db.add_stat_channel(ctx.guild.id, salon.id, kind, modele)
        await ctx.reply(
            embed=h.ok_embed(f"Compteur **{DESCRIPTIONS[kind]}** créé : {salon.mention}")
        )

    @statschannels.command(name="remove", aliases=["supprimer", "del"])
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def sc_remove(self, ctx, salon: discord.VoiceChannel):
        await self.bot.db.remove_stat_channel(salon.id)
        try:
            await salon.delete(reason="Compteur retiré")
        except discord.HTTPException:
            pass
        await ctx.reply(embed=h.ok_embed("Compteur supprimé."))

    @statschannels.command(name="refresh", aliases=["maj", "update"])
    @h.is_owner_or(administrator=True)
    async def sc_refresh(self, ctx):
        rows = await self.bot.db.stat_channels(ctx.guild.id)
        maj = 0
        for r in rows:
            salon = ctx.guild.get_channel(r["channel_id"])
            if not salon:
                continue
            modele = r["template"] or MODELES.get(r["kind"], "{count}")
            nom = modele.replace("{count}", f"{self.valeur(ctx.guild, r['kind']):,}")
            if salon.name != nom:
                try:
                    await salon.edit(name=nom)
                    maj += 1
                except discord.HTTPException:
                    pass
                await asyncio.sleep(1.5)
        await ctx.reply(
            embed=h.ok_embed(f"**{maj}** compteur(s) rafraîchi(s) manuellement.")
        )


# ==============================================================================
#  SECTION 16 - SYSTÈME DE LOGS
# ==============================================================================





class Logging(commands.Cog):
    """Journaux d'événements du serveur."""

    def __init__(self, bot):
        self.bot = bot

    async def envoyer(self, guild, colonne, embed):
        cfg = await self.bot.db.log_config(guild.id)
        if not cfg or not cfg["enabled"]:
            return
        chan_id = cfg[colonne]
        if not chan_id:
            return
        salon = guild.get_channel(chan_id)
        if salon:
            try:
                await salon.send(embed=embed)
            except discord.HTTPException:
                pass

    # ================================================================ textuel

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if not message.guild or message.author.bot:
            return
        e = h.base_embed(
            "\U0001f5d1\ufe0f Message supprimé", color=config.COLOR_ERROR
        )
        e.add_field(name="Auteur", value=f"{message.author.mention} `{message.author.id}`",
                    inline=True)
        e.add_field(name="Salon", value=message.channel.mention, inline=True)
        if message.content:
            e.add_field(name="Contenu", value=h.clean(message.content, 1024), inline=False)
        if message.attachments:
            e.add_field(name="Pièces jointes",
                        value=str(len(message.attachments)), inline=True)
        e.set_footer(text=f"ID auteur : {message.author.id}")
        await self.envoyer(message.guild, "log_text", e)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        e = h.base_embed("\u270f\ufe0f Message modifié", color=config.COLOR_WARN)
        e.add_field(name="Auteur", value=f"{before.author.mention}", inline=True)
        e.add_field(name="Salon", value=before.channel.mention, inline=True)
        e.add_field(name="Avant", value=h.clean(before.content, 500) or "*vide*",
                    inline=False)
        e.add_field(name="Après", value=h.clean(after.content, 500) or "*vide*",
                    inline=False)
        e.add_field(name="Lien", value=f"[Aller au message]({after.jump_url})",
                    inline=False)
        await self.envoyer(before.guild, "log_text", e)

    # ================================================================ modération

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        e = h.base_embed("\U0001f528 Membre banni", color=config.COLOR_ERROR)
        e.add_field(name="Membre", value=f"{user} `{user.id}`", inline=False)
        await self._ajouter_auteur(guild, discord.AuditLogAction.ban, user.id, e)
        await self.envoyer(guild, "log_mod", e)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        e = h.base_embed("\U0001f513 Membre débanni", color=config.COLOR_SUCCESS)
        e.add_field(name="Membre", value=f"{user} `{user.id}`", inline=False)
        await self.envoyer(guild, "log_mod", e)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        # Changements de rôles uniquement.
        if before.roles == after.roles:
            return
        ajoutes = [r for r in after.roles if r not in before.roles]
        retires = [r for r in before.roles if r not in after.roles]
        if not ajoutes and not retires:
            return
        e = h.base_embed("\U0001f3ad Rôles modifiés", color=config.COLOR_PRIMARY)
        e.add_field(name="Membre", value=after.mention, inline=False)
        if ajoutes:
            e.add_field(name="Ajoutés", value=", ".join(r.mention for r in ajoutes),
                        inline=False)
        if retires:
            e.add_field(name="Retirés", value=", ".join(r.mention for r in retires),
                        inline=False)
        await self.envoyer(after.guild, "log_mod", e)

    async def _ajouter_auteur(self, guild, action, cible_id, embed):
        """Retrouve qui a fait l'action via le journal d'audit, si accessible."""
        if not guild.me.guild_permissions.view_audit_log:
            return
        try:
            async for entree in guild.audit_logs(limit=5, action=action):
                if entree.target and entree.target.id == cible_id:
                    embed.add_field(
                        name="Par",
                        value=entree.user.mention if entree.user else "?",
                        inline=False,
                    )
                    if entree.reason:
                        embed.add_field(name="Raison",
                                        value=h.clean(entree.reason, 500), inline=False)
                    return
        except discord.HTTPException:
            return

    # ================================================================ vocal

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return
        e = None
        if before.channel is None and after.channel is not None:
            e = h.base_embed("\U0001f50a Arrivée en vocal", color=config.COLOR_SUCCESS)
            e.add_field(name="Membre", value=member.mention, inline=True)
            e.add_field(name="Salon", value=after.channel.mention, inline=True)
        elif before.channel is not None and after.channel is None:
            e = h.base_embed("\U0001f507 Départ du vocal", color=config.COLOR_MUTED)
            e.add_field(name="Membre", value=member.mention, inline=True)
            e.add_field(name="Salon", value=before.channel.mention, inline=True)
        elif before.channel != after.channel:
            e = h.base_embed("\U0001f504 Déplacement vocal", color=config.COLOR_PRIMARY)
            e.add_field(name="Membre", value=member.mention, inline=False)
            e.add_field(name="De", value=before.channel.mention, inline=True)
            e.add_field(name="Vers", value=after.channel.mention, inline=True)
        if e:
            await self.envoyer(member.guild, "log_voice", e)

    # ================================================================ arrivées / départs

    @commands.Cog.listener()
    async def on_member_join(self, member):
        e = h.base_embed("\U0001f4e5 Membre arrivé", color=config.COLOR_SUCCESS)
        e.add_field(name="Membre", value=f"{member.mention} `{member.id}`", inline=False)
        e.add_field(name="Compte créé", value=h.ts(member.created_at), inline=True)
        e.add_field(name="Membres", value=str(member.guild.member_count), inline=True)
        e.set_thumbnail(url=member.display_avatar.url)
        await self.envoyer(member.guild, "log_join", e)

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        e = h.base_embed("\U0001f4e4 Membre parti", color=config.COLOR_MUTED)
        e.add_field(name="Membre", value=f"{member} `{member.id}`", inline=False)
        roles = [r.mention for r in member.roles if r != member.guild.default_role]
        if roles:
            e.add_field(name="Rôles", value=h.clean(", ".join(roles), 500), inline=False)
        e.set_thumbnail(url=member.display_avatar.url)
        await self.envoyer(member.guild, "log_join", e)

    # ================================================================ commandes

    @commands.group(name="logs", aliases=["logging", "journaux"],
                    invoke_without_command=True,
                    help="Configure les journaux d'événements.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def logs(self, ctx):
        cfg = await self.bot.db.log_config(ctx.guild.id)
        p = ctx.prefix

        def salon(col):
            c = ctx.guild.get_channel(cfg[col]) if cfg[col] else None
            return c.mention if c else "*non défini*"

        e = h.base_embed(
            "\U0001f4cb Système de logs",
            f"**État :** {'activé' if cfg['enabled'] else 'désactivé'}\n\n"
            f"\U0001f4dd Textuel (suppr./édit.) : {salon('log_text')}\n"
            f"\U0001f528 Modération (bans/rôles) : {salon('log_mod')}\n"
            f"\U0001f50a Vocal (arrivées/départs) : {salon('log_voice')}\n"
            f"\U0001f6aa Arrivées/départs membres : {salon('log_join')}\n\n"
            f"`{p}logs setup` — crée tous les salons d'un coup\n"
            f"`{p}logs textuel <#salon>`\n"
            f"`{p}logs moderation <#salon>`\n"
            f"`{p}logs vocal <#salon>`\n"
            f"`{p}logs arrivees <#salon>`\n"
            f"`{p}logs on|off`",
        )
        await ctx.reply(embed=e)

    @logs.command(name="setup", aliases=["config"])
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def logs_setup(self, ctx):
        await self._faire_setup(ctx)

    @commands.command(name="setlogs", aliases=["setuplogs", "createlogs"],
                      help="Crée les salons de logs et y envoie tous les logs automatiquement.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    @commands.bot_has_permissions(manage_channels=True)
    async def setlogs(self, ctx):
        await self._faire_setup(ctx)

    async def _faire_setup(self, ctx):
        async with ctx.typing():
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(view_channel=False),
                ctx.guild.me: discord.PermissionOverwrite(view_channel=True,
                                                          send_messages=True),
            }
            categorie = discord.utils.get(ctx.guild.categories, name="\U0001f4cb logs")
            if categorie is None:
                categorie = await ctx.guild.create_category(
                    "\U0001f4cb logs", overwrites=overwrites, reason="Système de logs"
                )
            salons = {
                "log_text": "logs-textuel",
                "log_mod": "logs-moderation",
                "log_voice": "logs-vocal",
                "log_join": "logs-arrivees",
            }
            for colonne, nom in salons.items():
                existant = discord.utils.get(ctx.guild.text_channels, name=nom)
                if existant is None:
                    existant = await ctx.guild.create_text_channel(
                        nom, category=categorie, overwrites=overwrites,
                        reason="Salon de logs",
                    )
                await self.bot.db.set_log(ctx.guild.id, colonne, existant.id)
            # On s'assure que les logs sont bien activés.
            await self.bot.db.set_log(ctx.guild.id, "enabled", 1)
        await ctx.reply(
            embed=h.ok_embed(
                "Logs configurés et **activés** : **logs-textuel**, "
                "**logs-moderation**, **logs-vocal**, **logs-arrivees**.\n"
                "Tout est envoyé automatiquement dans les salons créés."
            )
        )

    @logs.command(name="textuel", aliases=["text", "texte"])
    @h.is_owner_or(administrator=True)
    async def logs_text(self, ctx, salon: discord.TextChannel):
        await self.bot.db.set_log(ctx.guild.id, "log_text", salon.id)
        await ctx.reply(embed=h.ok_embed(f"Logs textuels dans {salon.mention}."))

    @logs.command(name="moderation", aliases=["mod"])
    @h.is_owner_or(administrator=True)
    async def logs_mod(self, ctx, salon: discord.TextChannel):
        await self.bot.db.set_log(ctx.guild.id, "log_mod", salon.id)
        await ctx.reply(embed=h.ok_embed(f"Logs de modération dans {salon.mention}."))

    @logs.command(name="vocal", aliases=["voice"])
    @h.is_owner_or(administrator=True)
    async def logs_voice(self, ctx, salon: discord.TextChannel):
        await self.bot.db.set_log(ctx.guild.id, "log_voice", salon.id)
        await ctx.reply(embed=h.ok_embed(f"Logs vocaux dans {salon.mention}."))

    @logs.command(name="arrivees", aliases=["join", "arrivee"])
    @h.is_owner_or(administrator=True)
    async def logs_join(self, ctx, salon: discord.TextChannel):
        await self.bot.db.set_log(ctx.guild.id, "log_join", salon.id)
        await ctx.reply(embed=h.ok_embed(f"Logs d'arrivées/départs dans {salon.mention}."))

    @logs.command(name="on")
    @h.is_owner_or(administrator=True)
    async def logs_on(self, ctx):
        await self.bot.db.set_log(ctx.guild.id, "enabled", 1)
        await ctx.reply(embed=h.ok_embed("Logs activés."))

    @logs.command(name="off")
    @h.is_owner_or(administrator=True)
    async def logs_off(self, ctx):
        await self.bot.db.set_log(ctx.guild.id, "enabled", 0)
        await ctx.reply(embed=h.warn_embed("Logs désactivés."))


# ==============================================================================
#  SECTION 17 - SALONS PHOTO UNIQUEMENT
# ==============================================================================





IMAGE_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".heic", ".tiff")
IMAGE_URL_RE = re.compile(
    r"https?://\S+\.(?:png|jpe?g|gif|webp|bmp|heic|tiff)(?:\?\S*)?", re.IGNORECASE
)


class MediaOnly(commands.Cog):
    """Salons où seules les photos sont autorisées."""

    def __init__(self, bot):
        self.bot = bot

    def a_une_image(self, message: discord.Message) -> bool:
        # 1) pièce jointe image
        for a in message.attachments:
            if a.content_type and a.content_type.startswith("image"):
                return True
            if a.filename.lower().endswith(IMAGE_EXT):
                return True
        # 2) embed image/vignette (lien d'image collé)
        for e in message.embeds:
            if e.type in ("image", "gifv") or e.image or e.thumbnail:
                return True
        # 3) lien direct vers une image dans le texte
        if IMAGE_URL_RE.search(message.content):
            return True
        # 4) sticker (une image aussi)
        if message.stickers:
            return True
        return False

    def est_exempt(self, member: discord.Member) -> bool:
        if member.bot:
            return True
        if member.id in config.OWNER_IDS or member.guild.owner_id == member.id:
            return True
        p = member.guild_permissions
        return p.administrator or p.manage_messages or p.manage_guild

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        row = await self.bot.db.get_media_channel(message.channel.id)
        if not row:
            return
        if self.est_exempt(message.author):
            return
        # Un message avec image : autorisé, on ne touche à rien.
        if self.a_une_image(message):
            return
        # Certains liens (Tenor, Imgur page) mettent une seconde à générer leur
        # embed image. On laisse une petite chance avant de sévir.
        if message.content and ("tenor.com" in message.content
                                or "imgur.com" in message.content
                                or "giphy.com" in message.content):
            await asyncio.sleep(2)
            try:
                message = await message.channel.fetch_message(message.id)
            except discord.HTTPException:
                return
            if self.a_une_image(message):
                return

        # Message texte pur dans un salon photo -> suppression + mute.
        minutes = row["mute_minutes"] or 10
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        applied = "message supprimé"
        try:
            until = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
            await message.author.timeout(until, reason=f"Salon photo uniquement : "
                                                       f"message texte dans {message.channel}")
            applied = f"muet {minutes} min"
        except discord.HTTPException:
            pass

        await self.bot.db.add_case(
            message.guild.id, message.author.id, self.bot.user.id,
            "mediaonly-mute", f"texte dans le salon photo {message.channel}",
        )

        # Petit rappel auto-effacé, pour que la personne comprenne.
        try:
            await message.channel.send(
                embed=h.warn_embed(
                    f"{message.author.mention}, ce salon est **réservé aux photos**. "
                    f"Ton message texte a été supprimé et tu es muet **{minutes} min**."
                ),
                delete_after=8,
            )
        except discord.HTTPException:
            pass

        # Log modération si configuré.
        cog_log = self.bot.get_cog("Logging")
        if cog_log:
            e = h.base_embed(
                "\U0001f4f7 Salon photo — message texte bloqué",
                f"**Membre :** {message.author.mention} `{message.author.id}`\n"
                f"**Salon :** {message.channel.mention}\n"
                f"**Sanction :** {applied}",
                config.COLOR_WARN,
            )
            await cog_log.envoyer(message.guild, "log_mod", e)

    # ------------------------------------------------------------ commandes
    @commands.group(name="mediaonly", aliases=["photoonly", "photouniquement", "salonphoto"],
                    invoke_without_command=True,
                    help="Salon où seules les photos sont autorisées.")
    @commands.guild_only()
    @h.is_owner_or(manage_channels=True)
    async def mediaonly(self, ctx):
        rows = await self.bot.db.all_media_channels(ctx.guild.id)
        p = ctx.prefix
        if not rows:
            corps = (
                f"Aucun salon photo configuré.\n\n"
                f"`{p}mediaonly add [#salon] [minutes]` — active (10 min par défaut)\n"
                f"`{p}mediaonly remove [#salon]` — désactive\n\n"
                f"Dans un salon actif, un message **sans photo** est supprimé et "
                f"l'auteur est rendu muet."
            )
        else:
            lignes = []
            for r in rows:
                salon = ctx.guild.get_channel(r["channel_id"])
                lignes.append(f"• {salon.mention if salon else r['channel_id']} — "
                              f"mute {r['mute_minutes']} min")
            corps = "\n".join(lignes) + f"\n\n`{p}mediaonly remove #salon` pour retirer."
        await ctx.reply(embed=h.base_embed("\U0001f4f7 Salons photo uniquement", corps))

    @mediaonly.command(name="add", aliases=["set", "on"])
    @h.is_owner_or(manage_channels=True)
    async def mo_add(self, ctx, salon: discord.TextChannel = None, minutes: int = 10):
        salon = salon or ctx.channel
        minutes = max(1, min(minutes, 60 * 24 * 28))  # limite du timeout Discord
        await self.bot.db.add_media_channel(salon.id, ctx.guild.id, minutes)
        await ctx.reply(
            embed=h.ok_embed(
                f"{salon.mention} est maintenant **photo uniquement**.\n"
                f"Un message sans image = supprimé + mute **{minutes} min**."
            )
        )

    @mediaonly.command(name="remove", aliases=["del", "off"])
    @h.is_owner_or(manage_channels=True)
    async def mo_remove(self, ctx, salon: discord.TextChannel = None):
        salon = salon or ctx.channel
        await self.bot.db.remove_media_channel(salon.id)
        await ctx.reply(embed=h.ok_embed(f"{salon.mention} n'est plus restreint aux photos."))


# ==============================================================================
#  SECTION 18 - OUTILS (afk, tags, concours...)
# ==============================================================================


import ast
import base64
import operator



# Opérateurs autorisés dans -calc. Tout le reste est refusé, ce qui évite
# d'exposer un eval() complet à n'importe quel membre du serveur.
OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def calcul_sur(noeud):
    if isinstance(noeud, ast.Constant):
        if isinstance(noeud.value, (int, float)):
            return noeud.value
        raise ValueError("valeur non numérique")
    if isinstance(noeud, ast.BinOp) and type(noeud.op) in OPS:
        gauche, droite = calcul_sur(noeud.left), calcul_sur(noeud.right)
        if isinstance(noeud.op, ast.Pow) and (abs(droite) > 100 or abs(gauche) > 10**6):
            raise ValueError("puissance trop grande")
        return OPS[type(noeud.op)](gauche, droite)
    if isinstance(noeud, ast.UnaryOp) and type(noeud.op) in OPS:
        return OPS[type(noeud.op)](calcul_sur(noeud.operand))
    raise ValueError("expression non autorisée")


class Tools(commands.Cog):
    """AFK, tags, concours, infos et utilitaires."""

    def __init__(self, bot):
        self.bot = bot
        self.verif_concours.start()

    def cog_unload(self):
        self.verif_concours.cancel()

    # ================================================================ AFK

    @commands.command(name="afk", aliases=["absence"], help="Marque ton absence. -afk je mange")
    @commands.guild_only()
    async def afk(self, ctx, *, raison: str = "Absent"):
        ancien = ctx.author.nick
        await self.bot.db.set_afk(ctx.guild.id, ctx.author.id, h.clean(raison, 200), ancien)
        try:
            if ctx.author.top_role < ctx.guild.me.top_role:
                await ctx.author.edit(nick=f"[AFK] {ctx.author.display_name}"[:32])
        except discord.HTTPException:
            pass
        await ctx.reply(
            embed=h.ok_embed(f"Tu es maintenant AFK : *{h.clean(raison, 200)}*")
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Retour de l'auteur
        row = await self.bot.db.get_afk(message.guild.id, message.author.id)
        if row and not message.content.startswith(f"{config.PREFIX}afk"):
            duree = h.now() - (row["since"] or h.now())
            await self.bot.db.remove_afk(message.guild.id, message.author.id)
            try:
                if message.author.nick and message.author.nick.startswith("[AFK]"):
                    await message.author.edit(nick=row["old_nick"])
            except discord.HTTPException:
                pass
            await message.channel.send(
                embed=h.ok_embed(
                    f"Bon retour {message.author.mention}, "
                    f"tu étais parti **{h.human_duration(duree)}**."
                ),
                delete_after=10,
            )

        # Quelqu'un mentionne un membre AFK
        for membre in message.mentions[:3]:
            info = await self.bot.db.get_afk(message.guild.id, membre.id)
            if info:
                await message.channel.send(
                    embed=h.warn_embed(
                        f"**{membre.display_name}** est AFK depuis "
                        f"{h.ts(info['since'])} : *{h.clean(info['reason'], 200)}*"
                    ),
                    delete_after=15,
                )

        # Message épinglé automatique
        await self._replacer_sticky(message)

    # ================================================================ sticky

    async def _replacer_sticky(self, message):
        row = await self.bot.db.get_sticky(message.channel.id)
        if not row or message.author.id == self.bot.user.id:
            return
        if row["last_id"]:
            try:
                ancien = await message.channel.fetch_message(row["last_id"])
                await ancien.delete()
            except discord.HTTPException:
                pass
        try:
            nouveau = await message.channel.send(
                embed=h.base_embed("\U0001f4cc Épinglé", h.clean(row["content"], 3000))
            )
            await self.bot.db.sticky_last(message.channel.id, nouveau.id)
        except discord.HTTPException:
            pass

    @commands.group(name="sticky", invoke_without_command=True,
                    help="Message toujours affiché en bas du salon.")
    @commands.guild_only()
    @h.is_owner_or(manage_messages=True)
    async def sticky(self, ctx):
        row = await self.bot.db.get_sticky(ctx.channel.id)
        await ctx.reply(
            embed=h.base_embed(
                "Message épinglé automatique",
                h.clean(row["content"], 1000) if row else "*aucun dans ce salon*",
            )
        )

    @sticky.command(name="set")
    @h.is_owner_or(manage_messages=True)
    async def sticky_set(self, ctx, *, texte: str):
        await self.bot.db.set_sticky(ctx.channel.id, ctx.guild.id, texte[:3000])
        await ctx.reply(embed=h.ok_embed("Message épinglé activé dans ce salon."))

    @sticky.command(name="remove", aliases=["del", "off"])
    @h.is_owner_or(manage_messages=True)
    async def sticky_remove(self, ctx):
        await self.bot.db.del_sticky(ctx.channel.id)
        await ctx.reply(embed=h.ok_embed("Message épinglé retiré."))

    # ================================================================ tags

    @commands.group(name="tag", aliases=["t"], invoke_without_command=True,
                    help="Affiche un tag. -tag regles")
    @commands.guild_only()
    async def tag(self, ctx, *, nom: str = None):
        if nom is None:
            return await ctx.invoke(self.tag_list)
        row = await self.bot.db.get_tag(ctx.guild.id, nom.lower())
        if not row:
            return await ctx.reply(embed=h.err_embed(f"Aucun tag nommé `{h.clean(nom, 40)}`."))
        await self.bot.db.bump_tag(ctx.guild.id, nom.lower())
        await ctx.send(h.clean(row["content"], 1900))

    @tag.command(name="create", aliases=["add", "set"])
    @h.is_owner_or(manage_messages=True)
    async def tag_create(self, ctx, nom: str, *, contenu: str):
        nom = nom.lower()[:40]
        if self.bot.get_command(nom):
            return await ctx.reply(
                embed=h.err_embed("Ce nom est déjà celui d'une commande du bot.")
            )
        await self.bot.db.set_tag(ctx.guild.id, nom, contenu[:1900], ctx.author.id)
        await ctx.reply(embed=h.ok_embed(f"Tag `{nom}` enregistré."))

    @tag.command(name="delete", aliases=["del", "remove"])
    @h.is_owner_or(manage_messages=True)
    async def tag_delete(self, ctx, nom: str):
        await self.bot.db.del_tag(ctx.guild.id, nom.lower())
        await ctx.reply(embed=h.ok_embed(f"Tag `{nom.lower()}` supprimé."))

    @tag.command(name="list", aliases=["liste"])
    async def tag_list(self, ctx):
        rows = await self.bot.db.list_tags(ctx.guild.id)
        if not rows:
            return await ctx.reply(embed=h.base_embed(description="Aucun tag enregistré."))
        texte = ", ".join(f"`{r['name']}` ({r['uses']})" for r in rows[:60])
        await ctx.reply(embed=h.base_embed(f"Tags ({len(rows)})", texte))

    @tag.command(name="info")
    async def tag_info(self, ctx, nom: str):
        row = await self.bot.db.get_tag(ctx.guild.id, nom.lower())
        if not row:
            return await ctx.reply(embed=h.err_embed("Tag introuvable."))
        auteur = ctx.guild.get_member(row["owner_id"])
        e = h.base_embed(f"Tag — {row['name']}")
        e.add_field(name="Créé par",
                    value=auteur.mention if auteur else f"`{row['owner_id']}`")
        e.add_field(name="Utilisations", value=str(row["uses"]))
        e.add_field(name="Créé le", value=h.ts(row["created_at"]))
        await ctx.reply(embed=e)

    # ================================================================ concours

    @commands.group(name="giveaway", aliases=["ga", "concours"],
                    invoke_without_command=True)
    @commands.guild_only()
    async def giveaway(self, ctx):
        rows = await self.bot.db.active_giveaways(ctx.guild.id)
        if not rows:
            return await ctx.reply(
                embed=h.base_embed(
                    description=f"Aucun concours en cours.\n"
                                f"`{ctx.prefix}ga start 1h 1 Nitro classique`"
                )
            )
        lignes = [
            f"**{r['prize']}** — {r['winners']} gagnant(s) · fin {h.ts(r['ends_at'])}\n"
            f"↳ [message](https://discord.com/channels/{r['guild_id']}/"
            f"{r['channel_id']}/{r['message_id']})"
            for r in rows[:10]
        ]
        await ctx.reply(embed=h.base_embed("Concours en cours", "\n\n".join(lignes)))

    @giveaway.command(name="start", aliases=["lancer"],
                      help="+ga start 1h 2 Un mois de Nitro")
    @h.is_owner_or(manage_guild=True)
    async def ga_start(self, ctx, duree: str, gagnants: int, *, lot: str):
        secondes = h.parse_duration(duree)
        if not secondes or secondes > 60 * 60 * 24 * 30:
            return await ctx.reply(
                embed=h.err_embed("Durée invalide (30 jours maximum). Ex : `2h`, `3d`.")
            )
        gagnants = max(1, min(gagnants, 20))
        fin = h.now() + secondes

        e = h.base_embed(
            f"\U0001f389 {h.clean(lot, 250)}",
            (
                f"Réagis avec \U0001f389 pour participer !\n\n"
                f"**Gagnants :** {gagnants}\n"
                f"**Fin :** {h.ts(fin)} ({h.ts(fin, 'f')})\n"
                f"**Organisé par :** {ctx.author.mention}"
            ),
            config.COLOR_SUCCESS,
        )
        message = await ctx.send(embed=e)
        await message.add_reaction("\U0001f389")
        await self.bot.db.add_giveaway(
            message.id, ctx.channel.id, ctx.guild.id, ctx.author.id,
            h.clean(lot, 250), gagnants, fin,
        )

    @giveaway.command(name="end", aliases=["stop"])
    @h.is_owner_or(manage_guild=True)
    async def ga_end(self, ctx, message_id: int):
        row = await self.bot.db.get_giveaway(message_id)
        if not row or row["ended"]:
            return await ctx.reply(embed=h.err_embed("Concours introuvable ou déjà terminé."))
        await self.cloturer(row)
        await ctx.reply(embed=h.ok_embed("Concours clôturé."))

    @giveaway.command(name="reroll", aliases=["relancer"])
    @h.is_owner_or(manage_guild=True)
    async def ga_reroll(self, ctx, message_id: int):
        row = await self.bot.db.get_giveaway(message_id)
        if not row:
            return await ctx.reply(embed=h.err_embed("Concours introuvable."))
        gagnants = await self.tirer(row)
        if not gagnants:
            return await ctx.reply(embed=h.warn_embed("Pas assez de participants."))
        await ctx.send(
            embed=h.ok_embed(
                f"Nouveau tirage pour **{row['prize']}** : "
                f"{', '.join(g.mention for g in gagnants)}"
            )
        )

    async def tirer(self, row):
        salon = self.bot.get_channel(row["channel_id"])
        if salon is None:
            return []
        try:
            message = await salon.fetch_message(row["message_id"])
        except discord.HTTPException:
            return []
        participants = []
        for reaction in message.reactions:
            if str(reaction.emoji) == "\U0001f389":
                async for membre in reaction.users():
                    if not membre.bot:
                        participants.append(membre)
        if not participants:
            return []
        nombre = min(row["winners"], len(participants))
        return random.sample(participants, nombre)

    async def cloturer(self, row):
        gagnants = await self.tirer(row)
        await self.bot.db.end_giveaway(row["message_id"])
        salon = self.bot.get_channel(row["channel_id"])
        if salon is None:
            return
        if not gagnants:
            return await salon.send(
                embed=h.warn_embed(
                    f"Concours **{row['prize']}** terminé — aucun participant."
                )
            )
        mention = ", ".join(g.mention for g in gagnants)
        await salon.send(
            content=mention,
            embed=h.base_embed(
                "\U0001f389 Concours terminé",
                f"**Lot :** {row['prize']}\n**Gagnant(s) :** {mention}\n\n"
                f"Félicitations !",
                config.COLOR_SUCCESS,
            ),
        )

    @tasks.loop(seconds=20)
    async def verif_concours(self):
        try:
            for row in await self.bot.db.due_giveaways(h.now()):
                await self.cloturer(row)
        except Exception:
            pass

    @verif_concours.before_loop
    async def avant_concours(self):
        await self.bot.wait_until_ready()

    # ================================================================ infos

    @commands.command(name="channelinfo", aliases=["ci", "saloninfo"])
    @commands.guild_only()
    async def channelinfo(self, ctx, salon: discord.TextChannel = None):
        salon = salon or ctx.channel
        e = h.base_embed(f"#{salon.name}")
        e.add_field(name="ID", value=f"`{salon.id}`", inline=True)
        e.add_field(name="Catégorie",
                    value=salon.category.name if salon.category else "aucune", inline=True)
        e.add_field(name="Créé le", value=h.ts(salon.created_at), inline=True)
        e.add_field(name="NSFW", value="oui" if salon.is_nsfw() else "non", inline=True)
        e.add_field(name="Mode lent",
                    value=h.human_duration(salon.slowmode_delay) if salon.slowmode_delay
                    else "désactivé", inline=True)
        e.add_field(name="Fils actifs", value=str(len(salon.threads)), inline=True)
        if salon.topic:
            e.add_field(name="Sujet", value=h.clean(salon.topic, 500), inline=False)
        await ctx.reply(embed=e)

    @commands.command(name="emojiinfo")
    @commands.guild_only()
    async def emojiinfo(self, ctx, emoji: discord.Emoji):
        e = h.base_embed(f"Émoji — {emoji.name}")
        e.set_thumbnail(url=emoji.url)
        e.add_field(name="ID", value=f"`{emoji.id}`", inline=True)
        e.add_field(name="Animé", value="oui" if emoji.animated else "non", inline=True)
        e.add_field(name="Créé le", value=h.ts(emoji.created_at), inline=True)
        e.add_field(name="Code", value=f"`{str(emoji)}`", inline=False)
        e.add_field(name="Lien", value=f"[Ouvrir]({emoji.url})", inline=False)
        await ctx.reply(embed=e)

    @commands.command(name="emojis", aliases=["emojilist"])
    @commands.guild_only()
    async def emojis(self, ctx):
        if not ctx.guild.emojis:
            return await ctx.reply(embed=h.base_embed(description="Aucun émoji."))
        texte = " ".join(str(e) for e in ctx.guild.emojis[:120])
        await ctx.reply(
            embed=h.base_embed(f"Émojis ({len(ctx.guild.emojis)})", texte[:4000])
        )

    @commands.command(name="stealemoji", aliases=["steal", "voler"],
                      help="Ajoute un émoji d'un autre serveur. -steal :emoji: nom")
    @commands.guild_only()
    @h.is_owner_or(manage_expressions=True)
    @commands.bot_has_permissions(manage_expressions=True)
    async def stealemoji(self, ctx, emoji: discord.PartialEmoji, nom: str = None):
        try:
            octets = await emoji.read()
            nouveau = await ctx.guild.create_custom_emoji(
                name=nom or emoji.name, image=octets, reason=f"Ajouté par {ctx.author}"
            )
        except discord.HTTPException as exc:
            return await ctx.reply(
                embed=h.err_embed(f"Échec : {exc.text if hasattr(exc, 'text') else exc}")
            )
        await ctx.reply(embed=h.ok_embed(f"Émoji ajouté : {nouveau} `{nouveau.name}`"))

    @commands.command(name="boosters", aliases=["boosts"])
    @commands.guild_only()
    async def boosters(self, ctx):
        boosters = sorted(
            [m for m in ctx.guild.members if m.premium_since],
            key=lambda m: m.premium_since,
        )
        if not boosters:
            return await ctx.reply(embed=h.base_embed(description="Aucun booster."))
        lignes = [
            f"• {m.mention} — depuis {h.ts(m.premium_since)}" for m in boosters[:30]
        ]
        await ctx.reply(
            embed=h.base_embed(f"Boosters ({len(boosters)})", "\n".join(lignes))
        )

    @commands.command(name="inrole", help="Liste les membres ayant un rôle.")
    @commands.guild_only()
    async def inrole(self, ctx, *, role: discord.Role):
        membres = role.members
        if not membres:
            return await ctx.reply(embed=h.base_embed(description="Personne n'a ce rôle."))
        texte = ", ".join(m.display_name for m in membres[:60])
        e = h.base_embed(f"{role.name} — {len(membres)} membre(s)", h.clean(texte, 3500))
        await ctx.reply(embed=e)

    @commands.command(name="newmembers", aliases=["nouveaux"])
    @commands.guild_only()
    async def newmembers(self, ctx, nombre: int = 10):
        nombre = max(1, min(nombre, 25))
        membres = sorted(
            [m for m in ctx.guild.members if m.joined_at],
            key=lambda m: m.joined_at, reverse=True,
        )[:nombre]
        lignes = [f"• {m.mention} — {h.ts(m.joined_at)}" for m in membres]
        await ctx.reply(
            embed=h.base_embed(f"{nombre} derniers arrivés", "\n".join(lignes))
        )

    @commands.command(name="membercount", aliases=["mc"])
    @commands.guild_only()
    async def membercount(self, ctx):
        humains = sum(1 for m in ctx.guild.members if not m.bot)
        await ctx.reply(
            embed=h.base_embed(
                "Membres",
                f"**{ctx.guild.member_count:,}** au total\n"
                f"**{humains:,}** humains · **{ctx.guild.member_count - humains:,}** bots",
            )
        )

    @commands.command(name="firstmessage", aliases=["premier"])
    @commands.guild_only()
    async def firstmessage(self, ctx, salon: discord.TextChannel = None):
        salon = salon or ctx.channel
        async for message in salon.history(limit=1, oldest_first=True):
            e = h.base_embed(
                "Premier message du salon",
                h.clean(message.content, 500) or "*aucun texte*",
            )
            e.set_author(name=str(message.author),
                         icon_url=message.author.display_avatar.url)
            e.add_field(name="Envoyé", value=h.ts(message.created_at))
            e.add_field(name="Lien", value=f"[Aller au message]({message.jump_url})")
            return await ctx.reply(embed=e)
        await ctx.reply(embed=h.warn_embed("Salon vide."))

    @commands.command(name="banner", aliases=["banniere"])
    @commands.guild_only()
    async def banner(self, ctx):
        if not ctx.guild.banner:
            return await ctx.reply(embed=h.warn_embed("Ce serveur n'a pas de bannière."))
        e = h.base_embed("Bannière du serveur")
        e.set_image(url=ctx.guild.banner.url)
        await ctx.reply(embed=e)

    @commands.command(name="servericon", aliases=["icone"])
    @commands.guild_only()
    async def servericon(self, ctx):
        if not ctx.guild.icon:
            return await ctx.reply(embed=h.warn_embed("Ce serveur n'a pas d'icône."))
        e = h.base_embed("Icône du serveur", f"[Ouvrir]({ctx.guild.icon.url})")
        e.set_image(url=ctx.guild.icon.url)
        await ctx.reply(embed=e)

    @commands.command(name="perms", aliases=["permissions"])
    @commands.guild_only()
    async def perms(self, ctx, membre: discord.Member = None,
                    salon: discord.TextChannel = None):
        membre = membre or ctx.author
        salon = salon or ctx.channel
        p = salon.permissions_for(membre)
        oui = [n.replace("_", " ") for n, v in p if v]
        non = [n.replace("_", " ") for n, v in p if not v]
        e = h.base_embed(f"Permissions de {membre.display_name} dans #{salon.name}")
        e.add_field(name=f"Accordées ({len(oui)})",
                    value=h.clean(", ".join(oui) or "aucune", 1000), inline=False)
        e.add_field(name=f"Refusées ({len(non)})",
                    value=h.clean(", ".join(non) or "aucune", 1000), inline=False)
        await ctx.reply(embed=e)

    # ================================================================ utilitaires

    @commands.command(name="color", aliases=["couleur"], help="+color #5865F2")
    async def color(self, ctx, code: str):
        code = code.lstrip("#")
        try:
            valeur = int(code, 16)
            if not 0 <= valeur <= 0xFFFFFF:
                raise ValueError
        except ValueError:
            return await ctx.reply(embed=h.err_embed("Format attendu : `#5865F2`."))
        r, v, b = (valeur >> 16) & 255, (valeur >> 8) & 255, valeur & 255
        e = h.base_embed(
            f"#{code.upper()}",
            f"**RGB :** {r}, {v}, {b}\n**Décimal :** {valeur}",
            valeur,
        )
        await ctx.reply(embed=e)

    @commands.command(name="timestamp", aliases=["ts"],
                      help="Génère un horodatage Discord. -ts 2h")
    async def timestamp(self, ctx, *, duree: str = "0"):
        secondes = h.parse_duration(duree) or 0
        cible = h.now() + secondes
        styles = ["t", "T", "d", "D", "f", "F", "R"]
        lignes = [f"`<t:{cible}:{s}>` → <t:{cible}:{s}>" for s in styles]
        await ctx.reply(embed=h.base_embed("Horodatages Discord", "\n".join(lignes)))

    @commands.command(name="calc", aliases=["calcul"], help="+calc 2 * (3 + 4)")
    async def calc(self, ctx, *, expression: str):
        try:
            arbre = ast.parse(expression, mode="eval")
            resultat = calcul_sur(arbre.body)
        except Exception:
            return await ctx.reply(
                embed=h.err_embed(
                    "Expression invalide. Opérateurs autorisés : `+ - * / // % **`"
                )
            )
        await ctx.reply(
            embed=h.base_embed("Calcul", f"`{h.clean(expression, 200)}` = **{resultat}**")
        )

    @commands.command(name="base64", aliases=["b64"], help="+base64 encode Bonjour")
    async def base64_cmd(self, ctx, mode: str, *, texte: str):
        try:
            if mode.lower().startswith("e"):
                sortie = base64.b64encode(texte.encode()).decode()
            else:
                sortie = base64.b64decode(texte.encode()).decode()
        except Exception:
            return await ctx.reply(embed=h.err_embed("Impossible de traiter ce texte."))
        await ctx.reply(embed=h.base_embed("Base64", f"```{h.clean(sortie, 1800)}```"))

    @commands.command(name="reverse", aliases=["envers"])
    async def reverse(self, ctx, *, texte: str):
        await ctx.reply(h.clean(texte[::-1], 1900))

    @commands.command(name="mock", help="tRaNsFoRmE lE tExTe")
    async def mock(self, ctx, *, texte: str):
        sortie = "".join(
            c.upper() if i % 2 else c.lower() for i, c in enumerate(texte)
        )
        await ctx.reply(h.clean(sortie, 1900))

    @commands.command(name="clap", help="Ajoute 👏 entre 👏 les 👏 mots")
    async def clap(self, ctx, *, texte: str):
        await ctx.reply(h.clean(" \U0001f44f ".join(texte.split()), 1900))

    @commands.command(name="espace", aliases=["spaced"])
    async def espace(self, ctx, *, texte: str):
        await ctx.reply(h.clean(" ".join(texte), 1900))

    @commands.command(name="suggest", aliases=["suggestion"],
                      help="Propose une idée au staff.")
    @commands.guild_only()
    async def suggest(self, ctx, *, idee: str):
        e = h.base_embed("\U0001f4a1 Suggestion", h.clean(idee, 2000))
        e.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        e.set_footer(text=f"ID : {ctx.author.id}")
        message = await ctx.send(embed=e)
        for emoji in ("\U0001f44d", "\U0001f44e"):
            await message.add_reaction(emoji)

    @commands.command(name="poll2", aliases=["sondage"],
                      help="Sondage rapide oui/non. -sondage On change de logo ?")
    @commands.guild_only()
    async def sondage(self, ctx, *, question: str):
        e = h.base_embed("\U0001f4ca " + h.clean(question, 250),
                         f"— {ctx.author.mention}")
        message = await ctx.send(embed=e)
        for emoji in ("\u2705", "\u274c", "\U0001f937"):
            await message.add_reaction(emoji)

    @commands.command(name="uptime", aliases=["enligne"])
    async def uptime(self, ctx):
        secondes = int(
            (discord.utils.utcnow() - self.bot.start_time).total_seconds()
        )
        await ctx.reply(
            embed=h.base_embed(
                "En ligne depuis",
                f"**{h.human_duration(secondes)}**\n"
                f"Démarré {h.ts(self.bot.start_time)}",
            )
        )


# ==============================================================================
#  SECTION 19 - PANNEAU DE COMMANDES
# ==============================================================================




B = config.PREFIX
E = config.ELEVATED_PREFIX

FICHES = {
    "Modération": ("\U0001f528", B, [
        (f"{B}ban <@user|ID> [durée] [raison]", "Bannit un membre"),
        (f"{B}tempban <@user> <durée> <raison>", "Ban temporaire auto"),
        (f"{B}kick <@user> [raison]", "Expulse un membre"),
        (f"{B}softban <@user> [raison]", "Ban + unban (purge messages)"),
        (f"{B}tempmute <@user|ID> [durée]", "Rend un membre muet"),
        (f"{B}unmute <@user|ID>", "Retire le mute"),
        (f"{B}unmuteall", "Retire les mutes de tout le monde"),
        (f"{B}warn <@user|ID> <raison>", "Ajoute un avertissement"),
        (f"{B}clear <nombre|all>", "Supprime des messages"),
        (f"{B}lock / {B}unlock", "Bloque / rouvre le salon"),
        (f"{B}slowmode <temps>", "Active le mode lent"),
        (f"{B}jail <@user> [durée]", "Emprisonne un membre"),
    ]),
    "Surveillance & Infos": ("\U0001f50e", B, [
        (f"{B}history <@user|ID>", "Dossier du membre (casier)"),
        (f"{B}user <@user|ID>", "Infos détaillées"),
        (f"{B}pic <@user|ID>", "Photo de profil (pp)"),
        (f"{B}banner", "Bannière du serveur"),
        (f"{B}snipe", "Dernier message supprimé"),
        (f"{B}editsnipe", "Dernière modification"),
        (f"{B}modstats [@user]", "Classement des modérateurs"),
        (f"{B}absence [raison]", "Déclarer une absence"),
        (f"{B}member", "Statistiques du serveur"),
        (f"{B}vc", "Statistiques vocales"),
        (f"{B}notes <@user>", "Notes internes sur un membre"),
    ]),
    "Sanctions & Logs": ("\U0001f4dc", E, [
        (f"{E}sanction <@user|ID>", "Historique des sanctions"),
        (f"{E}mutelist", "Liste des membres mute/bannis"),
        (f"{E}delsanction <ID>", "Supprime une sanction"),
        (f"{E}delallsanction <@user>", "Efface tout l'historique"),
        (f"{E}note <@user> <texte>", "Ajoute une note interne"),
        (f"{E}delnote <ID>", "Supprime une note"),
        (f"{E}auditlog [n]", "Journal d'audit du serveur"),
        (f"{E}clearwarns <@user>", "Efface les dossiers d'un membre"),
    ]),
    "Blacklist / Hardban (Owner)": ("\U0001f6ab", E, [
        (f"{E}bl <@user|ID> [raison]", "Ban anti-retour + anti-alt"),
        (f"{E}unbl <ID>", "Lève le ban"),
        (f"{E}bls", "Liste des bannis"),
        (f"{E}hbconfig", "Réglages anti-alt"),
        (f"{E}botbl <@user>", "Bloque juste l'usage du bot (léger)"),
        (f"{E}whitelist add <@role>", "Rôle exempté de l'automod"),
    ]),
    "Rôles & Salons (Owner)": ("\u2699\ufe0f", E, [
        (f"{E}createrole <nom> [#couleur]", "Crée un rôle"),
        (f"{E}deleterole <@role>", "Supprime un rôle"),
        (f"{E}rolecolor <@role> <#hex>", "Change la couleur d'un rôle"),
        (f"{E}rolename <@role> <nom>", "Renomme un rôle"),
        (f"{E}roleall <@role>", "Donne un rôle à tout le monde"),
        (f"{E}temprole <@user> <@role> <durée>", "Rôle temporaire"),
        (f"{E}createchannel <nom>", "Crée un salon"),
        (f"{E}deletechannel [salon]", "Supprime un salon"),
        (f"{E}hidechannel / {E}showchannel", "Masque / réaffiche un salon"),
        (f"{E}nuke", "Recrée le salon (efface tout)"),
        (f'{E}addrolecS "nom" [emoji]', "Ajoute un rôle au menu de choix"),
        (f"{E}rolepanel [#salon]", "Publie le menu « choisis ton rôle »"),
    ]),
    "Vocal": ("\U0001f39b\ufe0f", B, [
        (f"{B}vckick <@user>", "Déconnecte du vocal"),
        (f"{B}vcmove <@user> <salon>", "Déplace en vocal"),
        (f"{B}summon <@user>", "Amène un membre dans ton salon"),
        (f"{B}followme <@role>", "Rassemble un rôle chez toi"),
        (f"{B}vclock / {B}vcunlock", "Verrouille un salon vocal"),
        (f"{B}muteall / {B}unmuteall", "Coupe le micro de tout le vocal"),
        (f"{B}voice setup", "Salons « créer votre salon »"),
    ]),
    "Tickets & Bienvenue": ("\U0001f3ab", E, [
        (f"{E}ticket panel", "Publie le panneau de tickets"),
        (f"{E}ticket staff <@role>", "Rôle du staff des tickets"),
        (f"{E}welcome channel <#salon>", "Salon de bienvenue"),
        (f"{E}welcome autorole <@role>", "Rôle automatique à l'arrivée"),
        (f"{E}goodbye channel <#salon>", "Salon des départs"),
    ]),
    "Sécurité (Owner)": ("\U0001f6e1\ufe0f", E, [
        (f"{E}antiraid on / off", "Active la protection anti-raid"),
        (f"{E}antiraid set <clé> <valeur>", "Règle les seuils"),
        (f"{E}antiraid panic [min]", "Verrouillage d'urgence"),
        (f"{E}hardban <@user|ID> [raison]", "Ban anti-retour + anti-alt"),
        (f"{E}unhardban <ID>", "Lève un hardban"),
        (f"{E}hardbans", "Liste des hardbans"),
        (f"{E}massban <ID...> [raison]", "Bannit plusieurs IDs"),
        (f"{E}lockdown on / off", "Verrouille tout le serveur"),
        (f"{E}verifylevel <niveau>", "Niveau de vérification"),
    ]),
    "Outils & Fun": ("\U0001f9f0", B, [
        (f"{B}tag <nom>", "Réponses personnalisées"),
        (f"{B}giveaway start <durée> <n> <lot>", "Lance un concours"),
        (f"{B}sticky set <texte>", "Message toujours épinglé"),
        (f"{B}remind <durée> <note>", "Rappel personnel"),
        (f"{B}calc <expression>", "Calculatrice"),
        (f"{B}poll <question>", "Sondage"),
        (f"{B}8ball <question>", "Boule magique"),
        (f"{B}claim <@user> [label]", "Pseudo consensuel (avec accord)"),
    ]),
}


class PanelSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label=titre, emoji=data[0],
                                 description=f"Préfixe {data[1]}", value=titre)
            for titre, data in FICHES.items()
        ]
        super().__init__(placeholder="Choisis une catégorie...",
                         options=options, custom_id="panel:select")

    async def callback(self, interaction: discord.Interaction):
        titre = self.values[0]
        emoji, prefixe, lignes = FICHES[titre]
        corps = "\n".join(f"`{usage}` — {desc}" for usage, desc in lignes)
        e = h.base_embed(f"{emoji} {titre}", corps)
        e.set_footer(
            text=f"{prefixe}help <commande> pour plus de détails · "
                 f"préfixe : {prefixe}"
        )
        await interaction.response.send_message(embed=e, ephemeral=True)


class PanelView(discord.ui.View):
    def __init__(self, bot=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(PanelSelect())


class Panel(commands.Cog):
    """Panneau de commandes thématique."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="panel", aliases=["panneau", "menu", "commandes", "cmds"],
                      help="Affiche le panneau de commandes.")
    @commands.guild_only()
    async def panel(self, ctx):
        total = len([c for c in self.bot.walk_commands() if not c.hidden])
        e = h.base_embed(
            f"{config.EMOJI['crown']} Panneau de commandes",
            (
                f"**{total}+** commandes en **{len(FICHES)}** catégories.\n\n"
                f"**Deux préfixes actifs :**\n"
                f"`{B}` — commandes de base (clear, ping, profil...)\n"
                f"`{E}` — commandes de rang supérieur (blacklist, sanctions...)\n\n"
                f"*Les deux fonctionnent partout ; le préfixe indiqué est la "
                f"convention.*\n\n"
                f"Choisis une catégorie ci-dessous."
            ),
        )
        for titre, (emoji, prefixe, lignes) in FICHES.items():
            e.add_field(name=f"{emoji} {titre}",
                        value=f"`{prefixe}` · {len(lignes)} cmd", inline=True)
        if ctx.guild.icon:
            e.set_thumbnail(url=ctx.guild.icon.url)
        e.set_footer(text=ctx.guild.name)
        await ctx.send(embed=e, view=PanelView(self.bot))


# ==============================================================================
#  SECTION 20 - SALONS VOCAUX TEMPORAIRES
# ==============================================================================





HUB_NAME = "\u300e+\u300f Cr\u00e9er votre salon"


# ============================================================ modals

class RenameModal(discord.ui.Modal, title="Renommer le salon"):
    nom = discord.ui.TextInput(
        label="Nouveau nom",
        placeholder="Ex : Chill entre potes",
        max_length=95,
        min_length=1,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.channel.edit(
                name=str(self.nom), reason=f"Renommé par {interaction.user}"
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                embed=h.err_embed(
                    "Discord a refusé le renommage. Tu ne peux renommer qu'environ "
                    "2 fois toutes les 10 minutes — c'est une limite de leur API."
                ),
                ephemeral=True,
            )
        await interaction.response.send_message(
            embed=h.ok_embed(f"Salon renommé en **{self.nom}**."), ephemeral=True
        )


class LimitModal(discord.ui.Modal, title="Limite de membres"):
    limite = discord.ui.TextInput(
        label="Nombre maximum (0 = illimité)",
        placeholder="Ex : 5",
        max_length=2,
    )

    async def on_submit(self, interaction: discord.Interaction):
        value = str(self.limite).strip()
        if not value.isdigit():
            return await interaction.response.send_message(
                embed=h.err_embed("Donne un nombre entre 0 et 99."), ephemeral=True
            )
        n = min(int(value), 99)
        await interaction.channel.edit(user_limit=n)
        texte = "illimitée" if n == 0 else f"**{n}** membres"
        await interaction.response.send_message(
            embed=h.ok_embed(f"Limite réglée sur {texte}."), ephemeral=True
        )


# ============================================================ selects éphémères

class KickSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Choisis qui expulser du salon",
            min_values=1, max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        cible = self.values[0]
        membre = interaction.guild.get_member(cible.id)
        if membre is None or membre.voice is None or membre.voice.channel != interaction.channel:
            return await interaction.response.send_message(
                embed=h.err_embed("Ce membre n'est pas dans le salon."), ephemeral=True
            )
        if membre.id == interaction.user.id:
            return await interaction.response.send_message(
                embed=h.err_embed("Tu ne peux pas t'expulser toi-même."), ephemeral=True
            )
        try:
            await membre.move_to(None, reason=f"Expulsé par {interaction.user}")
            # On l'empêche aussi de revenir immédiatement.
            await interaction.channel.set_permissions(membre, connect=False)
        except discord.HTTPException:
            return await interaction.response.send_message(
                embed=h.err_embed("Je n'ai pas pu le déplacer."), ephemeral=True
            )
        await interaction.response.send_message(
            embed=h.ok_embed(f"**{membre.display_name}** a été expulsé du salon."),
            ephemeral=True,
        )


class TransferSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Choisis le nouveau propriétaire",
            min_values=1, max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        cible = self.values[0]
        membre = interaction.guild.get_member(cible.id)
        if membre is None or membre.voice is None or membre.voice.channel != interaction.channel:
            return await interaction.response.send_message(
                embed=h.err_embed("Ce membre doit être dans le salon."), ephemeral=True
            )
        if membre.bot:
            return await interaction.response.send_message(
                embed=h.err_embed("Pas à un bot."), ephemeral=True
            )
        await interaction.client.db.set_temp_voice_owner(interaction.channel.id, membre.id)
        await interaction.response.send_message(
            embed=h.ok_embed(f"{membre.mention} est maintenant propriétaire du salon.")
        )


class EphemeralSelectView(discord.ui.View):
    def __init__(self, item):
        super().__init__(timeout=60)
        self.add_item(item)


# ============================================================ panneau

class VoicePanelView(discord.ui.View):
    """Panneau de contrôle envoyé dans le chat du salon vocal. Persistant."""

    def __init__(self, bot=None):
        super().__init__(timeout=None)
        self.bot = bot

    # -------------------------------------------------- contrôle d'accès
    async def _owner_check(self, interaction: discord.Interaction) -> bool:
        """
        Le propriétaire, ou n'importe quel modérateur, peut agir.
        Tout le reste est refusé en éphémère pour ne pas polluer le salon.
        """
        bot = interaction.client
        row = await bot.db.get_temp_voice(interaction.channel.id)
        if row is None:
            await interaction.response.send_message(
                embed=h.err_embed("Ce salon n'est pas un salon temporaire."),
                ephemeral=True,
            )
            return False
        if interaction.user.id == row["owner_id"]:
            return True
        if interaction.user.guild_permissions.manage_channels:
            return True
        proprio = interaction.guild.get_member(row["owner_id"])
        await interaction.response.send_message(
            embed=h.err_embed(
                f"Seul {proprio.mention if proprio else 'le propriétaire'} peut "
                f"utiliser ce panneau.\nS'il a quitté le salon, clique sur "
                f"**Réclamer**."
            ),
            ephemeral=True,
        )
        return False

    # -------------------------------------------------- ligne 1
    @discord.ui.button(label="Renommer", emoji="\u270f\ufe0f", row=0,
                       style=discord.ButtonStyle.secondary, custom_id="voice:rename")
    async def rename(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        await interaction.response.send_modal(RenameModal())

    @discord.ui.button(label="Limite", emoji="\U0001f465", row=0,
                       style=discord.ButtonStyle.secondary, custom_id="voice:limit")
    async def limit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        await interaction.response.send_modal(LimitModal())

    @discord.ui.button(label="Verrouiller", emoji="\U0001f512", row=0,
                       style=discord.ButtonStyle.primary, custom_id="voice:lock")
    async def lock(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        everyone = interaction.guild.default_role
        ow = interaction.channel.overwrites_for(everyone)
        verrouille = ow.connect is False
        ow.connect = None if verrouille else False
        await interaction.channel.set_permissions(everyone, overwrite=ow)
        await interaction.response.send_message(
            embed=h.ok_embed(
                "Salon **déverrouillé** — tout le monde peut rejoindre."
                if verrouille else
                "Salon **verrouillé** — plus personne ne peut rejoindre."
            )
        )

    @discord.ui.button(label="Masquer", emoji="\U0001f441\ufe0f", row=0,
                       style=discord.ButtonStyle.primary, custom_id="voice:hide")
    async def hide(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        everyone = interaction.guild.default_role
        ow = interaction.channel.overwrites_for(everyone)
        masque = ow.view_channel is False
        ow.view_channel = None if masque else False
        await interaction.channel.set_permissions(everyone, overwrite=ow)
        await interaction.response.send_message(
            embed=h.ok_embed(
                "Salon **visible** de nouveau." if masque
                else "Salon **masqué** — invisible pour les autres."
            )
        )

    # -------------------------------------------------- ligne 2
    @discord.ui.button(label="Expulser", emoji="\U0001f462", row=1,
                       style=discord.ButtonStyle.danger, custom_id="voice:kick")
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        await interaction.response.send_message(
            embed=h.base_embed("Expulser un membre", "Choisis-le dans la liste."),
            view=EphemeralSelectView(KickSelect()),
            ephemeral=True,
        )

    @discord.ui.button(label="Autoriser", emoji="\u2795", row=1,
                       style=discord.ButtonStyle.success, custom_id="voice:allow")
    async def allow(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return

        class AllowSelect(discord.ui.UserSelect):
            def __init__(self):
                super().__init__(placeholder="Qui autoriser à rejoindre ?",
                                 min_values=1, max_values=1)

            async def callback(self, inter: discord.Interaction):
                membre = inter.guild.get_member(self.values[0].id)
                await inter.channel.set_permissions(
                    membre, connect=True, view_channel=True
                )
                await inter.response.send_message(
                    embed=h.ok_embed(
                        f"{membre.mention} peut rejoindre, même si le salon est fermé."
                    ),
                    ephemeral=True,
                )

        await interaction.response.send_message(
            embed=h.base_embed("Autoriser un membre", "Choisis-le dans la liste."),
            view=EphemeralSelectView(AllowSelect()),
            ephemeral=True,
        )

    @discord.ui.button(label="Transférer", emoji="\U0001f451", row=1,
                       style=discord.ButtonStyle.secondary, custom_id="voice:transfer")
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._owner_check(interaction):
            return
        await interaction.response.send_message(
            embed=h.base_embed("Transférer la propriété",
                               "Le membre doit être présent dans le salon."),
            view=EphemeralSelectView(TransferSelect()),
            ephemeral=True,
        )

    @discord.ui.button(label="Réclamer", emoji="\U0001f64b", row=1,
                       style=discord.ButtonStyle.success, custom_id="voice:claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        bot = interaction.client
        row = await bot.db.get_temp_voice(interaction.channel.id)
        if row is None:
            return await interaction.response.send_message(
                embed=h.err_embed("Ce salon n'est pas un salon temporaire."),
                ephemeral=True,
            )
        if row["owner_id"] == interaction.user.id:
            return await interaction.response.send_message(
                embed=h.warn_embed("Tu es déjà propriétaire."), ephemeral=True
            )
        # On ne peut réclamer que si l'ancien propriétaire n'est plus là.
        proprio = interaction.guild.get_member(row["owner_id"])
        if proprio and proprio.voice and proprio.voice.channel == interaction.channel:
            return await interaction.response.send_message(
                embed=h.err_embed(
                    f"{proprio.mention} est toujours dans le salon. "
                    f"Impossible de le réclamer."
                ),
                ephemeral=True,
            )
        if interaction.user.voice is None or interaction.user.voice.channel != interaction.channel:
            return await interaction.response.send_message(
                embed=h.err_embed("Tu dois être dans le salon pour le réclamer."),
                ephemeral=True,
            )
        await bot.db.set_temp_voice_owner(interaction.channel.id, interaction.user.id)
        await interaction.response.send_message(
            embed=h.ok_embed(f"{interaction.user.mention} est le nouveau propriétaire.")
        )


# ============================================================ cog

class TempVoice(commands.Cog):
    """Salons vocaux temporaires créés à la demande."""

    ROLE_PV = "All"  # rôle requis pour +privvoc et +decalepv

    def __init__(self, bot):
        self.bot = bot
        # Salons créés par +decalepv : {channel_id: owner_id}.
        # Quand le propriétaire quitte, le salon est supprimé immédiatement.
        self.pv_channels: dict[int, int] = {}

    # -------------------------------------------------- panneau

    def panel_embed(self, owner: discord.Member) -> discord.Embed:
        e = h.base_embed(
            "\U0001f39b\ufe0f Panneau de contrôle",
            (
                f"Salon de {owner.mention}. Tu es le seul à pouvoir utiliser ces "
                f"boutons (le staff aussi).\n\n"
                f"\u270f\ufe0f **Renommer** — change le nom du salon\n"
                f"\U0001f465 **Limite** — nombre maximum de membres\n"
                f"\U0001f512 **Verrouiller** — empêche les nouvelles arrivées\n"
                f"\U0001f441\ufe0f **Masquer** — rend le salon invisible\n"
                f"\U0001f462 **Expulser** — vire quelqu'un du salon\n"
                f"\u2795 **Autoriser** — laisse entrer quelqu'un malgré le verrou\n"
                f"\U0001f451 **Transférer** — donne le salon à un autre\n"
                f"\U0001f64b **Réclamer** — si le propriétaire est parti\n\n"
                f"*Le salon se supprime tout seul quand il se vide.*"
            ),
        )
        e.set_thumbnail(url=owner.display_avatar.url)
        return e

    # -------------------------------------------------- événement principal

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before, after):
        if member.bot:
            return

        # --- +decalepv : le propriétaire quitte son salon PV -> suppression directe
        if (before.channel and before.channel != after.channel
                and before.channel.id in self.pv_channels
                and self.pv_channels[before.channel.id] == member.id):
            self.pv_channels.pop(before.channel.id, None)
            try:
                await before.channel.delete(reason="PV : le propriétaire a quitté")
            except discord.HTTPException:
                pass

        cfg = await self.bot.db.tempvoice_config(member.guild.id)

        # --- création : le membre rejoint le salon d'accueil
        if after.channel and cfg["hub_channel"] and after.channel.id == cfg["hub_channel"]:
            await self.create_channel(member, cfg)

        # --- suppression : le salon temporaire quitté est maintenant vide
        if before.channel and before.channel != after.channel:
            row = await self.bot.db.get_temp_voice(before.channel.id)
            if row and len(before.channel.members) == 0:
                try:
                    await before.channel.delete(reason="Salon temporaire vide")
                except discord.HTTPException:
                    pass
                await self.bot.db.remove_temp_voice(before.channel.id)

    async def create_channel(self, member: discord.Member, cfg):
        guild = member.guild
        category = guild.get_channel(cfg["category"]) if cfg["category"] else None
        if category is None:
            hub = guild.get_channel(cfg["hub_channel"])
            category = hub.category if hub else None

        nom = (cfg["name_template"] or "Salon de {user}").replace(
            "{user}", member.display_name
        ).replace("{username}", member.name)[:95]

        overwrites = {
            member: discord.PermissionOverwrite(
                connect=True, view_channel=True, manage_channels=True,
                move_members=True, mute_members=True,
            ),
            guild.me: discord.PermissionOverwrite(
                connect=True, view_channel=True, manage_channels=True,
                move_members=True, send_messages=True,
            ),
        }

        try:
            channel = await guild.create_voice_channel(
                name=nom,
                category=category,
                user_limit=cfg["default_limit"] or 0,
                overwrites=overwrites,
                reason=f"Salon temporaire pour {member}",
            )
        except discord.Forbidden:
            return
        except discord.HTTPException:
            return

        try:
            await member.move_to(channel, reason="Salon temporaire créé")
        except discord.HTTPException:
            # Le membre est parti avant qu'on ait fini : on nettoie.
            await channel.delete(reason="Le membre a quitté avant le déplacement")
            return

        await self.bot.db.add_temp_voice(channel.id, guild.id, member.id)

        if cfg["send_panel"]:
            try:
                await channel.send(
                    content=member.mention,
                    embed=self.panel_embed(member),
                    view=VoicePanelView(self.bot),
                )
            except discord.HTTPException:
                pass

    # -------------------------------------------------- configuration

    @commands.group(name="voice", aliases=["vocal", "salonvocal"], invoke_without_command=True)
    @commands.guild_only()
    async def voice(self, ctx):
        cfg = await self.bot.db.tempvoice_config(ctx.guild.id)
        hub = ctx.guild.get_channel(cfg["hub_channel"]) if cfg["hub_channel"] else None
        cat = ctx.guild.get_channel(cfg["category"]) if cfg["category"] else None
        actifs = await self.bot.db.all_temp_voice(ctx.guild.id)

        nom_cat = cat.name if cat else "celle du salon d'accueil"
        e = h.base_embed("\U0001f39b\ufe0f Salons vocaux temporaires")
        e.description = (
            f"**Salon d'accueil :** {hub.mention if hub else '*non configuré*'}\n"
            f"**Catégorie :** {nom_cat}\n"
            f"**Modèle de nom :** `{cfg['name_template']}`\n"
            f"**Limite par défaut :** "
            f"{cfg['default_limit'] or 'illimitée'}\n"
            f"**Panneau auto :** {'oui' if cfg['send_panel'] else 'non'}\n"
            f"**Salons actifs :** {len(actifs)}\n\n"
            f"`{ctx.prefix}voice setup` — tout créer automatiquement\n"
            f"`{ctx.prefix}voice hub <salon vocal>` — définir l'accueil\n"
            f"`{ctx.prefix}voice categorie <catégorie>`\n"
            f"`{ctx.prefix}voice nom <modèle>` — ex. `Salon de {{user}}`\n"
            f"`{ctx.prefix}voice limite <0-99>`\n"
            f"`{ctx.prefix}voice panneau on|off`\n"
            f"`{ctx.prefix}voice off` — désactiver le système"
        )
        await ctx.reply(embed=e)

    @voice.command(name="setup", aliases=["config"],
                   help="Crée la catégorie et le salon d'accueil automatiquement.")
    @h.is_owner_or(administrator=True)
    async def voice_setup(self, ctx):
        async with ctx.typing():
            categorie = discord.utils.get(ctx.guild.categories, name="Salons vocaux")
            if categorie is None:
                categorie = await ctx.guild.create_category(
                    "Salons vocaux", reason="Système de salons temporaires"
                )
            hub = discord.utils.get(ctx.guild.voice_channels, name=HUB_NAME)
            if hub is None:
                hub = await ctx.guild.create_voice_channel(
                    HUB_NAME,
                    category=categorie,
                    reason="Salon d'accueil des salons temporaires",
                )
            await self.bot.db.set_tempvoice(ctx.guild.id, "hub_channel", hub.id)
            await self.bot.db.set_tempvoice(ctx.guild.id, "category", categorie.id)

        await ctx.reply(
            embed=h.ok_embed(
                f"Système prêt.\n"
                f"**Accueil :** {hub.mention}\n"
                f"**Catégorie :** {categorie.name}\n\n"
                f"Rejoins {hub.mention} pour tester — ton salon sera créé "
                f"immédiatement, avec son panneau de contrôle."
            )
        )

    @voice.command(name="hub", aliases=["accueil"])
    @h.is_owner_or(administrator=True)
    async def voice_hub(self, ctx, channel: discord.VoiceChannel):
        await self.bot.db.set_tempvoice(ctx.guild.id, "hub_channel", channel.id)
        await ctx.reply(
            embed=h.ok_embed(f"Salon d'accueil réglé sur {channel.mention}.")
        )

    @voice.command(name="categorie", aliases=["category", "cat"])
    @h.is_owner_or(administrator=True)
    async def voice_category(self, ctx, category: discord.CategoryChannel):
        await self.bot.db.set_tempvoice(ctx.guild.id, "category", category.id)
        await ctx.reply(
            embed=h.ok_embed(f"Les salons seront créés dans **{category.name}**.")
        )

    @voice.command(name="nom", aliases=["name", "template"])
    @h.is_owner_or(administrator=True)
    async def voice_name(self, ctx, *, template: str):
        if "{user}" not in template and "{username}" not in template:
            return await ctx.reply(
                embed=h.err_embed(
                    "Le modèle doit contenir `{user}` (pseudo affiché) "
                    "ou `{username}` (nom d'utilisateur)."
                )
            )
        await self.bot.db.set_tempvoice(ctx.guild.id, "name_template", template[:90])
        apercu = template.replace("{user}", ctx.author.display_name).replace(
            "{username}", ctx.author.name
        )
        await ctx.reply(
            embed=h.ok_embed(f"Modèle enregistré.\nAperçu : **{apercu[:90]}**")
        )

    @voice.command(name="limite", aliases=["limit"])
    @h.is_owner_or(administrator=True)
    async def voice_limit(self, ctx, amount: int):
        amount = max(0, min(amount, 99))
        await self.bot.db.set_tempvoice(ctx.guild.id, "default_limit", amount)
        await ctx.reply(
            embed=h.ok_embed(
                f"Limite par défaut : **{amount or 'illimitée'}**."
            )
        )

    @voice.command(name="panneau", aliases=["panel"])
    @h.is_owner_or(administrator=True)
    async def voice_panel(self, ctx, state: str = "on"):
        on = state.lower() in ("on", "oui", "true", "1", "yes")
        await self.bot.db.set_tempvoice(ctx.guild.id, "send_panel", int(on))
        await ctx.reply(
            embed=h.ok_embed(
                f"Panneau automatique **{'activé' if on else 'désactivé'}**."
            )
        )

    @voice.command(name="off", aliases=["disable", "stop"])
    @h.is_owner_or(administrator=True)
    async def voice_off(self, ctx):
        await self.bot.db.set_tempvoice(ctx.guild.id, "hub_channel", None)
        await ctx.reply(
            embed=h.warn_embed(
                "Système désactivé. Les salons déjà créés restent jusqu'à ce "
                "qu'ils se vident."
            )
        )

    @voice.command(name="clean", aliases=["nettoyer"],
                   help="Supprime les salons temporaires vides oubliés.")
    @h.is_owner_or(administrator=True)
    async def voice_clean(self, ctx):
        rows = await self.bot.db.all_temp_voice(ctx.guild.id)
        supprimes = 0
        for row in rows:
            channel = ctx.guild.get_channel(row["channel_id"])
            if channel is None:
                await self.bot.db.remove_temp_voice(row["channel_id"])
                supprimes += 1
            elif len(channel.members) == 0:
                try:
                    await channel.delete(reason="Nettoyage des salons vides")
                except discord.HTTPException:
                    continue
                await self.bot.db.remove_temp_voice(row["channel_id"])
                supprimes += 1
            await asyncio.sleep(0.2)
        await ctx.reply(
            embed=h.ok_embed(f"**{supprimes}** salon(s) nettoyé(s).")
        )

    @commands.command(name="vcpanneau", aliases=["vcpanel"],
                      help="Réaffiche le panneau de contrôle du salon vocal courant.")
    @commands.guild_only()
    async def panneau(self, ctx):
        if ctx.author.voice is None:
            return await ctx.reply(
                embed=h.err_embed("Tu dois être dans un salon vocal.")
            )
        channel = ctx.author.voice.channel
        row = await self.bot.db.get_temp_voice(channel.id)
        if row is None:
            return await ctx.reply(
                embed=h.err_embed("Ce salon n'est pas un salon temporaire.")
            )
        proprio = ctx.guild.get_member(row["owner_id"]) or ctx.author
        await channel.send(
            embed=self.panel_embed(proprio), view=VoicePanelView(self.bot)
        )

    # -------------------------------------------------- commandes PV (rôle All)

    @commands.command(name="privvoc",
                      help="+privvoc [off] — verrouille (ou déverrouille) ton salon vocal.")
    @commands.guild_only()
    @commands.has_role("All")
    async def privvoc(self, ctx, mode: str = "on"):
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            return await ctx.reply(embed=h.err_embed("Tu dois être dans un salon vocal."))
        voc = ctx.author.voice.channel
        unlock = mode.lower() in ("off", "unlock", "open")
        try:
            await voc.set_permissions(
                ctx.guild.default_role,
                connect=None if unlock else False,
                reason=f"privvoc par {ctx.author}",
            )
        except discord.Forbidden:
            return await ctx.reply(
                embed=h.err_embed("Il me manque la permission de gérer ce salon.")
            )
        if unlock:
            await ctx.reply(embed=h.ok_embed(f"**{voc.name}** est déverrouillé."))
        else:
            await ctx.reply(embed=h.ok_embed(f"**{voc.name}** est verrouillé."))

    @commands.command(name="decalepv",
                      help="+decalepv — crée un vocal privé et y déplace tout le monde. "
                           "Supprimé dès que tu quittes.")
    @commands.guild_only()
    @commands.has_role("All")
    async def decalepv(self, ctx):
        if ctx.author.voice is None or ctx.author.voice.channel is None:
            return await ctx.reply(embed=h.err_embed("Tu dois être dans un salon vocal."))
        ancien = ctx.author.voice.channel

        overwrites = {
            ctx.author: discord.PermissionOverwrite(
                connect=True, view_channel=True, manage_channels=True,
                move_members=True, mute_members=True,
            ),
            ctx.guild.me: discord.PermissionOverwrite(
                connect=True, view_channel=True, manage_channels=True,
                move_members=True, send_messages=True,
            ),
        }
        try:
            nouveau = await ctx.guild.create_voice_channel(
                name=f"PV de {ctx.author.display_name}"[:95],
                category=ancien.category,
                overwrites=overwrites,
                reason=f"decalepv par {ctx.author}",
            )
        except discord.Forbidden:
            return await ctx.reply(
                embed=h.err_embed("Il me manque la permission de créer un salon vocal.")
            )

        # Enregistré AVANT les déplacements : si le propriétaire ressort
        # pendant qu'on déplace les autres, le listener nettoie quand même.
        self.pv_channels[nouveau.id] = ctx.author.id

        deplaces = 0
        for membre in list(ancien.members):
            try:
                await membre.move_to(nouveau, reason=f"decalepv par {ctx.author}")
                deplaces += 1
            except discord.HTTPException:
                pass

        if deplaces == 0:
            self.pv_channels.pop(nouveau.id, None)
            try:
                await nouveau.delete(reason="decalepv : aucun membre déplacé")
            except discord.HTTPException:
                pass
            return await ctx.reply(
                embed=h.err_embed("Je n'ai pas pu déplacer les membres (permission Déplacer les membres ?)")
            )

        await ctx.reply(
            embed=h.ok_embed(
                f"**{nouveau.name}** créé — {deplaces} membre(s) déplacé(s).\n"
                f"Le salon sera supprimé dès que tu le quittes."
            )
        )


# ==============================================================================
#  SECTION 21 - SCHEDULER (temp punishment expiry)
# ==============================================================================





log = logging.getLogger("scheduler")


class Scheduler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.tick.start()
        self.housekeeping.start()

    def cog_unload(self):
        self.tick.cancel()
        self.housekeeping.cancel()

    # ------------------------------------------------------------ main loop
    @tasks.loop(seconds=15)
    async def tick(self):
        try:
            due = await self.bot.db.due_actions(h.now())
        except Exception:
            log.exception("Failed to read due actions")
            return

        for row in due:
            guild = self.bot.get_guild(row["guild_id"])
            if guild is None:
                await self.bot.db.complete_action(row["id"])
                continue
            try:
                await self.reverse(guild, row)
            except discord.HTTPException as exc:
                log.warning("Could not reverse action %s: %s", row["id"], exc)
            finally:
                await self.bot.db.complete_action(row["id"])

    async def reverse(self, guild: discord.Guild, row):
        action = row["action"]
        user_id = row["user_id"]
        payload = json.loads(row["payload"] or "{}")

        if action == "ban":
            try:
                user = await self.bot.fetch_user(user_id)
                await guild.unban(user, reason="Temporary ban expired")
                await self.announce(guild, f"**{user}** débanni — le bannissement temporaire a expiré.")
            except discord.NotFound:
                pass

        elif action == "mute":
            member = guild.get_member(user_id)
            if not member:
                return
            role = guild.get_role(payload.get("role", 0))
            if role and role in member.roles:
                await member.remove_roles(role, reason="Temporary mute expired")
            if member.is_timed_out():
                await member.timeout(None, reason="Temporary mute expired")
            await self.announce(guild, f"**{member}** n'est plus muet — le mute temporaire a expiré.")

        elif action == "jail":
            member = guild.get_member(user_id)
            if not member:
                return
            jail_row = await self.bot.db.get_jail(guild.id, user_id)
            role = guild.get_role(payload.get("role", 0))
            restore = []
            if jail_row:
                for rid in json.loads(jail_row["roles"] or "[]"):
                    r = guild.get_role(rid)
                    if r and r < guild.me.top_role:
                        restore.append(r)
            keep = [r for r in member.roles
                    if r != guild.default_role and r != role]
            try:
                await member.edit(roles=list(set(keep + restore)),
                                  reason="Jail sentence expired")
            except discord.HTTPException:
                pass
            await self.bot.db.remove_jail(guild.id, user_id)
            await self.announce(
                guild,
                f"**{member}** est sorti de prison — la peine a expiré. "
                f"{len(restore)} rôle(s) restaurés."
            )

        elif action == "temprole":
            member = guild.get_member(user_id)
            role = guild.get_role(payload.get("role", 0)) if member else None
            if member and role and role in member.roles:
                try:
                    await member.remove_roles(role, reason="Rôle temporaire expiré")
                except discord.HTTPException:
                    pass
                await self.announce(
                    guild, f"Rôle **{role.name}** retiré à **{member}** — durée expirée."
                )

        elif action == "quarantine":
            member = guild.get_member(user_id)
            role = guild.get_role(payload.get("role", 0)) if member else None
            if member and role and role in member.roles:
                await member.remove_roles(role, reason="Quarantine expired")

    async def announce(self, guild, text):
        settings = await self.bot.db.guild_settings(guild.id)
        if not settings or not settings["mod_log"]:
            return
        channel = guild.get_channel(settings["mod_log"])
        if channel:
            try:
                await channel.send(
                    embed=h.base_embed(
                        f"{config.EMOJI['clock']} Libération automatique",
                        text,
                        config.COLOR_SUCCESS,
                    )
                )
            except discord.HTTPException:
                pass

    @tick.before_loop
    async def before_tick(self):
        await self.bot.wait_until_ready()

    # ------------------------------------------------------------ housekeeping
    @tasks.loop(hours=1)
    async def housekeeping(self):
        # Trim finished temp actions older than a week so the table stays small.
        cutoff = h.now() - 604800
        await self.bot.db.execute(
            "DELETE FROM temp_actions WHERE done=1 AND expires_at < ?", (cutoff,)
        )
        # Refresh presence with the current guild count.
        try:
            await self.bot.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"{config.PREFIX}help | {len(self.bot.guilds)} servers",
                )
            )
        except discord.HTTPException:
            pass

    @housekeeping.before_loop
    async def before_housekeeping(self):
        await self.bot.wait_until_ready()


# ==============================================================================
#  SECTION 22 - HELP & UTILITY
# ==============================================================================





CATEGORY_META = {
    "Moderation": (config.EMOJI["hammer"], "Bans, mutes, avertissements, purges, verrouillages"),
    "AntiRaid": (config.EMOJI["shield"], "Détection de raids, automod, anti-nuke"),
    "Tickets": (config.EMOJI["ticket"], "Salons d'assistance privés"),
    "Welcome": (config.EMOJI["wave"], "Messages d'arrivée et de départ, rôle auto"),
    "Stats": (config.EMOJI["chart"], "Profils, classements, infos serveur"),
    "Fun": ("\U0001f3b2", "Jeux, réclamations, sondages, rappels"),
    "Utility": ("\U0001f527", "Aide, ping, configuration, diagnostics"),
    "Scheduler": ("\u23f1\ufe0f", "Tâches de fond (aucune commande)"),
}


class HelpSelect(discord.ui.Select):
    def __init__(self, bot, ctx):
        self.bot = bot
        self.ctx = ctx
        options = [
            discord.SelectOption(label="Vue d'ensemble", emoji="\U0001f3e0", value="__home__")
        ]
        for name, cog in bot.cogs.items():
            if not cog.get_commands():
                continue
            emoji, desc = CATEGORY_META.get(name, ("\U0001f4c1", "Commandes"))
            options.append(
                discord.SelectOption(label=name, emoji=emoji, description=desc[:90],
                                     value=name)
            )
        super().__init__(placeholder="Parcourir une catégorie...", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.ctx.author.id:
            return await interaction.response.send_message(
                embed=h.err_embed("Lance ton propre `+help`."), ephemeral=True
            )
        choice = self.values[0]
        cog_helper = self.bot.get_cog("Utility")
        if choice == "__home__":
            embed = cog_helper.overview_embed(self.ctx)
        else:
            embed = cog_helper.cog_embed(self.ctx, self.bot.get_cog(choice))
        await interaction.response.edit_message(embed=embed)


class HelpView(discord.ui.View):
    def __init__(self, bot, ctx):
        super().__init__(timeout=180)
        self.add_item(HelpSelect(bot, ctx))


class Utility(commands.Cog):
    """Aide, diagnostics, configuration."""

    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------ embeds
    def overview_embed(self, ctx) -> discord.Embed:
        total = len([c for c in self.bot.walk_commands()])
        e = h.base_embed(
            f"{ctx.me.display_name} — guide des commandes",
            (
                f"Le préfixe ici est **`{ctx.prefix}`** (me mentionner marche aussi).\n"
                f"**{total}** commandes réparties en **{len(self.bot.cogs)}** modules.\n\n"
                f"Choisis une catégorie ci-dessous, ou lance "
                f"`{ctx.prefix}help <commande>` pour le détail d'une commande."
            ),
        )
        for name, cog in self.bot.cogs.items():
            cmds = cog.get_commands()
            if not cmds:
                continue
            emoji, desc = CATEGORY_META.get(name, ("\U0001f4c1", ""))
            e.add_field(
                name=f"{emoji} {name} — {len(cmds)}",
                value=desc or (cog.__doc__ or "").strip()[:80],
                inline=True,
            )
        e.set_footer(text=f"Demandé par {ctx.author}",
                     icon_url=ctx.author.display_avatar.url)
        if ctx.me.display_avatar:
            e.set_thumbnail(url=ctx.me.display_avatar.url)
        return e

    def cog_embed(self, ctx, cog) -> discord.Embed:
        emoji, desc = CATEGORY_META.get(cog.qualified_name, ("\U0001f4c1", ""))
        e = h.base_embed(f"{emoji} {cog.qualified_name}", desc)
        for cmd in sorted(cog.get_commands(), key=lambda c: c.name):
            sig = f"{ctx.prefix}{cmd.qualified_name} {cmd.signature}".strip()
            aliases = f"\n*alias : {', '.join(cmd.aliases)}*" if cmd.aliases else ""
            sub = ""
            if isinstance(cmd, commands.Group):
                sub = "\n*sous-commandes : " + ", ".join(
                    c.name for c in cmd.commands
                ) + "*"
            e.add_field(
                name=f"`{sig}`",
                value=(cmd.help or cmd.short_doc or "Aucune description.")[:200]
                      + aliases + sub,
                inline=False,
            )
        return e

    # ------------------------------------------------------------ help
    @commands.command(name="help", aliases=["h", "commands"])
    async def help_cmd(self, ctx, *, query: str = None):
        if query is None:
            return await ctx.reply(
                embed=self.overview_embed(ctx),
                view=HelpView(self.bot, ctx),
                mention_author=False,
            )

        cog = discord.utils.find(
            lambda c: c[0].lower() == query.lower(), self.bot.cogs.items()
        )
        if cog:
            return await ctx.reply(embed=self.cog_embed(ctx, cog[1]),
                                   mention_author=False)

        cmd = self.bot.get_command(query.lower())
        if not cmd:
            return await ctx.reply(
                embed=h.err_embed(f"Aucune commande ou catégorie nommée `{h.clean(query, 50)}`."),
                mention_author=False,
            )

        e = h.base_embed(f"`{ctx.prefix}{cmd.qualified_name}`",
                         cmd.help or "Aucune description.")
        e.add_field(
            name="Utilisation",
            value=f"`{ctx.prefix}{cmd.qualified_name} {cmd.signature}`".strip(),
            inline=False,
        )
        if cmd.aliases:
            e.add_field(name="Alias",
                        value=", ".join(f"`{a}`" for a in cmd.aliases), inline=False)
        if isinstance(cmd, commands.Group):
            e.add_field(
                name="Sous-commandes",
                value="\n".join(
                    f"`{ctx.prefix}{c.qualified_name} {c.signature}` — "
                    f"{(c.help or c.short_doc or '')[:60]}"
                    for c in cmd.commands
                )[:1000],
                inline=False,
            )
        e.set_footer(text=f"Module : {cmd.cog_name or 'aucun'}")
        await ctx.reply(embed=e, mention_author=False)

    # ------------------------------------------------------------ diagnostics
    @commands.command(name="ping")
    async def ping(self, ctx):
        start = time.perf_counter()
        msg = await ctx.reply(embed=h.base_embed("Ping en cours..."), mention_author=False)
        rtt = (time.perf_counter() - start) * 1000

        db_start = time.perf_counter()
        await self.bot.db.fetchone("SELECT 1")
        db_ms = (time.perf_counter() - db_start) * 1000

        ws = self.bot.latency * 1000
        color = (config.COLOR_SUCCESS if ws < 150 else
                 config.COLOR_WARN if ws < 400 else config.COLOR_ERROR)
        e = h.base_embed(
            "\U0001f3d3 Pong",
            f"**Passerelle :** {ws:.0f}ms\n"
            f"**Aller-retour :** {rtt:.0f}ms\n"
            f"**Base de données :** {db_ms:.1f}ms",
            color,
        )
        await msg.edit(embed=e)

    @commands.command(name="botinfo", aliases=["about", "info"])
    async def botinfo(self, ctx):
        uptime = int((discord.utils.utcnow() - self.bot.start_time).total_seconds())
        members = sum(g.member_count or 0 for g in self.bot.guilds)
        e = h.base_embed(f"{ctx.me.display_name}")
        e.add_field(name="En ligne depuis", value=h.human_duration(uptime), inline=True)
        e.add_field(name="Serveurs", value=f"{len(self.bot.guilds):,}", inline=True)
        e.add_field(name="Membres", value=f"{members:,}", inline=True)
        e.add_field(name="Commandes", value=str(len(list(self.bot.walk_commands()))),
                    inline=True)
        e.add_field(name="Latence", value=f"{self.bot.latency * 1000:.0f}ms", inline=True)
        e.add_field(name="discord.py", value=discord.__version__, inline=True)
        e.add_field(name="Python", value=platform.python_version(), inline=True)
        e.set_thumbnail(url=ctx.me.display_avatar.url)
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="setup", help="Te guide dans toute la configuration.")
    @commands.guild_only()
    @h.is_owner_or(administrator=True)
    async def setup_cmd(self, ctx):
        p = ctx.prefix
        e = h.base_embed(
            "\U0001f527 Liste de configuration",
            "À lancer dans l'ordre. Chaque étape est indépendante — saute ce que tu ne veux pas.",
        )
        e.add_field(
            name="1. Journalisation",
            value=f"`{p}setmodlog #mod-logs`\n`{p}antiraid logchannel #alerts`",
            inline=False,
        )
        e.add_field(
            name="2. Protection",
            value=(
                f"`{p}antiraid on`\n"
                f"`{p}antiraid alertrole @Moderateurs`\n"
                f"`{p}antiraid set raid_action lockdown`\n"
                f"Tout revoir avec `{p}antiraid`"
            ),
            inline=False,
        )
        e.add_field(
            name="3. Tickets",
            value=(
                f"`{p}ticket category <category>`\n"
                f"`{p}ticket staff @Support`\n"
                f"`{p}ticket log #ticket-logs`\n"
                f"`{p}ticket panel #support`"
            ),
            inline=False,
        )
        e.add_field(
            name="4. Bienvenue",
            value=(
                f"`{p}welcome channel #general`\n"
                f"`{p}welcome message {{mention}} welcome to {{server}}!`\n"
                f"`{p}welcome autorole @Member`\n"
                f"`{p}goodbye channel #general`\n"
                f"Aperçu avec `{p}welcome test`"
            ),
            inline=False,
        )
        e.add_field(
            name="5. Vérifier mes permissions",
            value=f"`{p}permcheck`",
            inline=False,
        )
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="permcheck")
    @commands.guild_only()
    async def permcheck(self, ctx):
        needed = {
            "manage_guild": "réglages",
            "ban_members": "bannissements",
            "kick_members": "expulsions",
            "moderate_members": "exclusions temporaires",
            "manage_roles": "rôle muet, rôle auto",
            "manage_channels": "verrouillages, tickets, nuke",
            "manage_messages": "purge",
            "manage_nicknames": "pseudo, réclamation",
            "view_audit_log": "anti-nuke",
            "embed_links": "tout",
            "attach_files": "transcriptions",
            "read_message_history": "purge, transcriptions",
            "add_reactions": "sondages",
        }
        p = ctx.guild.me.guild_permissions
        good, bad = [], []
        for perm, why in needed.items():
            line = f"`{perm}` — {why}"
            (good if getattr(p, perm) else bad).append(line)

        e = h.base_embed(
            "Vérification des permissions",
            color=config.COLOR_SUCCESS if not bad else config.COLOR_WARN,
        )
        if bad:
            e.add_field(name=f"{config.EMOJI['no']} Manquantes",
                        value="\n".join(bad)[:1000], inline=False)
        e.add_field(name=f"{config.EMOJI['ok']} Présentes ({len(good)})",
                    value="\n".join(good)[:1000] or "aucune", inline=False)
        role_pos = ctx.guild.me.top_role.position
        highest = max(r.position for r in ctx.guild.roles)
        e.set_footer(
            text=f"Mon rôle le plus haut est en position {role_pos} sur {highest}. "
                 f"Monte-le si la modération échoue."
        )
        await ctx.reply(embed=e, mention_author=False)

    @commands.command(name="invite")
    async def invite(self, ctx):
        perms = discord.Permissions(
            manage_guild=True, ban_members=True, kick_members=True,
            moderate_members=True, manage_roles=True, manage_channels=True,
            manage_messages=True, manage_nicknames=True, view_audit_log=True,
            embed_links=True, attach_files=True, read_message_history=True,
            add_reactions=True, send_messages=True, view_channel=True,
        )
        url = discord.utils.oauth_url(self.bot.user.id, permissions=perms)
        await ctx.reply(
            embed=h.base_embed("M'ajouter à un serveur", f"[Clique ici]({url})"),
            mention_author=False,
        )




# ==============================================================================
#  SECTION 22b - MENU DE SÉLECTION DE RÔLE (self-roles)
# ==============================================================================


CUSTOM_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")

TITRE_DEFAUT = "Sélectionne ton rôle d'affichage"
PLACEHOLDER_DEFAUT = "Choisis ton rôle"


def est_emoji(texte: str) -> bool:
    """Vrai si le texte ressemble à un émoji (personnalisé ou unicode)."""
    if not texte:
        return False
    if CUSTOM_EMOJI_RE.fullmatch(texte):
        return True
    if len(texte) > 8:
        return False
    return all(ord(c) > 0x2000 for c in texte)


def trouver_role(guild: discord.Guild, texte: str):
    """Accepte une mention, un ID ou un nom (exact puis partiel)."""
    brut = texte.strip().strip("<@&>")
    if brut.isdigit():
        role = guild.get_role(int(brut))
        if role:
            return role
    cible = texte.strip().lower()
    role = discord.utils.find(lambda r: r.name.lower() == cible, guild.roles)
    if role:
        return role
    return discord.utils.find(lambda r: cible in r.name.lower(), guild.roles)


def construire_options(guild: discord.Guild, rows, multiple: bool):
    """Transforme les lignes de la base en options de menu déroulant."""
    options = []
    for r in rows[:24]:  # 24 + l'option « retirer » = 25, le maximum Discord
        role = guild.get_role(r["role_id"])
        if role is None:
            continue
        options.append(
            discord.SelectOption(
                label=(r["label"] or role.name)[:100],
                value=str(role.id),
                description=(r["description"] or None),
                emoji=(r["emoji"] or None),
            )
        )
    if options:
        options.append(
            discord.SelectOption(
                label="Retirer mon rôle",
                value="__none__",
                description="Enlève le ou les rôles pris ici",
                emoji="\u274c",
            )
        )
    return options


class SelfRoleSelect(discord.ui.Select):
    """
    Menu persistant. Au redémarrage, les vraies options viennent du message
    déjà publié sur Discord : celles d'ici ne servent que de remplissage pour
    que discord.py accepte l'objet.
    """

    def __init__(self, options=None, multiple=False, placeholder=None):
        opts = options or [discord.SelectOption(label="\u2014", value="__none__")]
        super().__init__(
            placeholder=placeholder or PLACEHOLDER_DEFAUT,
            options=opts,
            custom_id="selfrole:select",
            min_values=0,
            max_values=len(opts) if multiple else 1,
        )

    async def callback(self, interaction: discord.Interaction):
        bot = interaction.client
        guild = interaction.guild
        membre = interaction.user

        rows = await bot.db.selfroles(guild.id)
        panel = await bot.db.selfrole_panel(guild.id)
        multiple = bool(panel and panel["multiple"])

        gerables = [
            role for role in (guild.get_role(r["role_id"]) for r in rows)
            if role is not None
        ]
        if not gerables:
            return await interaction.response.send_message(
                embed=h.err_embed("Aucun rôle n'est configuré dans ce menu."),
                ephemeral=True,
            )

        vider = "__none__" in self.values
        choisis = []
        if not vider:
            for valeur in self.values:
                if valeur.isdigit():
                    role = guild.get_role(int(valeur))
                    if role in gerables:
                        choisis.append(role)

        me = guild.me
        if any(r >= me.top_role for r in choisis):
            return await interaction.response.send_message(
                embed=h.err_embed(
                    "Ce rôle est au-dessus du mien, je ne peux pas l'attribuer. "
                    "Préviens le staff."
                ),
                ephemeral=True,
            )

        possede = [r for r in gerables if r in membre.roles]

        if vider:
            a_ajouter, a_retirer = [], [r for r in possede if r < me.top_role]
        elif multiple:
            # En mode multiple, on bascule : un rôle déjà pris est retiré.
            a_ajouter = [r for r in choisis if r not in possede]
            a_retirer = [r for r in choisis if r in possede and r < me.top_role]
        else:
            # Mode unique : le rôle choisi remplace l'ancien.
            a_ajouter = [r for r in choisis if r not in possede]
            a_retirer = [r for r in possede if r not in choisis and r < me.top_role]

        if not a_ajouter and not a_retirer:
            return await interaction.response.send_message(
                embed=h.base_embed(description="Rien à changer."), ephemeral=True
            )

        try:
            if a_retirer:
                await membre.remove_roles(*a_retirer, reason="Menu de rôles")
            if a_ajouter:
                await membre.add_roles(*a_ajouter, reason="Menu de rôles")
        except discord.Forbidden:
            return await interaction.response.send_message(
                embed=h.err_embed(
                    "Discord a refusé — mon rôle doit être au-dessus de ceux du menu."
                ),
                ephemeral=True,
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                embed=h.err_embed("Échec de la modification des rôles."),
                ephemeral=True,
            )

        lignes = []
        if a_ajouter:
            lignes.append("**Ajouté :** " + ", ".join(r.mention for r in a_ajouter))
        if a_retirer:
            lignes.append("**Retiré :** " + ", ".join(r.mention for r in a_retirer))
        await interaction.response.send_message(
            embed=h.ok_embed("\n".join(lignes)), ephemeral=True
        )


class SelfRolePanelView(discord.ui.View):
    def __init__(self, bot=None, options=None, multiple=False, placeholder=None):
        super().__init__(timeout=None)
        self.bot = bot
        self.add_item(SelfRoleSelect(options, multiple, placeholder))


class SelfRoles(commands.Cog):
    """Menu déroulant permettant aux membres de choisir leur rôle."""

    def __init__(self, bot):
        self.bot = bot

    # ------------------------------------------------------------ helpers

    def _panel_embed(self, guild, panel) -> discord.Embed:
        e = h.base_embed(
            panel["title"] or TITRE_DEFAUT,
            panel["description"] or None,
        )
        if guild.icon:
            e.set_thumbnail(url=guild.icon.url)
        return e

    async def _publier(self, guild, salon, panel, rows):
        options = construire_options(guild, rows, bool(panel["multiple"]))
        if not options:
            return None
        vue = SelfRolePanelView(
            self.bot, options, bool(panel["multiple"]), panel["placeholder"]
        )
        return await salon.send(embed=self._panel_embed(guild, panel), view=vue)

    # ------------------------------------------------------------ commandes

    @commands.command(
        name="addrolecs",
        aliases=["addrolec", "addselfrole", "ajouterrolec"],
        help='-addrolecS "nom du role" [emoji] [description] — ajoute un rôle au menu.',
    )
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def addrolecs(self, ctx, role: str, emoji: str = None, *,
                        description: str = None):
        # Si le 2e argument n'est pas un émoji, c'est en fait le début de la
        # description : on recolle les morceaux.
        if emoji and not est_emoji(emoji):
            description = f"{emoji} {description}".strip() if description else emoji
            emoji = None

        cible = trouver_role(ctx.guild, role)
        if cible is None:
            return await ctx.reply(
                embed=h.err_embed(
                    f"Aucun rôle nommé « {h.clean(role, 50)} ».\n"
                    f'Utilise des guillemets : `{ctx.prefix}addrolecS "Mon rôle"`'
                )
            )
        if cible.is_default():
            return await ctx.reply(embed=h.err_embed("Pas @everyone."))
        if cible.managed:
            return await ctx.reply(
                embed=h.err_embed("Ce rôle est géré par une intégration.")
            )
        if cible >= ctx.guild.me.top_role:
            return await ctx.reply(
                embed=h.err_embed(
                    f"{cible.mention} est au-dessus de mon rôle — je ne pourrai pas "
                    f"l'attribuer. Monte mon rôle plus haut dans les paramètres."
                )
            )
        if cible >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            return await ctx.reply(embed=h.err_embed("Ce rôle est au-dessus du tien."))

        rows = await self.bot.db.selfroles(ctx.guild.id)
        if len(rows) >= 24 and not any(r["role_id"] == cible.id for r in rows):
            return await ctx.reply(
                embed=h.err_embed(
                    "Le menu est plein : Discord limite à 24 rôles par menu."
                )
            )

        await self.bot.db.add_selfrole(
            ctx.guild.id, cible.id, cible.name,
            emoji, h.clean(description, 90) if description else None,
        )
        rows = await self.bot.db.selfroles(ctx.guild.id)
        await ctx.reply(
            embed=h.ok_embed(
                f"{cible.mention} ajouté au menu ({len(rows)} rôle(s)).\n"
                f"Publie ou rafraîchis le menu avec `{ctx.prefix}rolepanel`."
            )
        )
        await self._auto_refresh(ctx.guild)

    @commands.command(
        name="delrolecs",
        aliases=["removerolecs", "delrolec", "delselfrole"],
        help='-delrolecS "nom du role" — retire un rôle du menu.',
    )
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    async def delrolecs(self, ctx, *, role: str):
        cible = trouver_role(ctx.guild, role)
        if cible is None:
            return await ctx.reply(
                embed=h.err_embed(f"Aucun rôle nommé « {h.clean(role, 50)} ».")
            )
        await self.bot.db.remove_selfrole(ctx.guild.id, cible.id)
        await ctx.reply(embed=h.ok_embed(f"{cible.mention} retiré du menu."))
        await self._auto_refresh(ctx.guild)

    @commands.command(
        name="listrolecs",
        aliases=["rolecs", "selfroles", "listrolec"],
        help="Liste les rôles proposés dans le menu.",
    )
    @commands.guild_only()
    async def listrolecs(self, ctx):
        rows = await self.bot.db.selfroles(ctx.guild.id)
        if not rows:
            return await ctx.reply(
                embed=h.base_embed(
                    description=f"Aucun rôle dans le menu.\n"
                                f'`{ctx.prefix}addrolecS "Mon rôle"` pour en ajouter.'
                )
            )
        lignes = []
        for r in rows:
            role = ctx.guild.get_role(r["role_id"])
            if role is None:
                continue
            emoji = f"{r['emoji']} " if r["emoji"] else ""
            desc = f" — *{h.clean(r['description'], 60)}*" if r["description"] else ""
            lignes.append(f"• {emoji}{role.mention}{desc}")
        panel = await self.bot.db.selfrole_panel(ctx.guild.id)
        mode = "multiple" if panel["multiple"] else "unique"
        e = h.base_embed(f"Menu de rôles ({len(lignes)})", "\n".join(lignes))
        e.set_footer(text=f"Mode : {mode} · {ctx.prefix}rolepanel pour publier")
        await ctx.reply(embed=e)

    # ------------------------------------------------------------ panneau

    @commands.group(
        name="rolepanel",
        aliases=["panelrole", "menurole"],
        invoke_without_command=True,
        help="+rolepanel [#salon] — publie le menu de sélection de rôle.",
    )
    @commands.guild_only()
    @h.is_owner_or(manage_roles=True)
    async def rolepanel(self, ctx, salon: discord.TextChannel = None):
        salon = salon or ctx.channel
        rows = await self.bot.db.selfroles(ctx.guild.id)
        if not rows:
            return await ctx.reply(
                embed=h.warn_embed(
                    f"Ajoute d'abord des rôles :\n"
                    f'`{ctx.prefix}addrolecS "Mon rôle" 🎮 Une description`'
                )
            )
        panel = await self.bot.db.selfrole_panel(ctx.guild.id)
        message = await self._publier(ctx.guild, salon, panel, rows)
        if message is None:
            return await ctx.reply(
                embed=h.err_embed("Tous les rôles enregistrés ont été supprimés.")
            )
        await self.bot.db.set_selfrole_panel(ctx.guild.id, "channel_id", salon.id)
        await self.bot.db.set_selfrole_panel(ctx.guild.id, "message_id", message.id)
        if salon != ctx.channel:
            await ctx.reply(embed=h.ok_embed(f"Menu publié dans {salon.mention}."))

    @rolepanel.command(name="titre", aliases=["title"])
    @h.is_owner_or(manage_roles=True)
    async def rp_titre(self, ctx, *, texte: str):
        await self.bot.db.set_selfrole_panel(ctx.guild.id, "title", texte[:250])
        await ctx.reply(embed=h.ok_embed("Titre enregistré."))
        await self._auto_refresh(ctx.guild)

    @rolepanel.command(name="texte", aliases=["description", "desc"])
    @h.is_owner_or(manage_roles=True)
    async def rp_texte(self, ctx, *, texte: str):
        await self.bot.db.set_selfrole_panel(ctx.guild.id, "description", texte[:3000])
        await ctx.reply(embed=h.ok_embed("Description enregistrée."))
        await self._auto_refresh(ctx.guild)

    @rolepanel.command(name="placeholder", aliases=["ph"])
    @h.is_owner_or(manage_roles=True)
    async def rp_placeholder(self, ctx, *, texte: str):
        await self.bot.db.set_selfrole_panel(ctx.guild.id, "placeholder", texte[:100])
        await ctx.reply(embed=h.ok_embed(f"Texte du menu : **{h.clean(texte, 100)}**"))
        await self._auto_refresh(ctx.guild)

    @rolepanel.command(name="mode")
    @h.is_owner_or(manage_roles=True)
    async def rp_mode(self, ctx, mode: str):
        multiple = mode.lower() in ("multiple", "plusieurs", "multi")
        await self.bot.db.set_selfrole_panel(ctx.guild.id, "multiple", int(multiple))
        await ctx.reply(
            embed=h.ok_embed(
                "Mode **multiple** : un membre peut cumuler plusieurs rôles."
                if multiple else
                "Mode **unique** : le nouveau rôle remplace l'ancien."
            )
        )
        await self._auto_refresh(ctx.guild)

    @rolepanel.command(name="refresh", aliases=["maj", "update"])
    @h.is_owner_or(manage_roles=True)
    async def rp_refresh(self, ctx):
        if await self._auto_refresh(ctx.guild):
            await ctx.reply(embed=h.ok_embed("Menu mis à jour."))
        else:
            await ctx.reply(
                embed=h.warn_embed(
                    f"Aucun menu publié à mettre à jour — lance `{ctx.prefix}rolepanel`."
                )
            )

    async def _auto_refresh(self, guild) -> bool:
        """Réécrit le message du menu déjà publié, s'il existe encore."""
        panel = await self.bot.db.selfrole_panel(guild.id)
        if not panel or not panel["channel_id"] or not panel["message_id"]:
            return False
        salon = guild.get_channel(panel["channel_id"])
        if salon is None:
            return False
        try:
            message = await salon.fetch_message(panel["message_id"])
        except discord.HTTPException:
            return False
        rows = await self.bot.db.selfroles(guild.id)
        options = construire_options(guild, rows, bool(panel["multiple"]))
        if not options:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            await self.bot.db.set_selfrole_panel(guild.id, "message_id", None)
            return False
        vue = SelfRolePanelView(
            self.bot, options, bool(panel["multiple"]), panel["placeholder"]
        )
        try:
            await message.edit(embed=self._panel_embed(guild, panel), view=vue)
        except discord.HTTPException:
            return False
        return True

    # ------------------------------------------------------------ entretien

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """Un rôle supprimé disparaît aussi du menu."""
        try:
            await self.bot.db.remove_selfrole(role.guild.id, role.id)
        except Exception:
            return
        await self._auto_refresh(role.guild)


# ==============================================================================
#  SECTION 23 - BOT CLASS & ENTRY POINT
# ==============================================================================




try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("bot")


# --------------------------------------------------------------------------
# Prefix resolution: per-guild override, falling back to config.PREFIX.
# Mentioning the bot always works too.
# --------------------------------------------------------------------------
async def get_prefix(bot: "MyBot", message: discord.Message):
    """
    Deux préfixes actifs en même temps :
      &  -> commandes de rang supérieur (owner / admin / staff)
      +  -> commandes de base (clear, ping, etc.)
    Les deux fonctionnent pour toutes les commandes ; la distinction est surtout
    une convention affichée dans les panneaux d'aide. Le préfixe personnalisé
    éventuel du serveur s'ajoute à la liste.
    """
    prefixes = [config.PREFIX, config.ELEVATED_PREFIX]
    if message.guild:
        cached = bot.prefix_cache.get(message.guild.id)
        if cached is None:
            row = await bot.db.guild_settings(message.guild.id)
            cached = (row["prefix"] if row and row["prefix"] else config.PREFIX)
            bot.prefix_cache[message.guild.id] = cached
        if cached not in prefixes:
            prefixes.append(cached)
    return commands.when_mentioned_or(*prefixes)(bot, message)


class AutoContext(commands.Context):
    """
    Context whose replies clean themselves up.

    Every `ctx.reply(...)` in the bot goes through here, so one override covers
    all commands instead of adding delete_after to a hundred call sites.
    A command that needs a permanent message uses `ctx.send(...)` instead
    (polls, ticket panels, -say), or passes delete_after explicitly.
    """

    async def reply(self, *args, **kwargs):
        kwargs.setdefault("mention_author", False)
        if config.AUTO_DELETE_SECONDS and "delete_after" not in kwargs:
            kwargs["delete_after"] = config.AUTO_DELETE_SECONDS
        try:
            return await super().reply(*args, **kwargs)
        except discord.HTTPException:
            # The message being replied to was already deleted — send normally.
            kwargs.pop("mention_author", None)
            return await super().send(*args, **kwargs)


class MyBot(commands.Bot):
    def __init__(self, with_presences: bool = True):
        intents = discord.Intents.default()
        intents.members = True          # required: welcome/goodbye, anti-raid
        intents.message_content = True  # required: prefix commands, automod
        intents.guilds = True
        intents.voice_states = True
        intents.presences = with_presences  # compteur "En ligne" (privilégié)

        super().__init__(
            command_prefix=get_prefix,
            intents=intents,
            help_command=None,
            case_insensitive=True,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True, replied_user=True
            ),
            max_messages=5000,
        )
        self.db = Database()
        self.prefix_cache: dict[int, str] = {}
        self.start_time = discord.utils.utcnow()
        self.persistent_views_added = False

    # ---------------------------------------------------------------- setup
    async def setup_hook(self):
        os.makedirs("data", exist_ok=True)
        await self.db.connect()
        log.info("Database ready at %s", config.DB_PATH)

        for cog in (Moderation, AntiRaid, Tickets, Welcome,
                    Stats, Fun, OpMod, Tools, VoiceStats, Extras, HardBan, Rules, StatsChannels, Logging, MediaOnly, Panel, TempVoice, SelfRoles, Scheduler, Utility):
            try:
                await self.add_cog(cog(self))
                log.info("Loaded %s", cog.__name__)
            except Exception:
                log.error("Failed to load %s", cog.__name__)
                traceback.print_exc()

        # Persistent views survive restarts (ticket panel buttons).
        if not self.persistent_views_added:
            self.add_view(TicketPanelView(self))
            self.add_view(TicketControlView(self))
            self.add_view(VoicePanelView(self))
            self.add_view(PanelView(self))
            self.add_view(RulesView(self))
            self.add_view(SelfRolePanelView(self))
            self.persistent_views_added = True

    async def close(self):
        await self.db.close()
        await super().close()

    # ---------------------------------------------------------------- events
    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        log.info("Serving %d guild(s), %d users", len(self.guilds),
                 sum(g.member_count or 0 for g in self.guilds))
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=f"{config.PREFIX}help | {len(self.guilds)} servers",
            )
        )

    async def get_context(self, message, *, cls=AutoContext):
        return await super().get_context(message, cls=cls)

    async def can_run_check(self, ctx):
        return True

    async def invoke(self, ctx):
        # Bloque les membres en liste noire avant toute commande.
        if ctx.command is not None and ctx.guild is not None:
            try:
                if await self.db.is_blacklisted(ctx.guild.id, ctx.author.id):
                    if not ctx.author.guild_permissions.administrator:
                        return
            except Exception:
                pass
        await super().invoke(ctx)

    async def on_command_completion(self, ctx: commands.Context):
        if ctx.guild:
            await self.db.bump_stat(ctx.guild.id, ctx.author.id, "commands")
            await self.db.bump_command(ctx.guild.id, ctx.author.id, ctx.command.qualified_name)

        # Remove the user's own "-command" message so channels stay tidy.
        if (config.DELETE_INVOKING_MESSAGE and ctx.guild
                and ctx.guild.me.guild_permissions.manage_messages):
            await asyncio.sleep(config.DELETE_INVOKING_DELAY)
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

    # ---------------------------------------------------------------- errors
    async def on_command_error(self, ctx: commands.Context, error):
        error = getattr(error, "original", error)

        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            usage = f"{ctx.prefix}{ctx.command.qualified_name} {ctx.command.signature}"
            return await ctx.reply(
                embed=h.err_embed(
                    f"Argument manquant : `{error.param.name}`.\n**Utilisation :** `{usage}`"
                ),
                mention_author=False,
            )
        if isinstance(error, commands.BadArgument):
            return await ctx.reply(
                embed=h.err_embed(f"Argument invalide : {error}"), mention_author=False
            )
        if isinstance(error, commands.MemberNotFound):
            return await ctx.reply(
                embed=h.err_embed("Membre introuvable."), mention_author=False
            )
        if isinstance(error, commands.CommandOnCooldown):
            return await ctx.reply(
                embed=h.warn_embed(
                    f"Doucement — réessaie dans {error.retry_after:.1f}s."
                ),
                mention_author=False,
                delete_after=6,
            )
        if isinstance(error, commands.MissingRole):
            return await ctx.reply(
                embed=h.err_embed(
                    f"Cette commande nécessite le rôle **{error.missing_role}**."
                ),
                mention_author=False,
            )
        if isinstance(error, (commands.MissingPermissions, commands.CheckFailure)):
            return await ctx.reply(
                embed=h.err_embed("Tu n'as pas la permission de faire ça."),
                mention_author=False,
            )
        if isinstance(error, commands.BotMissingPermissions):
            perms = ", ".join(error.missing_permissions)
            return await ctx.reply(
                embed=h.err_embed(f"Il me manque des permissions : `{perms}`"),
                mention_author=False,
            )
        if isinstance(error, discord.Forbidden):
            return await ctx.reply(
                embed=h.err_embed(
                    "Discord a refusé — vérifie la position de mon rôle et mes permissions."
                ),
                mention_author=False,
            )
        if isinstance(error, commands.NoPrivateMessage):
            return await ctx.reply(embed=h.err_embed("Commande utilisable uniquement sur un serveur."))

        log.error("Unhandled error in %s", ctx.command, exc_info=error)
        await ctx.reply(
            embed=h.err_embed(
                f"Quelque chose a cassé.\n```py\n{type(error).__name__}: {str(error)[:300]}\n```"
            ),
            mention_author=False,
        )


async def main():
    if not config.TOKEN:
        print("No DISCORD_TOKEN set. Put it in a .env file:\n  DISCORD_TOKEN=...")
        sys.exit(1)

    bot = MyBot()
    try:
        async with bot:
            await bot.start(config.TOKEN)
    except discord.PrivilegedIntentsRequired:
        log.warning(
            "Un intent privilégié n'est pas activé dans le portail Discord "
            "(probablement PRESENCE INTENT). Redémarrage sans 'presences' — le "
            "compteur 'En ligne' sera inexact tant que tu ne l'auras pas coché "
            "sur https://discord.com/developers/applications -> Bot -> "
            "Privileged Gateway Intents."
        )
        bot = MyBot(with_presences=False)
        try:
            async with bot:
                await bot.start(config.TOKEN)
        except discord.PrivilegedIntentsRequired:
            log.error(
                "Il manque toujours un intent privilégié. Active SERVER MEMBERS "
                "INTENT et MESSAGE CONTENT INTENT dans le portail Discord, puis "
                "relance."
            )
            sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nArrêt en cours.")