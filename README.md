# 🤖 Telegram Forwarder Bot

A powerful Telegram bot that forwards messages from source channels to target channels with advanced features like live mode, selective forwarding, and custom modes. Perfect for Koyeb deployment!

## ✨ Features

- **🔴 Live Mode**: Automatically forward all new messages in real-time
- **📝 Message Range**: Forward messages between specific message numbers
- **🔢 Till Message**: Forward all messages up to a specific message number
- **📁 Till File**: Forward a specific number of files/media
- **✅ Remove Forwarded Tag**: Messages are sent without "Forwarded from" tag
- **📊 Status Tracking**: Track forwarded message count
- **⚙️ Easy Setup**: Interactive menu-driven configuration
- **🔒 Admin Control**: Only authorized users can use the bot

## 📋 Prerequisites

1. **Telegram API Credentials**
   - Go to https://my.telegram.org/apps
   - Create a new application
   - Note down your `API_ID` and `API_HASH`

2. **Bot Token**
   - Message [@BotFather](https://t.me/BotFather) on Telegram
   - Create a new bot with `/newbot`
   - Save your bot token

3. **Admin User ID**
   - Message [@userinfobot](https://t.me/userinfobot) to get your user ID

## 🚀 Deployment on Koyeb

### Method 1: Using Koyeb Dashboard

1. **Fork/Clone this repository** to your GitHub account

2. **Create a Koyeb account** at https://www.koyeb.com

3. **Create a new app**:
   - Click "Create App"
   - Choose "GitHub" as deployment method
   - Select your repository
   - Choose the branch to deploy

4. **Set Environment Variables**:
   - `API_ID`: Your Telegram API ID
   - `API_HASH`: Your Telegram API Hash
   - `BOT_TOKEN`: Your bot token from BotFather
   - `ADMIN_IDS`: Your Telegram user ID (comma-separated for multiple admins)

5. **Configure Service**:
   - Instance type: Nano (free tier)
   - Region: Choose closest to you
   - Port: 8000 (optional, bot doesn't need web interface)

6. **Deploy**: Click "Deploy" and wait for deployment to complete

### Method 2: Using Koyeb CLI

```bash
# Install Koyeb CLI
curl -fsSL https://koyeb.com/install.sh | bash

# Login to Koyeb
koyeb login

# Deploy the bot
koyeb app init telegram-forwarder-bot \
  --git github.com/yourusername/your-repo \
  --git-branch main \
  --ports 8000:http \
  --routes /:8000 \
  --env API_ID=YOUR_API_ID \
  --env API_HASH=YOUR_API_HASH \
  --env BOT_TOKEN=YOUR_BOT_TOKEN \
  --env ADMIN_IDS=YOUR_USER_ID
```

## 🏃 Local Development

1. **Clone the repository**:
```bash
git clone <your-repo-url>
cd telegram-forwarder-bot
```

2. **Install dependencies**:
```bash
pip install -r requirements.txt
```

3. **Create .env file**:
```bash
cp .env.example .env
```

4. **Edit .env file** with your credentials:
```env
API_ID=your_api_id
API_HASH=your_api_hash
BOT_TOKEN=your_bot_token
ADMIN_IDS=your_user_id
```

5. **Run the bot**:
```bash
python bot.py
```

## 📖 How to Use

1. **Start the bot**: Send `/start` to your bot

2. **Set up channels**:
   - Click "📤 Set Source Channel"
   - Send source channel username (@channel) or ID
   - Click "📥 Set Target Channel"
   - Send target channel username (@channel) or ID
   
   **Note**: The bot must be an admin in both channels!

3. **Choose a forwarding mode**:
   - **🔴 Live Mode**: Forward all new messages automatically
   - **📝 Forward Range**: Forward messages between two message IDs
   - **🔢 Forward Till Message**: Forward from beginning to specific message
   - **📁 Forward Till File**: Forward specific number of files

4. **Monitor status**: Click "📊 Status" to see forwarding statistics

## 🎯 Forwarding Modes Explained

### Live Mode
- Forwards every new message as it arrives
- Perfect for ongoing channel synchronization
- Automatically removes forward tag

### Message Range
- Format: `START END` (e.g., `1 100`)
- Forwards messages from ID START to ID END
- Single number forwards from that message to latest

### Till Message
- Format: Single number (e.g., `500`)
- Forwards all messages from 1 to specified number

### Till File
- Format: Single number (e.g., `50`)
- Forwards first N files/media from the channel
- Skips text-only messages

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `API_ID` | Telegram API ID from my.telegram.org | Yes |
| `API_HASH` | Telegram API Hash | Yes |
| `BOT_TOKEN` | Bot token from @BotFather | Yes |
| `ADMIN_IDS` | Comma-separated user IDs who can use the bot | Yes |

### Channel Requirements

- Bot must be admin in **both** source and target channels
- Source channel: Read messages permission
- Target channel: Write messages permission

## 🛠️ Troubleshooting

### Bot not responding
- Check if bot is running (check Koyeb logs)
- Verify environment variables are set correctly
- Ensure your user ID is in ADMIN_IDS

### Can't set channels
- Make sure you send channel username with @ (e.g., @mychannel)
- Or use channel ID (e.g., -1001234567890)
- Or forward a message from the channel to the bot

### Forwarding not working
- Verify bot is admin in both channels
- Check bot has permission to read from source
- Check bot has permission to post in target
- Check Koyeb logs for errors

### Flood wait errors
- Telegram has rate limits
- Bot automatically waits when rate limited
- Consider reducing forwarding speed

## 📝 File Structure

```
telegram-forwarder-bot/
├── bot.py              # Main bot code
├── requirements.txt    # Python dependencies
├── Dockerfile         # Docker configuration
├── Procfile           # Process file for deployment
├── koyeb.json         # Koyeb configuration
├── .env.example       # Example environment variables
├── .gitignore         # Git ignore rules
└── README.md          # This file
```

## 🔒 Security Notes

- Never commit your `.env` file or expose your credentials
- Keep your `API_HASH` and `BOT_TOKEN` secret
- Only share bot access with trusted users
- Use admin IDs to restrict bot usage

## 📊 Tech Stack

- **Python 3.11**: Programming language
- **Telethon**: Telegram client library
- **python-dotenv**: Environment variable management
- **Koyeb**: Cloud hosting platform

## 🤝 Contributing

Contributions are welcome! Feel free to:
- Report bugs
- Suggest features
- Submit pull requests

## 📄 License

This project is open source and available under the MIT License.

## 💬 Support

If you need help:
1. Check the troubleshooting section
2. Review Koyeb deployment logs
3. Check bot logs for error messages
4. Open an issue on GitHub

## 🎉 Credits

Built with ❤️ using Telethon and deployed on Koyeb.

---

**Happy Forwarding! 🚀**
