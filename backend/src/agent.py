import logging
import json
import os
from datetime import datetime
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
    RunContext,
)

logger = logging.getLogger("agent")
load_dotenv(".env.local")

<<<<<<< Updated upstream
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
=======
# -----------------------------
# Simple catalog and order store
# -----------------------------

CATALOG = [
    {
        "id": "mug-001",
        "name": "Stoneware Coffee Mug",
        "description": "A sturdy white stoneware mug.",
        "price": 800,
        "currency": "INR",
        "category": "mug",
        "color": "white",
        "sizes": [],
    },
    {
        "id": "mug-002",
        "name": "Blue Ceramic Mug",
        "description": "Blue ceramic mug for hot drinks.",
        "price": 900,
        "currency": "INR",
        "category": "mug",
        "color": "blue",
        "sizes": [],
    },
    {
        "id": "tee-001",
        "name": "Black T-Shirt",
        "description": "Basic black cotton t-shirt.",
        "price": 700,
        "currency": "INR",
        "category": "tshirt",
        "color": "black",
        "sizes": ["S", "M", "L", "XL"],
    },
    {
        "id": "hoodie-001",
        "name": "Black Zip Hoodie",
        "description": "Cozy black hoodie with zipper.",
        "price": 1500,
        "currency": "INR",
        "category": "hoodie",
        "color": "black",
        "sizes": ["M", "L", "XL"],
    },
    {
        "id": "hoodie-002",
        "name": "Gray Pullover Hoodie",
        "description": "Soft gray pullover hoodie.",
        "price": 1400,
        "currency": "INR",
        "category": "hoodie",
        "color": "gray",
        "sizes": ["S", "M", "L"],
    },

    # Mobiles
    {
        "id": "phone-001",
        "name": "Nova X5 5G",
        "description": "Mid-range 5G Android phone with 6.5 inch display and 128GB storage.",
        "price": 18999,
        "currency": "INR",
        "category": "mobile",
        "color": "black",
        "sizes": [],
    },
    {
        "id": "phone-002",
        "name": "Nova X5 5G (Blue)",
        "description": "Same Nova X5 5G in blue with 128GB storage.",
        "price": 18999,
        "currency": "INR",
        "category": "mobile",
        "color": "blue",
        "sizes": [],
    },
    {
        "id": "phone-003",
        "name": "Lite A3",
        "description": "Budget Android phone with 64GB storage and dual camera.",
        "price": 11999,
        "currency": "INR",
        "category": "mobile",
        "color": "gray",
        "sizes": [],
    },

    # Laptops
    {
        "id": "laptop-001",
        "name": "ProBook 14",
        "description": "14 inch laptop with Intel i5, 8GB RAM, 512GB SSD.",
        "price": 55990,
        "currency": "INR",
        "category": "laptop",
        "color": "silver",
        "sizes": [],
    },
    {
        "id": "laptop-002",
        "name": "ProBook 15",
        "description": "15.6 inch laptop with Intel i5, 16GB RAM, 512GB SSD.",
        "price": 65990,
        "currency": "INR",
        "category": "laptop",
        "color": "gray",
        "sizes": [],
    },
    {
        "id": "laptop-003",
        "name": "SlimBook 13",
        "description": "13 inch lightweight laptop with Ryzen 5, 8GB RAM, 512GB SSD.",
        "price": 48990,
        "currency": "INR",
        "category": "laptop",
        "color": "silver",
        "sizes": [],
    },
]

ORDERS_FILE = "ORDERS/orders.json"
os.makedirs("ORDERS", exist_ok=True)


