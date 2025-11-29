# game_master.py
import logging
import json
import random
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    WorkerOptions,
    cli,
    metrics,
    tokenize,
    function_tool,
    RunContext
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("game-master")
logging.basicConfig(level=logging.INFO)

load_dotenv(".env.local")

# Create data directory for storing game state
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

GAME_STATE_FILE = DATA_DIR / "game_state.json"
GAME_HISTORY_FILE = DATA_DIR / "game_history.json"

# Game state tracking (unchanged)
game_state = {
    "player": {
        "name": "Adventurer",
        "health": 100,
        "inventory": [],
        "current_location": "The Dark Forest Entrance",
        "quest_status": "active"
    },
    "world": {
        "locations_visited": ["The Dark Forest Entrance"],
        "npcs_met": [],
        "key_events": [],
        "discovered_items": []
    },
    "story_progress": {
        "turn_count": 0,
        "major_decisions": []
    }
}


def save_game_state():
    """Save current game state to file"""
    logger.info("💾 Saving game state...")
    with open(GAME_STATE_FILE, "w") as f:
        json.dump(game_state, f, indent=2)
    logger.info("✓ Game state saved")


def load_game_state():
    """Load game state from file if it exists"""
    global game_state
    if GAME_STATE_FILE.exists():
        logger.info("📂 Loading existing game state...")
        with open(GAME_STATE_FILE, "r") as f:
            game_state = json.load(f)
        logger.info("✓ Game state loaded")
    else:
        logger.info("🆕 Starting new game")


def reset_game_state():
    """Reset game to initial state"""
    global game_state
    game_state = {
        "player": {
            "name": "Adventurer",
            "health": 100,
            "inventory": [],
            "current_location": "The Dark Forest Entrance",
            "quest_status": "active"
        },
        "world": {
            "locations_visited": ["The Dark Forest Entrance"],
            "npcs_met": [],
            "key_events": [],
            "discovered_items": []
        },
        "story_progress": {
            "turn_count": 0,
            "major_decisions": []
        }
    }
    save_game_state()
    logger.info("🔄 Game state reset")


def log_event(event_description: str):
    """Log a key event in the game"""
    game_state["world"]["key_events"].append({
        "turn": game_state["story_progress"]["turn_count"],
        "event": event_description,
        "timestamp": datetime.now().isoformat()
    })
    logger.info(f"📝 Event logged: {event_description}")


def make_agent_payload(text: str):
    """Create the JSON payload the UI expects for agent messages."""
    payload = {
        "type": "transcript",
        "role": "agent",
        "text": text,
        "meta": {
            "health": game_state["player"]["health"],
            "location": game_state["player"]["current_location"],
            "turn": game_state["story_progress"]["turn_count"],
            "inventory": [i["name"] if isinstance(i, dict) else i for i in game_state["player"]["inventory"]]
        }
    }
    return payload


async def send_room_data(room, payload: dict):
    """
    Send a JSON data packet to the LiveKit room so the frontend receives it via dataReceived.
    NOTE: depending on your LiveKit binding the actual method may differ. Adjust if needed.
    """
    try:
        # prefer binary bytes payload
        blob = json.dumps(payload).encode("utf-8")
        # The livekit room object in some SDKs exposes send_data or broadcast_data.
        # Try commonly used names; if none exist log the payload so developer can adapt.
        if hasattr(room, "send_data"):
            await room.send_data(blob)  # may be synchronous in some bindings
        elif hasattr(room, "broadcast_data"):
            await room.broadcast_data(blob)
        elif hasattr(room, "publish_data"):
            await room.publish_data(blob)
        else:
            # fallback: just log (UI won't receive it automatically)
            logger.warning("Room object has no recognized send_data API. Logged payload instead.")
            logger.info("DATA PAYLOAD: %s", json.dumps(payload))
    except Exception as e:
        logger.exception("Failed to send data to room: %s", e)


