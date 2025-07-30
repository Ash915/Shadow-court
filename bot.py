import os
import random
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv('BOT_TOKEN', '8253509018:AAFrrp0KSDv8_jk30aw2fK3XnTbp2RSprBg')

# Simple game state
players = {}
game_active = False
phase = "waiting"
votes = {}
night_actions = {}
group_chat_id = None

ROLES = {
    'bloodseeker': {'name': '🩸 Bloodseeker', 'team': 'evil'},
    'oracle': {'name': '🔮 Oracle', 'team': 'good'},
    'guardian': {'name': '🛡️ Guardian', 'team': 'good'},
    'citizen': {'name': '🌿 Citizen', 'team': 'good'}
}

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🌌 **SHADOW COURT GAME**\n\n"
        "Commands:\n"
        "• /join - Join game\n"
        "• /rules - Game rules\n"
        "• /status - Game status\n"
        "• /endgame - End game\n\n"
        "Need 4+ players to start!",
        parse_mode='Markdown'
    )

async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📜 **RULES**\n\n"
        "**Roles:**\n"
        "🩸 Bloodseeker - Kill at night (EVIL)\n"
        "🔮 Oracle - Investigate players (GOOD)\n"
        "🛡️ Guardian - Protect players (GOOD)\n"
        "🌿 Citizen - Vote to find evil (GOOD)\n\n"
        "**Goal:**\n"
        "Good wins: Eliminate all evil\n"
        "Evil wins: Equal/outnumber good",
        parse_mode='Markdown'
    )

async def join_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global players, game_active, group_chat_id
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ Use /join in group chat!")
        return
        
    user = update.effective_user
    
    if game_active:
        await update.message.reply_text("❌ Game in progress!")
        return
        
    if user.id in players:
        await update.message.reply_text(f"✅ {user.first_name} already joined!")
        return
        
    players[user.id] = {
        'name': user.first_name,
        'role': None,
        'alive': True
    }
    
    group_chat_id = update.effective_chat.id
    count = len(players)
    
    await update.message.reply_text(f"👑 {user.first_name} joined! ({count}/10)")
    
    if count >= 4:
        await start_game(context)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not players:
        await update.message.reply_text("No active game. Type /join!")
        return
        
    alive = [p for p in players.values() if p['alive']]
    
    status = f"**Status:** {'Active' if game_active else 'Waiting'}\n"
    status += f"**Players:** {len(players)}\n"
    status += f"**Alive:** {len(alive)}\n\n"
    
    for p in alive:
        status += f"• {p['name']}\n"
    
    await update.message.reply_text(status, parse_mode='Markdown')

async def endgame_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global players, game_active, phase, votes, night_actions
    
    players = {}
    game_active = False
    phase = "waiting"
    votes = {}
    night_actions = {}
    
    await update.message.reply_text("🏁 Game ended! Type /join for new game.")

async def start_game(context):
    global game_active, phase
    
    if len(players) < 4:
        return
        
    game_active = True
    phase = "night"
    
    # Assign roles
    player_ids = list(players.keys())
    roles = ['bloodseeker', 'oracle', 'guardian'] + ['citizen'] * (len(player_ids) - 3)
    random.shuffle(roles)
    
    for i, pid in enumerate(player_ids):
        players[pid]['role'] = roles[i]
        
    # Send roles via DM
    for pid, player in players.items():
        role_info = ROLES[player['role']]
        try:
            await context.bot.send_message(
                pid, 
                f"🌟 Your role: **{role_info['name']}**\nTeam: {role_info['team']}", 
                parse_mode='Markdown'
            )
        except:
            pass
    
    await context.bot.send_message(
        group_chat_id,
        "⚔️ **Game Started!** Roles sent via DM.\n🌙 Night phase - special roles act!"
    )
    
    await send_night_actions(context)

async def send_night_actions(context):
    alive_players = {pid: p for pid, p in players.items() if p['alive']}
    
    for pid, player in alive_players.items():
        if player['role'] == 'bloodseeker':
            # Send kill options
            targets = []
            for tid, target in alive_players.items():
                if tid != pid:
                    targets.append(InlineKeyboardButton(
                        f"Kill {target['name']}", 
                        callback_data=f"kill_{tid}"
                    ))
            
            if targets:
                keyboard = InlineKeyboardMarkup([targets])
                try:
                    await context.bot.send_message(
                        pid,
                        "🩸 Choose target to kill:",
                        reply_markup=keyboard
                    )
                except:
                    pass
        
        elif player['role'] == 'oracle':
            # Send investigate options
            targets = []
            for tid, target in alive_players.items():
                if tid != pid:
                    targets.append(InlineKeyboardButton(
                        f"Investigate {target['name']}", 
                        callback_data=f"investigate_{tid}"
                    ))
            
            if targets:
                keyboard = InlineKeyboardMarkup([targets])
                try:
                    await context.bot.send_message(
                        pid,
                        "🔮 Choose target to investigate:",
                        reply_markup=keyboard
                    )
                except:
                    pass
        
        elif player['role'] == 'guardian':
            # Send protect options
            targets = []
            for tid, target in alive_players.items():
                targets.append(InlineKeyboardButton(
                    f"Protect {target['name']}", 
                    callback_data=f"protect_{tid}"
                ))
            
            if targets:
                keyboard = InlineKeyboardMarkup([targets])
                try:
                    await context.bot.send_message(
                        pid,
                        "🛡️ Choose target to protect:",
                        reply_markup=keyboard
                    )
                except:
                    pass

