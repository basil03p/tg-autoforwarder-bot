import os
import asyncio
from telethon import TelegramClient, events, Button
from telethon.tl.types import InputPeerChannel
from telethon.errors import FloodWaitError, ChannelPrivateError
import logging
import json
from datetime import datetime
from aiohttp import web

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration from environment variables
API_ID = os.environ.get('API_ID')
API_HASH = os.environ.get('API_HASH')
BOT_TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_IDS = [int(x) for x in os.environ.get('ADMIN_IDS', '').split(',') if x]

# Data storage
CONFIG_FILE = 'config.json'

def load_config():
    """Load configuration from file"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading config: {e}")
    return {}

def save_config(config):
    """Save configuration to file"""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving config: {e}")

# Initialize bot
bot = TelegramClient('bot', API_ID, API_HASH).start(bot_token=BOT_TOKEN)

# User sessions storage
user_sessions = {}

class UserSession:
    def __init__(self, user_id):
        self.user_id = user_id
        self.source_channel = None
        self.target_channel = None
        self.mode = 'idle'  # idle, live, selective
        self.forward_count = 0
        
    def to_dict(self):
        return {
            'source_channel': self.source_channel,
            'target_channel': self.target_channel,
            'mode': self.mode,
            'forward_count': self.forward_count
        }

def get_session(user_id):
    """Get or create user session"""
    if user_id not in user_sessions:
        config = load_config()
        user_config = config.get(str(user_id), {})
        session = UserSession(user_id)
        if user_config:
            session.source_channel = user_config.get('source_channel')
            session.target_channel = user_config.get('target_channel')
            session.mode = user_config.get('mode', 'idle')
        user_sessions[user_id] = session
    return user_sessions[user_id]

def save_session(user_id):
    """Save user session to config"""
    if user_id in user_sessions:
        config = load_config()
        config[str(user_id)] = user_sessions[user_id].to_dict()
        save_config(config)

def is_admin(user_id):
    """Check if user is admin"""
    return user_id in ADMIN_IDS or len(ADMIN_IDS) == 0

async def check_bot_permissions(channel_id, permission_type="source"):
    """Check if bot is admin in the channel"""
    try:
        channel = await bot.get_entity(channel_id)
        me = await bot.get_me()
        participant = await bot.get_permissions(channel, me)
        
        if not participant.is_admin:
            return False, f"❌ Bot is not admin in {permission_type} channel!\n\n⚠️ Please make the bot an admin in the channel."
        
        return True, "✅ Bot has admin permissions"
    except Exception as e:
        return False, f"❌ Error checking permissions: {str(e)}"

@bot.on(events.NewMessage(pattern='/start'))
async def start_handler(event):
    """Handle /start command"""
    if not is_admin(event.sender_id):
        await event.respond("⛔ You are not authorized to use this bot.")
        return
    
    session = get_session(event.sender_id)
    
    buttons = [
        [Button.inline("📤 Set Source Channel", b"set_source")],
        [Button.inline("📥 Set Target Channel", b"set_target")],
        [Button.inline("⚙️ Forwarding Modes", b"modes")],
        [Button.inline("📊 Status", b"status")],
        [Button.inline("ℹ️ Help", b"help")]
    ]
    
    # Show preset values if available
    preset_info = ""
    if session.source_channel or session.target_channel:
        preset_info = "\n**📋 Saved Configuration:**\n"
        if session.source_channel:
            preset_info += f"📤 Source: `{session.source_channel}`\n"
        if session.target_channel:
            preset_info += f"📥 Target: `{session.target_channel}`\n"
    
    await event.respond(
        "**🤖 Telegram Forwarder Bot**\n\n"
        "Welcome! I can forward messages from one channel to another."
        f"{preset_info}\n"
        "Choose an option below:",
        buttons=buttons
    )

@bot.on(events.CallbackQuery(pattern=b"main_menu"))
async def main_menu(event):
    """Show main menu"""
    buttons = [
        [Button.inline("📤 Set Source Channel", b"set_source")],
        [Button.inline("📥 Set Target Channel", b"set_target")],
        [Button.inline("⚙️ Forwarding Modes", b"modes")],
        [Button.inline("📊 Status", b"status")],
        [Button.inline("ℹ️ Help", b"help")]
    ]
    
    await event.edit(
        "**🤖 Telegram Forwarder Bot**\n\n"
        "Choose an option:",
        buttons=buttons
    )

@bot.on(events.CallbackQuery(pattern=b"set_source"))
async def set_source(event):
    """Prompt user to set source channel"""
    await event.answer()
    await event.respond(
        "📤 **Set Source Channel**\n\n"
        "Please send me the source channel username or ID.\n"
        "Examples:\n"
        "• @channelname\n"
        "• -1001234567890\n\n"
        "Or forward a message from the channel."
    )
    session = get_session(event.sender_id)
    session.mode = 'awaiting_source'

@bot.on(events.CallbackQuery(pattern=b"set_target"))
async def set_target(event):
    """Prompt user to set target channel"""
    await event.answer()
    await event.respond(
        "📥 **Set Target Channel**\n\n"
        "Please send me the target channel username or ID.\n"
        "Examples:\n"
        "• @channelname\n"
        "• -1001234567890\n\n"
        "Or forward a message from the channel."
    )
    session = get_session(event.sender_id)
    session.mode = 'awaiting_target'

@bot.on(events.CallbackQuery(pattern=b"modes"))
async def show_modes(event):
    """Show forwarding modes"""
    session = get_session(event.sender_id)
    
    if not session.source_channel or not session.target_channel:
        await event.answer("⚠️ Please set source and target channels first!", alert=True)
        return
    
    buttons = [
        [Button.inline("🔴 Live Mode (Auto-forward new)", b"mode_live")],
        [Button.inline("📦 Send ALL Files & Messages", b"mode_send_all")],
        [Button.inline("📝 Forward Range", b"mode_range")],
        [Button.inline("🔢 Forward Till Message", b"mode_till_msg")],
        [Button.inline("📁 Forward Till File", b"mode_till_file")],
        [Button.inline("⏸️ Stop Forwarding", b"mode_stop")],
        [Button.inline("🔙 Back", b"main_menu")]
    ]
    
    current_mode = "🔴 Live" if session.mode == 'live' else "⏸️ Stopped"
    
    await event.edit(
        f"**⚙️ Forwarding Modes**\n\n"
        f"📋 **Saved Configuration:**\n"
        f"📤 Source: `{session.source_channel}`\n"
        f"📥 Target: `{session.target_channel}`\n"
        f"📊 Forwarded: {session.forward_count} messages\n"
        f"⚡ Current Mode: {current_mode}\n\n"
        f"**Select a mode:**",
        buttons=buttons
    )

@bot.on(events.CallbackQuery(pattern=b"mode_live"))
async def mode_live(event):
    """Enable live forwarding mode"""
    session = get_session(event.sender_id)
    session.mode = 'live'
    save_session(event.sender_id)
    
    await event.answer("✅ Live mode enabled!")
    buttons = [[Button.inline("🔙 Back to Modes", b"modes")]]
    await event.edit(
        "**🔴 Live Mode Enabled**\n\n"
        "All new messages from the source channel will be automatically forwarded to the target channel.\n\n"
        "The forwarded tag will be removed.",
        buttons=buttons
    )

@bot.on(events.CallbackQuery(pattern=b"mode_send_all"))
async def mode_send_all(event):
    """Send all files and messages from source to target"""
    session = get_session(event.sender_id)
    
    await event.answer("⏳ Starting...")
    buttons = [[Button.inline("🔙 Back to Modes", b"modes")]]
    await event.edit(
        "**📦 Sending ALL Files & Messages**\n\n"
        "⏳ Fetching all messages from source channel...\n"
        "This may take a while depending on channel size.",
        buttons=buttons
    )
    
    session.mode = 'idle'
    await forward_all_messages(event.sender_id)

async def forward_all_messages(user_id):
    """Forward all messages from source to target"""
    session = get_session(user_id)
    
    try:
        source = await bot.get_entity(session.source_channel)
        target = await bot.get_entity(session.target_channel)
        
        forwarded = 0
        failed = 0
        
        await bot.send_message(user_id, "📤 Starting to forward all messages...")
        
        async for message in bot.iter_messages(source, reverse=True):
            try:
                # Copy message without forward tag
                await bot.send_message(
                    target,
                    message.text or message.message or "",
                    file=message.media,
                    buttons=message.buttons,
                    formatting_entities=message.entities
                )
                forwarded += 1
                session.forward_count += 1
                
                # Status update every 50 messages
                if forwarded % 50 == 0:
                    await bot.send_message(user_id, f"⏳ Progress: {forwarded} messages forwarded...")
                    await asyncio.sleep(1)  # Prevent flood
                    
            except FloodWaitError as e:
                logger.warning(f"Flood wait: {e.seconds} seconds")
                await bot.send_message(user_id, f"⏸️ Rate limited. Waiting {e.seconds} seconds...")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(f"Error forwarding message: {e}")
                failed += 1
                continue
        
        save_session(user_id)
        await bot.send_message(
            user_id, 
            f"✅ **Completed!**\n\n"
            f"📊 Forwarded: {forwarded} messages\n"
            f"❌ Failed: {failed} messages"
        )
        
    except Exception as e:
        logger.error(f"Error in forward_all_messages: {e}")
        await bot.send_message(user_id, f"❌ Error: {str(e)}")

@bot.on(events.CallbackQuery(pattern=b"mode_range"))
async def mode_range(event):
    """Prompt for message range"""
    await event.answer()
    await event.respond(
        "**📝 Forward Message Range**\n\n"
        "Send the range in format: `START END`\n"
        "Example: `1 100` to forward messages 1 to 100\n\n"
        "Or send single number to forward from that message till latest."
    )
    session = get_session(event.sender_id)
    session.mode = 'awaiting_range'

@bot.on(events.CallbackQuery(pattern=b"mode_till_msg"))
async def mode_till_msg(event):
    """Prompt for message number"""
    await event.answer()
    await event.respond(
        "**🔢 Forward Till Message**\n\n"
        "Send the message number to forward up to.\n"
        "Example: `500` to forward all messages up to message 500"
    )
    session = get_session(event.sender_id)
    session.mode = 'awaiting_till_msg'

@bot.on(events.CallbackQuery(pattern=b"mode_till_file"))
async def mode_till_file(event):
    """Prompt for file count"""
    await event.answer()
    await event.respond(
        "**📁 Forward Till File Number**\n\n"
        "Send the number of files to forward.\n"
        "Example: `50` to forward the first 50 files"
    )
    session = get_session(event.sender_id)
    session.mode = 'awaiting_till_file'

@bot.on(events.CallbackQuery(pattern=b"mode_stop"))
async def mode_stop(event):
    """Stop forwarding"""
    session = get_session(event.sender_id)
    session.mode = 'idle'
    save_session(event.sender_id)
    
    await event.answer("⏸️ Forwarding stopped!")
    buttons = [[Button.inline("🔙 Back to Modes", b"modes")]]
    await event.edit(
        "**⏸️ Forwarding Stopped**\n\n"
        "No messages will be forwarded.",
        buttons=buttons
    )

@bot.on(events.CallbackQuery(pattern=b"status"))
async def show_status(event):
    """Show bot status"""
    session = get_session(event.sender_id)
    
    source = session.source_channel if session.source_channel else "Not set"
    target = session.target_channel if session.target_channel else "Not set"
    mode_text = {
        'idle': '⏸️ Stopped',
        'live': '🔴 Live Mode',
        'selective': '📝 Selective Mode'
    }.get(session.mode, session.mode)
    
    buttons = [[Button.inline("🔙 Back", b"main_menu")]]
    
    await event.edit(
        f"**📊 Bot Status**\n\n"
        f"**Source Channel:** `{source}`\n"
        f"**Target Channel:** `{target}`\n"
        f"**Mode:** {mode_text}\n"
        f"**Messages Forwarded:** {session.forward_count}\n"
        f"**Bot Status:** ✅ Active",
        buttons=buttons
    )

@bot.on(events.CallbackQuery(pattern=b"help"))
async def show_help(event):
    """Show help message"""
    buttons = [[Button.inline("🔙 Back", b"main_menu")]]
    
    await event.edit(
        "**ℹ️ Help & Instructions**\n\n"
        "**Setup:**\n"
        "1. Set source channel (where to copy from)\n"
        "2. Set target channel (where to copy to)\n"
        "3. Choose forwarding mode\n\n"
        "**Modes:**\n"
        "• **Live Mode** - Auto-forward all new messages\n"
        "• **Message Range** - Forward specific message range\n"
        "• **Till Message** - Forward up to a message number\n"
        "• **Till File** - Forward specific number of files\n\n"
        "**Features:**\n"
        "✅ Removes forwarded tag\n"
        "✅ Forwards all media types\n"
        "✅ Preserves captions\n"
        "✅ Real-time forwarding\n\n"
        "**Note:** Bot must be admin in both channels!",
        buttons=buttons
    )

@bot.on(events.NewMessage)
async def message_handler(event):
    """Handle incoming messages"""
    if not is_admin(event.sender_id):
        return
    
    session = get_session(event.sender_id)
    
    # Handle setting source channel
    if session.mode == 'awaiting_source':
        try:
            channel_input = event.message.text.strip()
            if event.message.forward:
                channel = await bot.get_entity(event.message.forward.chat)
                channel_input = channel.id
            
            # Convert string IDs to integers
            if isinstance(channel_input, str) and channel_input.lstrip('-').isdigit():
                channel_input = int(channel_input)
            
            entity = await bot.get_entity(channel_input)
            channel_id = entity.id if hasattr(entity, 'id') else channel_input
            
            # Check if bot is admin
            is_admin_perm, msg = await check_bot_permissions(channel_id, "source")
            if not is_admin_perm:
                await event.respond(msg)
                session.mode = 'idle'
                return
            
            session.source_channel = channel_id
            save_session(event.sender_id)
            session.mode = 'idle'
            
            await event.respond(f"✅ Source channel set: `{session.source_channel}`\n{msg}")
        except Exception as e:
            await event.respond(f"❌ Error: {str(e)}\nPlease try again.")
        return
    
    # Handle setting target channel
    if session.mode == 'awaiting_target':
        try:
            channel_input = event.message.text.strip()
            if event.message.forward:
                channel = await bot.get_entity(event.message.forward.chat)
                channel_input = channel.id
            
            # Convert string IDs to integers
            if isinstance(channel_input, str) and channel_input.lstrip('-').isdigit():
                channel_input = int(channel_input)
            
            entity = await bot.get_entity(channel_input)
            channel_id = entity.id if hasattr(entity, 'id') else channel_input
            
            # Check if bot is admin
            is_admin_perm, msg = await check_bot_permissions(channel_id, "target")
            if not is_admin_perm:
                await event.respond(msg)
                session.mode = 'idle'
                return
            
            session.target_channel = channel_id
            save_session(event.sender_id)
            session.mode = 'idle'
            
            await event.respond(f"✅ Target channel set: `{session.target_channel}`\n{msg}")
        except Exception as e:
            await event.respond(f"❌ Error: {str(e)}\nPlease try again.")
        return
    
    # Handle message range input
    if session.mode == 'awaiting_range':
        try:
            parts = event.message.text.split()
            if len(parts) == 2:
                start, end = int(parts[0]), int(parts[1])
            else:
                start, end = int(parts[0]), None
            
            session.mode = 'idle'
            await event.respond(f"⏳ Starting to forward messages from {start} to {end or 'latest'}...")
            await forward_message_range(event.sender_id, start, end)
        except Exception as e:
            await event.respond(f"❌ Error: {str(e)}\nPlease send valid numbers.")
        return
    
    # Handle till message input
    if session.mode == 'awaiting_till_msg':
        try:
            till_msg = int(event.message.text)
            session.mode = 'idle'
            await event.respond(f"⏳ Starting to forward messages up to {till_msg}...")
            await forward_message_range(event.sender_id, 1, till_msg)
        except Exception as e:
            await event.respond(f"❌ Error: {str(e)}\nPlease send a valid number.")
        return
    
    # Handle till file input
    if session.mode == 'awaiting_till_file':
        try:
            file_count = int(event.message.text)
            session.mode = 'idle'
            await event.respond(f"⏳ Starting to forward first {file_count} files...")
            await forward_files(event.sender_id, file_count)
        except Exception as e:
            await event.respond(f"❌ Error: {str(e)}\nPlease send a valid number.")
        return

async def forward_message_range(user_id, start_id, end_id=None):
    """Forward messages in a range"""
    session = get_session(user_id)
    
    try:
        source = await bot.get_entity(session.source_channel)
        target = await bot.get_entity(session.target_channel)
        
        forwarded = 0
        async for message in bot.iter_messages(source, min_id=start_id-1, max_id=end_id, reverse=True):
            try:
                # Copy message without forward tag
                await bot.send_message(
                    target,
                    message.text or message.message or "",
                    file=message.media,
                    buttons=message.buttons,
                    formatting_entities=message.entities
                )
                forwarded += 1
                session.forward_count += 1
                
                if forwarded % 10 == 0:
                    await asyncio.sleep(1)  # Prevent flood
                    
            except FloodWaitError as e:
                logger.warning(f"Flood wait: {e.seconds} seconds")
                await asyncio.sleep(e.seconds)
            except Exception as e:
                logger.error(f"Error forwarding message: {e}")
                continue
        
        save_session(user_id)
        await bot.send_message(user_id, f"✅ Forwarded {forwarded} messages!")
        
    except Exception as e:
        logger.error(f"Error in forward_message_range: {e}")
        await bot.send_message(user_id, f"❌ Error: {str(e)}")

async def forward_files(user_id, file_count):
    """Forward specific number of files"""
    session = get_session(user_id)
    
    try:
        source = await bot.get_entity(session.source_channel)
        target = await bot.get_entity(session.target_channel)
        
        forwarded = 0
        async for message in bot.iter_messages(source, reverse=True):
            if message.media and forwarded < file_count:
                try:
                    await bot.send_message(
                        target,
                        message.text or message.message or "",
                        file=message.media,
                        formatting_entities=message.entities
                    )
                    forwarded += 1
                    session.forward_count += 1
                    
                    if forwarded % 5 == 0:
                        await asyncio.sleep(1)
                        
                except FloodWaitError as e:
                    await asyncio.sleep(e.seconds)
                except Exception as e:
                    logger.error(f"Error forwarding file: {e}")
                    continue
            
            if forwarded >= file_count:
                break
        
        save_session(user_id)
        await bot.send_message(user_id, f"✅ Forwarded {forwarded} files!")
        
    except Exception as e:
        logger.error(f"Error in forward_files: {e}")
        await bot.send_message(user_id, f"❌ Error: {str(e)}")

# Live mode handler - monitors source channels
@bot.on(events.NewMessage())
async def live_forward_handler(event):
    """Handle live forwarding from source channels"""
    if event.is_private:
        return
    
    # Check all users with live mode enabled
    for user_id, session in user_sessions.items():
        if session.mode == 'live' and session.source_channel:
            try:
                # Check if message is from source channel
                if event.chat_id == session.source_channel:
                    target = await bot.get_entity(session.target_channel)
                    
                    # Forward without forward tag
                    await bot.send_message(
                        target,
                        event.message.text or event.message.message or "",
                        file=event.message.media,
                        buttons=event.message.buttons,
                        formatting_entities=event.message.entities
                    )
                    
                    session.forward_count += 1
                    save_session(user_id)
                    
            except Exception as e:
                logger.error(f"Error in live forward: {e}")
                continue

async def health_check(request):
    """Health check endpoint for Koyeb"""
    return web.Response(text="OK", status=200)

async def start_web_server():
    """Start HTTP server for health checks"""
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', 8000)
    await site.start()
    logger.info("Health check server started on port 8000")

async def main():
    """Start the bot and web server"""
    logger.info("Starting bot...")
    
    # Start health check server
    await start_web_server()
    
    logger.info("Bot started!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    bot.loop.run_until_complete(main())
