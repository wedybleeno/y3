import logging
import os
import re
import uuid
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp

# Ваш API токен для Telegram
TELEGRAM_TOKEN = '7172553910:AAFnuMN1b6eXa0MOkvsu1oQvsGmbIS_K53I'

# Путь к папке для хранения скачанных файлов
DOWNLOAD_DIR = '/tmp/downloads'
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sanitize_filename(filename):
    """Очистка имени файла от небезопасных символов."""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Привет! Отправь мне ссылку на видео из YouTube или SoundCloud, и я конвертирую его в MP3 для тебя.\n\n'
        'Примеры ссылок:\n'
        '• https://www.youtube.com/watch?v=dQw4w9WgXcQ\n'
        '• https://youtu.be/dQw4w9WgXcQ\n'
        '• https://soundcloud.com/artist/track-name'
    )

async def download_audio(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message_text = update.message.text.strip()
    
    # Проверяем, является ли сообщение ссылкой
    url_pattern = re.compile(
        r'https?://(www\.)?(youtube|youtu\.be|soundcloud)\.com/\S+|https?://youtu\.be/\S+'
    )
    
    if not url_pattern.match(message_text):
        await update.message.reply_text(
            'Пожалуйста, отправьте корректную ссылку на YouTube или SoundCloud.\n\n'
            'Примеры:\n'
            '• https://www.youtube.com/watch?v=dQw4w9WgXcQ\n'
            '• https://youtu.be/dQw4w9WgXcQ\n'
            '• https://soundcloud.com/artist/track-name'
        )
        return
    
    # Ссылка валидна, начинаем обработку
    status_message = await update.message.reply_text('Загружаю информацию о треке...')
    
    try:
        # Генерируем уникальное имя для временного файла
        unique_id = str(uuid.uuid4())
        temp_file_path = os.path.join(DOWNLOAD_DIR, f"{unique_id}")
        
        # Настройка yt-dlp
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f"{temp_file_path}.%(ext)s",
            'noplaylist': True,
            'quiet': True,
            'no_warnings': True,
            # Используем cookies из Chrome чтобы обойти "Sign in to confirm you're not a bot"
            'cookiefile': '/tmp/cookies.txt',
            # Добавляем больше опций для обхода ограничений
            'nocheckcertificate': True,
            'ignoreerrors': False,
            'logtostderr': False,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            # Постпроцессинг для конвертации в mp3
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        
        # Обновляем статус
        await status_message.edit_text('Получаю информацию о треке...')
        
        # Извлекаем информацию о видео
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(message_text, download=False)
            
            title = info.get('title', 'Unknown title')
            uploader = info.get('uploader', 'Unknown artist')
            
            await status_message.edit_text(f'Скачиваю: {title}...')
            
            # Скачиваем аудио
            ydl.download([message_text])
        
        # Путь к загруженному mp3 файлу
        mp3_file_path = f"{temp_file_path}.mp3"
        
        if not os.path.exists(mp3_file_path):
            raise Exception("Файл MP3 не был создан")
        
        # Создаем красивое имя файла на основе информации о треке
        nice_filename = sanitize_filename(f"{uploader} - {title}")
        
        # Отправляем аудиофайл
        await status_message.edit_text(f'Отправляю: {title}...')
        
        with open(mp3_file_path, 'rb') as audio_file:
            await update.message.reply_audio(
                audio=InputFile(audio_file, filename=f"{nice_filename}.mp3"),
                title=title,
                performer=uploader,
                caption=f"🎵 {title}\n👤 {uploader}"
            )
        
        # Удаляем временный файл
        if os.path.exists(mp3_file_path):
            os.remove(mp3_file_path)
        
        # Обновляем статус
        await status_message.edit_text('✅ Файл успешно отправлен!')
        
    except Exception as e:
        logger.error(f"Error downloading audio: {e}")
        # В случае ошибки YouTube, предлагаем решение
        if "Sign in to confirm you're not a bot" in str(e):
            await status_message.edit_text(
                "⚠️ YouTube требует подтверждение, что вы не бот.\n\n"
                "Попробуйте другую ссылку или попробуйте позже."
            )
        else:
            await status_message.edit_text(f"❌ Ошибка при скачивании: {str(e)[:100]}...")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, download_audio))
    
    application.run_polling()

if __name__ == '__main__':
    main()
