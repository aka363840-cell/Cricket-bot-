#!/usr/bin/env python3
"""
🏏 Cricket Bot for Telegram
Solo & Team cricket game with stats, leaderboard, voting
"""

import os, logging, sqlite3, asyncio, random, html
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup, Message
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.constants import ParseMode
from telegram.error import TelegramError, Forbidden

# ═══════════════════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════════════════
TOKEN    = os.environ.get("BOT_TOKEN", "")
DB_PATH  = os.environ.get("DB_PATH", "cricket.db")
JOIN_SEC = int(os.environ.get("JOIN_SECONDS", "90"))
BOWL_SEC = int(os.environ.get("BOWL_SECONDS", "60"))
BAT_SEC  = int(os.environ.get("BAT_SECONDS",  "60"))
VOTE_SEC = int(os.environ.get("VOTE_SECONDS", "30"))

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
#  EMOJIS & MESSAGES
# ═══════════════════════════════════════════════════════════════════
BALL_EMOJIS = {
    0: "🟤", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣",
    4: "🔵", 5: "5️⃣", 6: "🔴",
}

def runs_msg(n: int, batter: str) -> str:
    if n == 6:
        return (f"🔴🔴🔴 SIIIX! 🔴🔴🔴\n"
                f"💥 *{batter}* smashes it out of the park!\n"
                f"🏟️ The crowd goes WILD! 🎉🎊")
    elif n == 4:
        return (f"🔵🔵🔵 FOUR! 🔵🔵🔵\n"
                f"⚡ *{batter}* drives it to the boundary!\n"
                f"👏 Beautiful shot!")
    elif n == 3:
        return f"🏃‍♂️ *{batter}* scampers 3 runs! Great running! 💨"
    elif n == 2:
        return f"🏃 *{batter}* takes 2 runs! Quick between the wickets!"
    elif n == 1:
        return f"📍 *{batter}* pushes for 1 run. Dot ball — wait, 1 run!"
    else:
        return f"🟤 DOT BALL! Good length delivery, *{batter}* defends."

def wicket_msg(batter: str, bowler: str) -> str:
    modes = [
        f"💥 BOWLED! The stumps are shattered! 🏏",
        f"🎯 CAUGHT BEHIND! Edge and gone!",
        f"🤸 LBW! Plumb in front! Out!",
        f"🌪️ CLEAN BOWLED! What a delivery!",
        f"😱 CAUGHT! Brilliant catch in the field!",
    ]
    return (f"🚨🚨🚨 W I C K E T ! 🚨🚨🚨\n"
            f"{random.choice(modes)}\n"
            f"*{batter}* is OUT! 👋\n"
            f"🎳 *{bowler}* takes the wicket!")

