# ------------------------------------------------------------
# DOTENV

import os

from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Access variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")  # Default to 'localhost' if not set
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))  # Default to 6379 if not set

# ------------------------------------------------------------
# LOGGING

import logging

logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for more detailed logs
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),  # Save logs to a file
        logging.StreamHandler(),  # Output logs to the console
    ],
)

# ------------------------------------------------------------
# REDIS SESSIONS

import redis

redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def is_active_alert(
    user_id: str, address: str, metric: str, direction: str, threshold: float
) -> bool:
    # Check if the user is already tracking the coin

    # print ttl
    print(redis_client.ttl(f"{user_id}:{address}:{metric}:{direction}:{threshold}"))
    return redis_client.exists(f"{user_id}:{address}:{metric}:{direction}:{threshold}")


def add_alert_to_redis(
    user_id: str,
    address: str,
    metric: str,
    direction: str,
    threshold: float,
    max_timeout: int,
):

    print(f"max_timeout: {max_timeout}")

    # Store the tracking data in Redis with TTL
    redis_client.setex(
        f"{user_id}:{address}:{metric}:{direction}:{threshold}",
        max_timeout * 60,
        "tracking",
    )  # 1 key for user + address pair


def remove_alert_from_redis(
    user_id: str,
    address: str,
    metric: str,
    direction: str,
    threshold: float,
):
    # Remove the tracking information from Redis
    redis_client.delete(f"{user_id}:{address}:{metric}:{direction}:{threshold}")


def get_user_alerts(user_id: str) -> list:
    # Get all tracking information for a user
    keys = redis_client.keys(f"{user_id}*")
    return keys


def remove_user_alerts(user_id: str, address: str = None):
    # Remove all tracking information for a user
    keys = get_user_alerts(user_id)
    if address:
        keys = [key for key in keys if address in key]
    redis_client.delete(*keys)


# ------------------------------------------------------------
# COIN TRACKING

from data import get_market_cap, list_pairs, search_pairs
from models import Pair


async def prompt_user_for_selection(ctx, queries) -> Pair:
    """
    Prompt the user to select a token pair from the list of pairs.

        Parameters:
            ctx (commands.Context): The context of the Discord command.
            queries (list): The list of queries to search for the token pair.
        Returns:
            Pair: The selected coin pair
    """
    # Get the list of pairs for the token
    query = " ".join(queries)
    pairs = await search_pairs(query)
    if not pairs:
        await ctx.send("No pairs found")
        logging.error(f"No pairs found for: {query}.")
        return None

    length = len(pairs)
    markdown = await list_pairs(pairs)
    if not markdown or length == 0:
        await ctx.send("Not able to produce the list of pairs.")
        logging.error(f"Failed to produce the list of pairs for {address}.")
        return None

    if length == 1:
        # If only one pair is found, select it automatically
        await ctx.send(
            f"Pair selected: `{pairs[0].baseToken.symbol}/{pairs[0].quoteToken.symbol}` on `{pairs[0].dexId}`.\n{markdown[0]}"
        )
        return pairs[0]

    # Send the list of pairs
    prompt = "# Please select a pair from the list:\n"
    for m in markdown:
        await ctx.send(f"{prompt}\n{m}")
        prompt = ""

    def check(msg):
        # Ensure the response is from the same user and channel, and is a valid integer
        return (
            msg.author == ctx.author
            and msg.channel == ctx.channel
            and msg.content.isdigit()
        )

    try:
        # Wait for user response (timeout after 60 seconds)
        attempts = 3
        while attempts > 0:
            response = await ctx.bot.wait_for("message", check=check, timeout=60)
            if response.content == "cancel":
                await ctx.send("Selection cancelled.")
                return None

            if not response.content.isdigit():
                attempts -= 1
                if attempts > 0:
                    await ctx.send("Invalid input. Please enter a number.")
                continue

            if attempts == 0:
                await ctx.send("Failed to select a pair. Alert cancelled.")
                return None

            selection = int(response.content)

            if 1 <= selection <= length:  # Valid selection
                chosen_pair = pairs[selection - 1]
                await ctx.send(
                    f"Selected pair: `{chosen_pair.baseToken.symbol}/{chosen_pair.quoteToken.symbol}` on `{chosen_pair.dexId}`."
                )
                return chosen_pair

            else:  # Invalid range
                await ctx.send(
                    f"Invalid range. Please enter a number between 1 and {length}."
                )
                attempts -= 1

        await ctx.send("Failed to select a pair. Alert cancelled.")

    except asyncio.TimeoutError:
        # If the user doesn't respond in time
        await ctx.send("You took too long to respond. Alert cancelled.")
        return None


