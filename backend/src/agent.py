import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional
from livekit.plugins import silero, murf, google, deepgram, noise_cancellation
from livekit.plugins.turn_detector.multilingual import MultilingualModel
from dotenv import load_dotenv
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    JobProcess,
    MetricsCollectedEvent,
    RoomInputOptions,
    RunContext,
    ToolError,
    WorkerOptions,
    cli,
    function_tool,
    metrics,
    tokenize,
)

# Initialize logger
agent_logger = logging.getLogger("agent")
load_dotenv(".env.local")

AVAILABLE_MODES = ("learn", "quiz", "teach_back")

MODE_VOICE_CONFIG = {
    "learn": {
        "voice": "en-US-matthew",
        "style": "Conversation",
        "display": "Matthew",
        "tone": "calm, encouraging explanations",
    },
    "quiz": {
        "voice": "en-US-alicia",
        "style": "Conversation",
        "display": "Alicia",
        "tone": "energetic quiz master",
    },
    "teach_back": {
        "voice": "en-US-ken",
        "style": "Conversation",
        "display": "Ken",
        "tone": "supportive coach who listens closely",
    },
}


@dataclass
class LearningConcept:
    id: str
    title: str
    summary: str
    sample_question: str
    teach_back_prompt: str


@dataclass
class ProgressTracker:
    """Tracks learner's progress metrics."""
    times_learned: int = 0
    times_quizzed: int = 0
    times_taught_back: int = 0
    last_score: Optional[int] = None
    last_feedback: Optional[str] = None


@dataclass
class SessionContext:
    """Manages current session state and progress."""
    current_mode: Optional[str] = None
    current_concept_id: Optional[str] = None
    mastery: Dict[str, ProgressTracker] = field(default_factory=dict)

    def get_or_create_tracker(self, concept_id: str) -> ProgressTracker:
        if concept_id not in self.mastery:
            self.mastery[concept_id] = ProgressTracker()
        return self.mastery[concept_id]


