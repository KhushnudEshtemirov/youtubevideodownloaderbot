# YouTube Downloader Telegram Bot

A simple Telegram bot that downloads YouTube videos (or audio) via `yt-dlp` and sends them back to the user in chat.

## Features
- Send a YouTube link → get the video back as a file
- `/audio <link>` → get just the audio as an MP3
- Automatically picks a format under Telegram's 50MB upload limit when possible

## Setup

1. **Create a bot**
   - Message [@BotFather](https://t.me/BotFather) on Telegram
   - Run `/newbot` and follow the prompts
   - Copy the token it gives you

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Install ffmpeg** (required for merging video+audio and audio extraction)
   - Ubuntu/Debian: `sudo apt install ffmpeg`
   - macOS: `brew install ffmpeg`
   - Windows: download from ffmpeg.org and add it to your PATH

4. **Set your bot token**
   ```bash
   export TELEGRAM_BOT_TOKEN="123456:ABC-your-token-here"
   ```

5. **Run the bot**
   ```bash
   python bot.py
   ```

## Usage
- Open a chat with your bot on Telegram
- Send `/start` to see instructions
- Paste any YouTube link to get the video
- Use `/audio <link>` to get just the audio

## Limitations
- Telegram's standard Bot API caps file uploads from bots at **50MB**. Long or high-resolution videos may exceed this and won't be sendable unless you run your own [Local Bot API Server](https://github.com/tdlib/telegram-bot-api) (raises the limit to 2GB).
- This bot uses polling (`run_polling`), which is fine for personal/small-scale use. For production, consider switching to webhooks.

## Important
Only download videos you have the right to download — your own uploads, content you have permission to save, or videos under a license (e.g. Creative Commons) that allows it. Downloading copyrighted YouTube videos without permission violates YouTube's Terms of Service.

## Deploying
For 24/7 uptime, run this on a small VPS, a Raspberry Pi, or a service like Railway/Render, using something like `systemd`, `pm2`, or `screen`/`tmux` to keep it running, or a process manager of your choice.
