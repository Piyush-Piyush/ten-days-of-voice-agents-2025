import logging
import sqlite3
import os
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
logging.basicConfig(level=logging.INFO)

load_dotenv(".env.local")


DB_DIR = "DATABASE"
DB_PATH = os.path.join(DB_DIR, "fraud.db")
os.makedirs(DB_DIR, exist_ok=True)

def load_case_from_db(username: str):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        SELECT userName, securityIdentifier, cardEnding, merchant, amount,
               location, timestamp, transactionCategory, transactionSource,
               securityQuestion, securityAnswer, status, note
        FROM fraud_cases
        WHERE lower(userName) = lower(?)
        LIMIT 1
    """, (username,))
    row = cur.fetchone()

    if not row:
        conn.close()
        return None

    col_names = [d[0] for d in cur.description]
    case = dict(zip(col_names, row))

    conn.close()
    logger.info(f"✓ Loaded case: userName={case.get('userName')}, status={case.get('status')}")
    return case


def save_case_to_db(case: dict):
    """
    Updates the fraud case **by username**, since username is UNIQUE.
    """
    logger.info(f"→ Saving case: userName={case.get('userName')}, status={case.get('status')}, note={case.get('note')[:50] if case.get('note') else 'None'}...")
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # First verify the record exists
    cur.execute("SELECT userName, status FROM fraud_cases WHERE lower(userName)=lower(?)", (case.get("userName"),))
    existing = cur.fetchone()
    
    if not existing:
        conn.close()
        logger.error(f"✗ No record found for userName: {case.get('userName')}")
        return False

    logger.info(f"  Found existing: userName={existing[0]}, current status={existing[1]}")

    cur.execute("""
        UPDATE fraud_cases
        SET securityIdentifier=?, cardEnding=?, merchant=?, amount=?, location=?,
            timestamp=?, transactionCategory=?, transactionSource=?, securityQuestion=?,
            securityAnswer=?, status=?, note=?
        WHERE lower(userName)=lower(?)
    """, (
        case.get("securityIdentifier"),
        case.get("cardEnding"),
        case.get("merchant"),
        case.get("amount"),
        case.get("location"),
        case.get("timestamp"),
        case.get("transactionCategory"),
        case.get("transactionSource"),
        case.get("securityQuestion"),
        case.get("securityAnswer"),
        case.get("status"),
        case.get("note"),
        case.get("userName"),
    ))

    conn.commit()
    updated = cur.rowcount
    
    # Verify the update
    if updated > 0:
        cur.execute("SELECT status, note FROM fraud_cases WHERE lower(userName)=lower(?)", (case.get("userName"),))
        verification = cur.fetchone()
        if verification:
            logger.info(f"✓ SUCCESS: Updated to status={verification[0]}, note={verification[1][:50] if verification[1] else 'None'}...")
    else:
        logger.error(f"✗ FAILED: No rows updated for {case.get('userName')}")
    
    conn.close()
    return updated > 0


# Global state (since agent is stateless between calls)
conversation_state = {}


class FraudAgent(Agent):

    def __init__(self):
        super().__init__(
            instructions="""
                You are a fraud detection representative from SecureTrust Bank.
                
                CRITICAL: Follow these steps EXACTLY in order:
                
                1. Ask for the customer's name
                2. Call load_case_info with their name
                3. Ask them the security question from the case
                4. If they answer correctly, call verify_security with answer="correct"
                5. If they answer incorrectly, call verify_security with answer="incorrect"
                6. After successful verification, present the transaction details
                7. Ask if they made the transaction (yes/no)
                8. Call confirm_transaction with their answer ("yes" or "no")
                
                Always use the tools provided. Do not skip any steps.
            """
        )

    @function_tool
    async def load_case_info(self, ctx: RunContext, customer_name: str):
        """
        Load fraud case information for a customer by name.
        Call this after getting the customer's name.
        """
        logger.info(f"🔧 TOOL CALLED: load_case_info(customer_name='{customer_name}')")
        
        case = load_case_from_db(customer_name)
        if not case:
            return f"No case found for {customer_name}. Please verify the name."
        
        # Store in global state
        conversation_state['case'] = case
        conversation_state['customer_name'] = customer_name
        
        return f"""Case loaded for {case['userName']}.
Security Question: {case['securityQuestion']}
Transaction Details:
- Merchant: {case['merchant']}
- Amount: {case['amount']}
- Location: {case['location']}
- Time: {case['timestamp']}

Current Status: {case['status']}

Now ask them the security question."""

    @function_tool
    async def verify_security(self, ctx: RunContext, answer: str):
        """
        Verify the customer's security answer.
        
        Args:
            answer: Either "correct" or "incorrect" based on their response
        """
        logger.info(f"🔧 TOOL CALLED: verify_security(answer='{answer}')")
        
        if 'case' not in conversation_state:
            return "Error: No case loaded. Please load case first."
        
        case = conversation_state['case']
        
        if answer.lower() == "incorrect":
            case['status'] = 'verification_failed'
            case['note'] = 'User failed security verification.'
            success = save_case_to_db(case)
            
            return f"Verification failed. Case status updated: {success}. End the conversation politely."
        
        elif answer.lower() == "correct":
            conversation_state['verified'] = True
            return f"Verification successful. Now present the transaction details and ask if they made this purchase."
        
        return "Please specify 'correct' or 'incorrect'"

    @function_tool
    async def confirm_transaction(self, ctx: RunContext, user_response: str):
        """
        Record the customer's response about whether they made the transaction.
        
        Args:
            user_response: "yes" if they made it, "no" if they didn't
        """
        logger.info(f"🔧 TOOL CALLED: confirm_transaction(user_response='{user_response}')")
        
        if 'case' not in conversation_state:
            return "Error: No case loaded."
        
        if not conversation_state.get('verified', False):
            return "Error: Customer not verified yet."
        
        case = conversation_state['case']
        response = user_response.lower()
        
        if 'yes' in response or 'y' == response:
            case['status'] = 'confirmed_safe'
            case['note'] = 'User confirmed the transaction as legitimate.'
            success = save_case_to_db(case)
            
            return f"""Transaction marked as legitimate. Database updated: {success}.
Tell the customer: 'Thank you for confirming. I've marked this transaction as legitimate. Your account is secure and no further action is needed.'"""
        
        elif 'no' in response or 'n' == response:
            case['status'] = 'confirmed_fraud'
            case['note'] = 'User denied the transaction. Fraudulent activity confirmed.'
            success = save_case_to_db(case)
            
            return f"""Transaction marked as FRAUD. Database updated: {success}.
Tell the customer: 'Thank you for letting us know. I've marked this as fraudulent activity and your card has been temporarily blocked for your protection. A new card will be sent to you within 5-7 business days.'"""
        
        return "Please call this tool with 'yes' or 'no' based on what the customer said."


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
        preemptive_generation=True
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
        agent=FraudAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        )
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=prewarm
        )
    )