import os
import asyncio
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot token
BOT_TOKEN = os.getenv('BOT_TOKEN', '8253509018:AAFrrp0KSDv8_jk30aw2fK3XnTbp2RSprBg')
PORT = int(os.environ.get('PORT', 8080))

# Game state
class GameState:
    def __init__(self):
        self.players = {}
        self.game_active = False
        self.phase = "waiting"
        self.votes = {}
        self.night_actions = {}
        self.group_chat_id = None
        
    def reset(self):
        self.__init__()

game = GameState()

# Roles
ROLES = {
    'bloodseeker': {'name': '🩸 Bloodseeker', 'team': 'evil', 'action': 'kill'},
    'oracle': {'name': '🔮 Oracle', 'team': 'good', 'action': 'investigate'},
    'guardian': {'name': '🛡️ Guardian', 'team': 'good', 'action': 'protect'},
    'citizen': {'name': '🌿 Citizen', 'team': 'good', 'action': None},
    'trickster': {'name': '🃏 Trickster', 'team': 'neutral', 'action': None}
}

def get_role_distribution(count):
    if count <= 4:
        return ['bloodseeker', 'oracle', 'guardian', 'citizen']
    elif count <= 6:
        return ['bloodseeker', 'oracle', 'guardian', 'citizen', 'citizen', 'trickster']
    else:
        return ['bloodseeker', 'bloodseeker', 'oracle', 'guardian', 'citizen', 'citizen', 'trickster', 'citizen']

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome = """🌌 **SHADOW COURT: THE SECRET COUNCIL**

**Commands:**
• /join - Join the game (4+ needed)
• /rules - Game rules
• /status - Current game state
• /help - All commands
• /endgame - End current game

**How to Play:**
1. Players join with /join
2. Game auto-starts at 4+ players
3. Roles assigned via DM
4. Phases rotate automatically
5. Secret voting via DM

Ready? Type /join!"""
    
    await update.message.reply_text(welcome, parse_mode='Markdown')

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rules = """📜 **GAME RULES**

**Roles:**
🩸 **Bloodseeker** - Kill at night (EVIL)
🔮 **Oracle** - Investigate players (GOOD)
🛡️ **Guardian** - Protect from kills (GOOD)
🌿 **Citizen** - Vote to find evil (GOOD)
🃏 **Trickster** - Survive to win (NEUTRAL)

**Phases:**
🌙 **Night** - Special roles act
☀️ **Dawn** - Show results
⚖️ **Trial** - Secret voting
🔥 **Banishment** - Exile player

**Win Conditions:**
✅ Good wins: All evil eliminated
❌ Evil wins: Equal/outnumber good
🃏 Trickster wins: Survives to end"""
    
    await update.message.reply_text(rules, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = """🎮 **ALL COMMANDS**

**/start** - Welcome message
**/rules** - Game rules
**/join** - Join waiting list
**/status** - Game status
**/help** - This menu
**/endgame** - End game

**Game Info:**
• 4-10 players supported
• Auto-start when ready
• Secret voting system
• Fantasy themed roles
• Fully automated phases

Type /join to play!"""
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ Use /join in group chat!")
        return
        
    user = update.effective_user
    
    if game.game_active:
        await update.message.reply_text("❌ Game in progress!")
        return
        
    if user.id in game.players:
        await update.message.reply_text(f"✅ {user.first_name}, you're already in!")
        return
        
    game.players[user.id] = {
        'name': user.first_name,
        'role': None,
        'alive': True
    }
    
    game.group_chat_id = update.effective_chat.id
    count = len(game.players)
    
    await update.message.reply_text(
        f"👑 **{user.first_name}** joined!\n**Players:** {count}/10\n\n{'🎮 Starting soon!' if count >= 4 else '⏳ Need 4+ players'}"
    )
    
    if count >= 4 and not game.game_active:
        context.job_queue.run_once(lambda c: asyncio.create_task(start_game(c)), 3)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not game.players:
        await update.message.reply_text("🌌 **No active game**\n\nType /join to start!")
        return
        
    alive = [p for p in game.players.values() if p['alive']]
    dead = [p for p in game.players.values() if not p['alive']]
    
    status = f"""🌌 **SHADOW COURT STATUS**

**State:** {'🎮 Active' if game.game_active else '⏳ Waiting'}
**Phase:** {game.phase.title()}
**Players:** {len(game.players)}/10

**👥 Alive ({len(alive)}):**
{chr(10).join([f"• {p['name']}" for p in alive])}

**💀 Dead ({len(dead)}):**
{chr(10).join([f"• {p['name']}" for p in dead]) if dead else "None"}

{'⚔️ Check DM for actions!' if game.game_active else '📝 Type /join!'}"""
    
    await update.message.reply_text(status, parse_mode='Markdown')

async def endgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not game.game_active:
        await update.message.reply_text("❌ No active game!")
        return
        
    game.reset()
    await update.message.reply_text("🏁 **Game ended!**\n\nType /join for new game!")

async def start_game(context):
    if len(game.players) < 4:
        return
        
    game.game_active = True
    game.phase = "night"
    
    # Assign roles
    player_ids = list(game.players.keys())
    roles = get_role_distribution(len(player_ids))
    random.shuffle(roles)
    
    for i, pid in enumerate(player_ids):
        game.players[pid]['role'] = roles[i]
        
    # Send role DMs
    for pid, player in game.players.items():
        role = ROLES[player['role']]
        msg = f"🌟 **YOUR ROLE: {role['name']}**\n\nTeam: {role['team'].title()}\n\nKeep it secret!"
        
        try:
            await context.bot.send_message(pid, msg, parse_mode='Markdown')
        except:
            pass
    
    # Announce start
    await context.bot.send_message(
        game.group_chat_id,
        "⚔️ **SHADOW COURT BEGINS!**\n\n🔮 Roles sent via DM\n🌙 Night phase starting...",
        parse_mode='Markdown'
    )
    
    context.job_queue.run_once(lambda c: asyncio.create_task(night_phase(c)), 5)

async def night_phase(context):
    if not game.game_active:
        return
        
    game.phase = "night"
    game.night_actions = {}
    
    await context.bot.send_message(
        game.group_chat_id,
        "🌙 **NIGHT PHASE** (30s)\n\nSpecial roles: Check DM!"
    )
    
    # Send action DMs
    alive = {pid: p for pid, p in game.players.items() if p['alive']}
    
    for pid, player in alive.items():
        role = ROLES[player['role']]
        if not role['action']:
            continue
            
        targets = []
        for tid, target in alive.items():
            if tid != pid or role['action'] == 'protect':
                targets.append(InlineKeyboardButton(
                    f"🎯 {target['name']}", 
                    callback_data=f"night_{role['action']}_{tid}"
                ))
        
        targets.append(InlineKeyboardButton("⏭️ Skip", callback_data="night_skip"))
        keyboard = [targets[i:i+2] for i in range(0, len(targets), 2)]
        
        try:
            await context.bot.send_message(
                pid,
                f"🌙 **{role['name']} Action**\n\nChoose target:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass
    
    context.job_queue.run_once(lambda c: asyncio.create_task(dawn_phase(c)), 30)

async def dawn_phase(context):
    if not game.game_active:
        return
        
    game.phase = "dawn"
    
    # Process actions
    killed = []
    protected = []
    
    kills = game.night_actions.get('kill', {})
    protects = game.night_actions.get('protect', {})
    investigations = game.night_actions.get('investigate', {})
    
    protected_ids = list(protects.values())
    
    for killer, target in kills.items():
        if target not in protected_ids and game.players[target]['alive']:
            game.players[target]['alive'] = False
            killed.append(game.players[target])
        elif target in protected_ids:
            protected.append(game.players[target])
    
    # Dawn message
    msg = "☀️ **DAWN BREAKS**\n\n"
    if killed:
        for p in killed:
            role_name = ROLES[p['role']]['name']
            msg += f"💀 **{p['name']}** died! ({role_name})\n"
    if protected:
        for p in protected:
            msg += f"🛡️ **{p['name']}** was protected!\n"
    if not killed and not protected:
        msg += "🕊️ Peaceful night...\n"
        
    await context.bot.send_message(game.group_chat_id, msg, parse_mode='Markdown')
    
    # Send investigation results
    for investigator, target in investigations.items():
        if target in game.players:
            team = ROLES[game.players[target]['role']]['team']
            result = f"🔮 **Investigation Result**\n\n{game.players[target]['name']}: {team.title()}"
            try:
                await context.bot.send_message(investigator, result, parse_mode='Markdown')
            except:
                pass
    
    if await check_win(context):
        return
    
    context.job_queue.run_once(lambda c: asyncio.create_task(trial_phase(c)), 10)

async def trial_phase(context):
    if not game.game_active:
        return
        
    game.phase = "trial"
    game.votes = {}
    
    await context.bot.send_message(
        game.group_chat_id,
        "⚖️ **TRIAL PHASE** (45s)\n\nVote secretly via DM!"
    )
    
    # Send voting DMs
    alive = {pid: p for pid, p in game.players.items() if p['alive']}
    
    for voter_id, voter in alive.items():
        targets = []
        for target_id, target in alive.items():
            if target_id != voter_id:
                targets.append(InlineKeyboardButton(
                    f"🗳️ {target['name']}", 
                    callback_data=f"vote_{target_id}"
                ))
        
        targets.append(InlineKeyboardButton("⏭️ Skip", callback_data="vote_skip"))
        keyboard = [targets[i:i+2] for i in range(0, len(targets), 2)]
        
        try:
            await context.bot.send_message(
                voter_id,
                "⚖️ **SECRET VOTE**\n\nWho should be exiled?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except:
            pass
    
    context.job_queue.run_once(lambda c: asyncio.create_task(banish_phase(c)), 45)

async def banish_phase(context):
    if not game.game_active:
        return
        
    game.phase = "banishment"
    
    # Count votes
    alive = {pid: p for pid, p in game.players.items() if p['alive']}
    vote_counts = {pid: 0 for pid in alive.keys()}
    
    for voter, voted_for in game.votes.items():
        if voted_for != "skip" and voted_for in vote_counts:
            vote_counts[voted_for] += 1
    
    if max(vote_counts.values()) == 0:
        await context.bot.send_message(
            game.group_chat_id,
            "⚖️ **NO EXILE**\n\nNo votes cast..."
        )
    else:
        max_votes = max(vote_counts.values())
        candidates = [pid for pid, votes in vote_counts.items() if votes == max_votes]
        exiled_id = random.choice(candidates)
        
        game.players[exiled_id]['alive'] = False
        exiled = game.players[exiled_id]
        role_name = ROLES[exiled['role']]['name']
        
        await context.bot.send_message(
            game.group_chat_id,
            f"🔥 **{exiled['name']} EXILED!**\n\nRole: {role_name}\nVotes: {vote_counts[exiled_id]}",
            parse_mode='Markdown'
        )
    
    if await check_win(context):
        return
    
    context.job_queue.run_once(lambda c: asyncio.create_task(night_phase(c)), 10)

async def check_win(context):
    if not game.game_active:
        return True
        
    alive = {pid: p for pid, p in game.players.items() if p['alive']}
    
    if len(alive) <= 1:
        game.game_active = False
        await context.bot.send_message(
            game.group_chat_id,
            "🏁 **GAME OVER**\n\nToo few players!\n\nType /join for new game!"
        )
        game.reset()
        return True
    
    good = evil = 0
    for p in alive.values():
        team = ROLES[p['role']]['team']
        if team == 'good':
            good += 1
        elif team == 'evil':
            evil += 1
    
    if evil == 0:
        game.game_active = False
        await context.bot.send_message(
            game.group_chat_id,
            "👑 **GOOD WINS!**\n\n✨ Evil eliminated!\n\nType /join for new game!"
        )
        game.reset()
        return True
    elif evil >= good:
        game.game_active = False
        await context.bot.send_message(
            game.group_chat_id,
            "💀 **EVIL WINS!**\n\n🌑 Darkness prevails!\n\nType /join for new game!"
        )
        game.reset()
        return True
    
    return False

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if not game.game_active or user_id not in game.players or not game.players[user_id]['alive']:
        await query.edit_message_text("❌ Cannot perform action")
        return
    
    if data.startswith("night_"):
        parts = data.split("_")
        action = parts[1]
        
        if action == "skip":
            await query.edit_message_text("⏭️ Skipped night action")
            return
            
        target_id = int(parts[2])
        
        if action not in game.night_actions:
            game.night_actions[action] = {}
        
        game.night_actions[action][user_id] = target_id
        target_name = game.players[target_id]['name']
        
        await query.edit_message_text(f"✅ **{target_name}** targeted!")
        
    elif data.startswith("vote_"):
        if data == "vote_skip":
            game.votes[user_id] = "skip"
            await query.edit_message_text("⏭️ Vote skipped")
        else:
            target_id = int(data.split("_")[1])
            game.votes[user_id] = target_id
            target_name = game.players[target_id]['name']
            await query.edit_message_text(f"🗳️ Voted for **{target_name}**!")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("rules", rules_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("join", join_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("endgame", endgame_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    # For Render deployment
    if os.environ.get('PORT'):
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"https://shadow-court.onrender.com/"
        )
    else:
        app.run_polling()

if __name__ == '__main__':
    main()