class GameMaster(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are an engaging and dramatic Game Master running a fantasy adventure in the realm of Eldergrove, a mystical land filled with ancient forests, forgotten ruins, and magical creatures.

🎭 YOUR ROLE AS GAME MASTER:
You are the narrator and world-builder. You describe vivid scenes, control NPCs, and respond to the player's actions with consequences and new developments.

🌍 THE SETTING - ELDERGROVE:
- A dark, enchanted forest where ancient magic still lingers
- Mysterious ruins of a lost civilization
- Creatures both friendly and hostile roam the woods
- The player seeks the legendary Crystal of Lumina, said to be hidden deep within the forest

🎯 STORYTELLING STYLE:
- Be dramatic and atmospheric in your descriptions
- Use sensory details (sights, sounds, smells)
- Create tension and excitement
- Keep responses concise but engaging (2-4 sentences per response)
- ALWAYS end each response with a clear question: "What do you do?" or a similar prompt for action

📜 GAME MECHANICS:
- The player has health (starts at 100)
- They can find items and add them to inventory
- They can meet NPCs and remember past interactions
- Track their journey through different locations
- Make decisions have consequences

🎲 YOUR DUTIES:
1. Describe scenes vividly and concisely
2. Present choices and consequences
3. Control NPC dialogue and behavior
4. Update game state when significant events occur
5. Remember and reference past events
6. Build toward finding the Crystal of Lumina

⚠️ IMPORTANT RULES:
- Keep each response SHORT (2-4 sentences max)
- ALWAYS ask "What do you do?" at the end
- Reference past events to maintain continuity
- Make the player feel their choices matter
- Balance danger with hope for success
- Use the function tools to track game state changes
- Call advance_turn() after each player action to update the turn counter

🎪 TONE:
Dramatic, mysterious, and slightly ominous, but with moments of wonder and hope. Think classic D&D adventure with a touch of dark fantasy.

Remember: You're not just telling a story, you're reacting to the player's choices and building the world around their actions!""",
        )

    # Helper to broadcast a short agent message to the room (so UI sees it)
    async def _broadcast_agent_text(self, context: RunContext, text: str):
        try:
            payload = make_agent_payload(text)
            # RunContext should have a .room reference in this environment
            room = getattr(context, "room", None)
            if room:
                await send_room_data(room, payload)
            else:
                logger.debug("No room on RunContext; cannot broadcast agent data.")
        except Exception:
            logger.exception("Error broadcasting agent text.")

    @function_tool
    async def update_player_health(self, context: RunContext, health_change: int, reason: str):
        """Update player's health when they take damage or heal."""
        logger.info(f"🔧 TOOL: update_player_health(change={health_change}, reason='{reason}')")

        old_health = game_state["player"]["health"]
        game_state["player"]["health"] = max(0, min(100, old_health + health_change))
        new_health = game_state["player"]["health"]

        log_event(f"Player health changed from {old_health} to {new_health}: {reason}")
        save_game_state()

        if health_change < 0:
            text = f"You take {abs(health_change)} damage from {reason}! Health: {new_health}/100. What do you do?"
        else:
            text = f"You heal {health_change} health from {reason}! Health: {new_health}/100. What do you do?"

        # broadcast to UI
        await self._broadcast_agent_text(context, text)
        return text

    @function_tool
    async def add_to_inventory(self, context: RunContext, item_name: str, item_description: str):
        """Add an item to player's inventory."""
        logger.info(f"🔧 TOOL: add_to_inventory(item='{item_name}')")

        item = {
            "name": item_name,
            "description": item_description,
            "acquired_at_turn": game_state["story_progress"]["turn_count"]
        }

        game_state["player"]["inventory"].append(item)
        game_state["world"]["discovered_items"].append(item_name)

        log_event(f"Player acquired: {item_name}")
        save_game_state()

        text = f"Added {item_name} to inventory! You now have {len(game_state['player']['inventory'])} items. What do you do?"
        await self._broadcast_agent_text(context, text)
        return text

    @function_tool
    async def remove_from_inventory(self, context: RunContext, item_name: str):
        """Remove an item from player's inventory."""
        logger.info(f"🔧 TOOL: remove_from_inventory(item='{item_name}')")

        inventory = game_state["player"]["inventory"]
        item = next((i for i in inventory if i["name"].lower() == item_name.lower()), None)

        if item:
            inventory.remove(item)
            log_event(f"Player used/lost: {item_name}")
            save_game_state()
            text = f"Removed {item_name} from inventory. What do you do?"
            await self._broadcast_agent_text(context, text)
            return text
        else:
            text = f"Item {item_name} not found in inventory. What do you do?"
            await self._broadcast_agent_text(context, text)
            return text

    @function_tool
    async def change_location(self, context: RunContext, new_location: str, location_description: str):
        """Change player's current location."""
        logger.info(f"🔧 TOOL: change_location(location='{new_location}')")

        old_location = game_state["player"]["current_location"]
        game_state["player"]["current_location"] = new_location

        if new_location not in game_state["world"]["locations_visited"]:
            game_state["world"]["locations_visited"].append(new_location)

        log_event(f"Player moved from {old_location} to {new_location}")
        save_game_state()

        text = f"You've moved from {old_location} to {new_location}. {location_description} What do you do?"
        await self._broadcast_agent_text(context, text)
        return text

    @function_tool
    async def meet_npc(self, context: RunContext, npc_name: str, npc_description: str, disposition: str):
        """Record meeting a new NPC."""
        logger.info(f"🔧 TOOL: meet_npc(npc='{npc_name}', disposition='{disposition}')")

        npc = {
            "name": npc_name,
            "description": npc_description,
            "disposition": disposition,
            "met_at_location": game_state["player"]["current_location"],
            "met_at_turn": game_state["story_progress"]["turn_count"]
        }

        game_state["world"]["npcs_met"].append(npc)
        log_event(f"Player met {npc_name} ({disposition})")
        save_game_state()

        text = f"You've encountered {npc_name}. They seem {disposition}. What do you do?"
        await self._broadcast_agent_text(context, text)
        return text

    @function_tool
    async def roll_dice(self, context: RunContext, dice_type: str, reason: str):
        """Roll dice for a skill check or random event."""
        logger.info(f"🔧 TOOL: roll_dice(dice='{dice_type}', reason='{reason}')")

        max_value = int(dice_type.lower().replace('d', ''))
        roll_result = random.randint(1, max_value)

        log_event(f"Dice roll: {dice_type} = {roll_result} for {reason}")

        if dice_type.lower() == "d20":
            if roll_result >= 15:
                outcome = "CRITICAL SUCCESS"
            elif roll_result >= 10:
                outcome = "Success"
            elif roll_result >= 5:
                outcome = "Partial Success"
            else:
                outcome = "Failure"
        else:
            outcome = "Roll complete"

        text = f"🎲 Rolling {dice_type} for {reason}... Result: {roll_result} ({outcome}). What do you do?"
        await self._broadcast_agent_text(context, text)
        return text

    @function_tool
    async def check_inventory(self, context: RunContext):
        """Show player's current inventory."""
        logger.info(f"🔧 TOOL: check_inventory()")

        inventory = game_state["player"]["inventory"]

        if not inventory:
            text = "Your inventory is empty. You carry nothing but your wits and courage. What do you do?"
            await self._broadcast_agent_text(context, text)
            return text

        items_list = "\n".join([f"- {item['name']}: {item['description']}" for item in inventory])
        text = f"📦 Your inventory ({len(inventory)} items):\n{items_list}\nWhat do you do?"
        await self._broadcast_agent_text(context, text)
        return text

    @function_tool
    async def check_status(self, context: RunContext):
        """Show player's current status and game progress."""
        logger.info(f"🔧 TOOL: check_status()")

        player = game_state["player"]
        world = game_state["world"]
        progress = game_state["story_progress"]

        status = f"""
📊 ADVENTURER STATUS:
━━━━━━━━━━━━━━━━━━━━
🏃 Name: {player['name']}
❤️  Health: {player['health']}/100
📍 Location: {player['current_location']}
🎯 Quest: {player['quest_status']}
🎒 Inventory: {len(player['inventory'])} items
🗺️  Locations Visited: {len(world['locations_visited'])}
👥 NPCs Met: {len(world['npcs_met'])}
📖 Turn: {progress['turn_count']}
"""
        text = status.strip() + "\nWhat do you do?"
        await self._broadcast_agent_text(context, text)
        return text

    @function_tool
    async def record_decision(self, context: RunContext, decision_description: str, impact: str):
        """Record a major player decision."""
        logger.info(f"🔧 TOOL: record_decision(decision='{decision_description}')")

        decision = {
            "turn": game_state["story_progress"]["turn_count"],
            "decision": decision_description,
            "impact": impact,
            "location": game_state["player"]["current_location"]
        }

        game_state["story_progress"]["major_decisions"].append(decision)
        log_event(f"Major decision: {decision_description}")
        save_game_state()

        text = f"Decision recorded: {decision_description}. {impact} What do you do?"
        await self._broadcast_agent_text(context, text)
        return text

    @function_tool
    async def advance_turn(self, context: RunContext):
        """Advance the turn counter. Call this after each player action."""
        logger.info(f"🔧 TOOL: advance_turn()")

        game_state["story_progress"]["turn_count"] += 1
        save_game_state()

        turn_num = game_state["story_progress"]["turn_count"]
        logger.info(f"⏩ Turn advanced to {turn_num}")

        text = f"Turn {turn_num}. What do you do?"
        await self._broadcast_agent_text(context, text)
        return text

    @function_tool
    async def restart_game(self, context: RunContext):
        """Restart the game from the beginning."""
        logger.info(f"🔧 TOOL: restart_game()")

        reset_game_state()

        text = "🔄 Game restarted! You stand once again at the entrance to the Dark Forest, ready for a new adventure. What do you do?"
        # broadcast to UI
        await self._broadcast_agent_text(context, text)
        return text


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
    # Load existing game state if available
    load_game_state()

    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice="en-US-matthew",
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")

    ctx.add_shutdown_callback(log_usage)

    # Start session with our GameMaster agent
    await session.start(
        agent=GameMaster(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()

    # Immediately send a short opening scene so the frontend shows the GM message right away
    try:
        opening = (
            "You stand at the mossy threshold of the Dark Forest. Mist curls between ancient trunks and "
            "a faint blue glow shimmers beneath the roots — the first whisper of the Crystal's power. "
            "The path ahead splits: one route descends toward a ruined watchtower, another winds into a shadowed hollow. "
            "What do you do?"
        )
        # increase turn to 1 for the opening "turn"
        game_state["story_progress"]["turn_count"] += 1
        save_game_state()
        payload = make_agent_payload(opening)
        # If ctx.room supports async send, try to send bytes.
        await send_room_data(ctx.room, payload)
    except Exception as e:
        logger.exception("Failed to send initial opening message: %s", e)

    logger.info("D&D Voice Game Master is ready!")
    logger.info(f"Current location: {game_state['player']['current_location']}")
    logger.info(f"Player health: {game_state['player']['health']}/100")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
