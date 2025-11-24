import logging
import json
import asyncio
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
)
from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("agent")

load_dotenv(".env.local")

with open("./shared-data/teach_the_tutor.json", "r") as f:
    TUTOR_CONTENT = json.load(f)

CONCEPT_INDEX = {c["id"]: c for c in TUTOR_CONTENT}



# -----------------------------
class Assistant(Agent):
    def __init__(self):
        super().__init__(
            instructions="""
                You are an Active Recall AI Tutor with three modes: learn, quiz, and teach_back.

                Your job:
                1. Greet the user and ask which mode they want.
                2. Track mode, selected concept, and mastery score using memory.
                3. Modes:
                    - learn: explain the concept using its summary
                    - quiz: ask the user the sample question
                    - teach_back: let the user explain, then give qualitative feedback

                User can say:
                - switch to quiz
                - teach me variables
                - change to learn mode
                - let's teach back loops

                Extract:
                - intent (learn/quiz/teach_back)
                - concept id (variables / loops)

                Always answer plainly.
            """
        )


# -----------------------------
#         PREWARM
# -----------------------------
def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()
    proc.userdata["mode"] = None
    proc.userdata["concept"] = None
    proc.userdata["mastery"] = {}  # concept → score



async def entrypoint(ctx: JobContext):
    ctx.log_context_fields = {"room": ctx.room.name}

    current_voice = "en-US-matthew"

    def set_voice(session, voice):
        session.tts = murf.TTS(
            voice=voice,
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        )

    # Agent session
    session = AgentSession(
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice=current_voice,
            style="Conversation",
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
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


    @session.on("agent_response")
    def _on_agent_response(response):
        asyncio.create_task(tutor_logic(response))

   
    async def tutor_logic(response):
        text = response.text.lower()

        mode = ctx.proc.userdata["mode"]
        concept = ctx.proc.userdata["concept"]

        # Mode switching
        if "learn" in text:
            ctx.proc.userdata["mode"] = "learn"
            set_voice(session, "en-US-matthew")

        elif "quiz" in text:
            ctx.proc.userdata["mode"] = "quiz"
            set_voice(session, "en-US-alicia")

        elif "teach back" in text or "teachback" in text:
            ctx.proc.userdata["mode"] = "teach_back"
            set_voice(session, "en-US-ken")

        # Concept detection
        for c in CONCEPT_INDEX.keys():
            if c in text:
                ctx.proc.userdata["concept"] = c

        mode = ctx.proc.userdata["mode"]
        concept = ctx.proc.userdata["concept"]

        if mode is None:
            response.override_text("Hello! Which mode would you like? Learn, quiz, or teach back?")
            return

        if concept is None:
            response.override_text("Great. Which concept should we work on? Variables or loops?")
            return

        # Load concept
        data = CONCEPT_INDEX[concept]

        if mode == "learn":
            response.override_text(
                f"Here is an explanation of {data['title']}. {data['summary']}"
            )

        elif mode == "quiz":
            response.override_text(
                f"Here is your question: {data['sample_question']}"
            )

        elif mode == "teach_back":
            # Basic heuristic scoring
            if any(word in text for word in ["because", "means", "used to", "purpose", "helps"]):
                score = 1
                ctx.proc.userdata["mastery"][concept] = (
                    ctx.proc.userdata["mastery"].get(concept, 0) + score
                )
                response.override_text("Thank you. That was a good explanation!")
            else:
                response.override_text(
                    f"Teach this concept back to me. {data['sample_question']}"
                )

    # Start session
    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()


# -----------------------------
#         MAIN
# -----------------------------
if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
