import os
import asyncio
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
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

# Initialize bot client (will connect in main)
bot = TelegramClient('bot', API_ID, API_HASH)

# Initialize user client for fetching messages (created per user)
user_clients = {}  # Store user clients per user_id

# User sessions storage
user_sessions = {}

class UserSession:
    def __init__(self, user_id):
        self.user_id = user_id
        self.source_channel = None
        self.target_channel = None
        self.mode = 'idle'  # idle, live, selective, awaiting_phone, awaiting_auth_code
        self.forward_count = 0
        self.user_phone = None
        self.session_string = None  # Store session string
        self.stop_forwarding = False  # Flag to stop ongoing forwarding
        
    def to_dict(self):
        return {
            'source_channel': self.source_channel,
            'target_channel': self.target_channel,
            'mode': self.mode,
            'forward_count': self.forward_count,
            'user_phone': self.user_phone,
            'session_string': self.session_string
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
            session.user_phone = user_config.get('user_phone')
            session.session_string = user_config.get('session_string')
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

async def get_client_for_fetching(user_id):
    """Get appropriate client for fetching messages"""
    session = get_session(user_id)
    
    # Check if user has set phone number
    if not session.user_phone:
        await bot.send_message(
            user_id, 
            "⚠️ **Phone number not set!**\n\n"
            "To fetch message history, please:\n"
            "1. Click 📱 Set Phone Number\n"
            "2. Send your phone with country code\n\n"
            "This is required to bypass Telegram bot limitations."
        )
        return None
    
    # Create or get user client with StringSession
    if user_id not in user_clients:
        session_str = session.session_string if session.session_string else ''
        user_clients[user_id] = TelegramClient(
            StringSession(session_str), 
            API_ID, 
            API_HASH
        )
    
    client = user_clients[user_id]
    
    # Connect and authorize if needed
    if not client.is_connected():
        await client.connect()
    
    if not await client.is_user_authorized():
        await client.send_code_request(session.user_phone)
        await bot.send_message(
            user_id,
            "📱 **Authorization Required**\n\n"
            f"A code has been sent to: `{session.user_phone}`\n\n"
            "Please send the code here (format: `12345`)"
        )
        session.mode = 'awaiting_auth_code'
        save_session(user_id)
        return None
    
    return client

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

@bot.on(events.NewMessage(pattern='/fix'))
async def fix_handler(event):
    """Fix channel IDs by adding -100 prefix"""
    if not is_admin(event.sender_id):
        return
    
    session = get_session(event.sender_id)
    fixed = []
    
    # Fix source if positive
    if session.source_channel and session.source_channel > 0:
        old = session.source_channel
        session.source_channel = int(f"-100{old}")
        fixed.append(f"Source: {old} → {session.source_channel}")
    
    # Fix target if positive
    if session.target_channel and session.target_channel > 0:
        old = session.target_channel
        session.target_channel = int(f"-100{old}")
        fixed.append(f"Target: {old} → {session.target_channel}")
    
    if fixed:
        save_session(event.sender_id)
        await event.respond(
            "✅ **Fixed channel IDs:**\n\n" + "\n".join(fixed) + 
            "\n\n✅ Your channels are now in the correct format!\nSend /start to continue."
        )
    else:
        await event.respond("✅ Channel IDs are already correct!")

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
        [Button.inline("📱 Set Phone Number", b"set_phone")],
        [Button.inline("⚙️ Forwarding Modes", b"modes")],
        [Button.inline("📊 Status", b"status")],
        [Button.inline("ℹ️ Help", b"help")]
    ]
    
    # Build configuration display
    config_display = "\n\n📋 **Current Configuration:**\n"
    
    if session.source_channel:
        config_display += f"✅ Source: `{session.source_channel}`\n"
    else:
        config_display += f"❌ Source: Not set\n"
    
    if session.target_channel:
        config_display += f"✅ Target: `{session.target_channel}`\n"
    else:
        config_display += f"❌ Target: Not set\n"
    
    if session.user_phone:
        config_display += f"✅ Phone: `{session.user_phone}`\n"
    else:
        config_display += f"⚠️ Phone: Not set (needed for history)\n"
    
    await event.respond(
        "**🤖 Telegram Forwarder Bot**\n\n"
        "Welcome! I can forward messages from one channel to another."
        f"{config_display}\n"
        "Choose an option below:",
        buttons=buttons
    )

@bot.on(events.CallbackQuery(pattern=b"main_menu"))
async def main_menu(event):
    """Show main menu"""
    buttons = [
        [Button.inline("📤 Set Source Channel", b"set_source")],
        [Button.inline("📥 Set Target Channel", b"set_target")],
        [Button.inline("📱 Set Phone Number", b"set_phone")],
        [Button.inline("⚙️ Forwarding Modes", b"modes")],
        [Button.inline("📊 Status", b"status")],
        [Button.inline("ℹ️ Help", b"help")]
    ]
    
    try:
        await event.edit(
            "**🤖 Telegram Forwarder Bot**\n\n"
            "Choose an option:",
            buttons=buttons
        )
    except Exception:
        pass  # Ignore if message not modified

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

