import logging
import json
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

# ORDER TEMPLATE
ORDER_TEMPLATE = {
    "drinkType": None,
    "size": None,
    "milk": None,
    "extras": [],
    "name": None
}


class Assistant(Agent):
    def __init__(self):
        super().__init__(
            instructions="""
                You are a friendly barista at a specialty coffee shop.
                Your job is to take the user's coffee order step-by-step.

                You must:
                1. Collect all fields of the order: drinkType, size, milk, extras, name.
                2. Ask clarifying questions until every field is filled.
                3. Keep responses short and conversational.
                4. When the order is complete, confirm it and call the save_order tool.
            """
        )

        # Fresh order for each session
        self.order = ORDER_TEMPLATE.copy()

    # --- TOOL: Save Order ---
    @function_tool
    async def save_order(self, ctx: RunContext, order: dict):
        """Save the completed coffee order to a JSON file."""
        with open("ORDERS/order.json", "w") as f:
            json.dump(order, f, indent=2)
        return "Order saved successfully."

    # --- MAIN LOGIC: Handle messages ---
    async def on_message(self, ctx: RunContext, message: str):
        msg = message.lower().strip()

        # Step 1: Drink type
        if self.order["drinkType"] is None:
            self.order["drinkType"] = msg
            await ctx.send("Great choice! What size would you like? Small, medium, or large?")
            return

        # Step 2: Size
        if self.order["size"] is None:
            self.order["size"] = msg
            await ctx.send("Got it. What kind of milk would you like? Dairy, almond, oat, or soy?")
            return

        # Step 3: Milk
        if self.order["milk"] is None:
            self.order["milk"] = msg
            await ctx.send("Would you like any extras? For example: whipped cream, caramel, or chocolate. Say 'no extras' if none.")
            return

        # Step 4: Extras
        if not self.order["extras"]:
            if msg == "no extras":
                self.order["extras"] = []
            else:
                self.order["extras"] = [x.strip() for x in msg.split(",")]
            await ctx.send("Alright! And what's your name for the cup?")
            return

        # Step 5: Name — order complete
        if self.order["name"] is None:
            self.order["name"] = msg

            summary = (
                f"Perfect {self.order['name']}! "
                f"So that's a {self.order['size']} {self.order['drinkType']} "
                f"with {self.order['milk']} milk and "
                f"extras: {', '.join(self.order['extras']) or 'none'}."
            )

            await ctx.send(summary)

            # Call the tool
            await self.save_order(ctx, self.order)

            await ctx.send("Your order is saved! It'll be ready shortly.")
            return




def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):

    ctx.log_context_fields = {"room": ctx.room.name}

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
    def _on_metrics(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        usage_collector.collect(ev.metrics)

    async def log_usage():
        logger.info("Usage summary: %s", usage_collector.get_summary())

    ctx.add_shutdown_callback(log_usage)

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm
        )
    )
