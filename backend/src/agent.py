import logging
import json
from typing import Annotated
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

logger = logging.getLogger("agent")

load_dotenv(".env.local")

# Improv scenarios pool
IMPROV_SCENARIOS = [
    "You are a time-travelling tour guide explaining modern smartphones to someone from the 1800s.",
    "You are a restaurant waiter who must calmly tell a customer that their order has escaped the kitchen.",
    "You are a customer trying to return an obviously cursed object to a very skeptical shop owner.",
    "You are a barista who has to tell a customer that their latte is actually a portal to another dimension.",
    "You are a museum security guard who just caught someone trying to steal a painting, but the painting keeps talking to you.",
    "You are a tech support agent helping an alien figure out how to use Earth's internet.",
    "You are a dog trainer whose client's pet is clearly just a person in a dog costume, but they won't admit it.",
    "You are a therapist counseling a superhero who is burned out from saving the world too many times.",
    "You are a real estate agent trying to sell a house that is clearly haunted, but you keep denying it.",
    "You are a chef on a cooking show, but all your ingredients keep mysteriously disappearing mid-recipe."
]

# Game state
class ImprovGameState:
    def __init__(self):
        self.player_name = None
        self.current_round = 0
        self.max_rounds = 3
        self.rounds = []  # {"scenario": str, "host_reaction": str, "player_performance": str}
        self.phase = "intro"  # "intro" | "scenario" | "awaiting_improv" | "reacting" | "done"
        self.current_scenario = None
        self.game_started = False

    def to_dict(self):
        return {
            "player_name": self.player_name,
            "current_round": self.current_round,
            "max_rounds": self.max_rounds,
            "phase": self.phase,
            "rounds_completed": len(self.rounds),
            "rounds": self.rounds
        }
    
    def save_to_file(self):
        """Save game state to JSON file"""
        try:
            with open(f'improv_session_{self.player_name or "unknown"}.json', 'w') as f:
                json.dump(self.to_dict(), f, indent=2)
            logger.info(f"Game state saved for {self.player_name}")
        except Exception as e:
            logger.error(f"Failed to save game state: {e}")


