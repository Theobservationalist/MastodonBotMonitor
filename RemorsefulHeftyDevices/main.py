import asyncio
import json
import logging
import pytz
from datetime import datetime
import aiohttp

# Logging Configuration
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# API & Filtering Config
API_URL = "https://debot.ai/api/dashboard/chain/recommend/hot_token"
PARAMS = {
    "chain": "solana",
    "duration": "1m",
    "sort_field": "creation_timestamp",
    "sort_order": "desc",
    "filter": json.dumps({
        "liquidity": [50000, 1000000],
        "mkt_cap": [200000, 900000],
        "holders": [400, 1e+308],
        "volume": [80000, 1e+308],
    }),
    "is_hide_honeypot": "true",
}

# Telegram Bot Config
TELEGRAM_BOT_TOKEN = "8030308483:AAHgaZvj3yjoHanlHOYOeR2P10nUttAVqk0"
SUBSCRIPTION_FILE = "subscribed_chats.json"

# Timezone
MOROCCO_TZ = pytz.timezone("Africa/Casablanca")

class TokenMonitor:
    def __init__(self):
        self.seen_addresses = set()
        self.subscribed_chats = set()
        self.load_subscriptions()
        self.last_update_id = 0

    def load_subscriptions(self):
        """Load subscribed chat IDs from file"""
        try:
            with open(SUBSCRIPTION_FILE, "r") as f:
                self.subscribed_chats = set(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            self.subscribed_chats = set()

    def save_subscriptions(self):
        """Save subscribed chat IDs to file"""
        with open(SUBSCRIPTION_FILE, "w") as f:
            json.dump(list(self.subscribed_chats), f)

    def get_time_ago(self, creation_ts):
        """Convert timestamp to human-readable relative time"""
        now = datetime.now(MOROCCO_TZ)
        created_at = datetime.fromtimestamp(creation_ts).astimezone(MOROCCO_TZ)
        delta = now - created_at

        if delta.total_seconds() < 60:
            return "Just now"
        elif delta.total_seconds() < 3600:
            return f"{int(delta.total_seconds() // 60)}m ago"
        elif delta.total_seconds() < 86400:
            return f"{int(delta.total_seconds() // 3600)}h ago"
        else:
            return f"{int(delta.total_seconds() // 86400)}d ago"

    async def fetch_token_data(self):
        """Fetch new tokens from API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(API_URL, params=PARAMS) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("data"):
                            token = data["data"][0]
                            return {
                                "address": token["address"],
                                "symbol": token["symbol"],
                                "fdv": token["market_info"]["fdv"],
                                "price": token["market_info"]["price"],
                                "holders": token["market_info"]["holders"],
                                "liquidity": token["pair_summary_info"]["liquidity"],
                                "volume": token["market_info"]["volume"],
                                "logo": token.get("logo", ""),
                                "created_ago": self.get_time_ago(token["creation_timestamp"]),
                                "detected_at": datetime.now(MOROCCO_TZ).strftime("%H:%M:%S"),
                                "twitter": token.get("social_info", {}).get("twitter", ""),
                                "telegram": token.get("social_info", {}).get("telegram", ""),
                                "website": token.get("social_info", {}).get("website", ""),
                            }
        except Exception as e:
            logger.error(f"Error fetching token data: {e}")
        return None

    async def handle_updates(self):
        """Poll Telegram for updates and handle commands"""
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        while True:
            try:
                params = {"offset": self.last_update_id + 1, "timeout": 10}
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params) as response:
                        data = await response.json()
                        if data.get("ok"):
                            for update in data["result"]:
                                self.last_update_id = update["update_id"]
                                if "message" in update and "text" in update["message"]:
                                    message = update["message"]
                                    chat_id = message["chat"]["id"]
                                    text = message["text"].lower()

                                    if text == "/start":
                                        if chat_id not in self.subscribed_chats:
                                            self.subscribed_chats.add(chat_id)
                                            self.save_subscriptions()
                                            await self.send_welcome_message(chat_id)
                                    elif text == "/stop":
                                        if chat_id in self.subscribed_chats:
                                            self.subscribed_chats.remove(chat_id)
                                            self.save_subscriptions()

            except Exception as e:
                logger.error(f"Error handling updates: {e}")
            await asyncio.sleep(1)

    async def send_welcome_message(self, chat_id):
        """Send welcome message to new subscribers"""
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        text = (
            "🚀 Welcome to Mastodon Scan Alerts!\n\n"
            "You'll now receive real-time alerts about new tokens.\n"
            "Use /stop to stop receiving alerts."
        )

        params = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, params=params) as response:
                    if response.status == 200:
                        logger.info(f"Welcome message sent to {chat_id}")
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")

    async def send_telegram_message(self, token_data):
        """Send alert to all subscribed users"""
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        caption = (f"🚀 *MASTODON SCAN ALERT* 🚀\n\n"
                   f"✨ *Symbol:* {token_data['symbol']}\n"
                   f"🔗 *Address:* `{token_data['address']}`\n"
                   f"📊 *Market Cap:* ${token_data['fdv']:,.2f}\n"
                   f"💰 *Price:* ${token_data['price']:.4f}\n"
                   f"💸 *24h Volume:* ${token_data['volume']:,.0f}\n"
                   f"👥 *Holders:* {token_data['holders']:,}\n"
                   f"🏦 *Liquidity:* ${token_data['liquidity']:,.0f}\n\n"
                   f"⏰ *Created:* {token_data['created_ago']}\n"
                   f"⏱️ *Detected:* {token_data['detected_at']}\n\n")

        # Social links
        social_links = []
        if token_data["twitter"]:
            social_links.append(f"🐦 Twitter: [Link]({token_data['twitter']})")
        if token_data["telegram"]:
            social_links.append(f"📢 Telegram: [Link]({token_data['telegram']})")
        if token_data["website"]:
            social_links.append(f"🌐 Website: [Link]({token_data['website']})")

        if social_links:
            caption += "\n".join(social_links) + "\n\n"

        caption += "⚡ *High potential runner detected!* ⚡"

        for chat_id in self.subscribed_chats:
            try:
                async with aiohttp.ClientSession() as session:
                    params = {
                        "chat_id": chat_id,
                        "photo": token_data["logo"],
                        "caption": caption,
                        "parse_mode": "Markdown",
                    }
                    async with session.post(url, params=params) as response:
                        if response.status == 200:
                            logger.info(f"Alert sent to {chat_id}")
                        else:
                            logger.error(f"Failed to send to {chat_id}: {await response.text()}")
            except Exception as e:
                logger.error(f"Error sending to {chat_id}: {e}")

    async def monitor_tokens(self):
        """Main monitoring loop"""
        while True:
            token_data = await self.fetch_token_data()
            if token_data:
                if token_data["address"].lower().endswith("pump"):
                    if token_data["address"] not in self.seen_addresses:
                        self.seen_addresses.add(token_data["address"])
                        await self.send_telegram_message(token_data)
            await asyncio.sleep(15)

async def main():
    monitor = TokenMonitor()
    await asyncio.gather(
        monitor.monitor_tokens(),
        monitor.handle_updates()
    )

if __name__ == "__main__":
    asyncio.run(main())