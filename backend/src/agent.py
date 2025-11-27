import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Optional, List

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

# Create data directory for storing catalog and orders
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

CATALOG_FILE = DATA_DIR / "catalog.json"
RECIPES_FILE = DATA_DIR / "recipes.json"
ORDERS_FILE = DATA_DIR / "orders.json"

SAMPLE_CATALOG = {
    "items": [
        {"id": "bread_01", "name": "Whole Wheat Bread", "category": "Groceries", "price": 3.99, "unit": "loaf", "tags": ["vegan"]},
        {"id": "bread_02", "name": "White Bread", "category": "Groceries", "price": 2.99, "unit": "loaf", "tags": ["vegan"]},
        {"id": "milk_01", "name": "Whole Milk", "category": "Groceries", "price": 4.49, "unit": "gallon", "tags": []},
        {"id": "eggs_01", "name": "Large Eggs", "category": "Groceries", "price": 5.99, "unit": "dozen", "tags": []},
        {"id": "butter_01", "name": "Salted Butter", "category": "Groceries", "price": 4.99, "unit": "lb", "tags": []},
        {"id": "peanut_butter_01", "name": "Creamy Peanut Butter", "category": "Groceries", "price": 6.49, "unit": "jar", "tags": ["vegan", "gluten-free"]},
        {"id": "pasta_01", "name": "Spaghetti Pasta", "category": "Groceries", "price": 2.49, "unit": "lb", "tags": ["vegan"]},
        {"id": "pasta_sauce_01", "name": "Marinara Sauce", "category": "Groceries", "price": 3.99, "unit": "jar", "tags": ["vegan", "gluten-free"]},
        {"id": "cheese_01", "name": "Parmesan Cheese", "category": "Groceries", "price": 7.99, "unit": "8oz", "tags": ["gluten-free"]},
        {"id": "apple_01", "name": "Gala Apples", "category": "Groceries", "price": 4.99, "unit": "lb", "tags": ["vegan", "gluten-free"]},
        {"id": "chips_01", "name": "Potato Chips", "category": "Snacks", "price": 3.49, "unit": "bag", "tags": ["vegan"]},
        {"id": "cookies_01", "name": "Chocolate Chip Cookies", "category": "Snacks", "price": 4.99, "unit": "pack", "tags": []},
        {"id": "nuts_01", "name": "Mixed Nuts", "category": "Snacks", "price": 8.99, "unit": "pack", "tags": ["vegan", "gluten-free"]},
        {"id": "pizza_01", "name": "Margherita Pizza", "category": "Prepared Food", "price": 12.99, "unit": "large", "tags": []},
        {"id": "pizza_02", "name": "Pepperoni Pizza", "category": "Prepared Food", "price": 14.99, "unit": "large", "tags": []},
        {"id": "sandwich_01", "name": "Turkey Club Sandwich", "category": "Prepared Food", "price": 8.99, "unit": "each", "tags": []},
        {"id": "juice_01", "name": "Orange Juice", "category": "Beverages", "price": 5.99, "unit": "half-gallon", "tags": ["vegan", "gluten-free"]},
        {"id": "soda_01", "name": "Cola", "category": "Beverages", "price": 6.99, "unit": "12-pack", "tags": ["vegan", "gluten-free"]},
        {"id": "tomato_01", "name": "Roma Tomatoes", "category": "Groceries", "price": 3.49, "unit": "lb", "tags": ["vegan", "gluten-free"]},
        {"id": "lettuce_01", "name": "Iceberg Lettuce", "category": "Groceries", "price": 2.49, "unit": "head", "tags": ["vegan", "gluten-free"]},
        {"id": "onion_01", "name": "Yellow Onions", "category": "Groceries", "price": 1.99, "unit": "lb", "tags": ["vegan", "gluten-free"]},
        {"id": "garlic_01", "name": "Fresh Garlic", "category": "Groceries", "price": 0.99, "unit": "bulb", "tags": ["vegan", "gluten-free"]},
        {"id": "olive_oil_01", "name": "Extra Virgin Olive Oil", "category": "Groceries", "price": 12.99, "unit": "bottle", "tags": ["vegan", "gluten-free"]},
        {"id": "rice_01", "name": "Basmati Rice", "category": "Groceries", "price": 8.99, "unit": "5lb bag", "tags": ["vegan", "gluten-free"]}
    ]
}