async def prompt_user_for_metric(ctx, pair) -> tuple:
    """
    Prompt the user to select a metric and threshold for the alert.

            Parameters:
                ctx (commands.Context): The context of the Discord command.
                pair (Pair): The selected pair for the alert.

            Returns:
                tuple: The selected metric and threshold
    """

    metric = None
    direction = None
    threshold = None

    def check(
        msg,
    ):  # Ensure the response is from the same user and channel, and is a valid integer
        return msg.author == ctx.author and msg.channel == ctx.channel

    try:
        # Prompt the user for metric selection ----------------------------------------------
        attempts = 3
        valid_metrics = {
            "1": "market_cap",
            "market cap": "market_cap",
            "marketcap": "market_cap",
            "mcap": "market_cap",
            "market": "market_cap",
        }

        await ctx.send(
            f"# Please select a metric for `{pair.baseToken.symbol}/{pair.quoteToken.symbol}`:\n"
            "1. Market Cap 🧢\n"
        )

        while attempts > 0:
            response = await ctx.bot.wait_for("message", check=check, timeout=60)
            if response.content == "cancel":
                await ctx.send("Selection cancelled.")
                return None, None, None

            if response.content not in valid_metrics:
                attempts -= 1
                if attempts > 0:
                    await ctx.send(
                        "Invalid input. Please enter a valid metric.\n1. Market Cap 🧢"
                    )

            if attempts == 0:
                await ctx.send("Failed to select a metric. Alert cancelled.")
                return None, None, None

            metric = valid_metrics[response.content]
            break

        # Prompt the user for direction and threshold ----------------------------------------
        attempts = 3
        valid_directions = {"above": "above", "below": "below"}

        await ctx.send(
            f"📈 Monitoring market cap... 📉\n# Please enter a direction and threshold value for the market cap of pair `{pair.baseToken.symbol}/{pair.quoteToken.symbol}`."
            "Examples:\n`above 1000000`\n`below 500000`."
        )

        while attempts > 0:
            response = await ctx.bot.wait_for("message", check=check, timeout=60)
            if response.content == "cancel":
                await ctx.send("Selection cancelled.")
                return None, None, None

            parts = response.content.split()
            if len(parts) != 2:
                attempts -= 1
                if attempts > 0:
                    await ctx.send(
                        "Invalid input. Please enter 'above' or 'below' and a threshold value."
                        "Examples:\n`above 1000000`\n`below 500000`."
                    )
                continue
            if parts[0] not in valid_directions:
                attempts -= 1
                if attempts > 0:
                    await ctx.send(
                        "Invalid input. Please enter 'above' or 'below' and a threshold value."
                        "Examples:\n`above 1000000`\n`below 500000`."
                    )
                continue

            direction = valid_directions[parts[0]]

            try:
                threshold = float(parts[1])
                if threshold <= 0:
                    attempts -= 1
                    if attempts > 0:
                        await ctx.send(
                            "Invalid direction. Please enter `above` or `below` and a valid threshold."
                        )
                    continue
                return metric, direciton, threshold

            except ValueError:
                attempts -= 1
                if attempts > 0:
                    await ctx.send(
                        "Invalid direction. Please enter `above` or `below` and a valid threshold."
                    )
                continue

            if attempts == 0:
                await ctx.send(
                    "Failed to select a direction and threshold. Alert cancelled."
                )
                return None, None, None

    except asyncio.TimeoutError:
        await ctx.send("You took too long to respond. Alert cancelled.")
        return None, None, None


# Utility function to get the value of a metric for a coin
async def get_metric_value(address: str, metric: str) -> float:
    if metric != "market_cap":
        logging.warning(f"Unsupported metric: {metric}.")
        return None

    return await get_market_cap(address)


async def monitor_coin_metric(
    ctx, address: str, metric: str, direction: str, threshold: float, max_timeout: int
):
    """
    Monitor a coin's metric and send an alert when the threshold is crossed in the specified direction.
    """

    add_alert_to_redis(
        ctx.author.id, address, metric, direction, threshold, max_timeout
    )

    failed_attempts = 0
    max_attempts = 3
    while is_active_alert(ctx.author.id, address, metric, direction, threshold):
        current_value = await get_metric_value(address, metric)
        if current_value is None:
            failed_attempts += 1
            if failed_attempts >= max_attempts:
                logging.error(
                    f"Failed to fetch {metric} for {address} after {max_attempts} consequitive attempts."
                )
                remove_alert_from_redis(
                    ctx.author.id, address, metric, direction, threshold
                )
                await ctx.send(
                    f"{max_attempts}: Failed to fetch `{metric}` for `{address}`. Alert removed."
                )
                return

            await ctx.send(
                f"{failed_attempts}: Failed to fetch `{metric}` for `{address}`. Retrying..."
            )
            logging.warning(f"Failed to fetch {metric} for {address}. Retrying...")
            await asyncio.sleep(5)
            continue

        failed_attempts = 0  # Reset failed attempts
        if (direction == "above" and current_value > threshold) or (
            direction == "below" and current_value < threshold
        ):

            remove_alert_from_redis(
                ctx.author.id, address, metric, direction, threshold
            )
            await ctx.send(
                f"{ctx.author.mention} Alert! `{address}` `{metric}` is now `{direction}` `{threshold}`. Current value: `{current_value}`."
            )
            return

        await asyncio.sleep(5)  # Wait for 5 sec before checking again

    await ctx.send(
        f"Timeout reached for alert on `{address}` `{metric}`. `{metric}` did not go `{direction}` `{threshold}`."
    )
    logging.info(
        f"Timeout reached for alert on {address} {metric}. {metric} did not go {direction} {threshold}."
    )