class ImprovHostAssistant(Agent):
    def __init__(self, game_state: ImprovGameState) -> None:
        self.game_state = game_state
        
        instructions = """You are the charismatic and witty host of "Improv Battle," a high-energy TV improv game show. 

YOUR PERSONALITY:
- Energetic, entertaining, and quick-witted
- You give HONEST, VARIED reactions - not always positive
- Sometimes you're amused, sometimes unimpressed, sometimes pleasantly surprised
- You can tease players lightly but always stay respectful and encouraging
- You're clear about rules and keep the show moving at a good pace

YOUR JOB:
1. Welcome the player warmly and explain the game in a fun, engaging way
2. Present improv scenarios one at a time
3. Let the player perform their improv scene
4. React authentically to their performance with specific feedback
5. After all rounds, give a personalized summary of their improv style

IMPORTANT RULES:
- Keep your responses conversational and concise (2-4 sentences usually)
- Don't use complex formatting, emojis, or asterisks
- When presenting a scenario, be crystal clear about the setup
- Listen to the FULL improv performance before reacting
- Your reactions should vary: sometimes "That was hilarious!", sometimes "Hmm, that felt a bit rushed", sometimes "I loved the character choice but you could have pushed it further"
- Be specific in your feedback - mention actual moments or choices the player made
- At the end, summarize their overall improv style (character-driven? absurdist? emotional? physical comedy?)

GAME FLOW:
- Start with a warm welcome and brief explanation
- Run through exactly 3 improv rounds
- Each round: present scenario → player improvises → you react with honest feedback
- After round 3: give a fun, personalized closing summary
- If player says "end scene" or similar, that's your cue they're done with that scenario

Remember: You're a HOST, not a player. Never improvise scenes yourself - your job is to set up scenarios and react to the player's performances."""

        super().__init__(instructions=instructions)
        self.game_state = game_state

    @function_tool
    async def get_game_state(self, context: RunContext):
        """Get the current state of the improv game.
        
        Returns:
            Game state including current round, phase, and player name
        """
        return json.dumps(self.game_state.to_dict())

    @function_tool
    async def start_next_round(self, context: RunContext):
        """Move to the next improv round and get the next scenario.
        
        Returns:
            The next improv scenario for the player
        """
        if self.game_state.current_round >= self.game_state.max_rounds:
            self.game_state.phase = "done"
            self.game_state.save_to_file()  # Save on completion
            return "All rounds completed. Time for closing summary."
        
        self.game_state.current_round += 1
        self.game_state.phase = "scenario"
        
        # Get a scenario (cycling through the list)
        scenario_index = (self.game_state.current_round - 1) % len(IMPROV_SCENARIOS)
        self.game_state.current_scenario = IMPROV_SCENARIOS[scenario_index]
        
        self.game_state.save_to_file()  # Save after each round starts
        return f"Round {self.game_state.current_round}: {self.game_state.current_scenario}"

    @function_tool
    async def record_round_reaction(
        self, 
        context: RunContext,
        reaction: Annotated[str, "Your reaction and feedback to the player's improv performance"],
        player_performance_summary: Annotated[str, "Brief summary of what the player did in their performance"] = ""
    ):
        """Record your reaction to the player's improv performance for this round.
        
        Args:
            reaction: Your honest feedback about the player's performance
            player_performance_summary: Brief summary of the player's performance
        """
        if self.game_state.current_scenario:
            self.game_state.rounds.append({
                "round": self.game_state.current_round,
                "scenario": self.game_state.current_scenario,
                "player_performance": player_performance_summary,
                "host_reaction": reaction
            })
            self.game_state.phase = "reacting"
            self.game_state.save_to_file()  # Save after each reaction
            return f"Reaction recorded. Ready for round {self.game_state.current_round + 1 if self.game_state.current_round < self.game_state.max_rounds else 'closing'}."
        return "No active scenario to record reaction for."

    @function_tool
    async def set_player_name(
        self, 
        context: RunContext,
        name: Annotated[str, "The player's name"]
    ):
        """Set the player's name when they introduce themselves.
        
        Args:
            name: The player's name
        """
        self.game_state.player_name = name
        self.game_state.save_to_file()  # Save when name is set
        logger.info(f"Player name set to: {name}")
        return f"Player name set to {name}"

    @function_tool
    async def end_game(self, context: RunContext):
        """End the game early if the player requests it.
        
        Returns:
            Confirmation that the game is ending
        """
        self.game_state.phase = "done"
        self.game_state.save_to_file()  # Save on early exit
        return "Game ended. Provide closing summary."


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()
    proc.userdata["game_state"] = ImprovGameState()


async def entrypoint(ctx: JobContext):
    # Logging setup
    ctx.log_context_fields = {
        "room": ctx.room.name,
    }

    # Get or create game state
    if "game_state" not in ctx.proc.userdata:
        ctx.proc.userdata["game_state"] = ImprovGameState()
    
    game_state = ctx.proc.userdata["game_state"]

    # Try to get player name from room participants
    async def wait_for_participant():
        """Wait for participant to join and extract player name from metadata"""
        participant = await ctx.wait_for_participant()
        if participant and participant.metadata:
            player_name = participant.metadata.strip()
            if player_name:
                game_state.player_name = player_name
                game_state.save_to_file()
                logger.info(f"Player joined: {player_name}")
        return participant

    # Set up voice AI pipeline
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

    # Metrics collection
    usage_collector = metrics.UsageCollector()

    @session.on("metrics_collected")
    def _on_metrics_collected(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        summary = usage_collector.get_summary()
        logger.info(f"Usage: {summary}")
        # Save final state on shutdown
        game_state.save_to_file()

    ctx.add_shutdown_callback(log_usage)

    # Start the session
    await session.start(
        agent=ImprovHostAssistant(game_state),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    # Join the room and wait for participant
    await ctx.connect()
    await wait_for_participant()

    logger.info(f"Improv Battle agent connected! Player: {game_state.player_name or 'Unknown'}")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))