async def process_night(context):
    global phase
    
    # Process kills and protections
    killed = []
    protected = []
    
    kills = [target for action, target in night_actions.items() if action.startswith('kill_')]
    protects = [target for action, target in night_actions.items() if action.startswith('protect_')]
    
    for target_id in kills:
        if target_id not in protects and target_id in players:
            players[target_id]['alive'] = False
            killed.append(players[target_id]['name'])
    
    # Send investigation results
    for action, target_id in night_actions.items():
        if action.startswith('investigate_') and target_id in players:
            investigator_id = None
            for pid, player in players.items():
                if player['role'] == 'oracle' and player['alive']:
                    investigator_id = pid
                    break
            
            if investigator_id:
                target_team = ROLES[players[target_id]['role']]['team']
                try:
                    await context.bot.send_message(
                        investigator_id,
                        f"🔮 {players[target_id]['name']} is {target_team}!"
                    )
                except:
                    pass
    
    # Dawn announcement
    if killed:
        msg = f"☀️ **Dawn breaks...**\n💀 {', '.join(killed)} died!"
    else:
        msg = "☀️ **Dawn breaks...**\n🕊️ No one died."
    
    await context.bot.send_message(group_chat_id, msg, parse_mode='Markdown')
    
    # Check win condition
    if await check_win(context):
        return
    
    # Start voting
    phase = "voting"
    await send_votes(context)

async def send_votes(context):
    alive_players = {pid: p for pid, p in players.items() if p['alive']}
    
    for pid, player in alive_players.items():
        targets = []
        for tid, target in alive_players.items():
            if tid != pid:
                targets.append(InlineKeyboardButton(
                    f"Vote {target['name']}", 
                    callback_data=f"vote_{tid}"
                ))
        
        targets.append(InlineKeyboardButton("Skip", callback_data="vote_skip"))
        
        if targets:
            keyboard = InlineKeyboardMarkup([targets])
            try:
                await context.bot.send_message(
                    pid,
                    "⚖️ Vote to exile:",
                    reply_markup=keyboard
                )
            except:
                pass

async def process_votes(context):
    global phase
    
    vote_counts = {}
    alive_players = {pid: p for pid, p in players.items() if p['alive']}
    
    for target_id in alive_players.keys():
        vote_counts[target_id] = 0
    
    for vote in votes.values():
        if vote != "skip" and vote in vote_counts:
            vote_counts[vote] += 1
    
    if vote_counts and max(vote_counts.values()) > 0:
        max_votes = max(vote_counts.values())
        candidates = [pid for pid, count in vote_counts.items() if count == max_votes]
        exiled_id = random.choice(candidates)
        
        players[exiled_id]['alive'] = False
        exiled_name = players[exiled_id]['name']
        exiled_role = ROLES[players[exiled_id]['role']]['name']
        
        await context.bot.send_message(
            group_chat_id,
            f"🔥 **{exiled_name}** exiled! ({exiled_role})",
            parse_mode='Markdown'
        )
    else:
        await context.bot.send_message(group_chat_id, "⚖️ No one exiled.")
    
    # Clear votes
    votes.clear()
    night_actions.clear()
    
    if await check_win(context):
        return
    
    # Next night
    phase = "night"
    await context.bot.send_message(group_chat_id, "🌙 Night falls...")
    await send_night_actions(context)

async def check_win(context):
    global game_active, players
    
    alive = {pid: p for pid, p in players.items() if p['alive']}
    
    if len(alive) <= 1:
        await context.bot.send_message(group_chat_id, "🏁 Game Over! Too few players.")
        await endgame_command(None, context)
        return True
    
    good_count = sum(1 for p in alive.values() if ROLES[p['role']]['team'] == 'good')
    evil_count = sum(1 for p in alive.values() if ROLES[p['role']]['team'] == 'evil')
    
    if evil_count == 0:
        await context.bot.send_message(group_chat_id, "👑 **Good team wins!**", parse_mode='Markdown')
        await endgame_command(None, context)
        return True
    elif evil_count >= good_count:
        await context.bot.send_message(group_chat_id, "💀 **Evil team wins!**", parse_mode='Markdown')
        await endgame_command(None, context)
        return True
    
    return False

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if user_id not in players or not players[user_id]['alive']:
        await query.edit_message_text("❌ Cannot perform action")
        return
    
    if data.startswith(('kill_', 'investigate_', 'protect_')):
        night_actions[data] = int(data.split('_')[1])
        action_type = data.split('_')[0]
        target_name = players[int(data.split('_')[1])]['name']
        
        await query.edit_message_text(f"✅ {action_type.title()} {target_name}")
        
        # Auto-process night after actions
        if len(night_actions) >= 2:  # Assuming bloodseeker + one other
            await process_night(context)
    
    elif data.startswith('vote_'):
        if data == 'vote_skip':
            votes[user_id] = 'skip'
            await query.edit_message_text("⏭️ Vote skipped")
        else:
            target_id = int(data.split('_')[1])
            votes[user_id] = target_id
            target_name = players[target_id]['name']
            await query.edit_message_text(f"🗳️ Voted {target_name}")
        
        # Auto-process votes when enough received
        alive_count = sum(1 for p in players.values() if p['alive'])
        if len(votes) >= alive_count:
            await process_votes(context)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("rules", rules_command))
    app.add_handler(CommandHandler("join", join_command))
    app.add_handler(CommandHandler("status", status_command))
    app.add_handler(CommandHandler("endgame", endgame_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    
    print("Bot starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
