import time
import os
import discord
from discord.ext import tasks, commands
from pyVinted import Vinted
import json
import logging
from datetime import datetime, timezone
import asyncio
import requests

TOKEN = "INSERT DISCORD BOT TOKEN HERE"

logging.basicConfig(level=logging.DEBUG)

def load_brand_channels(filename='brand_channels.json'):
    try:
        with open(filename, 'r') as f:
            data = json.load(f)
            return data.get('channel_mappings', {})
    except Exception as e:
        logging.error(f"Error loading brand channels: {str(e)}")
        return {}

class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.sent_items = []
        self.brand_channels = load_brand_channels()
        self.brand_aliases = self._create_alias_mapping()
        self.allowed_price = 200
        self.allowed_country_code = "co.uk"
        self.vinted = Vinted()
        self.check_vinted_task = self.check_vinted

    def _create_alias_mapping(self):
        """Create a mapping of aliases to their main brand names"""
        alias_mapping = {}
        for brand, data in self.brand_channels.items():
            channel_id = data['channel_id']
            aliases = data.get('aliases', [])
            for alias in aliases:
                alias_mapping[alias.lower()] = {
                    'main_brand': brand,
                    'channel_id': channel_id
                }
        return alias_mapping

    def _find_matching_brand(self, brand_title):
        """
        Find matching brand from aliases - case-insensitive matching with improved word handling
        
        Args:
            brand_title (str): The brand title from the Vinted item
            
        Returns:
            dict: Contains 'main_brand' and 'channel_id' if match found, None otherwise
        """
        if not brand_title:
            return None
        
        # Normalize the input brand title
        brand_lower = brand_title.lower().strip()
        
        # Try exact match first
        if brand_lower in self.brand_aliases:
            return self.brand_aliases[brand_lower]
        
        # Try matching with variations
        variations = [
            brand_lower,                          # original lowercase
            brand_lower.replace(" ", ""),         # no spaces
            brand_lower.replace("ü", "u"),        # handle umlauts
            brand_lower.replace("-", " "),        # handle hyphens
            brand_lower.replace(".", ""),         # handle dots
        ]
        
        # Try each variation against the aliases
        for variation in variations:
            if variation in self.brand_aliases:
                return self.brand_aliases[variation]
        
        # If no exact match found, try partial matching for complex brand names
        for alias, data in self.brand_aliases.items():

            if " x " in brand_lower:
                brand_parts = brand_lower.split(" x ")
                if any(part.strip() == alias for part in brand_parts):
                    return data
            

            specific_brands = ["cole buxton", "acne studios", "our legacy", "canada goose", 
                             "palace", "bape", "clints", "stussy"]
            if alias in specific_brands and alias in brand_lower:
                return data
        
        logging.debug(f"No brand match found for: {brand_title} (normalized: {brand_lower})")
        return None

    async def setup_hook(self):
        logging.info("Bot is setting up...")
        self.check_vinted_task.start()

    async def on_connect(self):
        logging.info(f"Connected to Discord (latency: {self.latency * 1000:.2f} ms)")

    async def on_ready(self):
        logging.info(f'Logged in as {self.user} (ID: {self.user.id})')
        logging.info(f'Connected to {len(self.guilds)} guilds')
        print(f'Bot connected as {self.user}')
        await self.change_presence(activity=discord.Game(name="Searching Vinted"))

    def fetch_vinted_items(self):
        try:
            items = self.vinted.items.search(
                f"https://www.vinted.co.uk/vetement?order=newest_first&price_to={self.allowed_price}&currency=GBP&country_code={self.allowed_country_code}", 10, 1
            )
            logging.debug(f"Fetched items: {items}")
            return items
        except Exception as e:
            logging.error(f"Failed to fetch Vinted items: {str(e)}")
            return None

    def fetch_user_feedback(self, user_id):
        url = f"https://vinted6.p.rapidapi.com/getUserByID?country=gb&user_id={user_id}"
        headers = {
            "x-rapidapi-host": "vinted6.p.rapidapi.com",
            "x-rapidapi-key": "INSERT RAPID API KEY HERE"
        }

        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                feedback_data = response.json()
                logging.debug(f"Feedback data for user {user_id}: {feedback_data}")
                return feedback_data
            except requests.exceptions.HTTPError as http_err:
                logging.error(f"HTTP error occurred: {http_err}")
                if response.status_code == 429:
                    logging.warning("Rate limit exceeded. Retrying...")
                    time.sleep(2 ** attempt)
                else:
                    break
            except requests.exceptions.RequestException as e:
                logging.error(f"Request error: {e}")
                time.sleep(2 ** attempt)

        logging.error(f"Failed to fetch feedback for user {user_id} after retries.")
        return None

    def fetch_item_description(self, item_id):
        url = f"https://vinted6.p.rapidapi.com/getProductByID"
        
        headers = {
            "x-rapidapi-host": "vinted6.p.rapidapi.com",
            "x-rapidapi-key": "INSERT RAPID API KEY HERE"
        }
        
        params = {
            "country": "gb",
            "product_id": str(item_id)
        }

        for attempt in range(3):
            try:
                response = requests.get(url, headers=headers, params=params)
                response.raise_for_status()
                item_data = response.json()
                logging.debug(f"Description data for item {item_id}: {item_data}")
                return item_data.get('description')
            except requests.exceptions.HTTPError as http_err:
                logging.error(f"HTTP error occurred: {http_err}")
                if response.status_code == 429:
                    logging.warning("Rate limit exceeded. Retrying...")
                    time.sleep(2 ** attempt)
                else:
                    break
            except requests.exceptions.RequestException as e:
                logging.error(f"Request error: {e}")
                time.sleep(2 ** attempt)

        logging.error(f"Failed to fetch description for item {item_id} after retries.")
        return None

    def get_star_rating(self, reputation_percentage):
        # Convert the percentage into a star rating from 0 to 5
        star_count = round(reputation_percentage / 20)  # Each 20% corresponds to 1 star

        stars = '⭐️' * star_count
        return stars

    async def send_item_to_discord(self, channel, item, user_feedback):
        try:
            # Extract basic item information
            titler = item.title if item.title else "Not found"
            screen = item.photo_url if hasattr(item, 'photo_url') else "Not found"
            brand = item.brand_title if item.brand_title else "Not found"
            price = item.price if item.price else "Not found"
            url = item.url if item.url else "Not found"
            condition = item.status if hasattr(item, 'status') else "Not specified"
            size = item.size_title if item.size_title else "Not specified"

            # Fetch and use RapidAPI description
            rapid_api_description = self.fetch_item_description(item.id)
            description = rapid_api_description if rapid_api_description else item.description
            
            # Add logging for description source
            if rapid_api_description:
                logging.debug(f"Using RapidAPI description for item {item.id}")
            else:
                logging.debug(f"Using fallback description for item {item.id}")

            # Extract user feedback information
            positive_feedback = user_feedback.get('positive_feedback_count', 0) if user_feedback else 0
            neutral_feedback = user_feedback.get('neutral_feedback_count', 0) if user_feedback else 0
            negative_feedback = user_feedback.get('negative_feedback_count', 0) if user_feedback else 0
            total_feedback = positive_feedback + neutral_feedback + negative_feedback
            reputation_percentage = round(float(positive_feedback) * 100 / total_feedback, 1) if total_feedback > 0 else 0

            # Get star rating based on the reputation percentage
            star_rating = self.get_star_rating(reputation_percentage)

            # Handle timestamp
            created_at_ts = item.created_at_ts
            if isinstance(created_at_ts, datetime):
                created_at = created_at_ts
            else:
                created_at = datetime.now(timezone.utc)
            create = self.time_ago(created_at)

            # Format price
            currency = item.currency if hasattr(item, 'currency') else "£"
            price_str = f"£{price}" if currency == "GBP" else f"{price}{currency}"

            # Create embed
            embed = discord.Embed(
                title=titler,
                description=f"**[New item found!]({url})**\n\n{description}",
                color=5763719
            )
            
            # Set embed images
            embed.set_image(url=screen)
            
            # Add main item fields
            embed.add_field(name="⌛ Time Uploaded", value=create, inline=True)
            embed.add_field(name="🔖 Brand", value=brand, inline=True)
            embed.add_field(name="📏 Size", value=size, inline=True)
            embed.add_field(name="💰 Price", value=price_str, inline=True)
            embed.add_field(name="🏷 Condition", value=condition, inline=True)
            
            # Add seller rating with total feedback count
            embed.add_field(name="⭐ Seller Rating", value=f"{star_rating} ({total_feedback})", inline=True)

            # Set footer
            embed.set_footer(text="VintBot")

            # Create buttons
            view = discord.ui.View()
            view_button = discord.ui.Button(style=discord.ButtonStyle.link, label="View", url=url)
            send_message_button = discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="Send Message",
                url=f"https://www.vinted.co.uk/items/{item.id}/want_it/new?button_name=receiver_id={item.id}"
            )
            buy_button = discord.ui.Button(
                style=discord.ButtonStyle.link,
                label="Buy",
                url=f"https://www.vinted.co.uk/transaction/buy/new?source_screen=item&transaction%5Bitem_id%5D={item.id}"
            )

            # Add buttons to view
            view.add_item(view_button)
            view.add_item(send_message_button)
            view.add_item(buy_button)

            # Send message and start update task
            message = await channel.send(embed=embed, view=view)
            logging.info(f"Sent item: {item.title}")
            self.loop.create_task(self.update_time_difference(message, created_at))
                
        except Exception as e:
            logging.error(f"Failed to send item to Discord: {str(e)}")
            logging.exception("Full traceback:")

    def time_ago(self, created_at):
        now = datetime.now(timezone.utc)
        diff = now - created_at
        seconds_diff = int(diff.total_seconds())

        if seconds_diff < 60:
            return f"{seconds_diff} seconds ago"
        elif seconds_diff < 3600:
            minutes = seconds_diff // 60
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif seconds_diff < 86400:
            hours = seconds_diff // 3600
            return f"{hours} hour{'s' if hours != 1 else ''} ago"
        else:
            days = seconds_diff // 86400
            return f"{days} day{'s' if days != 1 else ''} ago"

    async def update_time_difference(self, message, created_at):
        while True:
            await asyncio.sleep(60)
            now = datetime.now(timezone.utc)
            time_diff = self.time_ago(created_at)

            embed = message.embeds[0]
            embed.set_field_at(0, name="⌛ Time Uploaded", value=time_diff, inline=True)

            try:
                await message.edit(embed=embed)
            except discord.errors.NotFound:
                break
            except discord.errors.HTTPException as e:
                if e.code == 50001:
                    logging.error(f"Missing permissions to edit message: {e}")
                    break
                elif e.code == 50034:
                    logging.info("Message is too old to edit, stopping updates")
                    break
                else:
                    logging.error(f"Failed to edit message: {e}")

    def _is_child_size(self, size_title):
        """
        Check if the size indicates children's clothing.
        
        Args:
            size_title (str): The size title from the Vinted item
            
        Returns:
            bool: True if it's a child size, False otherwise
        """
        if not size_title:
            return False
            
        size_lower = size_title.lower()
        child_indicators = ['months', 'years', 'child', 'kids', 'baby']
        
        return any(indicator in size_lower for indicator in child_indicators)

    @tasks.loop(seconds=10)
    async def check_vinted(self):
        logging.info("Checking Vinted for new items...")
        items = self.fetch_vinted_items()
        if items is None:
            return

        for item in items:
            user_id = item.raw_data.get('user', {}).get('id')
            brand_title = item.brand_title.lower() if item.brand_title else ""

            # Skip children's sizes
            if self._is_child_size(item.size_title):
                logging.debug(f"Skipping item {item.title}: Children's size detected ({item.size_title})")
                continue

            # Find matching brand and channel
            brand_match = self._find_matching_brand(brand_title)
            
            # Skip items if there is no brand match or if the user ID is missing
            if not brand_match:
                logging.debug(f"Skipping item {item.title}: No matching brand found.")
                continue
            if user_id is None:
                logging.debug(f"Skipping item {item.title}: User ID is missing.")
                continue

            # Ensure item is not already sent
            if item.id not in self.sent_items:
                channel_id = brand_match['channel_id']
                channel = self.get_channel(channel_id)

                if channel is None:
                    logging.error(f"Channel with ID {channel_id} not found.")
                    continue

                logging.debug(f"Sending item {item.id} to channel {channel.name} (Brand: {brand_match['main_brand']})")

                user_feedback = self.fetch_user_feedback(user_id)
                
                try:
                    await self.send_item_to_discord(channel, item, user_feedback)
                    self.sent_items.append(item.id)
                except Exception as e:
                    logging.error(f"Error sending item to Discord: {str(e)}")


# Initialize and run the bot
intents = discord.Intents.default()
intents.message_content = True

bot = MyBot(command_prefix='!', intents=intents)

bot.run(TOKEN)

