import os
import asyncio
import random
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot token from environment
BOT_TOKEN = os.getenv('BOT_TOKEN', '8253509018:AAFrrp0KSDv8_jk30aw2fK3XnTbp2RSprBg')

# Game state
class GameState:
    def __init__(self):
        self.players = {}  # {user_id: {'name': str, 'role': str, 'alive': bool}}
        self.game_active = False
        self.phase = "waiting"  # waiting, night, dawn, trial, banishment
        self.votes = {}  # {voter_id: voted_for_id}
        self.night_actions = {}  # {role: {user_id: target_id}}
        self.host_id = None
        self.group_chat_id = None
        self.phase_timer = None
        
    def reset(self):
        self.__init__()

game = GameState()

# Role definitions with fantasy names
ROLES = {
    'bloodseeker': {
        'name': '🩸 Bloodseeker',
        'description': 'Kill one player each night',
        'team': 'evil',
        'action': 'kill'
    },
    'oracle': {
        'name': '🔮 Oracle', 
        'description': 'Investigate one player each night',
        'team': 'good',
        'action': 'investigate'
    },
    'guardian': {
        'name': '🛡️ Guardian',
        'description': 'Protect one player each night',
        'team': 'good', 
        'action': 'protect'
    },
    'citizen': {
        'name': '🌿 Citizen',
        'description': 'Vote during trials to find evil',
        'team': 'good',
        'action': None
    },
    'trickster': {
        'name': '🃏 Trickster',
        'description': 'Swap two players\' votes',
        'team': 'neutral',
        'action': 'swap'
    },
    'soulhunter': {
        'name': '🏹 Soulhunter', 
        'description': 'One-shot kill during day',
        'team': 'evil',
        'action': 'dayshoot'
    }
}

# Phase GIFs
PHASE_GIFS = {
    'gathering': 'https://media.giphy.com/media/l0HU7JI1m1eEwz7Kw/giphy.gif',
    'convening': 'https://media.giphy.com/media/3o7TKsQ8UQ4l4LhGz6/giphy.gif', 
    'moonlight': 'https://media.giphy.com/media/3o6ZtnbirCMpFbGQ36/giphy.gif',
    'dawn': 'https://media.giphy.com/media/3o6Zt6ML6BklcajjsA/giphy.gif',
    'trial': 'https://media.giphy.com/media/l0HU7JI1m1eEwz7Kw/giphy.gif',
    'banishment': 'https://media.giphy.com/media/3o7TKr7e5gZeU5tq2c/giphy.gif'
}

def get_role_distribution(player_count):
    """Get role distribution based on player count"""
    if player_count <= 4:
        return ['bloodseeker', 'oracle', 'guardian', 'citizen']
    elif player_count <= 6:
        return ['bloodseeker', 'oracle', 'guardian', 'citizen', 'citizen', 'trickster']
    elif player_count <= 8:
        return ['bloodseeker', 'bloodseeker', 'oracle', 'guardian', 'citizen', 'citizen', 'soulhunter', 'trickster']
    else:
        return ['bloodseeker', 'bloodseeker', 'bloodseeker', 'oracle', 'guardian', 'citizen', 'citizen', 'citizen', 'soulhunter', 'trickster']

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - show welcome message"""
    welcome_text = """
🌌 **SHADOW COURT: THE SECRET COUNCIL**
*A fantasy social deduction game*

**Quick Start:**
• `/join` - Join the waiting list  
• `/rules` - Learn how to play
• `/status` - Check current game state
• `/help` - Show all commands

**Game Flow:**
1️⃣ Players join with `/join` (4+ needed)
2️⃣ Game auto-starts when enough players
3️⃣ Roles are assigned secretly via DM
4️⃣ Phases rotate automatically:
   🌙 **Moonlight** (30s) - Special roles act
   ☀️ **Dawn** (10s) - Reveal night results  
   ⚖️ **Trial** (45s) - Secret voting
   🔥 **Banishment** (10s) - Exile results