# ═══════════════════════════════════════════════════════════════════
#  DATABASE
# ═══════════════════════════════════════════════════════════════════
def db_conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db_conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS players (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT,
            display_name  TEXT,
            runs          INTEGER DEFAULT 0,
            balls         INTEGER DEFAULT 0,
            sixes         INTEGER DEFAULT 0,
            fours         INTEGER DEFAULT 0,
            wickets       INTEGER DEFAULT 0,
            balls_bowled  INTEGER DEFAULT 0,
            runs_given    INTEGER DEFAULT 0,
            matches       INTEGER DEFAULT 0,
            highest       INTEGER DEFAULT 0,
            updated_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS matches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id     INTEGER,
            game_type   TEXT,
            summary     TEXT,
            played_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

def upsert_player(user_id, username, display_name):
    with db_conn() as c:
        c.execute("""INSERT OR IGNORE INTO players(user_id,username,display_name)
                     VALUES(?,?,?)""", (user_id, username or "", display_name))
        c.execute("""UPDATE players SET username=?,display_name=? WHERE user_id=?""",
                  (username or "", display_name, user_id))

def add_bat_stats(user_id, runs, balls, sixes, fours):
    with db_conn() as c:
        c.execute("""UPDATE players SET
            runs=runs+?, balls=balls+?, sixes=sixes+?, fours=fours+?,
            matches=matches+1,
            highest=MAX(highest,?),
            updated_at=CURRENT_TIMESTAMP
            WHERE user_id=?""", (runs, balls, sixes, fours, runs, user_id))

def add_bowl_stats(user_id, wickets, balls_bowled, runs_given):
    with db_conn() as c:
        c.execute("""UPDATE players SET
            wickets=wickets+?, balls_bowled=balls_bowled+?, runs_given=runs_given+?,
            updated_at=CURRENT_TIMESTAMP
            WHERE user_id=?""", (wickets, balls_bowled, runs_given, user_id))

def get_stats(user_id):
    with db_conn() as c:
        return c.execute("SELECT * FROM players WHERE user_id=?", (user_id,)).fetchone()

def get_leaderboard(n=10):
    with db_conn() as c:
        return c.execute(
            "SELECT * FROM players ORDER BY runs DESC LIMIT ?", (n,)
        ).fetchall()

# ═══════════════════════════════════════════════════════════════════
#  GAME STATE CLASSES
# ═══════════════════════════════════════════════════════════════════
class BatScore:
    def __init__(self, uid, name):
        self.uid   = uid
        self.name  = name
        self.runs  = 0
        self.balls = 0
        self.sixes = 0
        self.fours = 0
        self.out   = False

    def card(self):
        status = "💀" if self.out else "🏏"
        return f"{status} *{html.escape(self.name)}*: {self.runs}({self.balls}) | 6s:{self.sixes} 4s:{self.fours}"

class BowlScore:
    def __init__(self, uid, name):
        self.uid     = uid
        self.name    = name
        self.wickets = 0
        self.balls   = 0
        self.runs    = 0

    @property
    def overs(self):
        return f"{self.balls//6}.{self.balls%6}"

    def card(self):
        return f"🎳 *{html.escape(self.name)}*: {self.runs}R {self.wickets}W {self.overs}ov"

class GameState:
    def __init__(self, chat_id, gtype, host_id, host_name):
        self.chat_id      = chat_id
        self.gtype        = gtype        # 'solo' | 'team'
        self.host_id      = host_id
        self.host_name    = host_name
        self.status       = "joining"    # joining|bowling_wait|bat_wait|vote|ended

        self.players: list   = []        # user_ids in join order
        self.names: dict     = {}        # uid -> name

        # Batting
        self.bat_q: list     = []        # queue of uids yet to bat
        self.batter: int     = None      # current batter uid
        self.bat_scores: dict= {}        # uid -> BatScore
        self.batter_num: int = None      # batter's chosen number

        # Bowling
        self.bowl_q: list    = []        # cycling bowl list
        self.bowler: int     = None
        self.bowl_scores: dict = {}      # uid -> BowlScore
        self.bowler_num: int = None      # bowler's secret number
        self.balls_in_over   = 0

        # Vote
        self.votes: dict     = {}        # uid -> True/False
        self.vote_msg        = None      # Message object

        # Team mode extras
        self.team_a: list    = []
        self.team_b: list    = []
        self.bat_team        = "a"       # which team bats
        self.innings         = 1
        self.ta_total        = 0
        self.tb_total        = 0

    def n(self, uid): return self.names.get(uid, str(uid))

    def all_out(self):
        return all(s.out for s in self.bat_scores.values())

    def total_score(self):
        r = sum(s.runs for s in self.bat_scores.values())
        w = sum(1 for s in self.bat_scores.values() if s.out)
        return r, w

    def next_batter(self):
        for uid in self.bat_q:
            if not self.bat_scores.get(uid, BatScore(uid,"")).out:
                return uid
        return None

    def rotate_bowler(self):
        """Move to next bowler in queue."""
        if len(self.bowl_q) < 2:
            return
        self.bowl_q.append(self.bowl_q.pop(0))
        self.bowler = self.bowl_q[0]
        self.balls_in_over = 0

    def scorecard(self):
        lines = ["📋 *SCORECARD*\n"]
        total, wkts = self.total_score()
        lines.append("🏏 *BATTING*")
        for s in self.bat_scores.values():
            lines.append(s.card())
        lines.append(f"\n🏆 *Total: {total}/{wkts}*\n")
        bowl_cards = [s.card() for s in self.bowl_scores.values() if s.balls > 0]
        if bowl_cards:
            lines.append("🎳 *BOWLING*")
            lines.extend(bowl_cards)
        return "\n".join(lines)

# Active games and pending maps
games: dict       = {}   # chat_id -> GameState
bowl_pending: dict = {}   # uid -> chat_id (bowler waiting in DM)
bat_pending: dict  = {}   # chat_id -> uid  (batter waiting in group)

# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════
async def is_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE, uid: int) -> bool:
    try:
        member = await ctx.bot.get_chat_member(update.effective_chat.id, uid)
        return member.status in ("administrator", "creator")
    except:
        return False

async def send(ctx, chat_id, text, **kw):
    try:
        return await ctx.bot.send_message(chat_id, text,
            parse_mode=ParseMode.MARKDOWN, **kw)
    except TelegramError as e:
        log.warning(f"send error: {e}")

async def send_dm(ctx, uid, text, **kw):
    try:
        return await ctx.bot.send_message(uid, text,
            parse_mode=ParseMode.MARKDOWN, **kw)
    except Forbidden:
        return None  # user hasn't started bot
    except TelegramError as e:
        log.warning(f"DM error to {uid}: {e}")
        return None

def fmt_name(user):
    name = user.first_name or ""
    if user.last_name:
        name += f" {user.last_name}"
    return name.strip() or user.username or str(user.id)

