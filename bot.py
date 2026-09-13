"""
Telegram bot that downloads YouTube videos using yt-dlp.

Setup:
1. Create a bot with @BotFather on Telegram, get your bot token.
2. pip install -r requirements.txt
3. Install ffmpeg (needed for merging video/audio streams):
     - Ubuntu/Debian: sudo apt install ffmpeg
     - macOS: brew install ffmpeg
     - Windows: winget install ffmpeg (or download from ffmpeg.org and add to PATH)
4. Set your bot token as an environment variable:
     PowerShell:      $env:TELEGRAM_BOT_TOKEN="your_token_here"
     cmd:             set TELEGRAM_BOT_TOKEN=your_token_here
     macOS/Linux:     export TELEGRAM_BOT_TOKEN="your_token_here"
5. Run: python bot.py

Flow:
- User sends a YouTube link.
- Bot replies with "Video" / "Audio" buttons.
- If "Video" is chosen, bot replies with quality buttons (360p/480p/720p/1080p/Best).
- Bot downloads the chosen format and sends it back.

Note: Telegram bots can only send files up to 50MB via the standard Bot API
(2GB if you self-host a Local Bot API Server). Actual file size is checked
after download, and the user is warned if it's too large to send.
"""

import logging
import os
import re
import tempfile
import shutil
import asyncio
from pathlib import Path

import yt_dlp
from telegram import (
    Update,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
MAX_TELEGRAM_FILE_SIZE = 50 * 1024 * 1024  # 50MB, standard Bot API limit

YOUTUBE_URL_PATTERN = re.compile(
    r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/\S+"
)

# Quality tiers shown to the user -> yt-dlp format selector.
# Each falls back progressively so a match is (almost) always found.
QUALITY_FORMATS = {
    "360": (
        "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/"
        "best[height<=360][ext=mp4]/best[height<=360]/best"
    ),
    "480": (
        "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/"
        "best[height<=480][ext=mp4]/best[height<=480]/best"
    ),
    "720": (
        "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/"
        "best[height<=720][ext=mp4]/best[height<=720]/best"
    ),
    "1080": (
        "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/"
        "best[height<=1080][ext=mp4]/best[height<=1080]/best"
    ),
    "best": (
        "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
        "best[ext=mp4]/bestvideo+bestaudio/best"
    ),
}

QUALITY_LABELS = {
    "360": "360p",
    "480": "480p",
    "720": "720p (HD)",
    "1080": "1080p (Full HD)",
    "best": "Best available",
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hi! Send me a YouTube link and I'll ask what you want:\n"
        "- Video (pick a quality) or Audio (MP3)\n\n"
        "Note: Telegram limits bot uploads to 50MB, so very long or "
        "high-resolution videos may not be sendable."
    )


def find_youtube_url(text: str) -> str | None:
    match = YOUTUBE_URL_PATTERN.search(text)
    return match.group(0) if match else None


# Optional: path to a cookies.txt file (Netscape format) exported from a
# logged-in YouTube session. Set the YTDLP_COOKIES_FILE env var to enable.
# Using personal account cookies for a bot carries some risk to that account
# if used heavily -- only add this if the Android-client fallback isn't enough.
COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE")


def _base_ydl_opts(out_dir: str, audio_only: bool, format_selector: str | None) -> dict:
    if audio_only:
        opts = {
            "format": "bestaudio/best",
            "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "noplaylist": True,
            "quiet": True,
        }
    else:
        opts = {
            "format": format_selector or QUALITY_FORMATS["best"],
            "outtmpl": os.path.join(out_dir, "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
        }

    if COOKIES_FILE and os.path.exists(COOKIES_FILE):
        opts["cookiefile"] = COOKIES_FILE

    return opts


def download_video(
    url: str, out_dir: str, audio_only: bool = False, format_selector: str | None = None
) -> str:
    """Downloads a video (or audio) and returns the path to the resulting file.

    Cloud hosting IPs (Railway, Render, AWS, etc.) are often flagged by
    YouTube's bot-detection, which normally only appears when downloading
    from a browser-like client. As a first line of defense, we retry with
    the Android app's client identity, which frequently bypasses this.
    """
    ydl_opts = _base_ydl_opts(out_dir, audio_only, format_selector)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except yt_dlp.utils.DownloadError as e:
        if "sign in" in str(e).lower() or "not a bot" in str(e).lower():
            logger.warning("Bot check triggered, retrying with Android client...")
            retry_opts = dict(ydl_opts)
            retry_opts["extractor_args"] = {"youtube": {"player_client": ["android"]}}
            with yt_dlp.YoutubeDL(retry_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        else:
            raise

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        filepath = ydl.prepare_filename(info)
        if audio_only:
            # extension gets rewritten to mp3 by the postprocessor
            filepath = str(Path(filepath).with_suffix(".mp3"))
        return filepath


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text or ""
    url = find_youtube_url(text)

    if not url:
        await update.message.reply_text(
            "That doesn't look like a YouTube link. Send me a valid YouTube URL."
        )
        return

    # Stash the URL for this user so the follow-up button taps know what to download.
    context.user_data["pending_url"] = url

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🎬 Video", callback_data="type:video"),
                InlineKeyboardButton("🎵 Audio (MP3)", callback_data="type:audio"),
            ]
        ]
    )
    await update.message.reply_text("What would you like?", reply_markup=keyboard)


