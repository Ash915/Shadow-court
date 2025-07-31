import os
import asyncio
import random
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv('BOT_TOKEN', '8253509018:AAFrrp0KSDv8_jk30aw2fK3XnTbp2RSprBg')
PORT = int(os.environ.get('PORT', 8080))

# Game state management
class GameState:
    def __init__(self):
        self.players = {}  # {user_id: {'name': str, 'role': str, 'alive': bool, 'protected': bool}}
        self.game_active = False
        self.phase = "waiting"  # waiting, night, dawn, trial, banishment
        self.votes = {}  # {voter_id: voted_for_id}
        self.night_actions = {}  # {action_type: {user_id: target_id}}
        self.group_chat_id = None
        self.day_number = 0
        self.phase_start_time = None
        self.special_abilities_used = {}  # Track one-time abilities
        
    def reset(self):
        self.__init__()
    
    def get_alive_players(self):
        return {pid: pdata for pid, pdata in self.players.items() if pdata['alive']}
    
    def get_players_by_team(self, team):
        return {pid: pdata for pid, pdata in self.players.items() 
                if pdata['alive'] and ROLES.get(pdata['role'], {}).get('team') == team}

game = GameState()

# Enhanced role definitions with full features
ROLES = {
    'bloodseeker': {
        'name': '🩸 Bloodseeker',
        'description': 'Kill one player each night. Work with other evil players.',
        'team': 'evil',
        'action': 'kill',
        'win_condition': 'Eliminate all good players or equal their numbers'
    },
    'oracle': {
        'name': '🔮 Oracle', 
        'description': 'Investigate one player each night to learn their alignment.',
        'team': 'good',
        'action': 'investigate',
        'win_condition': 'Eliminate all evil players'
    },
    'guardian': {
        'name': '🛡️ Guardian',
        'description': 'Protect one player each night from death (including yourself).',
        'team': 'good', 
        'action': 'protect',
        'win_condition': 'Eliminate all evil players'
    },
    'citizen': {
        'name': '🌿 Citizen',
        'description': 'Vote during trials to find and eliminate evil players.',
        'team': 'good',
        'action': None,
        'win_condition': 'Eliminate all evil players'
    },
    'trickster': {
        'name': '🃏 Trickster',
        'description': 'Survive until the end. Can swap two players\' votes once per game.',
        'team': 'neutral',
        'action': 'swap',
        'win_condition': 'Survive to the final 3 players'
    },
    'soulhunter': {
        'name': '🏹 Soulhunter', 
        'description': 'Evil assassin with one daytime kill ability.',
        'team': 'evil',
        'action': 'dayshoot',
        'win_condition': 'Eliminate all good players or equal their numbers'
    },
    'justicar': {
        'name': '⚖️ Justicar',
        'description': 'Can cancel all votes once per game during trial phase.',
        'team': 'good',
        'action': 'cancel_votes',
        'win_condition': 'Eliminate all evil players'
    },
    'spiritwalker': {
        'name': '👻 Spiritwalker',
        'description': 'Can communicate with dead players and learn one role.',
        'team': 'good',
        'action': 'commune',
        'win_condition': 'Eliminate all evil players'
    }
}

# Phase GIFs for immersive experience
PHASE_GIFS = {
    'gathering': 'https://media.giphy.com/media/3o7TKQ8kAP0f9X5PoY/giphy.gif',
    'convening': 'https://media.giphy.com/media/3o7TKsQ8UQ4l4LhGz6/giphy.gif', 
    'moonlight': 'https://media.giphy.com/media/3o6ZtnbirCMpFbGQ36/giphy.gif',
    'dawn': 'https://media.giphy.com/media/3o6Zt6ML6BklcajjsA/giphy.gif',
    'trial': 'https://media.giphy.com/media/l0Iy69UBN8D3yLDYQ/giphy.gif',
    'banishment': 'https://media.giphy.com/media/3o7TKr7e5gZeU5tq2c/giphy.gif',
    'victory_good': 'https://media.giphy.com/media/26u4cqiYI30juCOGY/giphy.gif',
    'victory_evil': 'https://media.giphy.com/media/3o7TKBvOZ1VwfT1Yf6/giphy.gif'
}