class ContentRepository:
    def __init__(self, concepts: List[LearningConcept]):
        if not concepts:
            raise ValueError("ContentRepository needs at least one concept to function.")
        self._concept_map: Dict[str, LearningConcept] = {c.id: c for c in concepts}
        self._concept_sequence: List[str] = [c.id for c in concepts]

    @classmethod
    def load_from_file(cls, file_path: Path) -> "ContentRepository":
        if not file_path.exists():
            raise FileNotFoundError(f"Content file missing at: {file_path}")
        with open(file_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        concept_list = [LearningConcept(**item) for item in data]
        return cls(concept_list)

    @classmethod
    def initialize_from_environment(cls) -> "ContentRepository":
        base_dir = Path(__file__).resolve().parents[2]
        default_location = base_dir / "shared-data" / "materials.json"
        env_path = os.getenv("DAY4_TUTOR_CONTENT_PATH")
        actual_path = Path(env_path) if env_path else default_location
        return cls.load_from_file(actual_path)

    def get_all_concepts(self) -> List[LearningConcept]:
        return [self._concept_map[cid] for cid in self._concept_sequence]

    def retrieve_concept(self, concept_id: Optional[str]) -> LearningConcept:
        selected_id = concept_id or self._concept_sequence[0]
        if selected_id not in self._concept_map:
            raise KeyError(f"Concept not found: {selected_id}")
        return self._concept_map[selected_id]

    def get_next_in_sequence(self, current_id: Optional[str]) -> str:
        if current_id is None:
            return self._concept_sequence[0]
        try:
            position = self._concept_sequence.index(current_id)
        except ValueError:
            return self._concept_sequence[0]
        next_position = (position + 1) % len(self._concept_sequence)
        return self._concept_sequence[next_position]


@dataclass
class AgentUserdata:
    """Container for session and content data."""
    state: SessionContext
    content: ContentRepository


class ActiveRecallCoach(Agent):
    """AI tutor implementing active recall methodology."""

    def __init__(self, *, userdata: AgentUserdata) -> None:
        system_prompt = f"""You are Teach-the-Tutor, an active recall coach that helps users master core coding concepts.
Key behaviors:
- Greet the learner and immediately ask which learning mode they prefer (learn, quiz, teach_back).
- When the learner requests a mode change, call set_learning_mode to switch voices (Matthew for learn, Alicia for quiz, Ken for teach_back).
- Focus on one concept at a time. Use list_concepts, then set_focus_concept before explaining or quizzing.
- Use describe_current_concept for learn mode, get_quiz_prompt for quiz mode, and get_teach_back_prompt for teach_back mode.
- Track mastery by calling record_mastery_event with scores (0–100) and feedback.
- Keep responses concise and conversational.

Mode-specific guidance:
- Learn mode (Matthew): calm walkthroughs
- Quiz mode (Alicia): energetic questioning
- Teach_back mode (Ken): supportive coaching

Use function tools frequently to stay grounded in the JSON content."""

        super().__init__(instructions=system_prompt)

    async def on_agent_speech_committed(self, ctx: RunContext[AgentUserdata], message: str) -> None:
        agent_logger.info(f"🤖 Agent said: {message}")

    async def on_user_speech_committed(self, ctx: RunContext[AgentUserdata], message: str) -> None:
        agent_logger.info(f"👤 User said: {message}")

    def _fetch_active_concept(self, ctx: RunContext[AgentUserdata]) -> LearningConcept:
        session_state = ctx.userdata.state
        try:
            return ctx.userdata.content.retrieve_concept(session_state.current_concept_id)
        except KeyError as error:
            raise ToolError(str(error)) from error

    def _switch_voice_profile(self, ctx: RunContext[AgentUserdata], mode: str) -> None:
        """Changes voice with fallback mechanism if primary method fails"""
        voice_config = MODE_VOICE_CONFIG[mode]
        tts_instance = ctx.session.tts
        
        if not tts_instance:
            agent_logger.warning("Voice switching unavailable: no TTS engine in session.")
            return

        # Attempt direct option update first
        update_method = getattr(tts_instance, "update_options", None)
        if callable(update_method):
            try:
                update_method(voice=voice_config["voice"], style=voice_config["style"])
                agent_logger.info(f"✅ Voice profile changed to {voice_config['display']} for {mode} (via update_options)")
                return
            except Exception as error:
                agent_logger.warning(f"Direct update failed: {error}, switching to fallback method")

        # Fallback: Replace entire TTS engine
        try:
            sentence_tokenizer = tokenize.basic.SentenceTokenizer(min_sentence_len=2)
            replacement_tts = murf.TTS(
                voice=voice_config["voice"],
                style=voice_config["style"],
                tokenizer=sentence_tokenizer,
                text_pacing=True,
            )
            ctx.session.tts = replacement_tts
            agent_logger.info(f"✅ Voice profile changed to {voice_config['display']} for {mode} (via TTS replacement)")
        except Exception as error:
            agent_logger.error(f"Voice switching completely failed for mode {mode}: {error}")

    @function_tool
    async def list_concepts(self, ctx: RunContext[AgentUserdata]) -> str:
        """Lists all available learning concepts for selection."""
        all_concepts = ctx.userdata.content.get_all_concepts()
        concept_list = ", ".join(f"{c.id} ({c.title})" for c in all_concepts)
        return f"Available concepts: {concept_list}. Ask the learner which one they want to focus on."

    @function_tool
    async def set_focus_concept(self, ctx: RunContext[AgentUserdata], concept_id: str) -> str:
        """Sets the primary concept for the current session."""
        selected_concept = ctx.userdata.content.retrieve_concept(concept_id)
        ctx.userdata.state.current_concept_id = selected_concept.id
        ctx.userdata.state.get_or_create_tracker(selected_concept.id)
        return f"Concept locked: {selected_concept.title}. You're clear to continue working on {selected_concept.title}."

    @function_tool
    async def describe_current_concept(self, ctx: RunContext[AgentUserdata]) -> str:
        """Provides summary of the active concept for learning."""
        active_concept = self._fetch_active_concept(ctx)
        tracker = ctx.userdata.state.get_or_create_tracker(active_concept.id)
        tracker.times_learned += 1
        return f"{active_concept.title}: {active_concept.summary}"

    @function_tool
    async def get_quiz_prompt(self, ctx: RunContext[AgentUserdata]) -> str:
        """Retrieves quiz question for the current concept."""
        active_concept = self._fetch_active_concept(ctx)
        tracker = ctx.userdata.state.get_or_create_tracker(active_concept.id)
        tracker.times_quizzed += 1
        return f"Quiz question for {active_concept.title}: {active_concept.sample_question}"

    @function_tool
    async def get_teach_back_prompt(self, ctx: RunContext[AgentUserdata]) -> str:
        """Gets teach-back instructions for active concept."""
        active_concept = self._fetch_active_concept(ctx)
        tracker = ctx.userdata.state.get_or_create_tracker(active_concept.id)
        tracker.times_taught_back += 1
        return f"Teach this back: {active_concept.teach_back_prompt}"

    @function_tool
    async def set_learning_mode(self, ctx: RunContext[AgentUserdata], mode: str) -> str:
        """Changes the learning mode (learn, quiz, teach_back)."""
        mode_normalized = mode.lower()
        if mode_normalized not in AVAILABLE_MODES:
            raise ToolError(
                f"Invalid mode '{mode}'. Valid options: {', '.join(AVAILABLE_MODES)}."
            )
        ctx.userdata.state.current_mode = mode_normalized
        voice_profile = MODE_VOICE_CONFIG[mode_normalized]
        self._switch_voice_profile(ctx, mode_normalized)
        return (
            f"Switched to {mode_normalized} mode. Voice {voice_profile['display']} is now active "
            f"({voice_profile['tone']})."
        )

    @function_tool
    async def record_mastery_event(
        self,
        ctx: RunContext[AgentUserdata],
        mode: str,
        concept_id: Optional[str] = None,
        score: Optional[int] = None,
        feedback: Optional[str] = None,
    ) -> str:
        """Records progress after completing a learning activity."""
        mode_normalized = mode.lower()
        if mode_normalized not in AVAILABLE_MODES:
            raise ToolError(f"Mode must be one of {', '.join(AVAILABLE_MODES)}.")
        target_id = concept_id or ctx.userdata.state.current_concept_id
        if target_id is None:
            raise ToolError("Cannot record mastery without an active concept.")
        tracker = ctx.userdata.state.get_or_create_tracker(target_id)
        if score is not None:
            tracker.last_score = max(0, min(100, score))
        if feedback:
            tracker.last_feedback = feedback
        score_display = tracker.last_score if tracker.last_score is not None else 'n/a'
        return (
            f"Mastery updated for {target_id} after {mode_normalized} mode. "
            f"Latest score: {score_display}."
        )

    @function_tool
    async def get_mastery_snapshot(
        self,
        ctx: RunContext[AgentUserdata],
        concept_id: Optional[str] = None,
    ) -> str:
        """Generates summary of progress statistics."""
        if concept_id:
            concepts_to_check = [ctx.userdata.content.retrieve_concept(concept_id)]
        else:
            concepts_to_check = ctx.userdata.content.get_all_concepts()
        progress_summaries = []
        for concept in concepts_to_check:
            tracker = ctx.userdata.state.mastery.get(concept.id, ProgressTracker())
            score_display = tracker.last_score if tracker.last_score is not None else 'n/a'
            summary_text = (
                f"{concept.title}: learn={tracker.times_learned}, "
                f"quiz={tracker.times_quizzed}, teach_back={tracker.times_taught_back}, "
                f"last_score={score_display}"
            )
            if tracker.last_feedback:
                summary_text += f", feedback='{tracker.last_feedback}'"
            progress_summaries.append(summary_text)
        return " | ".join(progress_summaries)

    @function_tool
    async def advance_to_next_concept(self, ctx: RunContext[AgentUserdata]) -> str:
        """Moves to the next concept in the curriculum."""
        next_concept_id = ctx.userdata.content.get_next_in_sequence(ctx.userdata.state.current_concept_id)
        ctx.userdata.state.current_concept_id = next_concept_id
        ctx.userdata.state.get_or_create_tracker(next_concept_id)
        next_concept = ctx.userdata.content.retrieve_concept(next_concept_id)
        return f"Advanced to {next_concept.title}. Let the learner know the new focus."


def prewarm(proc: JobProcess):
    """Preloads models and educational content."""
    proc.userdata["vad"] = silero.VAD.load()
    proc.userdata["tutor_content"] = ContentRepository.initialize_from_environment()


async def entrypoint(ctx: JobContext):
    """Main entry point for the active recall coaching agent."""

    ctx.log_context_fields = {"room": ctx.room.name}

    repository = ctx.proc.userdata.get("tutor_content", ContentRepository.initialize_from_environment())
    initial_concept = repository.get_all_concepts()[0].id
    session_state = SessionContext(current_concept_id=initial_concept)
    agent_data = AgentUserdata(state=session_state, content=repository)

    agent_session = AgentSession[AgentUserdata](
        userdata=agent_data,
        stt=deepgram.STT(model="nova-3"),
        llm=google.LLM(model="gemini-2.5-flash"),
        tts=murf.TTS(
            voice=MODE_VOICE_CONFIG["learn"]["voice"],
            style=MODE_VOICE_CONFIG["learn"]["style"],
            tokenizer=tokenize.basic.SentenceTokenizer(min_sentence_len=2),
            text_pacing=True,
        ),
        turn_detection=MultilingualModel(),
        vad=ctx.proc.userdata["vad"],
        preemptive_generation=True,
    )

    metrics_collector = metrics.UsageCollector()

    @agent_session.on("metrics_collected")
    def handle_metrics_collection(ev: MetricsCollectedEvent):
        metrics.log_metrics(ev.metrics)
        metrics_collector.collect(ev.metrics)

    @agent_session.on("user_speech_committed")
    def handle_user_speech(ev):
        """Detects mode keywords for instant voice switching"""
        user_text = ev.text.lower()
        agent_logger.info(f" User speech: {user_text}")
        
        target_mode = None
        if "learn" in user_text and "mode" in user_text:
            target_mode = "learn"
        elif "quiz" in user_text and "mode" in user_text:
            target_mode = "quiz"
        elif ("teach back" in user_text or "teachback" in user_text or "teach-back" in user_text) and "mode" in user_text:
            target_mode = "teach_back"
        
        if target_mode:
            agent_data.state.current_mode = target_mode
            active_agent = agent_session.agent
            if isinstance(active_agent, ActiveRecallCoach):
                temp_context = type('obj', (object,), {
                    'userdata': agent_data,
                    'session': agent_session
                })()
                active_agent._switch_voice_profile(temp_context, target_mode)
                agent_logger.info(f"Instant mode switch to {target_mode} from user input")

    @agent_session.on("agent_speech_committed")
    def handle_agent_speech(ev):
        agent_logger.info(f"Agent speech: {ev.text}")

    @agent_session.on("error")
    def handle_session_error(ev):
        agent_logger.error(f"Session error: {ev}")

    async def report_usage():
        usage_summary = metrics_collector.get_summary()
        agent_logger.info(f"Usage: {usage_summary}")

    ctx.add_shutdown_callback(report_usage)

    coach_agent = ActiveRecallCoach(userdata=agent_data)

    await agent_session.start(
        agent=coach_agent,
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()
    agent_logger.info("✨ Day 4 Teach-the-Tutor agent with smooth voice switching is live!")


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))