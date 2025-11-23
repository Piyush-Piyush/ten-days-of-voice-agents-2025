import logging
import json
from datetime import datetime
from dotenv import load_dotenv
import os

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
    RunContext,
)

from livekit.plugins import murf, silero, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel

logger = logging.getLogger("wellness_agent")
load_dotenv(".env.local")

WELLNESS_LOG_PATH = "wellness_log.json"


def ensure_log_file_exists():
    if not os.path.exists(WELLNESS_LOG_PATH):
        with open(WELLNESS_LOG_PATH, "w") as f:
            json.dump([], f, indent=2)


def read_all_entries():
    ensure_log_file_exists()
    with open(WELLNESS_LOG_PATH, "r") as f:
        try:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
        except json.JSONDecodeError:
            return []


def append_entry(entry: dict):
    entries = read_all_entries()
    entries.append(entry)
    with open(WELLNESS_LOG_PATH, "w") as f:
        json.dump(entries, f, indent=2)


class WellnessAssistant(Agent):
    def __init__(self):
        super().__init__(
            instructions="""
                You are a supportive, grounded daily wellness companion. 
                Do short (concise) check-ins focused on mood, energy, and 1-3 practical goals for the day.
                Avoid medical diagnoses or medical advice. Offer small, actionable, non-technical suggestions only.
                At the end, give a short recap and confirm. Save each check-in to the wellness_log.json file.
                When possible, refer briefly to the most recent prior check-in (one small reference).
                Keep responses warm, clear, and short.
                """
        )

       
        self.state = None

        self.current = {
            "date": None,
            "mood": None,
            "energy": None,
            "stressors": None,
            "goals": None,
            "self_care": None,
            "summary": None,
        }

        self.past_entries = read_all_entries()
        self.last_entry = self.past_entries[-1] if self.past_entries else None

        self._greeted = False

    @function_tool
    async def save_checkin(self, ctx: RunContext, entry: dict):
        append_entry(entry)
        return "Check-in saved."

    async def on_message(self, ctx: RunContext, message: str):
        msg = (message or "").strip()
        if not self._greeted:
            greeting = "Hi — ready for today's quick check-in?"
            if self.last_entry:
                prev_mood = self.last_entry.get("mood", None)
                prev_energy = self.last_entry.get("energy", None)
                if prev_mood or prev_energy:
                    reference = " Last time you said"
                    if prev_mood:
                        reference += f" your mood was '{prev_mood}'"
                    if prev_energy:
                        reference += f" and energy was '{prev_energy}'"
                    reference += ". How are you today?"
                    greeting = greeting + reference
            await ctx.send(greeting)
            self._greeted = True
            # Ask first question
            await ctx.send("First — how are you feeling right now? (a few words is fine)")
            self.state = "asked_mood"
            return

        if self.state == "asked_mood":
            self.current["mood"] = msg or "not specified"
            await ctx.send("Thanks — and what is your energy like today? (low / medium / high or a few words)")
            self.state = "asked_energy"
            return

        if self.state == "asked_energy":
            self.current["energy"] = msg or "not specified"
            await ctx.send("Anything stressing you out right now or on your mind? (say 'no' if nothing)")
            self.state = "asked_stress"
            return

        if self.state == "asked_stress":
            self.current["stressors"] = msg if msg and msg.lower() != "no" else ""
            await ctx.send(
                "What are 1–3 practical things you'd like to get done today? (short list, comma separated)"
            )
            self.state = "asked_goals"
            return

        if self.state == "asked_goals":
            goals = [g.strip() for g in msg.split(",") if g.strip()]
            if not goals:
                goals = []
            self.current["goals"] = goals
            await ctx.send("Is there one small thing you'll do for yourself today? (rest, walk, hobby — or 'none')")
            self.state = "asked_selfcare"
            return

        if self.state == "asked_selfcare":
            self.current["self_care"] = msg if msg and msg.lower() != "none" else ""
            mood = self.current["mood"]
            energy = self.current["energy"]
            goals = self.current["goals"]
            selfcare = self.current["self_care"]

            summary_parts = []
            if mood:
                summary_parts.append(f"mood: {mood}")
            if energy:
                summary_parts.append(f"energy: {energy}")
            if goals:
                summary_parts.append(f"goals: {', '.join(goals)}")
            if selfcare:
                summary_parts.append(f"self-care: {selfcare}")

            summary_sentence = " | ".join(summary_parts) or "No details provided."
            self.current["summary"] = summary_sentence
            self.current["date"] = datetime.now().isoformat()

            suggestion = await self._generate_suggestion(ctx)


            recap = (
                f"Quick recap — {summary_sentence}. "
                f"Suggestion: {suggestion} "
                "Does that sound right?"
            )
            await ctx.send(recap)
            self.state = "asked_confirm"
            return

        if self.state == "asked_confirm":
            lowered = (msg or "").lower()
            if lowered in ("yes", "y", "correct", "sounds good", "right", "sure"):
                await self.save_checkin(ctx, self.current)
                await ctx.send("Got it — your check-in is saved. I’ll remember this for next time. Take care!")
                self.state = "done"
                return
            else:
                await ctx.send(
                    "No problem. Which part would you like to change? (mood / energy / goals / self-care / cancel)"
                )
                self.state = "awaiting_edit_choice"
                return

        if self.state == "awaiting_edit_choice":
            choice = (msg or "").lower()
            if "mood" in choice:
                await ctx.send("Okay — tell me your mood now (a few words).")
                self.state = "edit_mood"
                return
            if "energy" in choice:
                await ctx.send("Okay — tell me your energy now.")
                self.state = "edit_energy"
                return
            if "goal" in choice:
                await ctx.send("Okay — send me the updated 1–3 goals, comma separated.")
                self.state = "edit_goals"
                return
            if "self" in choice or "care" in choice:
                await ctx.send("Okay — what's your self-care item now? (or 'none')")
                self.state = "edit_selfcare"
                return
            if "cancel" in choice or "no" in choice:
                await ctx.send("Alright — keeping the original entry. Saving now.")
                await self.save_checkin(ctx, self.current)
                await ctx.send("Saved. Take care!")
                self.state = "done"
                return
            await ctx.send("I didn't catch that. Please say mood, energy, goals, self-care, or cancel.")
            return

        if self.state == "edit_mood":
            self.current["mood"] = msg or self.current["mood"]
            await ctx.send("Updated mood. Anything else to change? (say 'no' to keep the rest)")
            self.state = "awaiting_more_edits"
            return

        if self.state == "edit_energy":
            self.current["energy"] = msg or self.current["energy"]
            await ctx.send("Updated energy. Anything else to change? (say 'no' to keep the rest)")
            self.state = "awaiting_more_edits"
            return

        if self.state == "edit_goals":
            goals = [g.strip() for g in msg.split(",") if g.strip()]
            self.current["goals"] = goals
            await ctx.send("Updated goals. Anything else to change? (say 'no' to keep the rest)")
            self.state = "awaiting_more_edits"
            return

        if self.state == "edit_selfcare":
            self.current["self_care"] = msg if msg and msg.lower() != "none" else ""
            await ctx.send("Updated self-care. Anything else to change? (say 'no' to keep the rest)")
            self.state = "awaiting_more_edits"
            return

        if self.state == "awaiting_more_edits":
            lowered = (msg or "").lower()
            if lowered in ("no", "none", "that's it", "done"):
                await self.save_checkin(ctx, self.current)
                await ctx.send("Saved the updated check-in. Thanks — take care!")
                self.state = "done"
                return
            else:
                await ctx.send("Which part would you like to change next? (mood / energy / goals / self-care / cancel)")
                self.state = "awaiting_edit_choice"
                return

        if self.state == "done":
            await ctx.send("We've already saved today's check-in. Say 'start' if you want another check-in.")
            return

        await ctx.send("Sorry, I didn't understand that. Please say 'start' to begin a daily check-in.")
        return

    async def _generate_suggestion(self, ctx: RunContext) -> str:
        mood = self.current.get("mood") or ""
        energy = (self.current.get("energy") or "").lower()
        goals = self.current.get("goals") or []
        selfcare = self.current.get("self_care") or ""

        # --- Rule-Based Grounding ---
        base_hint = ""
        if "low" in energy or "tired" in energy:
            base_hint = (
                "Your energy seems low; suggest a very small first step, "
                "plus a short rest or 5-minute walk."
            )
        elif "high" in energy:
            base_hint = (
                "Your energy is high; suggest focusing on the most important task "
                "with a short focused work block."
            )
        else:
            base_hint = (
                "Energy is moderate or unclear; suggest a simple doable step "
                "and keeping things light."
            )

        # --- LLM Refinement ---
        prompt = f"""
        You are a supportive wellness companion.

        Base guidance:
        {base_hint}

        User info:
        - Mood: {mood}
        - Energy: {energy}
        - Goals: {goals}
        - Self-care: {selfcare}

        Guidelines:
        - Keep the suggestion short (max 20 words).
        - No medical or diagnostic advice.
        - Make it actionable, gentle, and practical.
        - Avoid over-optimism; stay realistic.

        Give exactly ONE suggestion sentence.
        """

        result = await ctx.session.llm.complete(prompt)
        suggestion = result.text.strip()

        # Fallback if LLM returns empty
        if not suggestion:
            suggestion = "Maybe take one small step toward a goal and give yourself a short break."

        return suggestion


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
            text_pacing=True,
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

    ensure_log_file_exists()

    await session.start(
        agent=WellnessAssistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(noise_cancellation=noise_cancellation.BVC()),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))