# ═══════════════════════════════════════════════════════════════════
#  START & HELP
# ═══════════════════════════════════════════════════════════════════
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    upsert_player(u.id, u.username, fmt_name(u))
    if update.effective_chat.type == "private":
        await update.message.reply_text(
            "🏏 *Cricket Bot*\n\n"
            "Add me to your group and use:\n"
            "`/newgame solo` — Solo cricket\n"
            "`/newgame team` — Team cricket\n"
            "`/stats` — Your stats\n"
            "`/leaderboard` — Top players\n\n"
            "⚠️ Start me here in DM first so I can send you bowling prompts!",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "🏏 *Cricket Bot ready!*\nUse `/newgame solo` or `/newgame team` to play!",
            parse_mode=ParseMode.MARKDOWN
        )

async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🏏 *CRICKET BOT — COMMANDS*\n\n"
        "▶️ `/newgame solo` — Start a solo game\n"
        "▶️ `/newgame team` — Start a team game\n"
        "▶️ `/joingame` — Join current game\n"
        "▶️ `/startgame` — Host starts the game\n\n"
        "🎮 *During Game:*\n"
        "• Send `1-6` in group to bat\n"
        "• Bowler sends `1-6` in bot DM\n"
        "• `/setbowler @user` — Host sets bowler (team mode)\n"
        "• `/setbatter @user` — Host sets batter (team mode)\n"
        "• `/teama @user` / `/teamb @user` — Assign team\n"
        "• `/skip` — Host skips current batter\n\n"
        "🏁 `/endgame` — Vote to end (admin confirms)\n"
        "📊 `/stats` — Your stats\n"
        "🏆 `/leaderboard` — Top 10 players\n"
        "📋 `/score` — Current scorecard\n",
        parse_mode=ParseMode.MARKDOWN
    )

# ═══════════════════════════════════════════════════════════════════
#  NEWGAME
# ═══════════════════════════════════════════════════════════════════
async def cmd_newgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    u    = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("❌ Play in a group!")
        return
    if chat.id in games and games[chat.id].status not in ("ended",):
        await update.message.reply_text("⚠️ A game is already running! Use `/endgame` to end it.")
        return

    args = ctx.args
    gtype = (args[0].lower() if args else "solo")
    if gtype not in ("solo", "team"):
        await update.message.reply_text("Usage: `/newgame solo` or `/newgame team`",
                                        parse_mode=ParseMode.MARKDOWN)
        return

    upsert_player(u.id, u.username, fmt_name(u))
    g = GameState(chat.id, gtype, u.id, fmt_name(u))
    g.players.append(u.id)
    g.names[u.id] = fmt_name(u)
    games[chat.id] = g

    mode_label = "🧍 SOLO" if gtype == "solo" else "👥 TEAM"
    await send(ctx, chat.id,
        f"🏏 *NEW CRICKET GAME!* {mode_label}\n\n"
        f"🎤 Host: *{html.escape(fmt_name(u))}*\n"
        f"⏳ Players have *{JOIN_SEC} seconds* to join!\n\n"
        f"Type `/joingame` to join!\n"
        f"Host can type `/startgame` to start early.\n\n"
        f"⚠️ Make sure you've DM'd me `/start` so I can send bowling prompts!"
    )

    # Auto-start after join period
    async def auto_start(cid=chat.id, uid=u.id):
        await asyncio.sleep(JOIN_SEC)
        g2 = games.get(cid)
        if g2 and g2.status == "joining":
            if len(g2.players) < 2:
                await send(ctx, cid, "❌ Not enough players. Game cancelled.")
                del games[cid]
            else:
                await start_match(ctx, cid)

    asyncio.create_task(auto_start())

