import os
import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Animation
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    CallbackContext
)

# ===== CONFIGURATION =====
BOT_TOKEN = os.getenv("BOT_TOKEN", "8253509018:AAFrrp0KSDv8_jk30aw2fK3XnTbp2RSprBg")
HOST_ID = int(os.getenv("HOST_ID", "1234567890"))  # REPLACE WITH YOUR ID
PHASE_TIMERS = {"moonlight": 30, "dawn": 10, "trial": 45, "banishment": 10}
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
game_state = {"phase": "idle", "host_id": None, "group_id": None, "votes": {}, "night_actions": {}, "job": None}
ROLES_SCALING = {
    4: ["🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen"],
    5: ["🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen", "🃏Trickster"],
    6: ["🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen", "🃏Trickster", "🌿Citizen"],
    7: ["🩸Bloodseeker", "🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen", "🏹Soulhunter", "🌿Citizen"],
    8: ["🩸Bloodseeker", "🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen", "🏹Soulhunter", "🌿Citizen", "⚔️Traitor"],
    9: ["🩸Bloodseeker", "🩸Bloodseeker", "🔮Oracle", "🛡️Guardian", "🌿Citizen", "🏹Soulhunter", "🌿Citizen", "⚔️Traitor", "🌿Citizen"],
    10: ["🩸Bloodseeker"]*3 + ["🔮Oracle", "🛡️Guardian", "⚖️Justicar", "👻Spiritwalker", "🌑Corruptor"] + ["🌿Citizen"]*2
}

# ===== SETUP LOGGING =====
logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ===== COMMAND HANDLERS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👑 Welcome to SHADOW COURT!\n"
        "📜 Use /rules to learn how to play\n"
        "💬 In a group: /join to participate\n"
        "⚔️ Host: /start_game to begin\n"
        "🛑 Host: /close_game to stop"
    )

async def rules(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "⚔️ *SHADOW COURT RULES*\n\n"
        "1. Find and eliminate the Bloodseekers!\n"
        "2. Phases:\n"
        "   🌙 Moonlight: Special roles act\n"
        "   ☀️ Dawn: Night results\n"
        "   ⚖️ Trial: Secret voting\n"
        "   🔥 Banishment: Execution\n"
        "3. Phases auto-advance after 30-45s\n\n"
        "🔑 *COMMANDS*\n"
        "/join - Join game\n"
        "/start_game - Begin (host)\n"
        "/close_game - Stop (host)\n"
        "/status - Game state\n"
        "/rules - This info",
        parse_mode="Markdown"
    )

async def join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if game_state["phase"] != "gathering":
        await update.message.reply_text("❌ No game in signup phase!")
        return
    user = update.effective_user
    if user.id in players:
        await update.message.reply_text("⚠️ Already joined!")
        return
    players[user.id] = {"name": user.first_name, "role": None, "alive": True}
    count = len(players)
    await context.bot.send_animation(
        chat_id=update.effective_chat.id,
        animation=PHASE_GIFS["gathering"],
        caption=f"👑 {user.first_name} joined! ({count}/10)"
    )

async def start_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if game_state["phase"] != "gathering":
        await update.message.reply_text("❌ Game already started!")
        return
    if len(players) < 4:
        await update.message.reply_text("❌ Need 4+ players!")
        return
    game_state.update({
        "phase": "convene",
        "host_id": update.effective_user.id,
        "group_id": update.effective_chat.id
    })
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
    await context.bot.send_animation(
        chat_id=game_state["group_id"],
        animation=PHASE_GIFS["convene"],
        caption="⚔️ COURT CONVENES! Check DMs for role. Night starts in 10s..."
    )
    context.job_queue.run_once(start_night_phase, 10)

