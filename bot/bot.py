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


async def prompt_user_for_selection(ctx, address: str) -> str:
    """
    Prompt the user to select a token pair from the list of pairs.

        Parameters:
            ctx (commands.Context): The context of the Discord command.
            address (str): The address of the token to prompt the user for selection.

        Returns:
            str: The selected token pair address.
    """
    # Get the list of pairs for the token
    pairs = await search_pairs(address)
    if not pairs:
        await ctx.send("No pairs found for the given address.")
        logging.error(f"No pairs found for the address: {address}.")
        return None

    length = len(pairs)
    markdown = await list_pairs(pairs)
    if not markdown or length == 0:
        await ctx.send("Not able to produce the list of pairs.")
        logging.error(f"Failed to produce the list of pairs for {address}.")
        return None

    # Send the list of pairs
    for m in markdown:
        await ctx.send(f"# Please select a pair from the list:\n\n{m}")

    def check(msg):
        # Ensure the response is from the same user and channel, and is a valid integer
        return (
            msg.author == ctx.author
            and msg.channel == ctx.channel
            and msg.content.isdigit()
        )

    try:
        # Wait for user response (timeout after 60 seconds)
        response = await ctx.bot.wait_for("message", check=check, timeout=60)
        selection = int(response.content)

        if 1 <= selection <= length:
            # Valid selection
            chosen_pair = pairs[selection - 1]
            await ctx.send(
                f"Selected pair: {chosen_pair.baseToken.symbol}/{chosen_pair.quoteToken.symbol} on {chosen_pair.dexId}."
            )
            return chosen_pair.pairAddress

        else:
            # Invalid range
            await ctx.send("Invalid selection. Please try again.")
            return None

    except asyncio.TimeoutError:
        # If the user doesn't respond in time
        await ctx.send("You took too long to respond. Please try again.")
        return None
    except ValueError:
        # If the user doesn't enter a number
        await ctx.send("Invalid input. Please enter a number.")
        return None


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
async def alert(
    ctx,
    address: str = None,
    metric: str = "market_cap",
    direction: str = "above",
    threshold: float = None,
    max_timeout: int = 60,
):
    """
    Set an alert for a coin's metric (default: market cap) with an optional direction and timeout.
    - Defaults to 'above' for direction and 60 minutes for timeout.
    - Maximum timeout is capped at 60 minutes.
    """
    if address is None or threshold is None:
        await ctx.send(
            "You must specify a coin, metric, direction, and threshold. Use `!alert help` for more information."
        )
        return

    if threshold <= 0:
        await ctx.send("Threshold must be a positive number.")
        logging.warning(
            f"Invalid threshold: {threshold} provided by {ctx.author} on server {ctx.guild}."
        )
        return

    if metric != "market_cap":
        await ctx.send(
            f"Unsupported metric `{metric}`. Currently, only `market_cap` is supported."
        )
        logging.warning(
            f"Unsupported metric: {metric} provided by {ctx.author} on server {ctx.guild}."
        )
        return

    if direction not in ["above", "below"]:
        await ctx.send("Direction must be either `above` or `below`.")
        logging.warning(
            f"Invalid direction: {direction} provided by {ctx.author} on server {ctx.guild}."
        )
        return

    if is_active_alert(ctx.author.id, address, metric, direction, threshold):
        await ctx.send(
            f"You are already tracking an alert for coin `{address}` with `{metric} {direction} {threshold}`."
        )
        logging.warning(
            f"Duplicate alert for coin: {address}, metric: {metric}, direction: {direction}, thresh: {threshold} by {ctx.author} on server {ctx.guild}."
        )
        return

    """if not is_valid_coin(address):
        await ctx.send(f"Invalid address: `{address}`. Please provide a valid address.")
        logging.warning(
            f"Invalid address: {address} provided by {ctx.author} on server {ctx.guild}."
        )
        return"""

    if max_timeout > 60 or max_timeout < 1:
        await ctx.send("Timeout must be between 1 and 60 minutes.")
        logging.warning(
            f"Invalid timeout: {max_timeout} provided by {ctx.author} on server {ctx.guild}."
        )
        return

    pair_address = await prompt_user_for_selection(ctx, address)
    if not pair_address:
        await ctx.send("Failed to select pair address. Please try again.")
        logging.error(
            f"Failed to select pair address for {address} by {ctx.author} on server {ctx.guild}."
        )
        return

    # Confirm alert setup
    await ctx.send(
        f"Alert set for pair `{pair_address}`:`{metric}` going `{direction}` `{threshold}`. Timeout: `{max_timeout}` minutes."
    )

    # Log the event
    logging.info(
        f"{ctx.author} on server: {ctx.guild} set an alert for pair: {pair_address}, metric: {metric}, direction: {direction}, threshold: {threshold}, timeout: {max_timeout} minutes."
    )

    # Start monitoring the coin's metric
    await monitor_coin_metric(
        ctx, pair_address, metric, direction, threshold, max_timeout
    )


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
@alert.command(name="list")
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
