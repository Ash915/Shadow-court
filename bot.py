import os
import logging
import random
from datetime import datetime, timedelta
from typing import Dict, List

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Animation
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    CallbackContext
)

# ===== CONFIGURATION =====
BOT_TOKEN = "8253509018:AAFrrp0KSDv8_jk30aw2fK3XnTbp2RSprBg"
HOST_ID = 1234567890  # REPLACE WITH YOUR TELEGRAM ID
PHASE_TIMERS = {
    "moonlight": 30,    # 30 seconds for night actions
    "dawn": 10,         # 10 seconds for dawn reveal
    "trial": 45,        # 45 seconds for voting
    "banishment": 10    # 10 seconds for exile reveal
}
PHASE_GIFS = {
    "gathering": "https://media.giphy.com/media/l0HU7JI1m1eEwz7Kw/giphy.gif",
    "convene": "https://media.giphy.com/media/3o7TKsQ8UQ4l4LhGz6/giphy.gif",
    "moonlight": "https://media.giphy.com/media/3o6ZtnbirCMpFbGQ36/giphy.gif",
    "dawn": "https://media.giphy.com/media/3o6Zt6ML6BklcajjsA/giphy.gif",
    "trial": "https://media.giphy.com/media/l0HU7JI1m1eEwz7Kw/giphy.gif",
    "banishment": "https://media.giphy.com/media/3o7TKr7e5gZeU5tq2c/giphy.gif"
}

# ===== GAME STATE =====
players = {}
game_state = {
    "phase": "idle",
    "host_id": None,
    "group_id": None,
    "votes": {},
    "night_actions": {},
    "job": None
}
ROLES_SCALING = {
    4: ["🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen"],
    5: ["🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen", "🃏Trickster"],
    6: ["🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen", "🃏Trickster", "🌿Citizen"],
    7: ["🩸Bloodseeker", "🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen", "🏹Soulhunter", "🌿Citizen"],
    8: ["🩸Bloodseeker", "🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen", "🏹Soulhunter", "🌿Citizen", "⚔️Traitor"],
    9: ["🩸Bloodseeker", "🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen", "🏹Soulhunter", "🌿Citizen", "⚔️Traitor", "🌿Citizen"],
    10: ["🩸Bloodseeker"]*3 + ["🔮Oracle", "🛡️Guardian", "⚖️Justicar", "👻Spiritwalker", "🌑Corruptor"] + ["🌿Citizen"]*2
}