async def close_game(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != game_state.get("host_id"):
        await update.message.reply_text("🚫 Host only!")
        return
    if game_state.get("job"):
        game_state["job"].schedule_removal()
    players.clear()
    game_state.update({"phase": "idle", "votes": {}, "night_actions": {}, "job": None})
    await update.message.reply_text("🛑 Game closed!")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if game_state["phase"] == "idle":
        await update.message.reply_text("🕸️ No active game")
        return
    alive = sum(1 for p in players.values() if p["alive"])
    await update.message.reply_text(
        f"⚡ *GAME STATUS*\nPhase: {game_state['phase'].capitalize()}\n"
        f"Players: {len(players)}\nAlive: {alive}\nHost: <@{game_state['host_id']}>",
        parse_mode="Markdown"
    )

# ===== PHASE HANDLERS =====
async def start_night_phase(context: CallbackContext):
    game_state.update({"phase": "moonlight", "night_actions": {}, "job": None})
    for user_id, data in players.items():
        if data["alive"] and data["role"] in ["🩸Bloodseeker", "🛡️Guardian", "🔮Oracle"]:
            await send_action_request(context, user_id, data["role"])
    await context.bot.send_animation(
        chat_id=game_state["group_id"],
        animation=PHASE_GIFS["moonlight"],
        caption=f"🌙 NIGHT PHASE: Act now! ({PHASE_TIMERS['moonlight']}s)"
    )
    game_state["job"] = context.job_queue.run_once(dawn_phase, PHASE_TIMERS["moonlight"])

async def dawn_phase(context: CallbackContext):
    game_state["phase"] = "dawn"
    message = process_night_actions()
    await context.bot.send_animation(
        chat_id=game_state["group_id"],
        animation=PHASE_GIFS["dawn"],
        caption=f"☀️ DAWN: {message}\nVoting in {PHASE_TIMERS['dawn']}s"
    )
    game_state["job"] = context.job_queue.run_once(trial_phase, PHASE_TIMERS["dawn"])

async def trial_phase(context: CallbackContext):
    game_state.update({"phase": "trial", "votes": {}, "job": None})
    for user_id in [uid for uid, data in players.items() if data["alive"]]:
        await send_vote_interface(context, user_id)
    await context.bot.send_animation(
        chat_id=game_state["group_id"],
        animation=PHASE_GIFS["trial"],
        caption=f"⚖️ VOTE PHASE: Check DMs! ({PHASE_TIMERS['trial']}s)"
    )
    game_state["job"] = context.job_queue.run_once(banishment_phase, PHASE_TIMERS["trial"])

async def banishment_phase(context: CallbackContext):
    game_state["phase"] = "banishment"
    exiled_id = tally_votes()
    exiled_name = players[exiled_id]["name"]
    exiled_role = players[exiled_id]["role"]
    players[exiled_id]["alive"] = False
    if check_game_end():
        await end_game(context)
        return
    await context.bot.send_animation(
        chat_id=game_state["group_id"],
        animation=PHASE_GIFS["banishment"],
        caption=f"🔥 {exiled_name} EXILED! ({exiled_role})\nNext night in {PHASE_TIMERS['banishment']}s"
    )
    game_state["job"] = context.job_queue.run_once(start_night_phase, PHASE_TIMERS["banishment"])

# ===== HELPER FUNCTIONS =====
def get_role_description(role: str) -> str:
    return {
        "🩸Bloodseeker": "Kill one player each night",
        "🔮Oracle": "Investigate one player each night",
        "🛡️Guardian": "Protect one player each night",
        "🌿Citizen": "Eliminate Bloodseekers",
        "🃏Trickster": "Get yourself executed to win!",
        "🏹Soulhunter": "One-time kill ability",
        "⚔️Traitor": "Appear innocent to Oracles",
        "⚖️Justicar": "Cancel one vote per game",
        "👻Spiritwalker": "Send clues after death",
        "🌑Corruptor": "Convert players to your side"
    }.get(role, "Fulfill your mission")

async def send_action_request(context: CallbackContext, user_id: int, role: str):
    buttons = []
    for target_id in [uid for uid, data in players.items() if data["alive"] and uid != user_id]:
        buttons.append([InlineKeyboardButton(players[target_id]["name"], callback_data=f"action_{target_id}")])
    await context.bot.send_message(
        chat_id=user_id,
        text=f"🌑 {role} ACTION:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def send_vote_interface(context: CallbackContext, user_id: int):
    buttons = []
    for target_id in [uid for uid, data in players.items() if data["alive"] and uid != user_id]:
        buttons.append([InlineKeyboardButton(players[target_id]["name"], callback_data=f"vote_{target_id}")])
    buttons.append([InlineKeyboardButton("Skip Vote", callback_data="vote_skip")])
    await context.bot.send_message(
        chat_id=user_id,
        text="⚖️ SECRET VOTE: Who to exile?",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

def process_night_actions() -> str:
    deaths = []
    protected = []
    for actor_id, target_id in game_state["night_actions"].items():
        if players[actor_id]["role"] == "🩸Bloodseeker":
            if not any(t == target_id and players[a]["role"] == "🛡️Guardian" for a, t in game_state["night_actions"].items()):
                players[target_id]["alive"] = False
                deaths.append(players[target_id]["name"])
            else:
                protected.append(players[target_id]["name"])
    return "\n".join([
        f"💀 Slain: {', '.join(deaths)}" if deaths else "",
        f"🛡️ Protected: {', '.join(protected)}" if protected else "All survived!"
    ]).strip()

def tally_votes() -> int:
    vote_count = {uid: 0 for uid, data in players.items() if data["alive"]}
    for target in game_state["votes"].values():
        if target != "skip" and target in vote_count:
            vote_count[target] += 1
    return max(vote_count, key=vote_count.get)

def check_game_end() -> bool:
    bloodseekers = sum(1 for data in players.values() if "Bloodseeker" in data["role"] and data["alive"])
    others = sum(1 for data in players.values() if "Bloodseeker" not in data["role"] and data["alive"])
    return bloodseekers == 0 or bloodseekers >= others

async def end_game(context: CallbackContext):
    bloodseekers = sum(1 for data in players.values() if "Bloodseeker" in data["role"] and data["alive"])
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
    players.clear()
    game_state.update({"phase": "idle", "votes": {}, "night_actions": {}, "job": None})

# ===== CALLBACK HANDLER =====
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data
    
    if data.startswith("action_") and game_state["phase"] == "moonlight":
        target_id = int(data.split("_")[1])
        game_state["night_actions"][user_id] = target_id
        await query.edit_message_text("✅ Action recorded!")
    
    elif data.startswith("vote_") and game_state["phase"] == "trial":
        target = data.split("_")[1]
        game_state["votes"][user_id] = target if target != "skip" else "skip"
        await query.edit_message_text("🗳️ Vote recorded!")

# ===== MAIN =====
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("rules", rules))
    app.add_handler(CommandHandler("join", join))
    app.add_handler(CommandHandler("start_game", start_game))
    app.add_handler(CommandHandler("close_game", close_game))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