if not CATALOG_FILE.exists():
    logger.info("Creating catalog.json with sample data...")
    with open(CATALOG_FILE, "w") as f:
        json.dump(SAMPLE_CATALOG, f, indent=2)
    logger.info("✓ Catalog file created successfully")

if not ORDERS_FILE.exists():
    logger.info("Creating orders.json...")
    with open(ORDERS_FILE, "w") as f:
        json.dump({"orders": []}, f, indent=2)
    logger.info("✓ Orders file created successfully")

if not RECIPES_FILE.exists():
    logger.info("Creating recipes.json...")
    with open(RECIPES_FILE, "w") as f:
        json.dump({"recipes": []}, f, indent=2)
    logger.info("✓ Recipes file created successfully")


conversation_state = {
    "cart": []
}


def load_catalog():
    """Load the catalog from JSON file"""
    with open(CATALOG_FILE, "r") as f:
        return json.load(f)


def load_recipes():
    """Load recipes from JSON file"""
    with open(RECIPES_FILE, "r") as f:
        return json.load(f)


def save_recipes(recipes_data):
    """Save recipes to JSON file"""
    logger.info(f"→ Saving recipe to recipes.json...")
    with open(RECIPES_FILE, "w") as f:
        json.dump(recipes_data, f, indent=2)
    logger.info(f"✓ Recipe saved successfully")


def save_order(order_data):
    """Save an order to the orders file"""
    logger.info(f"→ Saving order {order_data['order_id']} to orders.json...")
    
    with open(ORDERS_FILE, "r") as f:
        data = json.load(f)
    
    data["orders"].append(order_data)
    
    with open(ORDERS_FILE, "w") as f:
        json.dump(data, f, indent=2)
    
    logger.info(f"✓ Order {order_data['order_id']} saved successfully. Total orders: {len(data['orders'])}")


def find_item_by_name(catalog, item_name: str):
    """Find an item in the catalog by name (fuzzy matching)"""
    item_name_lower = item_name.lower()
    for item in catalog["items"]:
        if item_name_lower in item["name"].lower():
            return item
    return None


def find_recipe(recipes_data, recipe_name: str):
    """Find a recipe by name"""
    recipe_name_lower = recipe_name.lower()
    for recipe in recipes_data["recipes"]:
        if recipe_name_lower in recipe["name"].lower():
            return recipe
    return None


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are a friendly food and grocery ordering assistant for FreshMart Online Store. 

Your role is to help users:
- Browse and order groceries and prepared foods
- Add items to their cart with quantities
- Handle requests like "I need ingredients for X" by intelligently figuring out what ingredients are needed
- Modify their cart (add, remove, update quantities)
- Show what's in their cart
- Place their order when they're done

IMPORTANT: When a user asks for "ingredients for [recipe/meal]":
1. First check if the recipe exists using check_recipe_exists
2. If it exists, use add_recipe_to_cart to add those ingredients
3. If it doesn't exist, you should:
   - Use your knowledge to determine what ingredients are typically needed for that recipe/meal
   - Call add_ingredients_for_new_recipe with the recipe name and the list of ingredient names you determine
   - This will automatically create the recipe, save it, and add items to the cart
   - Confirm to the user what ingredients were added

For example:
- "peanut butter sandwich" needs: bread, peanut butter
- "pasta" needs: pasta, marinara sauce, parmesan cheese
- "breakfast" needs: eggs, bread, butter, milk
- "salad" needs: lettuce, tomatoes, olive oil
- "spaghetti" needs: spaghetti pasta, marinara sauce, parmesan cheese