# ═══════════════════════════════════════════════════════════════════
#  JOINGAME
# ═══════════════════════════════════════════════════════════════════
async def cmd_joingame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    u    = update.effective_user
    if chat.type == "private":
        await update.message.reply_text("❌ Use this in a group!")
        return

    g = games.get(chat.id)
    if not g:
        await update.message.reply_text("❌ No game found. Start one with `/newgame solo`",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    if g.status != "joining":
        await update.message.reply_text("⚠️ Game already started, you can't join now!")
        return
    if u.id in g.players:
        await update.message.reply_text(f"😊 *{html.escape(fmt_name(u))}*, you're already in!",
                                        parse_mode=ParseMode.MARKDOWN)
        return

    upsert_player(u.id, u.username, fmt_name(u))
    g.players.append(u.id)
    g.names[u.id] = fmt_name(u)
    await update.message.reply_text(
        f"🎉 *{html.escape(fmt_name(u))}* joined! (Player {len(g.players)}) 👍",
        parse_mode=ParseMode.MARKDOWN
    )

# ═══════════════════════════════════════════════════════════════════
#  STARTGAME
# ═══════════════════════════════════════════════════════════════════
async def cmd_startgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    u    = update.effective_user
    g    = games.get(chat.id)

    if not g:
        await update.message.reply_text("❌ No game to start. Use `/newgame`",
                                        parse_mode=ParseMode.MARKDOWN)
        return
    if g.status != "joining":
        await update.message.reply_text("⚠️ Game already started!")
        return
    if u.id != g.host_id and not await is_admin(update, ctx, u.id):
        await update.message.reply_text("❌ Only the host or admins can start!")
        return
    if len(g.players) < 2:
        await update.message.reply_text("⚠️ Need at least 2 players!")
        return

    await start_match(ctx, chat.id)

# ═══════════════════════════════════════════════════════════════════
#  START MATCH LOGIC
# ═══════════════════════════════════════════════════════════════════
async def start_match(ctx, chat_id: int):
    g = games.get(chat_id)
    if not g or g.status != "joining":
        return

    g.status = "active"
    player_list = "\n".join(
        f"{i+1}. *{html.escape(g.names[uid])}*" for i, uid in enumerate(g.players)
    )

    await send(ctx, chat_id,
        f"🏏 *MATCH BEGINS!* {'🧍 Solo' if g.gtype=='solo' else '👥 Team'}\n\n"
        f"👥 *Players:*\n{player_list}\n\n"
        + ("🏏 Each player bats once. The bowler rotates every over!\n"
           "Send `1-6` in group when it's your batting turn."
           if g.gtype == "solo"
           else
           "🔀 Host assigns teams below!\nUse `/teama @user` and `/teamb @user`\n"
           "Then `/setbatter @user` and `/setbowler @user` to begin.")
    )

    if g.gtype == "solo":
        # Batting order = join order, bowl order = reverse (last joiner bowls first)
        g.bat_q    = list(g.players)
        g.bowl_q   = list(reversed(g.players))
        # Init scores
        for uid in g.players:
            g.bat_scores[uid]  = BatScore(uid, g.names[uid])
            g.bowl_scores[uid] = BowlScore(uid, g.names[uid])
        g.bowler = g.bowl_q[0]
        g.batter = g.bat_q[0]
        await next_ball(ctx, chat_id)
    else:
        # Team mode: wait for host to assign teams
        await send(ctx, chat_id,
            "📋 *Assign teams now:*\n"
            "`/teama @username` — add to Team A 🔵\n"
            "`/teamb @username` — add to Team B 🟡\n"
            "Then `/beginteam` to start the match!"
        )

# ═══════════════════════════════════════════════════════════════════
#  BALL-BY-BALL LOGIC
# ═══════════════════════════════════════════════════════════════════
async def next_ball(ctx, chat_id: int):
    """Prompt bowler in DM, then prompt batter in group."""
    g = games.get(chat_id)
    if not g or g.status == "ended":
        return

    # Check if all batters are out
    if g.all_out() or not g.next_batter():
        await finish_innings(ctx, chat_id)
        return

    batter_uid  = g.batter if g.batter and not g.bat_scores[g.batter].out else g.next_batter()
    g.batter    = batter_uid
    bowler_uid  = g.bowler
    g.bowler_num = None
    g.batter_num = None
    g.status    = "bowling_wait"

    batter_name = g.n(batter_uid)
    bowler_name = g.n(bowler_uid)

    # DM the bowler
    dm_ok = await send_dm(ctx, bowler_uid,
        f"🎳 *You're bowling!*\n"
        f"Batter: *{html.escape(batter_name)}*\n\n"
        f"Send a number *1-6* here (secretly!) 🤫\n"
        f"You have {BOWL_SEC} seconds!"
    )

    bowl_pending[bowler_uid] = chat_id

    if dm_ok is None:
        # Bowler hasn't started bot — use random number
        await send(ctx, chat_id,
            f"⚠️ *{html.escape(bowler_name)}* hasn't DMed me yet!\n"
            f"Auto-bowling with random number... 🤖"
        )
        g.bowler_num = random.randint(1, 6)
        bowl_pending.pop(bowler_uid, None)
        await prompt_batter(ctx, chat_id)
        return

    # Announce in group
    await send(ctx, chat_id,
        f"🎳 *{html.escape(bowler_name)}* is bowling...\n"
        f"🏏 *{html.escape(batter_name)}* get ready!\n"
        f"_(Waiting for bowler to send number in DM)_"
    )

    # Timeout watchdog
    async def bowl_timeout(cid=chat_id, bid=bowler_uid):
        await asyncio.sleep(BOWL_SEC)
        g2 = games.get(cid)
        if g2 and g2.status == "bowling_wait" and g2.bowler_num is None:
            if bid in bowl_pending:
                bowl_pending.pop(bid, None)
                g2.bowler_num = random.randint(1, 6)
                await send(ctx, cid,
                    f"⏰ *{html.escape(g2.n(bid))}* timed out! Auto-bowl: 🤖"
                )
                await prompt_batter(ctx, cid)

    asyncio.create_task(bowl_timeout())

async def prompt_batter(ctx, chat_id: int):
    g = games.get(chat_id)
    if not g:
        return
    g.status = "bat_wait"
    batter_uid = g.batter
    bname = g.n(batter_uid)
    bat_pending[chat_id] = batter_uid

    await send(ctx, chat_id,
        f"🏏 *{html.escape(bname)}'s turn!*\n"
        f"Send a number *1-6* in this chat! ⏳ {BAT_SEC}s"
    )

    async def bat_timeout(cid=chat_id, uid=batter_uid):
        await asyncio.sleep(BAT_SEC)
        g2 = games.get(cid)
        if g2 and g2.status == "bat_wait" and g2.batter_num is None:
            if bat_pending.get(cid) == uid:
                bat_pending.pop(cid, None)
                g2.batter_num = random.randint(1, 6)
                await send(ctx, cid,
                    f"⏰ *{html.escape(g2.n(uid))}* timed out! Auto-bat: {g2.batter_num} 🤖"
                )
                await resolve_ball(ctx, cid)

    asyncio.create_task(bat_timeout())

async def resolve_ball(ctx, chat_id: int):
    g = games.get(chat_id)
    if not g:
        return
    g.status = "active"

    bn = g.batter_num
    wn = g.bowler_num
    batter = g.batter
    bowler = g.bowler
    bname  = g.n(batter)
    wname  = g.n(bowler)

    bs = g.bat_scores[batter]
    ws = g.bowl_scores.setdefault(bowler, BowlScore(bowler, wname))
    bs.balls += 1
    ws.balls += 1
    g.balls_in_over += 1

    reveal = f"🔢 *{html.escape(bname)}* chose: `{bn}` | *{html.escape(wname)}* bowled: `{wn}`\n\n"

    if bn == wn:
        # WICKET
        bs.out = True
        ws.wickets += 1
        await send(ctx, chat_id, reveal + wicket_msg(bname, wname))
        # Save stats for this batter
        add_bat_stats(batter, bs.runs, bs.balls, bs.sixes, bs.fours)
        # Move to next batter or end
        g.batter_num = None
        g.bowler_num = None
        nxt = g.next_batter()
        if not nxt:
            await finish_innings(ctx, chat_id)
        else:
            g.batter = nxt
            await asyncio.sleep(2)
            await next_ball(ctx, chat_id)
    else:
        # Runs
        runs = bn
        bs.runs += runs
        ws.runs += runs
        if runs == 6: bs.sixes += 1
        if runs == 4: bs.fours += 1
        await send(ctx, chat_id, reveal + runs_msg(runs, bname))
        # Rotate bowler after every 6 balls
        if g.balls_in_over >= 6:
            g.rotate_bowler()
            await send(ctx, chat_id,
                f"🔄 *Over complete!* New bowler: *{html.escape(g.n(g.bowler))}* 🎳"
            )
        g.batter_num = None
        g.bowler_num = None
        await asyncio.sleep(2)
        await next_ball(ctx, chat_id)

async def finish_innings(ctx, chat_id: int):
    g = games.get(chat_id)
    if not g:
        return

    # Save bowl stats
    for uid, bs in g.bowl_scores.items():
        add_bowl_stats(uid, bs.wickets, bs.balls, bs.runs)

    total, wkts = g.total_score()
    sc = g.scorecard()

    if g.gtype == "team" and g.innings == 1:
        # Second innings
        g.ta_total = total
        g.innings  = 2
        g.bat_team = "b" if g.bat_team == "a" else "a"
        batting_ids  = g.team_b if g.bat_team == "b" else g.team_a
        bowling_ids  = g.team_a if g.bat_team == "b" else g.team_b
        g.bat_scores = {uid: BatScore(uid, g.n(uid)) for uid in batting_ids}
        g.bowl_scores= {uid: BowlScore(uid, g.n(uid)) for uid in bowling_ids}
        g.bat_q      = list(batting_ids)
        g.bowl_q     = list(bowling_ids)
        g.batter     = g.bat_q[0]
        g.bowler     = g.bowl_q[0]
        await send(ctx, chat_id,
            sc + f"\n\n🔄 *Innings over! Target: {total+1}*\n"
            f"Now *Team {'B' if g.bat_team=='b' else 'A'}* bats! 🏏"
        )
        await asyncio.sleep(3)
        await next_ball(ctx, chat_id)
        return

    g.status = "ended"
    bat_pending.pop(chat_id, None)

    winner_text = ""
    if g.gtype == "team":
        g.tb_total = total
        if g.ta_total > g.tb_total:
            winner_text = "\n🏆 *Team A wins!* 🎉"
        elif g.tb_total > g.ta_total:
            winner_text = "\n🏆 *Team B wins!* 🎉"
        else:
            winner_text = "\n🤝 *It's a TIE!*"

    top = max(g.bat_scores.values(), key=lambda s: s.runs)
    await send(ctx, chat_id,
        f"🏁 *GAME OVER!*\n\n"
        + sc
        + winner_text
        + f"\n\n⭐ *Top scorer: {html.escape(top.name)}* — {top.runs}({top.balls})"
        + f"\n\nThanks for playing! 🏏"
    )

    # Cleanup
    for uid in g.players:
        bowl_pending.pop(uid, None)
    del games[chat_id]

# ═══════════════════════════════════════════════════════════════════
#  MESSAGE HANDLERS — Bat & Bowl numbers
# ═══════════════════════════════════════════════════════════════════
async def on_group_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle 1-6 numbers from batter in group."""
    msg  = update.message
    chat = update.effective_chat
    u    = update.effective_user
    text = (msg.text or "").strip()

    if not text.isdigit():
        return
    n = int(text)
    if n < 1 or n > 6:
        return

    g = games.get(chat.id)
    if not g or g.status != "bat_wait":
        return

    expected = bat_pending.get(chat.id)
    if u.id != expected:
        return  # Not this person's turn

    g.batter_num = n
    bat_pending.pop(chat.id, None)
    await resolve_ball(ctx, chat.id)

async def on_dm_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle 1-6 numbers from bowler in DM."""
    msg  = update.message
    u    = update.effective_user
    text = (msg.text or "").strip()

    # Register player on first DM
    if text == "/start":
        await cmd_start(update, ctx)
        return

    if not text.isdigit():
        return
    n = int(text)
    if n < 1 or n > 6:
        return

    chat_id = bowl_pending.get(u.id)
    if not chat_id:
        await msg.reply_text("✅ Number noted! Waiting for a game to start.")
        return

    g = games.get(chat_id)
    if not g or g.status != "bowling_wait":
        bowl_pending.pop(u.id, None)
        return

    g.bowler_num = n
    bowl_pending.pop(u.id, None)
    await msg.reply_text(f"✅ Bowled with *{n}*! Waiting for batter... 🤫",
                         parse_mode=ParseMode.MARKDOWN)
    await prompt_batter(ctx, chat_id)

# ═══════════════════════════════════════════════════════════════════
#  TEAM COMMANDS
# ═══════════════════════════════════════════════════════════════════
async def cmd_teama(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await assign_team(update, ctx, "a")

async def cmd_teamb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await assign_team(update, ctx, "b")

async def assign_team(update: Update, ctx: ContextTypes.DEFAULT_TYPE, team: str):
    chat = update.effective_chat
    u    = update.effective_user
    g    = games.get(chat.id)

    if not g or g.gtype != "team":
        await update.message.reply_text("❌ No team game in progress!")
        return
    if u.id != g.host_id and not await is_admin(update, ctx, u.id):
        await update.message.reply_text("❌ Only host/admin can assign teams!")
        return

    entities = update.message.parse_entities()
    mentioned = [e for e in entities if e.type == "mention"]
    if not mentioned and not update.message.entities:
        # Try text mention
        pass

    # Get mentioned usernames
    targets = []
    for e in (update.message.entities or []):
        if e.type == "mention":
            uname = update.message.text[e.offset+1:e.offset+e.length]
            for pid, pname in g.names.items():
                if (g.names[pid] or "").lower() == uname.lower():
                    targets.append(pid)

    if not targets:
        await update.message.reply_text(
            f"Usage: `/team{'a' if team=='a' else 'b'} @username`",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    label = "🔵 Team A" if team == "a" else "🟡 Team B"
    for pid in targets:
        if team == "a" and pid not in g.team_a:
            g.team_a.append(pid)
            g.team_b = [x for x in g.team_b if x != pid]
        else:
            g.team_b.append(pid)
            g.team_a = [x for x in g.team_a if x != pid]

    names = ", ".join(html.escape(g.n(pid)) for pid in targets)
    await update.message.reply_text(
        f"✅ *{names}* added to *{label}*!",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_beginteam(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    u    = update.effective_user
    g    = games.get(chat.id)

    if not g or g.gtype != "team":
        await update.message.reply_text("❌ No team game!")
        return
    if u.id != g.host_id and not await is_admin(update, ctx, u.id):
        await update.message.reply_text("❌ Only host/admin!")
        return
    if len(g.team_a) == 0 or len(g.team_b) == 0:
        await update.message.reply_text("⚠️ Both teams need at least 1 player!")
        return

    batting_ids  = g.team_a
    bowling_ids  = g.team_b
    g.bat_team   = "a"
    g.bat_scores = {uid: BatScore(uid, g.n(uid)) for uid in batting_ids}
    g.bowl_scores= {uid: BowlScore(uid, g.n(uid)) for uid in bowling_ids}
    g.bat_q      = list(batting_ids)
    g.bowl_q     = list(bowling_ids)
    g.batter     = g.bat_q[0]
    g.bowler     = g.bowl_q[0]

    ta = ", ".join(html.escape(g.n(x)) for x in g.team_a)
    tb = ", ".join(html.escape(g.n(x)) for x in g.team_b)
    await send(ctx, chat.id,
        f"⚔️ *TEAM MATCH BEGINS!*\n\n"
        f"🔵 *Team A (batting):* {ta}\n"
        f"🟡 *Team B (bowling):* {tb}\n\n"
        f"🏏 *{html.escape(g.n(g.batter))}* opens batting!"
    )
    await next_ball(ctx, chat.id)

async def cmd_setbatter(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    u    = update.effective_user
    g    = games.get(chat.id)

    if not g or g.gtype != "team":
        await update.message.reply_text("❌ Team mode only!")
        return
    if u.id != g.host_id and not await is_admin(update, ctx, u.id):
        await update.message.reply_text("❌ Host/admin only!")
        return

    for e in (update.message.entities or []):
        if e.type == "mention":
            uname = update.message.text[e.offset+1:e.offset+e.length]
            for pid, _ in g.names.items():
                if g.names.get(pid, "").lower() == uname.lower():
                    g.batter = pid
                    if pid not in g.bat_scores:
                        g.bat_scores[pid] = BatScore(pid, g.n(pid))
                    await update.message.reply_text(
                        f"🏏 *{html.escape(g.n(pid))}* is now batting!",
                        parse_mode=ParseMode.MARKDOWN)
                    return

async def cmd_setbowler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    u    = update.effective_user
    g    = games.get(chat.id)

    if not g:
        await update.message.reply_text("❌ No active game!")
        return
    if u.id != g.host_id and not await is_admin(update, ctx, u.id):
        await update.message.reply_text("❌ Host/admin only!")
        return

    for e in (update.message.entities or []):
        if e.type == "mention":
            uname = update.message.text[e.offset+1:e.offset+e.length]
            for pid in g.players:
                if g.names.get(pid, "").lower() == uname.lower():
                    old_bowler = g.bowler
                    g.bowler = pid
                    if pid not in g.bowl_scores:
                        g.bowl_scores[pid] = BowlScore(pid, g.n(pid))
                    bowl_pending.pop(old_bowler, None)
                    await update.message.reply_text(
                        f"🎳 *{html.escape(g.n(pid))}* is now bowling!",
                        parse_mode=ParseMode.MARKDOWN)
                    return

async def cmd_skip(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    u    = update.effective_user
    g    = games.get(chat.id)

    if not g:
        await update.message.reply_text("❌ No active game!")
        return
    if u.id != g.host_id and not await is_admin(update, ctx, u.id):
        await update.message.reply_text("❌ Host/admin only!")
        return

    if g.batter and g.batter in g.bat_scores:
        old = g.n(g.batter)
        g.bat_scores[g.batter].out = True
        bat_pending.pop(chat.id, None)
        await send(ctx, chat.id, f"⏭️ *{html.escape(old)}* was skipped!")
        nxt = g.next_batter()
        if not nxt:
            await finish_innings(ctx, chat.id)
        else:
            g.batter = nxt
            g.status = "active"
            await next_ball(ctx, chat.id)

# ═══════════════════════════════════════════════════════════════════
#  SCORE / STATS / LEADERBOARD
# ═══════════════════════════════════════════════════════════════════
async def cmd_score(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    g = games.get(update.effective_chat.id)
    if not g:
        await update.message.reply_text("❌ No active game!")
        return
    await update.message.reply_text(g.scorecard(), parse_mode=ParseMode.MARKDOWN)

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    upsert_player(u.id, u.username, fmt_name(u))
    s = get_stats(u.id)
    if not s:
        await update.message.reply_text("No stats yet! Play a game first 🏏")
        return
    avg = round(s["runs"] / max(s["matches"], 1), 2)
    overs = f"{s['balls_bowled']//6}.{s['balls_bowled']%6}"
    eco   = round(s["runs_given"] / max(s["balls_bowled"]/6, 1), 2) if s["balls_bowled"] else 0
    await update.message.reply_text(
        f"📊 *Stats — {html.escape(s['display_name'])}*\n\n"
        f"🏏 *BATTING*\n"
        f"Runs: `{s['runs']}` | Balls: `{s['balls']}`\n"
        f"6s: `{s['sixes']}` | 4s: `{s['fours']}`\n"
        f"Highest: `{s['highest']}` | Avg: `{avg}`\n\n"
        f"🎳 *BOWLING*\n"
        f"Wickets: `{s['wickets']}` | Overs: `{overs}`\n"
        f"Runs given: `{s['runs_given']}` | Economy: `{eco}`\n\n"
        f"🎮 Matches: `{s['matches']}`",
        parse_mode=ParseMode.MARKDOWN
    )

async def cmd_leaderboard(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = get_leaderboard(10)
    if not rows:
        await update.message.reply_text("No stats yet! Play a game first 🏏")
        return
    medals = ["🥇","🥈","🥉"] + ["🎖️"]*7
    lines  = ["🏆 *LEADERBOARD — TOP BATTERS*\n"]
    for i, r in enumerate(rows):
        avg = round(r["runs"] / max(r["matches"], 1), 2)
        lines.append(
            f"{medals[i]} *{html.escape(r['display_name'])}* — "
            f"`{r['runs']}` runs | HS `{r['highest']}` | Avg `{avg}`"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

# ═══════════════════════════════════════════════════════════════════
#  END GAME + VOTING
# ═══════════════════════════════════════════════════════════════════
async def cmd_endgame(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    u    = update.effective_user
    g    = games.get(chat.id)

    if not g:
        await update.message.reply_text("❌ No active game!")
        return

    admin_ok = await is_admin(update, ctx, u.id)

    if admin_ok:
        # Admin ends immediately, triggers group vote
        g.status   = "vote"
        g.votes    = {}

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ End Game", callback_data="vote_yes"),
            InlineKeyboardButton("❌ Keep Playing", callback_data="vote_no"),
        ]])
        msg = await send(ctx, chat.id,
            f"🗳️ *{html.escape(fmt_name(u))}* wants to end the game!\n"
            f"Vote below! Majority decides. ({VOTE_SEC}s)\n\n"
            f"Players: {len(g.players)}",
            reply_markup=kb
        )
        g.vote_msg = msg

        async def tally(cid=chat.id):
            await asyncio.sleep(VOTE_SEC)
            g2 = games.get(cid)
            if not g2 or g2.status != "vote":
                return
            yes = sum(1 for v in g2.votes.values() if v)
            no  = sum(1 for v in g2.votes.values() if not v)
            total_voters = len(g2.players)
            if yes > no or yes >= (total_voters / 2):
                await send(ctx, cid,
                    f"✅ *Vote passed!* ({yes} yes, {no} no)\nEnding game... 🏁")
                await finish_innings(ctx, cid)
            else:
                g2.status = g2.status if g2.status != "vote" else "active"
                await send(ctx, cid,
                    f"❌ *Vote failed!* ({yes} yes, {no} no)\nGame continues! 🏏")

        asyncio.create_task(tally())
    else:
        await update.message.reply_text(
            "❌ Only group admins can call an end-game vote!", 
            parse_mode=ParseMode.MARKDOWN
        )

async def vote_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    u = q.from_user
    await q.answer()

    chat = update.effective_chat
    g    = games.get(chat.id)
    if not g or g.status != "vote":
        return
    if u.id not in g.players:
        await q.answer("You're not a player!", show_alert=True)
        return

    g.votes[u.id] = (q.data == "vote_yes")
    yes = sum(1 for v in g.votes.values() if v)
    no  = sum(1 for v in g.votes.values() if not v)
    try:
        await q.edit_message_text(
            f"🗳️ *End Game Vote*\n✅ Yes: {yes} | ❌ No: {no}\n_{VOTE_SEC}s remaining..._",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ End Game", callback_data="vote_yes"),
                InlineKeyboardButton("❌ Keep Playing", callback_data="vote_no"),
            ]])
        )
    except:
        pass

# ═══════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════
def main():
    if not TOKEN:
        log.error("❌ BOT_TOKEN env variable not set!")
        return

    init_db()
    log.info("✅ Database initialised")

    app = Application.builder().token(TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start",       cmd_start))
    app.add_handler(CommandHandler("help",        cmd_help))
    app.add_handler(CommandHandler("newgame",     cmd_newgame))
    app.add_handler(CommandHandler("joingame",    cmd_joingame))
    app.add_handler(CommandHandler("startgame",   cmd_startgame))
    app.add_handler(CommandHandler("endgame",     cmd_endgame))
    app.add_handler(CommandHandler("score",       cmd_score))
    app.add_handler(CommandHandler("stats",       cmd_stats))
    app.add_handler(CommandHandler("leaderboard", cmd_leaderboard))
    app.add_handler(CommandHandler("teama",       cmd_teama))
    app.add_handler(CommandHandler("teamb",       cmd_teamb))
    app.add_handler(CommandHandler("beginteam",   cmd_beginteam))
    app.add_handler(CommandHandler("setbatter",   cmd_setbatter))
    app.add_handler(CommandHandler("setbowler",   cmd_setbowler))
    app.add_handler(CommandHandler("skip",        cmd_skip))

    # Vote callback
    app.add_handler(CallbackQueryHandler(vote_callback, pattern="^vote_"))

    # Number messages — group (batting)
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS,
        on_group_message
    ))

    # Number messages — DM (bowling)
    app.add_handler(MessageHandler(
        filters.TEXT & filters.ChatType.PRIVATE,
        on_dm_message
    ))

    log.info("🏏 Cricket Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
