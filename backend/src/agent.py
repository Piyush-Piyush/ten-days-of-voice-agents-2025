import logging
import json
from dotenv import load_dotenv
from pathlib import Path
import os

from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

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

logger = logging.getLogger("agent")
load_dotenv(".env.local")

# ----------------------------------------------------
# Load Knowledge Base
# ----------------------------------------------------
def load_knowledge_base():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    kb_path = os.path.join(current_dir, "knowledge_base.json")

    print("Looking for knowledge base at:", kb_path)

    if not os.path.isfile(kb_path):
        raise FileNotFoundError(f"Knowledge base JSON not found at: {kb_path}")

    with open(kb_path, "r", encoding="utf-8") as f:
        kb = json.load(f)

    # Inject company/product into FAQ answers
    if "faq" in kb:
        for key in kb["faq"]:
            kb["faq"][key] = kb["faq"][key].replace("{company_name}", kb["company_name"])
            kb["faq"][key] = kb["faq"][key].replace("{product_name}", kb["product_name"])

    return kb


KNOWLEDGE_BASE = load_knowledge_base()

# ----------------------------------------------------
# Lead Fields (Modified)
# ----------------------------------------------------
POTENTIAL_CUSTOMER_LEAD_FIELDS = [
    "customer_name",
    "customer_email",
    "product_use_case"
]

LEAD_TEMPLATE = {field: None for field in POTENTIAL_CUSTOMER_LEAD_FIELDS}


# ----------------------------------------------------
# SDR Assistant
# ----------------------------------------------------
class Assistant(Agent):
    def __init__(self):
        super().__init__(
            instructions=f"""
You are an SDR representing {KNOWLEDGE_BASE['company_name']} and the product {KNOWLEDGE_BASE['product_name']}.

You MUST answer ONLY using the knowledge base:
{json.dumps(KNOWLEDGE_BASE)}

RULES:
1. Never invent information not in the knowledge base.
2. Unknown questions → say: "I don't have that information in my knowledge base."
3. You must collect:
   - customer_name
   - customer_email
   - product_use_case
4. Automatically set "interested_company" as {KNOWLEDGE_BASE['company_name']}.
5. Ask one question at a time.
6. When all fields collected → call record_customer_info.
"""
        )

        self.lead = LEAD_TEMPLATE.copy()
        self.lead["interested_company"] = KNOWLEDGE_BASE["company_name"]

    # ------------------------------------------------
    # Tool: Save Lead
    # ------------------------------------------------
    @function_tool
    async def record_customer_info(
        self,
        ctx: RunContext,
        customer_name: str = None,
        customer_email: str = None,
        product_use_case: str = None,
        interested_company: str = None
    ):
        lead = {
            "customer_name": customer_name,
            "customer_email": customer_email,
            "product_use_case": product_use_case,
            "interested_company": interested_company,
        }

        Path("LEADS").mkdir(exist_ok=True)

        with open("LEADS/lead.json", "w") as f:
            json.dump(lead, f, indent=2)

        return "Lead information saved."

    # ------------------------------------------------
    # Message Handler
    # ------------------------------------------------
    async def on_message(self, ctx: RunContext, message: str):
        msg = message.lower().strip()

        # FAQ responses
        faq_map = {
            "what does your product do": "what_does_your_product_do",
            "who is this for": "who_is_this_for",
            "free tier": "do_you_have_a_free_tier",
            "free plan": "do_you_have_a_free_tier",
        }

        for key, faq_id in faq_map.items():
            if key in msg:
                await ctx.send(KNOWLEDGE_BASE["faq"][faq_id])
                break

        # Lead collection
        for field in POTENTIAL_CUSTOMER_LEAD_FIELDS:
            if self.lead[field] is None:
                self.lead[field] = message  # store user response

                prompts = {
                    "customer_name": "May I know your name?",
                    "customer_email": "What's the best email to reach you at?",
                    "product_use_case": "What would you like to use our product for?",
                }

                next_index = POTENTIAL_CUSTOMER_LEAD_FIELDS.index(field) + 1

                if next_index < len(POTENTIAL_CUSTOMER_LEAD_FIELDS):
                    next_field = POTENTIAL_CUSTOMER_LEAD_FIELDS[next_index]
                    await ctx.send(prompts[next_field])
                    return

                # All fields collected
                await ctx.send("Great! Saving your details now.")

                await self.record_customer_info(
                    ctx,
                    customer_name=self.lead["customer_name"],
                    customer_email=self.lead["customer_email"],
                    product_use_case=self.lead["product_use_case"],
                    interested_company=self.lead["interested_company"]
                )

                await ctx.send("Your info has been saved! How else can I help?")
                return

        await ctx.send("I don't have that information in my knowledge base.")


# ----------------------------------------------------
# Worker / Entry Point
# ----------------------------------------------------
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
