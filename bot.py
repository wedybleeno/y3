import logging
import os
import re
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# Ваш API токен для Telegram
TELEGRAM_TOKEN = '7172553910:AAFnuMN1b6eXa0MOkvsu1oQvsGmbIS_K53I'

# Jamendo API ключи из вашего скриншота
JAMENDO_CLIENT_ID = '8c63bc9b'
JAMENDO_CLIENT_SECRET = '2a0c3c9bb8719626cb037dac6e32720c'

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
    await update.message.reply_text('Привет! Отправь мне название песни или исполнителя, и я найду музыку для тебя.')

async def search_song(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    if not query:
        await update.message.reply_text('Пожалуйста, введите название песни или исполнителя.')
        return

    try:
        await update.message.reply_text('Ищу музыку, пожалуйста, подождите...')
        
        # Поиск через Jamendo API
        params = {
            'client_id': JAMENDO_CLIENT_ID,
            'format': 'json',
            'name': query,  # Изменено с namesearch на name для лучшего поиска
            'limit': 5,
            'include': 'musicinfo'
        }
        
        response = requests.get('https://api.jamendo.com/v3.0/tracks/', params=params)
        
        if response.status_code != 200:
            await update.message.reply_text(f'Ошибка при поиске: {response.status_code}')
            logger.error(f'API Error: {response.text}')
            return
            
        data = response.json()
        
        if 'results' not in data or len(data['results']) == 0:
            await update.message.reply_text('Ничего не найдено. Попробуйте другой запрос.')
            return
        
        # Отправляем список результатов
        buttons = []
        for index, track in enumerate(data['results'][:3]):
            artist = track.get('artist_name', 'Unknown')
            title = track.get('name', 'Unknown')
            button_text = f"{index + 1}. {artist} - {title}"
            if len(button_text) > 60:
                button_text = button_text[:57] + "..."
            
            # Сохраняем ID трека и URL аудио в callback_data
            # (ограничиваем длину до 64 байт согласно ограничениям Telegram)
            callback_data = str(track.get('id'))
            
            buttons.append((button_text, callback_data))
            
        # Создаем инлайн-клавиатуру
        keyboard = [[InlineKeyboardButton(text=btn[0], callback_data=btn[1])] for btn in buttons]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text('Выберите один из вариантов:', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f'Error during search: {e}')
        await update.message.reply_text(f'Произошла ошибка при поиске: {str(e)}')

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    track_id = query.data
    
    if not track_id:
        await query.edit_message_text(text="Выбор недействителен.")
        return
    
    try:
        await query.edit_message_text(text="Скачиваю аудио, пожалуйста, подождите...")
        
        # Получаем информацию о треке
        params = {
            'client_id': JAMENDO_CLIENT_ID,
            'format': 'json',
            'id': track_id
        }
        response = requests.get('https://api.jamendo.com/v3.0/tracks/', params=params)
        data = response.json()
        
        if 'results' not in data or len(data['results']) == 0:
            await query.edit_message_text(text="Не удалось получить информацию о треке.")
            return
        
        track = data['results'][0]
        title = track.get('name', 'Unknown')
        artist = track.get('artist_name', 'Unknown')
        download_url = track.get('audio')
        
        if not download_url:
            await query.edit_message_text(text="Ссылка на скачивание недоступна.")
            return
        
        # Скачиваем файл
        file_name = sanitize_filename(f"{artist} - {title}")
        file_path = os.path.join(DOWNLOAD_DIR, f"{file_name}.mp3")
        
        # Добавляем client_id к URL для скачивания
        if '?' not in download_url:
            download_url += f"?client_id={JAMENDO_CLIENT_ID}"
        else:
            download_url += f"&client_id={JAMENDO_CLIENT_ID}"
        
        response = requests.get(download_url, stream=True)
        
        if response.status_code != 200:
            await query.edit_message_text(text=f"Ошибка при скачивании: {response.status_code}")
            logger.error(f'Download Error: {response.text}')
            return
            
        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        # Отправляем файл
        await query.edit_message_text(text=f"Отправляю: {artist} - {title}")
        
        try:
            with open(file_path, 'rb') as audio:
                await query.message.reply_audio(
                    audio=InputFile(audio, filename=f"{file_name}.mp3"),
                    title=title,
                    performer=artist,
                    caption=f"Трек: {title}\nИсполнитель: {artist}\nИсточник: Jamendo"
                )
            
            # Отправляем сообщение об успехе
            await query.message.reply_text("✅ Трек отправлен!")
        except Exception as e:
            logger.error(f'Error sending file: {e}')
            await query.edit_message_text(text=f"Ошибка при отправке файла: {str(e)}")
        
        # Удаляем файл
        if os.path.exists(file_path):
            os.remove(file_path)
        
    except Exception as e:
        logger.error(f'Error: {e}')
        await query.edit_message_text(text=f"Произошла ошибка при скачивании: {str(e)}")

def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, search_song))
    application.add_handler(CallbackQueryHandler(button))
    
    application.run_polling()

if __name__ == '__main__':
    main()