**Win Conditions:**
• 👑 **Good team** wins when all evil eliminated
• 💀 **Evil team** wins when they equal/outnumber good
• 🃏 **Neutral** roles have unique win conditions

Ready to enter the Shadow Court? Type `/join`!
    """
    
    await update.message.reply_animation(
        animation=PHASE_GIFS['gathering'],
        caption=welcome_text,
        parse_mode='Markdown'
    )

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explain detailed game rules"""
    rules_text = """
📜 **SHADOW COURT RULES**

**🧙‍♂️ ROLES:**
🩸 **Bloodseeker** - Kill one player each night (EVIL)
🔮 **Oracle** - Investigate player alignment (GOOD)  
🛡️ **Guardian** - Protect from night kills (GOOD)
🌿 **Citizen** - Vote to find evil (GOOD)
🃏 **Trickster** - Swap votes, survive to end (NEUTRAL)
🏹 **Soulhunter** - One daytime kill (EVIL)

**🌙 NIGHT PHASE (30s):**
• Special roles act via DM buttons
• Actions resolve simultaneously
• Protection beats kills

**⚖️ TRIAL PHASE (45s):**  
• All players vote secretly via DM
• Most votes = exiled
• Ties decided randomly
• Dead players cannot vote

**🎯 WIN CONDITIONS:**
• **Good wins**: All evil eliminated
• **Evil wins**: Equal/outnumber good  
• **Trickster wins**: Survives to final 3

**⚠️ IMPORTANT:**
• Votes are completely secret
• Roles revealed only on death
• Game auto-manages all phases
• Host can `/endgame` if needed

Type `/join` to start playing!
    """
    
    await update.message.reply_text(rules_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all available commands"""
    help_text = """
🎮 **ALL COMMANDS**

**🌟 MAIN COMMANDS:**
• `/start` - Show welcome & instructions
• `/rules` - Detailed game rules  
• `/join` - Join the waiting list
• `/status` - Current game status
• `/help` - Show this help menu

**⚙️ GAME MANAGEMENT:**
• `/endgame` - Force end current game (host only)
• `/kick @username` - Remove player (host only)

**🔍 DURING GAME:**
• Voting & actions happen via DM buttons
• Check your DM when phases change
• Use `/status` to see who's alive

**📊 GAME INFO:**
• 4-10 players supported
• Auto-start when 4+ joined  
• Phases run on timers
• Secret voting system
• Fantasy-themed roles

**🆘 NEED HELP?**
Having issues? The bot auto-manages everything!
Just `/join` and wait for others to join too.

Ready to play? Type `/join` now!
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Join the game"""
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ Please use `/join` in the group chat, not here!")
        return
        
    user = update.effective_user
    
    if game.game_active:
        await update.message.reply_text("❌ Game already in progress! Wait for it to end.")
        return
        
    if user.id in game.players:
        await update.message.reply_text(f"✅ {user.first_name}, you're already in the game!")
        return
        
    # Add player
    game.players[user.id] = {
        'name': user.first_name,
        'username': user.username or user.first_name,
        'role': None,
        'alive': True
    }
    
    game.group_chat_id = update.effective_chat.id
    player_count = len(game.players)
    
    await update.message.reply_animation(
        animation=PHASE_GIFS['gathering'],
        caption=f"👑 **{user.first_name}** joined the Shadow Court!\n\n**Players:** {player_count}/10\n\n{'🎮 **Game will auto-start soon!**' if player_count >= 4 else '⏳ Need 4+ players to begin...'}"
    )
    
    # Auto-start if we have enough players
    if player_count >= 4 and not game.game_active:
        await asyncio.sleep(3)  # Brief delay for dramatic effect
        await start_game(context)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current game status"""
    if not game.players:
        status_text = """
🌌 **SHADOW COURT STATUS**

**Game State:** Gathering players
**Players:** 0/10
**Phase:** Waiting for players

Type `/join` to enter the court!
        """
    else:
        alive_players = [p for p in game.players.values() if p['alive']]
        dead_players = [p for p in game.players.values() if not p['alive']]
        
        status_text = f"""
🌌 **SHADOW COURT STATUS**

**Game State:** {'🎮 Active' if game.game_active else '⏳ Waiting'}
**Phase:** {game.phase.title()}
**Players:** {len(game.players)}/10

**👥 Alive ({len(alive_players)}):**
{chr(10).join([f"• {p['name']}" for p in alive_players])}

**💀 Dead ({len(dead_players)}):**
{chr(10).join([f"• {p['name']} ({ROLES.get(p.get('role', 'citizen'), {}).get('name', 'Unknown')})" for p in dead_players]) if dead_players else "None yet"}

{'⚔️ Check your DM for actions!' if game.game_active else '📝 Type `/join` to enter!'}
        """
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

async def endgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force end the current game"""
    user = update.effective_user
    
    # Only host or any player can end if game is stuck
    if not game.game_active:
        await update.message.reply_text("❌ No active game to end!")
        return
        
    game.reset()
    await update.message.reply_animation(
        animation=PHASE_GIFS['banishment'],
        caption="🏁 **Game ended by player request!**\n\nType `/join` to start a new game!"
    )

async def start_game(context):
    """Start the game with role assignment"""
    if len(game.players) < 4:
        return
        
    game.game_active = True
    game.phase = "convening"
    
    # Assign roles
    player_ids = list(game.players.keys())
    roles = get_role_distribution(len(player_ids))
    random.shuffle(roles)
    
    for i, player_id in enumerate(player_ids):
        game.players[player_id]['role'] = roles[i]
        
    # Send role DMs
    for player_id, player_data in game.players.items():
        role_key = player_data['role']
        role_info = ROLES[role_key]
        
        role_message = f"""
🌟 **YOUR ROLE: {role_info['name']}**

**Description:** {role_info['description']}
**Team:** {role_info['team'].title()}

{'🌙 **You will receive action buttons during night phases.**' if role_info['action'] else '⚖️ **You vote during trial phases only.**'}

**Remember:** Keep your role secret! Good luck in the Shadow Court!
        """
        
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=role_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send role DM to {player_id}: {e}")
    
    # Announce game start
    await context.bot.send_animation(
        chat_id=game.group_chat_id,
        animation=PHASE_GIFS['convening'],
        caption="⚔️ **THE SHADOW COURT CONVENES!**\n\n🔮 Roles have been assigned via DM\n🌙 Night phase begins shortly...\n\n*Check your private messages!*"
    )
    
    # Start first night phase
    context.job_queue.run_once(start_night_phase, 5)

async def start_night_phase(context):
    """Start the night phase"""
    if not game.game_active:
        return
        
    game.phase = "night" 
    game.night_actions = {}
    
    await context.bot.send_animation(
        chat_id=game.group_chat_id,
        animation=PHASE_GIFS['moonlight'],
        caption="🌙 **MOONLIGHT PHASE** (30 seconds)\n\n*The court sleeps... but some work in shadows.*\n*Special roles: Check your DM!*"
    )
    
    # Send action DMs to special roles
    await send_night_action_dms(context)
    
    # Set timer for dawn
    context.job_queue.run_once(start_dawn_phase, 30)

async def send_night_action_dms(context):
    """Send action buttons to players with night actions"""
    alive_players = {pid: pdata for pid, pdata in game.players.items() if pdata['alive']}
    
    for player_id, player_data in alive_players.items():
        role_key = player_data['role']
        role_info = ROLES.get(role_key, {})
        
        if not role_info.get('action'):
            continue
            
        # Create target buttons (exclude self for most actions)
        targets = []
        for target_id, target_data in alive_players.items():
            if target_id != player_id or role_info['action'] == 'protect':  # Guardian can self-protect
                targets.append(InlineKeyboardButton(
                    f"🎯 {target_data['name']}", 
                    callback_data=f"night_{role_info['action']}_{target_id}"
                ))
        
        # Add skip option
        targets.append(InlineKeyboardButton("⏭️ Skip Action", callback_data="night_skip"))
        
        # Arrange buttons in rows of 2
        keyboard = [targets[i:i+2] for i in range(0, len(targets), 2)]
        
        action_text = f"""
🌙 **NIGHT ACTION: {role_info['name']}**

**Your Power:** {role_info['description']}

⏰ **Choose your target (30 seconds):**
        """
        
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=action_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send night action DM to {player_id}: {e}")

async def start_dawn_phase(context):
    """Process night actions and show results"""
    if not game.game_active:
        return
        
    game.phase = "dawn"
    
    # Process night actions
    killed_players = []
    protected_players = []
    investigation_results = {}
    
    # Get actions
    kills = game.night_actions.get('kill', {})
    protections = game.night_actions.get('protect', {})
    investigations = game.night_actions.get('investigate', {})
    
    # Process protections first
    protected_ids = list(protections.values())
    
    # Process kills
    for killer_id, target_id in kills.items():
        if target_id not in protected_ids:
            if target_id in game.players and game.players[target_id]['alive']:
                game.players[target_id]['alive'] = False
                killed_players.append(game.players[target_id])
        else:
            protected_players.append(game.players[target_id])
    
    # Process investigations  
    for investigator_id, target_id in investigations.items():
        if target_id in game.players:
            target_role = game.players[target_id]['role']
            target_team = ROLES.get(target_role, {}).get('team', 'unknown')
            investigation_results[investigator_id] = {
                'target': game.players[target_id],
                'team': target_team
            }
    
    # Create dawn message
    dawn_messages = ["☀️ **DAWN BREAKS OVER THE SHADOW COURT**\n"]
    
    if killed_players:
        for player in killed_players:
            role_name = ROLES.get(player['role'], {}).get('name', 'Unknown')
            dawn_messages.append(f"💀 **{player['name']}** was slain! ({role_name})")
    
    if protected_players:
        for player in protected_players:
            dawn_messages.append(f"🛡️ **{player['name']}** survived an attack!")
    
    if not killed_players and not protected_players:
        dawn_messages.append("🕊️ **A peaceful night... no blood was spilled.**")
    
    dawn_message = "\n".join(dawn_messages)
    
    await context.bot.send_animation(
        chat_id=game.group_chat_id,
        animation=PHASE_GIFS['dawn'],
        caption=dawn_message,
        parse_mode='Markdown'
    )
    
    # Send investigation results privately
    for investigator_id, result in investigation_results.items():
        result_text = f"""
🔮 **ORACLE VISION**

**Target:** {result['target']['name']}
**Alignment:** {result['team'].title()}

{'✅ This player fights for good!' if result['team'] == 'good' else '❌ This player harbors darkness!' if result['team'] == 'evil' else '🔮 This player walks their own path...'}
        """
        
        try:
            await context.bot.send_message(
                chat_id=investigator_id,
                text=result_text,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send investigation result to {investigator_id}: {e}")
    
    # Check win conditions
    if await check_win_condition(context):
        return
    
    # Start trial phase
    context.job_queue.run_once(start_trial_phase, 10)

async def start_trial_phase(context):
    """Start the voting phase"""
    if not game.game_active:
        return
        
    game.phase = "trial"
    game.votes = {}
    
    await context.bot.send_animation(
        chat_id=game.group_chat_id,
        animation=PHASE_GIFS['trial'],
        caption="⚖️ **TRIAL PHASE** (45 seconds)\n\n*The court demands justice!*\n*Cast your secret votes via DM!*"
    )
    
    # Send voting DMs
    await send_voting_dms(context)
    
    # Set timer for banishment
    context.job_queue.run_once(start_banishment_phase, 45)

async def send_voting_dms(context):
    """Send voting buttons to all alive players"""
    alive_players = {pid: pdata for pid, pdata in game.players.items() if pdata['alive']}
    
    if len(alive_players) <= 1:
        return
    
    for voter_id, voter_data in alive_players.items():
        # Create voting buttons (exclude self)
        targets = []
        for target_id, target_data in alive_players.items():
            if target_id != voter_id:
                targets.append(InlineKeyboardButton(
                    f"🗳️ {target_data['name']}", 
                    callback_data=f"vote_{target_id}"
                ))
        
        # Add skip option
        targets.append(InlineKeyboardButton("⏭️ Skip Vote", callback_data="vote_skip"))
        
        # Arrange buttons in rows of 2
        keyboard = [targets[i:i+2] for i in range(0, len(targets), 2)]
        
        vote_text = f"""
⚖️ **SECRET VOTING**

**The Shadow Court must decide who to exile!**

⏰ **Cast your vote (45 seconds):**

*Remember: Your vote is completely secret!*
        """
        
        try:
            await context.bot.send_message(
                chat_id=voter_id,
                text=vote_text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send voting DM to {voter_id}: {e}")

async def start_banishment_phase(context):
    """Process votes and exile player"""
    if not game.game_active:
        return
        
    game.phase = "banishment"
    
    # Count votes
    vote_counts = {}
    alive_players = {pid: pdata for pid, pdata in game.players.items() if pdata['alive']}
    
    for target_id in alive_players.keys():
        vote_counts[target_id] = 0
    
    for voter_id, voted_for in game.votes.items():
        if voted_for != "skip" and voted_for in vote_counts:
            vote_counts[voted_for] += 1
    
    # Find player with most votes
    if not vote_counts or max(vote_counts.values()) == 0:
        # No votes cast
        await context.bot.send_animation(
            chat_id=game.group_chat_id,
            animation=PHASE_GIFS['banishment'],
            caption="⚖️ **THE COURT REMAINS SILENT**\n\n*No votes were cast... The trial ends in silence.*"
        )
    else:
        max_votes = max(vote_counts.values())
        candidates = [pid for pid, votes in vote_counts.items() if votes == max_votes]
        
        # Handle ties randomly
        exiled_id = random.choice(candidates)
        exiled_player = game.players[exiled_id]
        exiled_player['alive'] = False
        
        role_name = ROLES.get(exiled_player['role'], {}).get('name', 'Unknown')
        
        banishment_text = f"""
🔥 **THE COURT HAS SPOKEN!**

**{exiled_player['name']}** has been exiled!
**Role:** {role_name}
**Votes:** {vote_counts[exiled_id]}

*The shadows claim another soul...*
        """
        
        await context.bot.send_animation(
            chat_id=game.group_chat_id,
            animation=PHASE_GIFS['banishment'],
            caption=banishment_text,
            parse_mode='Markdown'
        )
    
    # Check win conditions
    if await check_win_condition(context):
        return
    
    # Start next night phase
    context.job_queue.run_once(start_night_phase, 10)

async def check_win_condition(context):
    """Check if game should end"""
    if not game.game_active:
        return True
        
    alive_players = {pid: pdata for pid, pdata in game.players.items() if pdata['alive']}
    
    if len(alive_players) <= 1:
        # Game over - not enough players
        game.game_active = False
        await context.bot.send_animation(
            chat_id=game.group_chat_id,
            animation=PHASE_GIFS['banishment'],
            caption="🏁 **GAME OVER**\n\n*Too few players remain...*\n\nType `/join` to start a new game!"
        )
        game.reset()
        return True
    
    # Count teams
    good_count = 0
    evil_count = 0
    neutral_count = 0
    
    for player_data in alive_players.values():
        role_key = player_data['role']
        team = ROLES.get(role_key, {}).get('team', 'good')
        
        if team == 'good':
            good_count += 1
        elif team == 'evil':
            evil_count += 1
        else:
            neutral_count += 1
    
    # Check win conditions
    if evil_count == 0:
        # Good wins
        game.game_active = False
        await context.bot.send_animation(
            chat_id=game.group_chat_id,
            animation=PHASE_GIFS['dawn'],
            caption="👑 **VICTORY FOR THE LIGHT!**\n\n✨ The Shadow Court is cleansed!\n🌟 Good team wins!\n\nType `/join` to start a new game!"
        )
        game.reset()
        return True
    elif evil_count >= good_count:
        # Evil wins
        game.game_active = False
        await context.bot.send_animation(
            chat_id=game.group_chat_id,
            animation=PHASE_GIFS['banishment'],
            caption="💀 **DARKNESS PREVAILS!**\n\n🌑 The Shadow Court falls to evil!\n⚔️ Evil team wins!\n\nType `/join` to start a new game!"
        )
        game.reset()
        return True
    
    return False

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if not game.game_active or user_id not in game.players or not game.players[user_id]['alive']:
        await query.edit_message_text("❌ You cannot perform this action.")
        return
    
    if data.startswith("night_"):
        # Night action
        parts = data.split("_")
        action = parts[1]
        
        if action == "skip":
            await query.edit_message_text(f"⏭️ You chose to skip your night action.")
            return
            
        target_id = int(parts[2])
        
        if action not in game.night_actions:
            game.night_actions[action] = {}
        
        game.night_actions[action][user_id] = target_id
        target_name = game.players[target_id]['name']
        
        action_names = {
            'kill': 'marked for death',
            'protect': 'protected', 
            'investigate': 'investigated'
        }
        
        await query.edit_message_text(f"✅ **{target_name}** has been {action_names.get(action, 'targeted')}!")
        
    elif data.startswith("vote_"):
        # Voting
        if data == "vote_skip":
            game.votes[user_id] = "skip"
            await query.edit_message_text("⏭️ You chose to skip voting.")
        else:
            target_id = int(data.split("_")[1])
            game.votes[user_id] = target_id
            target_name = game.players[target_id]['name']
            await query.edit_message_text(f"🗳️ Your secret vote for **{target_name}** has been cast!")

async def webhook_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle webhook updates"""
    pass

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("join", join_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("endgame", endgame_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # For webhook mode (required for Render)
    if os.environ.get('RENDER'):
        # Webhook mode for production
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"https://shadow-court.onrender.com/"
        )
    else:
        # Polling mode for development
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()[user_id]['alive']:
        await query.edit_message_text("❌ You cannot perform this action.")
        return
    
    if data.startswith("night_"):
        # Night action
        parts = data.split("_")
        action = parts[1]
        
        if action == "skip":
            await query.edit_message_text(f"⏭️ You chose to skip your night action.")
            return
            
        target_id = int(parts[2])
        
        if action not in game.night_actions:
            game.night_actions[action] = {}
        
        game.night_actions[action][user_id] = target_id
        target_name = game.players[target_id]['name']
        
        action_names = {
            'kill': 'marked for death',
            'protect': 'protected', 
            'investigate': 'investigated'
        }
        
        await query.edit_message_text(f"✅ **{target_name}** has been {action_names.get(action, 'targeted')}!")
        
    elif data.startswith("vote_"):
        # Voting
        if data == "vote_skip":
            game.votes[user_id] = "skip"
            await query.edit_message_text("⏭️ You chose to skip voting.")
        else:
            target_id = int(data.split("_")[1])
            game.votes[user_id] = target_id
            target_name = game.players[target_id]['name']
            await query.edit_message_text(f"🗳️ Your secret vote for **{target_name}** has been cast!")

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("join", join_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("endgame", endgame_command))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Start polling
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