def get_role_distribution(player_count):
    """Advanced role distribution based on player count"""
    if player_count == 4:
        return ['bloodseeker', 'oracle', 'guardian', 'citizen']
    elif player_count == 5:
        return ['bloodseeker', 'oracle', 'guardian', 'citizen', 'trickster']
    elif player_count == 6:
        return ['bloodseeker', 'oracle', 'guardian', 'citizen', 'citizen', 'trickster']
    elif player_count == 7:
        return ['bloodseeker', 'bloodseeker', 'oracle', 'guardian', 'citizen', 'citizen', 'trickster']
    elif player_count == 8:
        return ['bloodseeker', 'bloodseeker', 'oracle', 'guardian', 'soulhunter', 'citizen', 'citizen', 'trickster']
    elif player_count == 9:
        return ['bloodseeker', 'bloodseeker', 'oracle', 'guardian', 'soulhunter', 'citizen', 'citizen', 'citizen', 'justicar']
    else:  # 10+
        return ['bloodseeker', 'bloodseeker', 'bloodseeker', 'oracle', 'guardian', 'soulhunter', 'spiritwalker', 'citizen', 'citizen', 'justicar']

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced start command with full game explanation"""
    welcome_text = """
🌌 **SHADOW COURT: THE SECRET COUNCIL**
*The Ultimate Fantasy Social Deduction Game*

**🎮 QUICK START:**
• `/join` - Join the waiting list (4-10 players)
• `/rules` - Complete game rules & roles
• `/status` - Current game state & players
• `/help` - All available commands

**⚔️ EPIC GAME FLOW:**
1️⃣ **Join Phase**: Players gather with `/join`
2️⃣ **Auto-Start**: Game begins at 4+ players  
3️⃣ **Role Assignment**: Secret roles via DM
4️⃣ **Automated Phases**:
   🌙 **Moonlight** (30s) - Special roles act in shadows
   ☀️ **Dawn** (10s) - Reveal the night's events
   ⚖️ **Trial** (45s) - Secret voting for exile
   🔥 **Banishment** (10s) - Execute the court's decision

**🏆 WIN CONDITIONS:**
• 👑 **Good Team**: Eliminate all evil players
• 💀 **Evil Team**: Equal or outnumber good players  
• 🃏 **Neutral Roles**: Unique survival conditions

**🌟 SPECIAL FEATURES:**
• 🔒 **Anonymous Voting** - No vote pressure
• 🎭 **8 Unique Fantasy Roles** - Scalable 4-10 players
• 🎬 **Cinematic GIFs** - Immersive phase visuals
• 🤖 **Fully Automated** - No human host needed
• ⚡ **Fast-Paced** - 2-minute phases keep excitement