def _load_orders() -> list[dict]:
    if not os.path.exists(ORDERS_FILE):
        return []
    try:
        with open(ORDERS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []


def _save_orders(orders: list[dict]):
    with open(ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=2)


def list_products(filters: dict | None = None) -> list[dict]:
    if filters is None:
        filters = {}

    category = filters.get("category")
    max_price = filters.get("max_price")
    color = filters.get("color")
    text = filters.get("text")

    def matches(p: dict) -> bool:
        if category and p.get("category") != category:
            return False
        if max_price and p.get("price", 0) > max_price:
            return False
        if color and p.get("color") != color:
            return False
        if text:
            t = text.lower()
            if t not in p.get("name", "").lower() and t not in p.get("description", "").lower():
                return False
        return True

    return [p for p in CATALOG if matches(p)]


def create_order(line_items: list[dict], buyer: dict | None = None) -> dict:
    orders = _load_orders()

    # Simple order id
    order_id = f"order-{len(orders) + 1}"

    items = []
    total = 0
    currency = "INR"

    for li in line_items:
        pid = li["product_id"]
        qty = li.get("quantity", 1)
        product = next((p for p in CATALOG if p["id"] == pid), None)
        if not product:
            continue
        unit_amount = product["price"]
        currency = product.get("currency", currency)
        items.append(
            {
                "product_id": pid,
                "quantity": qty,
                "unit_amount": unit_amount,
                "currency": currency,
            }
        )
        total += unit_amount * qty

    order = {
        "id": order_id,
        "items": items,
        "total": total,
        "currency": currency,
        "buyer": buyer or {},
        "status": "CONFIRMED",
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    orders.append(order)
    _save_orders(orders)
    return order
>>>>>>> Stashed changes


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
<<<<<<< Updated upstream
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
=======
            instructions="""
                You are a friendly voice shopping assistant for a small store.

                Your job:
                - Help the user browse a small product catalog: mugs, t-shirts, hoodies, mobile phones, and laptops.
                - Use the list_products_tool to search the catalog based on user requests
                  like category, color, max price, or free-text search.
                - When the user wants to buy, resolve which product they mean
                  (e.g. 'the second laptop' or 'the black hoodie'), ask for missing details like quantity or size,
                  then call the create_order_tool.
                - After creating an order, summarize it briefly: product names, quantities, total, currency.
                - If the user asks things like "What did I just buy?" or "last order", use the get_last_order tool.
                - Keep responses short and conversational.
                - If the user asks you to list all the products, use the list_products_tool and return the broadest category.
            """
>>>>>>> Stashed changes
        )
        self.last_results: list[dict] = []
        self.last_order: dict | None = None

<<<<<<< Updated upstream
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
=======
    # -------------------
    # Tools for the agent
    # -------------------

    @function_tool
    async def list_products_tool(self, ctx: RunContext, filters: dict | None = None) -> list[dict]:
        """
        List products from the catalog using simple filters.
        filters can include:
        - category: "mug", "tshirt", "hoodie", "mobile", "laptop"
        - max_price: integer
        - color: "black", "blue", etc.
        - text: free text search in name/description
        """
        results = list_products(filters)
        # Remember last list for resolving "first / second / that one"
        self.last_results = results
        return results

    @function_tool
    async def create_order_tool(self, ctx: RunContext, line_items: list[dict], buyer: dict | None = None) -> dict:
        """
        Create an order with line_items and optional buyer info.
        line_items: [{ "product_id": "...", "quantity": 1 }, ...]
        """
        order = create_order(line_items, buyer=buyer)
        self.last_order = order
        return order

    @function_tool
    async def get_last_order(self, ctx: RunContext) -> dict | None:
        """
        Return the most recent order for this session (if any).
        """
        if self.last_order is not None:
            return self.last_order

        orders = _load_orders()
        if not orders:
            return None
        return orders[-1]

    # Optional: simple text handler for special cases.
    async def on_message(self, ctx: RunContext, message: str):
        lower = message.lower().strip()
        if lower in {
            "what did i just buy?",
            "what did i just buy",
            "last order",
            "what was my last order",
        }:
            last = await self.get_last_order(ctx)
            if not last:
                await ctx.send("You don't have any orders yet.")
                return
            item_count = sum(i["quantity"] for i in last["items"])
            await ctx.send(
                f"Your last order is {item_count} item(s) for a total of {last['total']} {last['currency']}, "
                f"order ID {last['id']}."
            )
            return

        # Otherwise, fall back to normal Agent behavior (LLM + tools).
        await super().on_message(ctx, message)
>>>>>>> Stashed changes


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
            prewarm_fnc=prewarm,
        )
    )