# ------------------------------------------------------------
# DISCORD BOT
import asyncio

import discord
from discord.ext import commands

# Define the intents
intents = discord.Intents.default()
intents.message_content = True  # Enable message content intent

# Create a bot instance with the necessary intents
bot = commands.Bot(command_prefix="!", intents=intents)


# Define the 'alert' group of commands
@bot.group(invoke_without_command=True)
async def alert(ctx, *queries):
    """
    Set an alert for a coin's metric (default: market cap) with an optional direction and timeout.
    - Defaults to 'above' for direction and 60 minutes for timeout.
    - Maximum timeout is capped at 60 minutes.
    """
    if not queries:
        ctx.send(
            f"** Usage: `!alert <pair address>`\n** Usage: `!alert <query search>`"
        )
        return

    pair = await prompt_user_for_selection(ctx, queries)
    if not pair or pair.pairAddress:
        logging.error(
            f"Failed to select pair address - {ctx.author} on server {ctx.guild}."
        )
        return

    metric, dir, thresh = await prompt_user_for_metric(ctx, pair)

    print(f"metric: {metric}, dir: {dir}, thresh: {thresh}")

    if not metric or not dir or not thresh:
        logging.error(
            f"Failed to select metric and threshold for {pair.pairAddress} by {ctx.author} on server {ctx.guild}."
        )
        return

    # Confirm alert setup
    await ctx.send(
        f"Alert set for pair `{pair.baseToken.symbol}/{pair.quoteToken.symbol}`:`{metric}` going `{dir}` `{thresh}`. Timeout: `{max_timeout}` minutes."
    )

    # Log the event
    logging.info(
        f"{ctx.author} on server: {ctx.guild} set an alert for pair:{pair.baseToken.symbol}/{pair.quoteToken.symbol} addr: {pair.pairAddress}, metric: {metric}, direction: {dir}, threshold: {thresh}, timeout: {max_timeout} minutes."
    )

    # Start monitoring the coin's metric
    await monitor_coin_metric(ctx, pair.pairAddress, metric, dir, thresh, max_timeout)


# Subcommand for 'remove'
@alert.command(name="remove")
async def alert_remove(ctx, address: str = None):
    """
    Remove all alerts set for the specified coin.
    """
    if address == "all":
        remove_user_alerts(ctx.author.id, None)
        await ctx.send("All alerts have been removed.")
        logging.info(f"All alerts removed by {ctx.author} on server {ctx.guild}.")
        return
    """if not is_valid_coin(address) or address is None:
        await ctx.send(f"Invalid address: `{address}`. Please provide a valid address.")
        logging.warning(
            f"Invalid address: {address} provided by {ctx.author} on server {ctx.guild}."
        )
        return"""

    remove_user_alerts(ctx.author.id, address)

    await ctx.send(f"All alerts for coin `{address}` have been removed.")
    logging.info(
        f"All alerts for coin {address} removed by {ctx.author} on server {ctx.guild}."
    )


# Subcommand for 'list'
@alert.command(name="list", aliases=["ls"])
async def alert_list(ctx):
    """
    List all alerts set by the user.
    """
    alerts = get_user_alerts(ctx.author.id)
    if not alerts:
        await ctx.send("You have not set any alerts.")
        return

    alert_list = "\n".join([f"- {alert}" for alert in alerts])
    await ctx.send(f"Your alerts:\n{alert_list}")


# Subcommand for 'help'
@alert.command(name="help")
async def alert_help(ctx):
    """
    Provides help for the 'alert' command.
    """
    help_text = (
        "`!alert <address> <metric> <direction> <threshold>`\n**Sets an alert for a coin's metric (default: market cap).**\n\n"
        "`!alert <address> <metric> <direction> <threshold> <max_timeout>`\n**Sets an alert with a custom timeout (capped at 60 minutes).**\n\n"
        "`!alert remove <address>`\n**Removes all alerts set for the specified coin.**\n\n"
        "`!alert list`\n**Lists all alerts set by the user.**\n\n"
        "**Parameters:**\n"
        "`metric` : **Currently supports only `market_cap`.**\n"
        "`direction` : **`above` or `below`.**\n"
        "`!alert help` : **Displays help information for the alert command.**"
    )
    await ctx.send(help_text)


# Example on_ready event
@bot.event
async def on_ready():
    logging.info(f"Bot is logged in: {bot.user}.")


"""@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        if not ctx.message.content.startswith("!alert"):
            return  # Do nothing for commands that are not `!alert`

        # Handle invalid commands under the `!alert` prefix
        await ctx.send(
            "Sorry, I don't recognize that command. Type `!alert help` for a list of available commands."
        )
    else:
        # Log any other errors for debugging
        logging.error(f"Error occurred: {error} in command: {ctx.message.content}")"""


# Run the bot with discord token
bot.run(DISCORD_TOKEN)