Ready to enter the Shadow Court? Type `/join` now! ⚔️
    """
    
    try:
        await update.message.reply_animation(
            animation=PHASE_GIFS['gathering'],
            caption=welcome_text,
            parse_mode='Markdown'
        )
    except Exception:
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Complete rules explanation with all roles"""
    rules_text = """
📜 **COMPLETE SHADOW COURT RULES**

**🧙‍♂️ ALL ROLES & ABILITIES:**

**👑 GOOD TEAM (Eliminate Evil):**
🔮 **Oracle** - Investigate alignment each night
🛡️ **Guardian** - Protect from night kills  
🌿 **Citizen** - Vote to find evil players
⚖️ **Justicar** - Cancel all votes once per game
👻 **Spiritwalker** - Commune with dead players

**💀 EVIL TEAM (Outnumber Good):**
🩸 **Bloodseeker** - Kill one player each night
🏹 **Soulhunter** - One-time daytime assassination

**🃏 NEUTRAL (Unique Win Conditions):**
🃏 **Trickster** - Survive to final 3, swap votes once

**🌙 NIGHT PHASE (30 seconds):**
• Special roles receive DM with action buttons
• Actions resolve simultaneously at phase end
• Guardian protection beats Bloodseeker kills
• Oracle learns target's team alignment

**⚖️ TRIAL PHASE (45 seconds):**  
• All living players vote secretly via DM
• Player with most votes is exiled
• Ties are broken randomly
• Dead players cannot vote
• Justicar can cancel all votes (once only)

**🎯 ADVANCED MECHANICS:**
• **Vote Weighting**: All votes count equally
• **Protection Rules**: Guardian saves override kills
• **Investigation**: Oracle sees "Good/Evil/Neutral"
• **Special Abilities**: Most are one-time use only
• **Death Reveal**: Role shown when eliminated

**📊 ROLE SCALING (Auto-Balanced):**
• **4-5 players**: Basic roles only
• **6-7 players**: Trickster added  
• **8+ players**: Advanced roles activated
• **10 players**: Full role complexity

**🔥 WINNING STRATEGIES:**
• **Good**: Use Oracle info, protect key players
• **Evil**: Blend in, eliminate threats at night
• **Trickster**: Stay neutral, don't seem threatening

Ready to master the Shadow Court? `/join` now! 🌌
    """
    
    await update.message.reply_text(rules_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comprehensive help with all commands"""
    help_text = """
🎮 **COMPLETE COMMAND GUIDE**

**🌟 MAIN COMMANDS:**
• `/start` - Game welcome & overview
• `/rules` - Complete rules & all roles  
• `/join` - Join the waiting list
• `/status` - Detailed game status
• `/help` - This comprehensive guide

**⚙️ GAME MANAGEMENT:**
• `/endgame` - Force end current game
• `/players` - List all joined players
• `/roles` - Quick role reference

**🔍 DURING GAMEPLAY:**
• All actions happen via **DM buttons**
• **Night actions**: Special roles get buttons
• **Voting**: Secret DM voting interface
• Use `/status` to see current phase & players

**📊 GAME INFORMATION:**
• **Players**: 4-10 supported (auto-scaling roles)
• **Duration**: ~10-20 minutes per game
• **Phases**: Auto-timed (30s night, 45s voting)
• **Hosting**: Fully automated (no host needed)

**🎭 ROLE ACTIONS:**
• **🩸 Bloodseeker**: Choose kill target
• **🔮 Oracle**: Choose investigation target  
• **🛡️ Guardian**: Choose protection target
• **🏹 Soulhunter**: Day-kill ability (once)
• **⚖️ Justicar**: Cancel votes (once)
• **🃏 Trickster**: Swap votes (once)

**🆘 TROUBLESHOOTING:**
• **No DM buttons?** Start private chat with bot first
• **Game stuck?** Use `/endgame` to reset
• **Missing players?** Check `/status` for current list

**💡 PRO TIPS:**
• Start private chat with bot before joining
• Pay attention to phase announcements
• Use investigation results strategically
• Vote patterns reveal information

The Shadow Court awaits your mastery! 🌌⚔️
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced join with player management"""
    if update.effective_chat.type == 'private':
        await update.message.reply_text(
            "❌ **Wrong Chat!**\n\nPlease use `/join` in the **group chat** where you want to play!\n\n"
            "💡 This private chat is for receiving your role and action buttons during the game."
        )
        return
        
    user = update.effective_user
    
    if game.game_active:
        alive_count = len(game.get_alive_players())
        await update.message.reply_text(
            f"❌ **Game In Progress!**\n\n"
            f"🎮 Current Phase: **{game.phase.title()}**\n"
            f"👥 Players Alive: **{alive_count}**\n"
            f"📅 Day: **{game.day_number}**\n\n"
            f"⏳ Wait for this game to end, then join the next one!"
        )
        return
        
    if user.id in game.players:
        await update.message.reply_text(f"✅ **{user.first_name}**, you're already in the Shadow Court!")
        return
        
    # Add player with enhanced data
    game.players[user.id] = {
        'name': user.first_name,
        'username': user.username or user.first_name,
        'role': None,
        'alive': True,
        'protected': False,
        'join_time': datetime.now()
    }
    
    game.group_chat_id = update.effective_chat.id
    player_count = len(game.players)
    
    # Enhanced join message
    join_message = f"""
👑 **{user.first_name}** enters the Shadow Court!

**📊 Court Status:**
👥 **Players**: {player_count}/10
🎯 **Status**: {'🎮 Ready to Begin!' if player_count >= 4 else f'⏳ Need {4-player_count} more players'}

**📋 Current Players:**
{chr(10).join([f"• {p['name']}" for p in game.players.values()])}

{'🚀 **Game will auto-start in 5 seconds!**' if player_count >= 4 else '📢 **Invite more players to begin the ritual!**'}
    """
    
    try:
        await update.message.reply_animation(
            animation=PHASE_GIFS['gathering'],
            caption=join_message,
            parse_mode='Markdown'
        )
    except Exception:
        await update.message.reply_text(join_message, parse_mode='Markdown')
    
    # Auto-start with minimum players
    if player_count >= 4 and not game.game_active:
        # Give players a moment to see the message
        await asyncio.sleep(5)
        await start_game(context)

async def players_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all players with enhanced info"""
    if not game.players:
        await update.message.reply_text("👥 **No Players**\n\nType `/join` to enter the Shadow Court!")
        return
    
    player_list = "👥 **SHADOW COURT ROSTER**\n\n"
    
    for i, (pid, pdata) in enumerate(game.players.items(), 1):
        status = "💀 Dead" if not pdata['alive'] else ("🛡️ Protected" if pdata.get('protected') else "⚔️ Alive")
        player_list += f"{i}. **{pdata['name']}** - {status}\n"
    
    player_list += f"\n📊 **Total**: {len(game.players)} players"
    
    if game.game_active:
        alive_count = len(game.get_alive_players())
        player_list += f"\n💓 **Alive**: {alive_count}"
        player_list += f"\n📅 **Day**: {game.day_number}"
        player_list += f"\n🎭 **Phase**: {game.phase.title()}"
    
    await update.message.reply_text(player_list, parse_mode='Markdown')

async def roles_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Quick role reference"""
    roles_text = """
🎭 **QUICK ROLE REFERENCE**

**👑 GOOD TEAM:**
🔮 **Oracle** - Investigate players
🛡️ **Guardian** - Protect from kills  
🌿 **Citizen** - Vote strategically
⚖️ **Justicar** - Cancel votes (once)
👻 **Spiritwalker** - Talk to dead

**💀 EVIL TEAM:**
🩸 **Bloodseeker** - Kill at night
🏹 **Soulhunter** - Day assassination

**🃏 NEUTRAL:**
🃏 **Trickster** - Survive & manipulate

Use `/rules` for complete details!
    """
    
    await update.message.reply_text(roles_text, parse_mode='Markdown')

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced status with full game information"""
    if not game.players:
        status_text = """
🌌 **SHADOW COURT STATUS**

**🎭 Game State:** No active session
**👥 Players:** 0/10  
**📍 Phase:** Waiting for players

**🚀 How to Start:**
1. Type `/join` to enter the court
2. Wait for 3+ other players to join  
3. Game auto-starts when ready!

**💡 Tip:** Invite friends to join faster!
        """
        await update.message.reply_text(status_text, parse_mode='Markdown')
        return
        
    # Enhanced status for active games
    alive_players = game.get_alive_players()
    dead_players = {pid: pdata for pid, pdata in game.players.items() if not pdata['alive']}
    
    # Count teams
    good_alive = len(game.get_players_by_team('good'))
    evil_alive = len(game.get_players_by_team('evil'))
    neutral_alive = len(game.get_players_by_team('neutral'))
    
    status_text = f"""
🌌 **SHADOW COURT STATUS**

**🎭 Game State:** {'🎮 Active Battle' if game.game_active else '⏳ Preparing'}
**📅 Day Number:** {game.day_number}
**🎯 Current Phase:** **{game.phase.title()}**
**👥 Total Players:** {len(game.players)}/10

**⚔️ TEAM BALANCE:**
👑 Good: **{good_alive}** alive
💀 Evil: **{evil_alive}** alive  
🃏 Neutral: **{neutral_alive}** alive

**👥 ALIVE PLAYERS ({len(alive_players)}):**
{chr(10).join([f"• {p['name']}" for p in alive_players.values()])}

**💀 FALLEN HEROES ({len(dead_players)}):**
{chr(10).join([f"• {p['name']} ({ROLES.get(p.get('role', 'unknown'), {}).get('name', 'Unknown Role')})" for p in dead_players.values()]) if dead_players else "None yet"}

**🎯 CURRENT OBJECTIVE:**
{get_phase_description(game.phase)}

{'⚡ Check your DM for action buttons!' if game.game_active and game.phase in ['night', 'trial'] else '📝 Type `/join` to enter the next game!'}
    """
    
    await update.message.reply_text(status_text, parse_mode='Markdown')

def get_phase_description(phase):
    """Get description for current phase"""
    descriptions = {
        'waiting': '👥 Gathering players for the ritual',
        'night': '🌙 Special roles act in the shadows',
        'dawn': '☀️ Revealing the night\'s dark deeds',
        'trial': '⚖️ The court votes for exile',
        'banishment': '🔥 Executing the court\'s judgment'
    }
    return descriptions.get(phase, 'Unknown phase')

async def endgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enhanced endgame with statistics"""
    if not game.game_active:
        await update.message.reply_text("❌ **No Active Game**\n\nThere's no game to end right now!")
        return
    
    # Game statistics
    total_players = len(game.players)
    survivors = len(game.get_alive_players())
    casualties = total_players - survivors
    
    endgame_text = f"""
🏁 **GAME FORCIBLY ENDED**

**📊 FINAL STATISTICS:**
👥 **Total Players:** {total_players}
💓 **Survivors:** {survivors}  
💀 **Casualties:** {casualties}
📅 **Days Survived:** {game.day_number}

*The Shadow Court dissolves into mist...*

🎮 **Ready for another round?** Type `/join`!
    """
    
    game.reset()
    
    try:
        await update.message.reply_animation(
            animation=PHASE_GIFS['banishment'],
            caption=endgame_text,
            parse_mode='Markdown'
        )
    except Exception:
        await update.message.reply_text(endgame_text, parse_mode='Markdown')

async def start_game(context):
    """Enhanced game start with full role assignment"""
    if len(game.players) < 4:
        return
        
    game.game_active = True
    game.phase = "convening"
    game.day_number = 1
    game.phase_start_time = datetime.now()
    
    # Advanced role assignment
    player_ids = list(game.players.keys())
    roles = get_role_distribution(len(player_ids))
    random.shuffle(roles)
    
    # Assign roles with validation
    for i, player_id in enumerate(player_ids):
        game.players[player_id]['role'] = roles[i]
        game.players[player_id]['protected'] = False
        
    # Send detailed role DMs
    for player_id, player_data in game.players.items():
        role_key = player_data['role']
        role_info = ROLES[role_key]
        
        role_message = f"""
🌟 **YOUR SHADOW COURT ROLE**

**🎭 Role:** {role_info['name']}
**📜 Description:** {role_info['description']}
**⚔️ Team:** {role_info['team'].title()}
**🎯 Win Condition:** {role_info['win_condition']}

{'🌙 **Night Actions:** You will receive action buttons during night phases.' if role_info['action'] else '⚖️ **Trial Actions:** You vote during trial phases only.'}

**🔒 CRITICAL:** Keep your role absolutely secret!
**💡 Strategy:** {get_role_strategy(role_key)}

🌌 **Welcome to the Shadow Court, {player_data['name']}!**
        """
        
        try:
            await context.bot.send_message(
                chat_id=player_id,
                text=role_message,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Failed to send role DM to {player_id}: {e}")
    
    # Enhanced game start announcement
    team_counts = {}
    for player_data in game.players.values():
        team = ROLES[player_data['role']]['team']
        team_counts[team] = team_counts.get(team, 0) + 1
    
    start_message = f"""
⚔️ **THE SHADOW COURT CONVENES!**

🔮 **{len(game.players)} souls** have entered the mystical realm
👑 **{team_counts.get('good', 0)} Good** vs **{team_counts.get('evil', 0)} Evil** vs **{team_counts.get('neutral', 0)} Neutral**

🌙 **Night Phase begins in 10 seconds...**
*Special roles will receive their powers via DM*

**📱 Important:** Check your private messages for your secret role!

*The ritual of shadows begins...*
    """
    
    try:
        await context.bot.send_animation(
            chat_id=game.group_chat_id,
            animation=PHASE_GIFS['convening'],
            caption=start_message,
            parse_mode='Markdown'
        )
    except Exception:
        await context.bot.send_message(
            chat_id=game.group_chat_id,
            text=start_message,
            parse_mode='Markdown'
        )
    
    # Start first night phase with delay
    await asyncio.sleep(10)
    await start_night_phase(context)

def get_role_strategy(role_key):
    """Get strategy tips for each role"""
    strategies = {
        'bloodseeker': 'Eliminate threats quietly, blend in during voting',
        'oracle': 'Investigate suspicious players, share info carefully',
        'guardian': 'Protect key players like Oracle, watch voting patterns',
        'citizen': 'Vote strategically, pressure test suspicious behavior',
        'trickster': 'Stay neutral, don\'t appear threatening to either side',
        'soulhunter': 'Save your day-kill for maximum impact',
        'justicar': 'Save vote cancellation for crucial moments',
        'spiritwalker': 'Use dead player knowledge to guide the living'
    }
    return strategies.get(role_key, 'Play strategically and trust your instincts')

async def start_night_phase(context):
    """Enhanced night phase with full role interactions"""
    if not game.game_active:
        return
        
    game.phase = "night" 
    game.night_actions = {}
    game.phase_start_time = datetime.now()
    
    # Clear protections from previous night
    for player_data in game.players.values():
        player_data['protected'] = False
    
    night_message = f"""
🌙 **NIGHT {game.day_number} DESCENDS** (30 seconds)

*The Shadow Court sleeps, but evil never rests...*

🩸 **Bloodseekers** choose their victims
🔮 **Oracle** peers into souls  
🛡️ **Guardian** watches over the innocent
🏹 **Soulhunter** prepares dark magic

**Special roles:** Check your DM for action buttons!
**Others:** Rest and prepare for dawn...

⏰ *Actions resolve automatically in 30 seconds*
    """
    
    try:
        await context.bot.send_animation(
            chat_id=game.group_chat_id,
            animation=PHASE_GIFS['moonlight'],
            caption=night_message,
            parse_mode='Markdown'
        )
    except Exception:
        await context.bot.send_message(
            chat_id=game.group_chat_id,
            text=night_message,
            parse_mode='Markdown'
        )
    
    # Send enhanced night action DMs
    await send_night_action_dms(context)
    
    # Auto-resolve after 30 seconds
    await asyncio.sleep(30)
    await start_dawn_phase(context)

async def send_night_action_dms(context):
    """Enhanced night actions with all role abilities"""
    alive_players = game.get_alive_players()
    
    for player_id, player_data in alive_players.items():
        role_key = player_data['role']
        role_info = ROLES.get(role_key, {})
        
        if not role_info.get('action'):
            continue
            
        # Create enhanced target buttons
        targets = []
        action_type = role_info['action']
        
        for target_id, target_data in alive_players.items():
            # Role-specific targeting rules
            if action_type == 'kill' and target_id == player_id:
                continue  # Can't kill self
            elif action_type in ['protect', 'investigate']:
                # Can target anyone including self for protection
                pass
            
            targets.append(InlineKeyboardButton(
                f"🎯 {target_data['name']}", 
                callback_data=f"night_{action_type}_{target_id}"
            ))
        
        # Add skip option for all roles
        targets.append(InlineKeyboardButton("⏭️ Skip Action", callback_data="night_skip"))
        
        # Arrange buttons in optimal layout
        keyboard = []
        for i in range(0, len(targets), 2):
            row = targets[i:i+2]
            keyboard.append(row)
        
        # Enhanced action descriptions
        action_descriptions = {
            'kill': 'Choose a player to eliminate tonight',
            'investigate': 'Choose a player to learn their team alignment',
            'protect': 'Choose a player to protect from death (including yourself)',
            'dayshoot': 'You have a one-time day kill ability',
            'cancel_votes': 'You can cancel all votes once during any trial',
            'commune': 'Speak with the dead to learn secrets'
        }
        
        action_text = f"""
🌙 **NIGHT ACTION: {role_info['name']}**

**🎯 Your Power:** {role_info['description']}
**⚡ Action:** {action_descriptions.get(action_type, 'Use your special ability')}

⏰ **You have 30 seconds to choose:**
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
    """Enhanced dawn phase with detailed event processing"""
    if not game.game_active:
        return
        
    game.phase = "dawn"
    game.phase_start_time = datetime.now()
    
    # Process all night actions with enhanced logic
    killed_players = []
    protected_players = []
    investigation_results = {}
    
    # Get all actions
    kills = game.night_actions.get('kill', {})
    protections = game.night_actions.get('protect', {})
    investigations = game.night_actions.get('investigate', {})
    
    # Process protections first
    protected_ids = list(protections.values())
    for target_id in protected_ids:
        if target_id in game.players:
            game.players[target_id]['protected'] = True
            protected_players.append(game.players[target_id])
    
    # Process kills with protection checks
    for killer_id, target_id in kills.items():
        if target_id in game.players and game.players[target_id]['alive']:
            if not game.players[target_id].get('protected', False):
                game.players[target_id]['alive'] = False
                killed_players.append(game.players[target_id])
    
    # Process investigations with enhanced results
    for investigator_id, target_id in investigations.items():
        if target_id in game.players:
            target_role = game.players[target_id]['role']
            target_team = ROLES.get(target_role, {}).get('team', 'unknown')
            investigation_results[investigator_id] = {
                'target': game.players[target_id],
                'team': target_team,
                'role_hint': get_investigation_hint(target_role)
            }
    
    # Create dramatic dawn message
    dawn_messages = [f"☀️ **DAWN OF DAY {game.day_number}**\n"]
    dawn_messages.append("*As sunlight pierces the shadow realm...*\n")
    
    if killed_players:
        dawn_messages.append("💀 **THE NIGHT CLAIMS VICTIMS:**")
        for player in killed_players:
            role_name = ROLES.get(player['role'], {}).get('name', 'Unknown')
            dawn_messages.append(f"🗡️ **{player['name']}** has fallen! (Role: {role_name})")
    
    if protected_players and any(p['name'] in [k['name'] for k in killed_players] for p in protected_players):
        dawn_messages.append("\n🛡️ **GUARDIAN'S INTERVENTION:**")
        for player in protected_players:
            if any(kill_target for kill_target in kills.values() if kill_target == list(game.players.keys())[list(game.players.values()).index(player)]):
                dawn_messages.append(f"✨ **{player['name']}** was saved from death!")
    
    if not killed_players and not any(kills.values()):
        dawn_messages.append("🕊️ **A peaceful night passes...**")
        dawn_messages.append("*No blood stains the shadow realm*")
    
    # Add atmospheric flavor
    dawn_messages.append(f"\n⚔️ **{len(game.get_alive_players())} souls remain in the court**")
    
    dawn_message = "\n".join(dawn_messages)
    
    try:
        await context.bot.send_animation(
            chat_id=game.group_chat_id,
            animation=PHASE_GIFS['dawn'],
            caption=dawn_message,
            parse_mode='Markdown'
        )
    except Exception:
        await context.bot.send_message(
            chat_id=game.group_chat_id,
            text=dawn_message,
            parse_mode='Markdown'
        )
    
    # Send enhanced investigation results privately
    for investigator_id, result in investigation_results.items():
        result_text = f"""
🔮 **ORACLE'S DIVINE VISION**

**🎭 Target:** {result['target']['name']}
**⚔️ Team:** {result['team'].title()}
**🔍 Insight:** {result['role_hint']}

{'✅ **This soul serves the light!**' if result['team'] == 'good' else '❌ **Darkness dwells within this one!**' if result['team'] == 'evil' else '🌀 **This soul walks a different path...**'}

*Use this knowledge wisely in the coming trial.*
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
    
    # Brief pause before trial
    await asyncio.sleep(10)
    await start_trial_phase(context)

def get_investigation_hint(role_key):
    """Get subtle hints about roles for Oracle"""
    hints = {
        'bloodseeker': 'Shadows cling to this one...',
        'oracle': 'A kindred spirit of wisdom',
        'guardian': 'Protective aura surrounds them',
        'citizen': 'Simple but pure intentions',
        'trickster': 'Mysterious and unpredictable',
        'soulhunter': 'Death follows in their wake',
        'justicar': 'Bearer of divine justice',
        'spiritwalker': 'One foot in the realm of the dead'
    }
    return hints.get(role_key, 'Their true nature remains hidden')

async def start_trial_phase(context):
    """Enhanced trial phase with advanced voting mechanics"""
    if not game.game_active:
        return
        
    game.phase = "trial"
    game.votes = {}
    game.phase_start_time = datetime.now()
    
    alive_players = game.get_alive_players()
    
    trial_message = f"""
⚖️ **TRIAL OF DAY {game.day_number}** (45 seconds)

*The Shadow Court convenes to render judgment!*

👥 **{len(alive_players)} members** must decide who faces exile
🗳️ **Secret voting** ensures pure judgment
⚖️ **Majority rules** - most votes determines fate
🎲 **Ties broken randomly** by the fates

**🔥 Remember:** 
• Vote wisely - appearances deceive
• Dead cannot return to testify  
• Your vote is completely anonymous
• Skip voting if uncertain

**All living members:** Check your DM to cast judgment!

⏰ *Voting closes automatically in 45 seconds*
    """
    
    try:
        await context.bot.send_animation(
            chat_id=game.group_chat_id,
            animation=PHASE_GIFS['trial'],
            caption=trial_message,
            parse_mode='Markdown'
        )
    except Exception:
        await context.bot.send_message(
            chat_id=game.group_chat_id,
            text=trial_message,
            parse_mode='Markdown'
        )
    
    # Send enhanced voting DMs
    await send_voting_dms(context)
    
    # Auto-resolve after 45 seconds
    await asyncio.sleep(45)
    await start_banishment_phase(context)

async def send_voting_dms(context):
    """Enhanced voting interface with player information"""
    alive_players = game.get_alive_players()
    
    if len(alive_players) <= 1:
        return
    
    for voter_id, voter_data in alive_players.items():
        # Create enhanced voting buttons with player info
        targets = []
        for target_id, target_data in alive_players.items():
            if target_id != voter_id:
                # Add subtle player info to help voting decisions
                targets.append(InlineKeyboardButton(
                    f"🗳️ Exile {target_data['name']}", 
                    callback_data=f"vote_{target_id}"
                ))
        
        # Add skip option
        targets.append(InlineKeyboardButton("⏭️ Skip Vote", callback_data="vote_skip"))
        
        # Arrange buttons optimally
        keyboard = []
        for i in range(0, len(targets), 2):
            row = targets[i:i+2]
            keyboard.append(row)
        
        vote_text = f"""
⚖️ **SECRET TRIAL VOTE**

**🏛️ You are:** {voter_data['name']}
**⚔️ Court Members:** {len(alive_players)} alive
**🎯 Your Mission:** Identify and exile threats

**🗳️ Cast your judgment:**
*Choose wisely - this vote is completely anonymous*

**💡 Voting Strategy:**
• Consider recent behavior patterns
• Trust your investigation results  
• Watch for defensive reactions
• Remember: innocents can act suspicious too

⏰ **Time remaining: 45 seconds**

*The fate of the Shadow Court rests in your hands...*
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
    """Enhanced banishment with dramatic flair and statistics"""
    if not game.game_active:
        return
        
    game.phase = "banishment"
    game.phase_start_time = datetime.now()
    
    # Enhanced vote counting with statistics
    vote_counts = {}
    alive_players = game.get_alive_players()
    
    # Initialize vote counts
    for target_id in alive_players.keys():
        vote_counts[target_id] = 0
    
    skip_votes = 0
    
    # Count all votes
    for voter_id, voted_for in game.votes.items():
        if voted_for == "skip":
            skip_votes += 1
        elif voted_for in vote_counts:
            vote_counts[voted_for] += 1
    
    total_votes = len(game.votes)
    
    # Determine exile result
    if not vote_counts or max(vote_counts.values()) == 0:
        # No exile - all skipped
        banishment_message = f"""
⚖️ **THE COURT SHOWS MERCY**

*Silence fills the shadow realm...*

📊 **Voting Results:**
• **Total Voters:** {total_votes}
• **Skipped Votes:** {skip_votes}
• **Exile Votes:** 0

🕊️ **No soul faces exile this day**
*Perhaps wisdom prevailed, or perhaps fear...*

*The Shadow Court remains unchanged...*
        """
        
    else:
        # Someone gets exiled
        max_votes = max(vote_counts.values())
        candidates = [pid for pid, votes in vote_counts.items() if votes == max_votes]
        exiled_id = random.choice(candidates)
        
        # Update game state
        game.players[exiled_id]['alive'] = False
        exiled_player = game.players[exiled_id]
        role_name = ROLES.get(exiled_player['role'], {}).get('name', 'Unknown')
        role_team = ROLES.get(exiled_player['role'], {}).get('team', 'unknown')
        
        # Create detailed vote breakdown
        vote_breakdown = []
        for pid, votes in sorted(vote_counts.items(), key=lambda x: x[1], reverse=True):
            if votes > 0:
                player_name = game.players[pid]['name']
                vote_breakdown.append(f"• **{player_name}:** {votes} vote{'s' if votes != 1 else ''}")
        
        banishment_message = f"""
🔥 **THE COURT RENDERS JUDGMENT!**

**⚖️ By majority decree:**
**{exiled_player['name']}** is sentenced to exile!

**🎭 REVEALED IDENTITY:**
**Role:** {role_name}
**Team:** {role_team.title()}

📊 **Final Vote Tally:**
{chr(10).join(vote_breakdown)}
• **Skipped:** {skip_votes} vote{'s' if skip_votes != 1 else ''}

{'🎯 **A threat eliminated!**' if role_team == 'evil' else '💔 **An innocent falls!**' if role_team == 'good' else '🌀 **The wildcard is removed!**'}

*The shadows consume another soul...*
        """
    
    try:
        await context.bot.send_animation(
            chat_id=game.group_chat_id,
            animation=PHASE_GIFS['banishment'],
            caption=banishment_message,
            parse_mode='Markdown'
        )
    except Exception:
        await context.bot.send_message(
            chat_id=game.group_chat_id,
            text=banishment_message,
            parse_mode='Markdown'
        )
    
    # Clear votes and increment day
    game.votes.clear()
    game.night_actions.clear()
    
    # Check win conditions
    if await check_win_condition(context):
        return
    
    # Advance to next day
    game.day_number += 1
    
    # Brief pause before next night
    await asyncio.sleep(10)
    await start_night_phase(context)

async def check_win_condition(context):
    """Enhanced win condition checking with dramatic endings"""
    if not game.game_active:
        return True
        
    alive_players = game.get_alive_players()
    
    # Check minimum players
    if len(alive_players) <= 1:
        game.game_active = False
        
        survivor_name = list(alive_players.values())[0]['name'] if alive_players else "None"
        
        ending_message = f"""
🏁 **THE SHADOW COURT FALLS SILENT**

**📊 Final Statistics:**
• **Days Survived:** {game.day_number}
• **Last Standing:** {survivor_name}
• **Total Casualties:** {len(game.players) - len(alive_players)}

*With so few souls remaining, the mystical realm dissolves...*

🎮 **Ready for another ritual?** Type `/join`!
        """
        
        try:
            await context.bot.send_animation(
                chat_id=game.group_chat_id,
                animation=PHASE_GIFS['banishment'],
                caption=ending_message,
                parse_mode='Markdown'
            )
        except Exception:
            await context.bot.send_message(
                chat_id=game.group_chat_id,
                text=ending_message,
                parse_mode='Markdown'
            )
        
        game.reset()
        return True
    
    # Count team members
    good_count = len(game.get_players_by_team('good'))
    evil_count = len(game.get_players_by_team('evil'))
    neutral_count = len(game.get_players_by_team('neutral'))
    
    # Check Good victory
    if evil_count == 0:
        game.game_active = False
        
        victory_message = f"""
👑 **VICTORY FOR THE LIGHT!**

✨ **The Shadow Court is purified!**

**🏆 TRIUMPHANT HEROES:**
{chr(10).join([f"🌟 **{p['name']}** ({ROLES[p['role']]['name']})" for p in alive_players.values() if ROLES[p['role']]['team'] == 'good'])}

**📊 Victory Statistics:**
• **Days to Victory:** {game.day_number}
• **Heroes Surviving:** {good_count}
• **Evil Eliminated:** {len([p for p in game.players.values() if not p['alive'] and ROLES[p['role']]['team'] == 'evil'])}

*Light banishes the darkness forever!*

🎮 **Play again?** Type `/join` for another epic battle!
        """
        
        try:
            await context.bot.send_animation(
                chat_id=game.group_chat_id,
                animation=PHASE_GIFS['victory_good'],
                caption=victory_message,
                parse_mode='Markdown'
            )
        except Exception:
            await context.bot.send_message(
                chat_id=game.group_chat_id,
                text=victory_messa
