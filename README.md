# 🏏 Cricket Telegram Bot — Complete Setup Guide

## What This Bot Does
- **Solo Mode**: All players join, each bats until OUT. Bowler sends number secretly in DM. If numbers match = WICKET!
- **Team Mode**: Two teams, host assigns players, controls batting/bowling order
- **Stats**: Every player's runs, wickets, highest score saved permanently
- **Voting**: Only group admins can call /endgame — group votes to confirm
- **Auto-bowl**: If bowler times out (60s), bot auto-bowls randomly

---

## STEP 1 — Create Your Telegram Bot (5 minutes)

1. Open Telegram, search for **@BotFather**
2. Send `/newbot`
3. Enter a name for your bot, e.g. `My Cricket Bot`
4. Enter a username ending in `bot`, e.g. `MyCricket_bot`
5. BotFather gives you a **TOKEN** that looks like:
   ```
   7123456789:AAHdqTcvCHhvGNUzRXi-P6yCLYZcBVqbLGM
   ```
6. **Copy and save this token!**

---

## STEP 2 — Put Files on GitHub (10 minutes)

1. Go to **https://github.com** → Sign up for free if you don't have account
2. Click the **+** button (top right) → **New repository**
3. Name it `cricket-bot` → Click **Create repository**
4. Click **uploading an existing file**
5. **Upload all 4 files**: `bot.py`, `requirements.txt`, `Procfile`, `railway.toml`
6. Click **Commit changes**

---

## STEP 3 — Deploy on Railway (10 minutes)

1. Go to **https://railway.app** → Sign up with GitHub
2. Click **New Project** → **Deploy from GitHub repo**
3. Select your `cricket-bot` repo → Click **Deploy Now**
4. Wait for it to say "Build succeeded" (takes ~2 minutes)

### Add Your Bot Token:
5. Click your project → Click **Variables** tab
6. Click **New Variable**
7. Name: `BOT_TOKEN`
8. Value: paste your token from Step 1
9. Click **Add** → Railway automatically restarts

### Check it's running:
10. Click **Deployments** tab → You should see ✅ green status
11. Click the deployment → Click **View Logs** → You should see:
    ```
    ✅ Database initialised
    🏏 Cricket Bot starting...
    ```

---

## STEP 4 — Set Up Your Bot (5 minutes)

### Important: Each player must DM the bot first!
1. Everyone who wants to BOWL needs to open the bot in DM and send `/start`
2. This allows the bot to DM them secretly for bowling numbers

### Add bot to your group:
1. In Telegram, open your group
2. Click group name → **Add Members**
3. Search your bot's username → Add it
4. Make the bot **admin** (so it can see all messages):
   - Group settings → Administrators → Add Administrator → select bot
   - Enable: Delete Messages, Post Messages

---

## HOW TO PLAY

### 🧍 Solo Game
```
/newgame solo       — Start game (anyone can start)
/joingame           — Others join (they have 90 seconds)
/startgame          — Host starts early

[Game starts automatically after 90 seconds]

— Bowler gets DM: "Send 1-6"
— Batter: send 1, 2, 3, 4, 5, or 6 in GROUP CHAT
— If numbers MATCH = 🚨 WICKET!
— If numbers DON'T match = batter's number = RUNS

/score              — See live scorecard
/endgame            — Admin starts vote to end
```

### 👥 Team Game
```
/newgame team       — Start team game
/joingame           — Everyone joins
/teama @username    — Host assigns player to Team A
/teamb @username    — Host assigns player to Team B
/beginteam          — Host starts the match

During match (host controls):
/setbatter @user    — Change who is batting
/setbowler @user    — Change who is bowling
/skip               — Skip current batter
```

### 📊 Stats & Leaderboard
```
/stats              — Your personal stats
/leaderboard        — Top 10 batters
```

---

## ALL COMMANDS QUICK REFERENCE

| Command | Who | What |
|---------|-----|-------|
| `/newgame solo` | Anyone | Start solo game |
| `/newgame team` | Anyone | Start team game |
| `/joingame` | Anyone | Join current game |
| `/startgame` | Host/Admin | Start early |
| `/endgame` | Admin ONLY | Vote to end |
| `/score` | Anyone | Live scorecard |
| `/stats` | Anyone | Personal stats |
| `/leaderboard` | Anyone | Top players |
| `/teama @user` | Host/Admin | Assign to Team A |
| `/teamb @user` | Host/Admin | Assign to Team B |
| `/beginteam` | Host/Admin | Start team match |
| `/setbatter @user` | Host/Admin | Change batter |
| `/setbowler @user` | Host/Admin | Change bowler |
| `/skip` | Host/Admin | Skip current batter |
| `/help` | Anyone | Show help |

---

## GAME RULES
- Send **1, 2, 3, 4, 5, or 6** only
- 🔴 **6 = SIX** (boundary)
- 🔵 **4 = FOUR** (boundary)  
- 🚨 **Match = WICKET** (batter is OUT)
- Bowler rotates every 6 balls (1 over)
- 60 second timeout — if you don't send, bot picks randomly
- Only group **admins** can use `/endgame`
- Game ends when all batters are OUT or vote passes

---

## TROUBLESHOOTING

**Bot doesn't respond?**
→ Check Railway logs for errors
→ Make sure BOT_TOKEN is set correctly in Variables
→ Make sure bot is admin in the group

**Bot can't DM bowler?**
→ That player must send `/start` to the bot in DM first
→ Bot will auto-bowl randomly if DM fails

**"No game found" error?**
→ Use `/newgame solo` to start a new game

**Railway shows error?**
→ Click Deployments → View Logs → share the error

---

## OPTIONAL SETTINGS (Railway Variables)
Add these in Railway Variables tab to customize:

| Variable | Default | What it does |
|----------|---------|--------------|
| `JOIN_SECONDS` | 90 | Seconds to join game |
| `BOWL_SECONDS` | 60 | Seconds bowler has to send number |
| `BAT_SECONDS` | 60 | Seconds batter has to send number |
| `VOTE_SECONDS` | 30 | Seconds for end-game vote |

---

*Bot built with python-telegram-bot v21 | Hosted on Railway*