async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /audio <youtube_link>")
        return

    url = find_youtube_url(" ".join(context.args))
    if not url:
        await update.message.reply_text("That doesn't look like a valid YouTube URL.")
        return

    status_msg = await update.message.reply_text("Downloading... this may take a moment.")
    await download_and_send(status_msg, context, url, audio_only=True)


async def on_type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    url = context.user_data.get("pending_url")
    if not url:
        await query.edit_message_text("That link expired. Please send it again.")
        return

    choice = query.data.split(":", 1)[1]  # "video" or "audio"

    if choice == "audio":
        await query.edit_message_text("Downloading audio... this may take a moment.")
        await download_and_send(query.message, context, url, audio_only=True)
        return

    # choice == "video" -> ask for quality
    buttons = [
        InlineKeyboardButton(QUALITY_LABELS[key], callback_data=f"quality:{key}")
        for key in ("360", "480", "720", "1080", "best")
    ]
    # 2 buttons per row
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    await query.edit_message_text(
        "Choose a video quality:", reply_markup=InlineKeyboardMarkup(rows)
    )


async def on_quality_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    url = context.user_data.get("pending_url")
    if not url:
        await query.edit_message_text("That link expired. Please send it again.")
        return

    quality = query.data.split(":", 1)[1]
    format_selector = QUALITY_FORMATS.get(quality, QUALITY_FORMATS["best"])
    label = QUALITY_LABELS.get(quality, "Best available")

    await query.edit_message_text(f"Downloading video ({label})... this may take a moment.")
    await download_and_send(
        query.message, context, url, audio_only=False, format_selector=format_selector
    )


async def download_and_send(
    status_msg: Message,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    audio_only: bool,
    format_selector: str | None = None,
) -> None:
    tmp_dir = tempfile.mkdtemp(prefix="ytdl_")
    try:
        filepath = await context.application.create_task(
            _run_download(url, tmp_dir, audio_only, format_selector)
        )

        size = os.path.getsize(filepath)
        if size > MAX_TELEGRAM_FILE_SIZE:
            await status_msg.edit_text(
                f"Downloaded, but the file is {size / (1024 * 1024):.1f}MB, "
                "which is over Telegram's 50MB bot upload limit, so I can't send it. "
                "Try a lower quality or /audio for just the sound."
            )
            return

        await status_msg.edit_text("Uploading to Telegram...")
        with open(filepath, "rb") as f:
            if audio_only:
                await status_msg.reply_audio(audio=f, caption="Here's your audio.")
            else:
                await status_msg.reply_video(video=f, caption="Here's your video.")

        await status_msg.delete()

    except yt_dlp.utils.DownloadError as e:
        logger.exception("yt-dlp download error")
        await status_msg.edit_text(f"Couldn't download that video: {e}")
    except Exception as e:
        logger.exception("Unexpected error")
        await status_msg.edit_text(f"Something went wrong: {e}")
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def _run_download(
    url: str, tmp_dir: str, audio_only: bool, format_selector: str | None
) -> str:
    # yt-dlp is synchronous/blocking, so run it in a thread to avoid
    # blocking the bot's event loop.
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, download_video, url, tmp_dir, audio_only, format_selector
    )


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit(
            "Set the TELEGRAM_BOT_TOKEN environment variable before running the bot."
        )

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(60)
        .read_timeout(120)
        .write_timeout(120)
        .pool_timeout(60)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("audio", audio_command))
    app.add_handler(CallbackQueryHandler(on_type_chosen, pattern=r"^type:"))
    app.add_handler(CallbackQueryHandler(on_quality_chosen, pattern=r"^quality:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()