# ===== LOGGING =====
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== COMMAND HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Initial bot introduction"""
    await update.message.reply_text(
        "👑 Welcome to SHADOW COURT!\n"
        "📜 Use /rules to learn how to play\n"
        "💬 In a group: /join to participate\n"
        "⚔️ Host: /start_game to begin\n"
        "🛑 Host: /close_game to stop"
    )

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explain game rules and commands"""
    await update.message.reply_text(
        "⚔️ *SHADOW COURT RULES*\n\n"
        "1. _Objective_: Find and eliminate the Bloodseekers!\n"
        "2. _Phases_: \n"
        "   🌙 Moonlight - Special roles act secretly\n"
        "   ☀️ Dawn - Night results revealed\n"
        "   ⚖️ Trial - Secret voting for exile\n"
        "   🔥 Banishment - Execution results\n"
        "3. _Automatic Timing_: Phases auto-advance after 30-45 seconds\n\n"
        "🔑 *COMMANDS*\n"
        "• /join - Join waiting list\n"
        "• /start_game - Begin game (host only)\n"
        "• /close_game - Force stop game (host)\n"
        "• /status - Check current game state\n"
        "• /rules - Show this message",
        parse_mode="Markdown"
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Player joins waiting list"""
    if game_state["phase"] != "gathering":
        await update.message.reply_text("❌ No game in signup phase!")
        return
    
    user = update.effective_user
    if user.id in players:
        await update.message.reply_text("⚠️ You've already joined!")
        return
    
    players[user.id] = {"name": user.first_name, "role": None, "alive": True}
    count = len(players)
    
    await context.bot.send_animation(
        chat_id=update.effective_chat.id,
        animation=PHASE_GIFS["gathering"],
        caption=f"👑 {user.first_name} joined! ({count}/10)"
    )

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Host starts the game"""
    if game_state["phase"] != "gathering":
        await update.message.reply_text("❌ Game already started!")
        return
    
    if len(players) < 4:
        await update.message.reply_text("❌ Need at least 4 players!")
        return
    
    # Initialize game
    game_state.update({
        "phase": "convene",
        "host_id": update.effective_user.id,
        "group_id": update.effective_chat.id
    })
    
    # Assign roles
    player_ids = list(players.keys())
    random.shuffle(player_ids)
    roles = ROLES_SCALING.get(len(players), ROLES_SCALING[10])[:len(players)]
    
    for idx, player_id in enumerate(player_ids):
        players[player_id]["role"] = roles[idx]
        await context.bot.send_message(
            chat_id=player_id,
            text=f"🌑 YOUR ROLE: *{roles[idx]}*\n{get_role_description(roles[idx])}",
            parse_mode="Markdown"
        )
    
    # Start game
    await context.bot.send_animation(
        chat_id=game_state["group_id"],
        animation=PHASE_GIFS["convene"],
        caption="⚔️ THE COURT CONVENES! Check DMs for your role. First night starts in 10 seconds..."
    )
    
    # Schedule first night phase
    context.job_queue.run_once(start_night_phase, 10)

async def close_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force stop the game"""
    if update.effective_user.id != game_state.get("host_id", None):
        await update.message.reply_text("🚫 Only host can close the game!")
        return
    
    # Cancel any scheduled jobs
    if game_state.get("job"):
        game_state["job"].schedule_removal()
    
    # Reset game
    players.clear()
    game_state.update({
        "phase": "idle",
        "votes": {},
        "night_actions": {},
        "job": None
    })
    
    await update.message.reply_text("🛑 Game forcefully closed!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show current game status"""
    if game_state["phase"] == "idle":
        await update.message.reply_text("🕸️ No active game")
        return
    
    alive = sum(1 for p in players.values() if p["alive"])
    phase = game_state["phase"].capitalize()
    
    await update.message.reply_text(
        f"⚡ *GAME STATUS*\n"
        f"• Phase: {phase}\n"
        f"• Players: {len(players)}\n"
        f"• Alive: {alive}\n"
        f"• Host: <@{game_state['host_id']}>",
        parse_mode="Markdown"
    )

# ===== PHASE HANDLERS =====
async def start_night_phase(context: CallbackContext):
    """Begin night phase"""
    game_state.update({
        "phase": "moonlight",
        "night_actions": {},
        "job": None
    })
    
    # Send action requests
    for user_id, data in players.items():
        if data["alive"] and data["role"] in ["🩸Bloodseeker", "🛡️Guardian", "🔮Oracle"]:
            await send_action_request(context, user_id, data["role"])
    
    # Send notification
    await context.bot.send_animation(
        chat_id=game_state["group_id"],
        animation=PHASE_GIFS["moonlight"],
        caption=f"🌙 MOONLIGHT PHASE: Special roles act now! ({PHASE_TIMERS['moonlight']}s)"
    )
    
    # Schedule next phase
    game_state["job"] = context.job_queue.run_once(
        dawn_phase, 
        PHASE_TIMERS["moonlight"]
    )

async def dawn_phase(context: CallbackContext):
    """Reveal night results"""
    game_state["phase"] = "dawn"
    message = process_night_actions()
    
    await context.bot.send_animation(
        chat_id=game_state["group_id"],
        animation=PHASE_GIFS["dawn"],
        caption=f"☀️ DAWN BREAKS...\n{message}\nTrial starts in {PHASE_TIMERS['dawn']}s"
    )
    
    # Schedule trial phase
    game_state["job"] = context.job_queue.run_once(
        trial_phase, 
        PHASE_TIMERS["dawn"]
    )

async def trial_phase(context: CallbackContext):
    """Begin voting phase"""
    game_state.update({
        "phase": "trial",
        "votes": {},
        "job": None
    })
    
    # Send voting DM to all alive players
    for user_id in [uid for uid, data in players.items() if data["alive"]]:
        await send_vote_interface(context, user_id)
    
    await context.bot.send_animation(
        chat_id=game_state["group_id"],
        animation=PHASE_GIFS["trial"],
        caption=f"⚖️ TRIAL PHASE: Vote via DM! ({PHASE_TIMERS['trial']}s)"
    )
    
    # Schedule banishment
    game_state["job"] = context.job_queue.run_once(
        banishment_phase, 
        PHASE_TIMERS["trial"]
    )

async def banishment_phase(context: CallbackContext):
    """Reveal voting results"""
    game_state["phase"] = "banishment"
    exiled_id = tally_votes()
    exiled_name = players[exiled_id]["name"]
    exiled_role = players[exiled_id]["role"]
    players[exiled_id]["alive"] = False
    
    # Check game end
    if check_game_end():
        await end_game(context)
        return
    
    # Send results
    await context.bot.send_animation(
        chat_id=game_state["group_id"],
        animation=PHASE_GIFS["banishment"],
        caption=f"🔥 {exiled_name} EXILED! ({exiled_role})\nNext night in {PHASE_TIMERS['banishment']}s"
    )
    
    # Schedule next night
    game_state["job"] = context.job_queue.run_once(
        start_night_phase, 
        PHASE_TIMERS["banishment"]
    )

# ===== GAME FUNCTIONS =====
def get_role_description(role: str) -> str:
    """Get role description"""
    descriptions = {
        "🩸Bloodseeker": "Kill one player each night",
        "🔮Oracle": "Investigate one player each night",
        "🛡️Guardian": "Protect one player each night",
        "🌿Citizen": "Find and eliminate the Bloodseekers",
        "🃏Trickster": "Get yourself executed to win!",
        "🏹Soulhunter": "One-time kill ability",
        "⚔️Traitor": "Appear innocent to Oracles",
        "⚖️Justicar": "Cancel one vote per game",
        "👻Spiritwalker": "Send clues after death",
        "🌑Corruptor": "Convert players to your side"
    }
    return descriptions.get(role, "Fulfill your secret mission")

async def send_action_request(context: CallbackContext, user_id: int, role: str):
    """Send action request to special roles"""
    buttons = []
    alive_players = [uid for uid, data in players.items() if data["alive"] and uid != user_id]
    
    for target_id in alive_players:
        name = players[target_id]["name"]
        buttons.append([InlineKeyboardButton(name, callback_data=f"action_{target_id}")])
    
    await context.bot.send_message(
        chat_id=user_id,
        text=f"🌑 {role} ACTION REQUESTED:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def send_vote_interface(context: CallbackContext, user_id: int):
    """Send voting interface"""
    buttons = []
    alive_players = [uid for uid, data in players.items() if data["alive"] and uid != user_id]
    
    for target_id in alive_players:
        name = players[target_id]["name"]
        buttons.append([InlineKeyboardButton(name, callback_data=f"vote_{target_id}")])
    
    buttons.append([InlineKeyboardButton("Skip Vote", callback_data="vote_skip")])
    
    await context.bot.send_message(
        chat_id=user_id,
        text="⚖️ SECRET VOTE: Who should be exiled?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def process_night_actions() -> str:
    """Process night actions and return message"""
    deaths = []
    protected = []
    
    # Simplified action processing
    for actor_id, target_id in game_state["night_actions"].items():
        role = players[actor_id]["role"]
        
        if role == "🩸Bloodseeker":
            # Check if protected
            is_protected = any(
                t == target_id and players[a]["role"] == "🛡️Guardian"
                for a, t in game_state["night_actions"].items()
            )
            
            if not is_protected:
                players[target_id]["alive"] = False
                deaths.append(players[target_id]["name"])
            else:
                protected.append(players[target_id]["name"])
    
    messages = []
    if deaths:
        messages.append(f"💀 Slain: {', '.join(deaths)}")
    if protected:
        messages.append(f"🛡️ Protected: {', '.join(protected)}")
    
    return "\n".join(messages) if messages else "All survived the night!"

def tally_votes() -> int:
    """Count votes and return exiled player ID"""
    vote_count = {uid: 0 for uid, data in players.items() if data["alive"]}
    
    for voter_id, target in game_state["votes"].items():
        if target != "skip" and target in vote_count:
            vote_count[target] += 1
    
    return max(vote_count, key=vote_count.get)

def check_game_end() -> bool:
    """Check if game should end"""
    bloodseekers = sum(1 for data in players.values() 
                      if "Bloodseeker" in data["role"] and data["alive"])
    others = sum(1 for data in players.values() 
               if "Bloodseeker" not in data["role"] and data["alive"])
    
    return bloodseekers == 0 or bloodseekers >= others

async def end_game(context: CallbackContext):
    """End the game and reveal roles"""
    bloodseekers = sum(1 for data in players.values() 
                      if "Bloodseeker" in data["role"] and data["alive"])
    winner = "Citizens" if bloodseekers == 0 else "Bloodseekers"
    
    result = [f"⚔️ *GAME OVER! {winner} win!*"]
    for user_id, data in players.items():
        status = "💀" if not data["alive"] else "❤️"
        result.append(f"{status} {data['name']}: {data['role']}")
    
    await context.bot.send_message(
        chat_id=game_state["group_id"],
        text="\n".join(result),
        parse_mode="Markdown"
    )
    
    # Reset game
    players.clear()
    game_state.update({
        "phase": "idle",
        "votes": {},
        "night_actions": {},
        "job": None
    })

# ===== CALLBACK HANDLERS =====
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all button presses"""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    
    if data.startswith("action_"):
        # Night action handling
        if game_state["phase"] != "moonlight":
            return
        
        target_id = int(data.split("_")[1])
        game_state["night_actions"][user_id] = target_id
        await query.edit_message_text("✅ Action recorded!")
    
    elif data.startswith("vote_"):
        # Voting handling
        if game_state["phase"] != "trial":
            return
        
        target = data.split("_")[1]
        game_state["votes"][user_id] = target if target != "skip" else "skip"
        await query.edit_message_text("🗳️ Vote recorded!")

# ===== MAIN SETUP =====
def main() -> None:
    """Run the bot"""
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("start_game", start_game))
    app.add_handler(CommandHandler("close_game", close_game))
    app.add_handler(CommandHandler("status", status))
    
    # Callback handler
    app.add_handler(CallbackQueryHandler(handle_callback))
    
    # Start polling
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