Use your general knowledge to determine appropriate ingredients. Don't ask the user what ingredients they want - figure it out yourself based on common recipes.

Keep your responses conversational and natural. Always confirm when items are added or removed from the cart.
When the user is ready to checkout, confirm their final cart and total, then place the order.

CRITICAL: Always use the global conversation_state cart. Never use self.cart.""",
        )

    @function_tool
    async def check_recipe_exists(self, context: RunContext, recipe_name: str):
        """Check if a recipe already exists in the database. Use this first before creating a new recipe.
        
        Args:
            recipe_name: The name of the recipe to check
            
        Returns:
            A string indicating if the recipe exists and what ingredients it contains, or that it doesn't exist
        """
        logger.info(f"🔧 TOOL CALLED: check_recipe_exists(recipe_name='{recipe_name}')")
        
        recipes_data = load_recipes()
        recipe = find_recipe(recipes_data, recipe_name)
        
        if recipe:
            ingredients_list = ", ".join(recipe["ingredients"])
            logger.info(f"✓ Recipe found: {recipe['name']}")
            return f"Recipe exists: '{recipe['name']}' with ingredients: {ingredients_list}"
        else:
            logger.info(f"✗ Recipe not found: {recipe_name}")
            return f"Recipe does not exist: '{recipe_name}'"

    @function_tool
    async def add_ingredients_for_new_recipe(self, context: RunContext, recipe_name: str, ingredient_names: List[str]):
        """Use this when a user asks for ingredients for a recipe that doesn't exist yet. 
        This will: (1) automatically determine ingredients based on your knowledge, (2) create and save the recipe, 
        (3) add all ingredients to the cart.
        
        Args:
            recipe_name: The name of the recipe (e.g., "peanut butter sandwich", "pasta dinner")
            ingredient_names: List of ingredient names you determine are needed (e.g., ["bread", "peanut butter"])
        """
        logger.info(f"🔧 TOOL CALLED: add_ingredients_for_new_recipe(recipe='{recipe_name}', ingredients={ingredient_names})")
        
        catalog = load_catalog()
        recipes_data = load_recipes()
        
        # Use global cart
        cart = conversation_state["cart"]
        
        # Find matching items in catalog and add to cart
        added_items = []
        not_found = []
        matched_ingredient_names = []
        
        for ingredient_name in ingredient_names:
            item = find_item_by_name(catalog, ingredient_name)
            if item:
                # Add to cart
                existing = next((ci for ci in cart if ci["id"] == item["id"]), None)
                if existing:
                    existing["quantity"] += 1
                    logger.info(f"  Updated {item['name']} quantity to {existing['quantity']}")
                else:
                    cart_item = {
                        "id": item["id"],
                        "name": item["name"],
                        "price": item["price"],
                        "unit": item["unit"],
                        "quantity": 1
                    }
                    cart.append(cart_item)
                    logger.info(f"  Added {item['name']} to cart")
                
                added_items.append(item["name"])
                matched_ingredient_names.append(item["name"])
            else:
                not_found.append(ingredient_name)
                logger.warning(f"  Ingredient not found in catalog: {ingredient_name}")
        
        if not matched_ingredient_names:
            return f"Sorry, none of the ingredients for '{recipe_name}' were found in our catalog."
        
        # Create and save recipe
        recipe = {
            "name": recipe_name.lower(),
            "ingredients": matched_ingredient_names,
            "created_at": datetime.now().isoformat()
        }
        
        recipes_data["recipes"].append(recipe)
        save_recipes(recipes_data)
        
        items_list = ", ".join(added_items)
        response = f"Added ingredients for {recipe_name}: {items_list} to your cart."
        
        if not_found:
            response += f" Note: These ingredients weren't available: {', '.join(not_found)}."
        
        logger.info(f"✓ Recipe created and items added to cart. Cart now has {len(cart)} items")
        return response

    @function_tool
    async def add_recipe_to_cart(self, context: RunContext, recipe_name: str, servings: int = 1):
        """Add all ingredients from an EXISTING saved recipe to the cart. 
        Only use this after confirming the recipe exists with check_recipe_exists.
        
        Args:
            recipe_name: The name of the existing recipe
            servings: Number of servings (multiplies ingredient quantities, default is 1)
        """
        logger.info(f"🔧 TOOL CALLED: add_recipe_to_cart(recipe='{recipe_name}', servings={servings})")
        
        recipes_data = load_recipes()
        recipe = find_recipe(recipes_data, recipe_name)
        
        if not recipe:
            logger.error(f"✗ Recipe not found: {recipe_name}")
            return f"Error: Recipe '{recipe_name}' not found. Use check_recipe_exists first."
        
        catalog = load_catalog()
        cart = conversation_state["cart"]
        added_items = []
        
        for ingredient_name in recipe["ingredients"]:
            item = find_item_by_name(catalog, ingredient_name)
            if item:
                # Check if already in cart
                existing = next((ci for ci in cart if ci["id"] == item["id"]), None)
                if existing:
                    existing["quantity"] += servings
                    logger.info(f"  Updated {item['name']} quantity to {existing['quantity']}")
                else:
                    cart_item = {
                        "id": item["id"],
                        "name": item["name"],
                        "price": item["price"],
                        "unit": item["unit"],
                        "quantity": servings
                    }
                    cart.append(cart_item)
                    logger.info(f"  Added {item['name']} to cart")
                added_items.append(item["name"])
        
        items_list = ", ".join(added_items)
        logger.info(f"✓ Recipe ingredients added. Cart now has {len(cart)} items")
        return f"Added ingredients for {recipe['name']}: {items_list} to your cart."

    @function_tool
    async def add_to_cart(self, context: RunContext, item_name: str, quantity: int = 1):
        """Add a specific item to the shopping cart.
        
        Args:
            item_name: The name of the item to add (e.g., "bread", "milk", "peanut butter")
            quantity: The quantity to add (default is 1)
        """
        logger.info(f"🔧 TOOL CALLED: add_to_cart(item='{item_name}', quantity={quantity})")
        
        catalog = load_catalog()
        item = find_item_by_name(catalog, item_name)
        
        if not item:
            logger.warning(f"✗ Item not found: {item_name}")
            return f"Sorry, I couldn't find '{item_name}' in our catalog. Could you try a different item?"
        
        cart = conversation_state["cart"]
        
        # Check if item already in cart
        existing = next((ci for ci in cart if ci["id"] == item["id"]), None)
        if existing:
            existing["quantity"] += quantity
            logger.info(f"✓ Updated {item['name']} quantity to {existing['quantity']}")
            return f"Updated {item['name']} quantity to {existing['quantity']} {item['unit']}s. Price: ${item['price'] * existing['quantity']:.2f}"
        else:
            cart_item = {
                "id": item["id"],
                "name": item["name"],
                "price": item["price"],
                "unit": item["unit"],
                "quantity": quantity
            }
            cart.append(cart_item)
            logger.info(f"✓ Added {item['name']} to cart. Cart now has {len(cart)} items")
            return f"Added {quantity} {item['unit']}(s) of {item['name']} to your cart at ${item['price']:.2f} each."

    @function_tool
    async def remove_from_cart(self, context: RunContext, item_name: str):
        """Remove an item from the shopping cart.
        
        Args:
            item_name: The name of the item to remove
        """
        logger.info(f"🔧 TOOL CALLED: remove_from_cart(item='{item_name}')")
        
        cart = conversation_state["cart"]
        item_to_remove = None
        
        for cart_item in cart:
            if item_name.lower() in cart_item["name"].lower():
                item_to_remove = cart_item
                break
        
        if item_to_remove:
            cart.remove(item_to_remove)
            logger.info(f"✓ Removed {item_to_remove['name']} from cart. Cart now has {len(cart)} items")
            return f"Removed {item_to_remove['name']} from your cart."
        else:
            logger.warning(f"✗ Item not found in cart: {item_name}")
            return f"I couldn't find '{item_name}' in your cart."

    @function_tool
    async def update_quantity(self, context: RunContext, item_name: str, new_quantity: int):
        """Update the quantity of an item in the cart.
        
        Args:
            item_name: The name of the item to update
            new_quantity: The new quantity (must be greater than 0)
        """
        logger.info(f"🔧 TOOL CALLED: update_quantity(item='{item_name}', new_quantity={new_quantity})")
        
        if new_quantity <= 0:
            return "Quantity must be greater than 0. Use remove_from_cart to remove items."
        
        cart = conversation_state["cart"]
        
        for cart_item in cart:
            if item_name.lower() in cart_item["name"].lower():
                old_qty = cart_item["quantity"]
                cart_item["quantity"] = new_quantity
                logger.info(f"✓ Updated {cart_item['name']} from {old_qty} to {new_quantity}")
                return f"Updated {cart_item['name']} from {old_qty} to {new_quantity} {cart_item['unit']}(s)."
        
        logger.warning(f"✗ Item not found in cart: {item_name}")
        return f"I couldn't find '{item_name}' in your cart."

    @function_tool
    async def show_cart(self, context: RunContext):
        """Show all items currently in the shopping cart with quantities and prices."""
        logger.info(f"🔧 TOOL CALLED: show_cart()")
        
        cart = conversation_state["cart"]
        
        if not cart:
            logger.info("Cart is empty")
            return "Your cart is empty. What would you like to order?"
        
        cart_summary = "Here's what's in your cart:\n"
        total = 0
        for item in cart:
            item_total = item["price"] * item["quantity"]
            total += item_total
            cart_summary += f"- {item['name']}: {item['quantity']} {item['unit']}(s) at ${item['price']:.2f} each = ${item_total:.2f}\n"
        
        cart_summary += f"\nTotal: ${total:.2f}"
        logger.info(f"✓ Cart has {len(cart)} items, total: ${total:.2f}")
        return cart_summary

    @function_tool
    async def place_order(self, context: RunContext, customer_name: Optional[str] = None, delivery_address: Optional[str] = None):
        """Place the order and save it to file. Call this when the user is ready to checkout.
        
        Args:
            customer_name: Optional customer name
            delivery_address: Optional delivery address
        """
        logger.info(f"🔧 TOOL CALLED: place_order(customer='{customer_name}', address='{delivery_address}')")
        
        cart = conversation_state["cart"]
        
        if not cart:
            logger.warning("✗ Cannot place order - cart is empty")
            return "Your cart is empty. Please add some items before placing an order."
        
        # Calculate total
        total = sum(item["price"] * item["quantity"] for item in cart)
        
        # Create order object
        order = {
            "order_id": f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "customer_name": customer_name or "Guest",
            "delivery_address": delivery_address or "Not provided",
            "items": cart.copy(),
            "total": round(total, 2),
            "status": "placed"
        }
        
        # Save order
        save_order(order)
        
        # Clear cart
        conversation_state["cart"] = []
        
        logger.info(f"✓ Order {order['order_id']} placed successfully. Total: ${order['total']:.2f}")
        return f"Order placed successfully! Your order ID is {order['order_id']}. Total: ${order['total']:.2f}. Thank you for shopping with FreshMart!"


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


async def entrypoint(ctx: JobContext):
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

    await session.start(
        agent=Assistant(),
        room=ctx.room,
        room_input_options=RoomInputOptions(
            noise_cancellation=noise_cancellation.BVC(),
        ),
    )

    await ctx.connect()


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, prewarm_fnc=prewarm))