@bot.on(events.CallbackQuery(pattern=b"set_phone"))
async def set_phone(event):
    """Prompt user to set phone number"""
    await event.answer()
    session = get_session(event.sender_id)
    
    current_phone = session.user_phone or "Not set"
    has_session = "✅ Active" if session.session_string else "❌ Not authorized"
    
    buttons = [[Button.inline("🔑 Import Session String", b"import_session")]]
    
    await event.respond(
        "📱 **Phone Number Setup**\n\n"
        f"📞 Phone: `{current_phone}`\n"
        f"🔐 Session: {has_session}\n\n"
        "**To setup new session:**\n"
        "Send your phone number with country code\n"
        "Examples: +1234567890, +919876543210\n\n"
        "**Or import existing session:**\n"
        "Click button below to import session string",
        buttons=buttons
    )
    session.mode = 'awaiting_phone'

@bot.on(events.CallbackQuery(pattern=b"import_session"))
async def import_session(event):
    """Prompt user to import session string"""
    await event.answer()
    await event.respond(
        "🔑 **Import Session String**\n\n"
        "Please send your session string.\n\n"
        "This is the string you received after authorization.\n"
        "Format: Long alphanumeric string"
    )
    session = get_session(event.sender_id)
    session.mode = 'awaiting_session_string'

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
    try:
        await event.edit(
            "**📦 Sending ALL Files & Messages**\n\n"
            "⏳ Fetching all messages from source channel...\n"
            "This may take a while depending on channel size.",
            buttons=buttons
        )
    except Exception:
        pass  # Ignore if message not modified
    
    session.mode = 'idle'
    await forward_all_messages(event.sender_id)

async def forward_all_messages(user_id):
    """Forward all messages from source to target"""
    session = get_session(user_id)
    session.stop_forwarding = False  # Reset stop flag
    
    try:
        # Get appropriate client for fetching
        fetch_client = await get_client_for_fetching(user_id)
        
        if not fetch_client:
            return  # Error message already sent
        
        source = await fetch_client.get_entity(session.source_channel)
        target = await bot.get_entity(session.target_channel)
        
        forwarded = 0
        failed = 0
        
        await bot.send_message(user_id, "📤 Starting to forward all messages...")
        
        async for message in fetch_client.iter_messages(source, reverse=True):
            # Check if user wants to stop
            if session.stop_forwarding:
                await bot.send_message(user_id, "⏸️ Forwarding stopped by user!")
                session.stop_forwarding = False
                break
                
            try:
                # Forward message (simple and reliable for all media types)
                await bot.forward_messages(target, message.id, source)
                    
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
    session.stop_forwarding = True  # Signal to stop ongoing forwarding
    save_session(event.sender_id)
    
    await event.answer("⏸️ Stopping forwarding...")
    buttons = [[Button.inline("🔙 Back to Modes", b"modes")]]
    try:
        await event.edit(
            "**⏸️ Forwarding Stopped**\n\n"
            "Ongoing forwarding will stop at the next message.",
            buttons=buttons
        )
    except Exception:
        pass

@bot.on(events.CallbackQuery(pattern=b"status"))
async def show_status(event):
    """Show bot status"""
    session = get_session(event.sender_id)
    
    source = session.source_channel if session.source_channel else "❌ Not set"
    target = session.target_channel if session.target_channel else "❌ Not set"
    phone = session.user_phone or "❌ Not set"
    
    mode_text = {
        'idle': '⏸️ Stopped',
        'live': '🔴 Live Mode',
        'selective': '📝 Selective Mode'
    }.get(session.mode, session.mode)
    
    buttons = [[Button.inline("🔙 Back", b"main_menu")]]
    
    await event.edit(
        f"**📊 Bot Status**\n\n"
        f"📤 **Source Channel:** `{source}`\n"
        f"📥 **Target Channel:** `{target}`\n"
        f"📱 **Phone Number:** `{phone}`\n"
        f"⚡ **Mode:** {mode_text}\n"
        f"📊 **Messages Forwarded:** {session.forward_count}\n\n"
        f"🟢 **Bot Status:** Active",
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
    
    # Handle phone number input
    if session.mode == 'awaiting_phone':
        try:
            phone = event.message.text.strip()
            
            # Basic validation
            if not phone.startswith('+') or not phone[1:].replace(' ', '').isdigit():
                await event.respond("❌ Invalid phone number format. Please use format: +1234567890")
                return
            
            session.user_phone = phone
            save_session(event.sender_id)
            session.mode = 'idle'
            
            await event.respond(
                f"✅ Phone number set: `{phone}`\n\n"
                "When you use forwarding features, you'll receive a verification code via Telegram.\n"
                "Just send it to the bot to authorize!"
            )
        except Exception as e:
            await event.respond(f"❌ Error: {str(e)}\nPlease try again.")
        return
    
    # Handle session string input
    if session.mode == 'awaiting_session_string':
        try:
            session_str = event.message.text.strip()
            
            # Test the session string
            test_client = TelegramClient(StringSession(session_str), API_ID, API_HASH)
            await test_client.connect()
            
            if await test_client.is_user_authorized():
                me = await test_client.get_me()
                session.session_string = session_str
                session.user_phone = me.phone
                save_session(event.sender_id)
                session.mode = 'idle'
                
                # Store in user_clients
                user_clients[event.sender_id] = test_client
                
                await event.respond(
                    "✅ **Session imported successfully!**\n\n"
                    f"📞 Phone: `+{me.phone}`\n"
                    f"👤 Name: {me.first_name}\n\n"
                    "You can now use all forwarding features!"
                )
            else:
                await test_client.disconnect()
                await event.respond(
                    "❌ Session string is invalid or expired.\n\n"
                    "Please check your session string and try again."
                )
                session.mode = 'idle'
        except Exception as e:
            await event.respond(
                f"❌ Error importing session: {str(e)}\n\n"
                "Please make sure you're using a valid session string."
            )
            session.mode = 'idle'
        return
    
    # Handle authorization code input
    if session.mode == 'awaiting_auth_code':
        try:
            code = event.message.text.strip().replace(' ', '').replace('-', '')
            
            if event.sender_id not in user_clients:
                await event.respond("❌ Session expired. Please try the operation again.")
                session.mode = 'idle'
                return
            
            client = user_clients[event.sender_id]
            await client.sign_in(session.user_phone, code)
            
            # Save session string
            session.session_string = client.session.save()
            session.mode = 'idle'
            save_session(event.sender_id)
            
            await event.respond(
                "✅ **Authorization successful!**\n\n"
                "🔐 Your session has been saved securely.\n"
                "You can now use all forwarding features!\n\n"
                f"🔑 Session String (save this!):\n`{session.session_string}`\n\n"
                "💡 Keep this string safe - you can use it to restore your session."
            )
            
        except Exception as e:
            await event.respond(
                f"❌ Authorization failed: {str(e)}\n\n"
                "Please try again or check your code."
            )
            session.mode = 'idle'
        return

async def forward_message_range(user_id, start_id, end_id=None):
    """Forward messages in a range"""
    session = get_session(user_id)
    session.stop_forwarding = False  # Reset stop flag
    
    try:
        # Get appropriate client for fetching
        fetch_client = await get_client_for_fetching(user_id)
        
        if not fetch_client:
            return  # Error message already sent
        
        source = await fetch_client.get_entity(session.source_channel)
        target = await bot.get_entity(session.target_channel)
        
        forwarded = 0
        async for message in fetch_client.iter_messages(source, min_id=start_id-1, max_id=end_id, reverse=True):
            # Check if user wants to stop
            if session.stop_forwarding:
                await bot.send_message(user_id, "⏸️ Forwarding stopped by user!")
                session.stop_forwarding = False
                break
                
            try:
                # Forward message (simple and reliable for all media types)
                await bot.forward_messages(target, message.id, source)
                    
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
    session.stop_forwarding = False  # Reset stop flag
    
    try:
        # Get appropriate client for fetching
        fetch_client = await get_client_for_fetching(user_id)
        
        if not fetch_client:
            return  # Error message already sent
        
        source = await fetch_client.get_entity(session.source_channel)
        target = await bot.get_entity(session.target_channel)
        
        forwarded = 0
        async for message in fetch_client.iter_messages(source, reverse=True):
            # Check if user wants to stop
            if session.stop_forwarding:
                await bot.send_message(user_id, "⏸️ Forwarding stopped by user!")
                session.stop_forwarding = False
                break
                
            if message.media and forwarded < file_count:
                try:
                    # Forward message (simple and reliable for all media types)
                    await bot.forward_messages(target, message.id, source)
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
    
    # Connect bot with flood wait handling
    while True:
        try:
            await bot.start(bot_token=BOT_TOKEN)
            break
        except FloodWaitError as e:
            logger.warning(f"FloodWaitError: Waiting {e.seconds} seconds before retry...")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logger.error(f"Error starting bot: {e}")
            await asyncio.sleep(5)
    
    # Start health check server
    await start_web_server()
    
    logger.info("Bot started!")
    await bot.run_until_disconnected()

if __name__ == '__main__':
    asyncio.run(main())
