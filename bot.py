import os
import asyncio
import sqlite3
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.types import FSInputFile
from aiogram.exceptions import TelegramBadRequest
from analytics import generate_statistics
from ai_module import analyze_english_text, generate_topic_suggestions
from aiogram import BaseMiddleware

# Завантажуємо змінні оточення
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

# Ініціалізуємо бота та диспетчер
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Визначаємо стани
class BotStates(StatesGroup):
    waiting_for_text = State()
    waiting_for_level_check = State()

# Створюємо головне меню
main_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📝 Написати текст"), KeyboardButton(text="🎯 Перевірити рівень")],
        [KeyboardButton(text="💡 Запропонувати тему"), KeyboardButton(text="📊 Моя статистика")]
    ],
    resize_keyboard=True,
    input_field_placeholder="Оберіть дію в меню..."
)

def get_feature_limit(user_id, feature_name):
    """Перевіряє, скільки запитів для конкретної фічі користувач зробив сьогодні"""
    conn = sqlite3.connect('english_practice.db')
    cursor = conn.cursor()
    
    # Створюємо нову таблицю для лімітів по категоріях, якщо її ще немає
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feature_usage (
            user_id INTEGER,
            feature_name TEXT,
            usage_date DATE,
            requests_count INTEGER,
            UNIQUE(user_id, feature_name, usage_date)
        )
    ''')
    
    cursor.execute('''
        SELECT requests_count FROM feature_usage 
        WHERE user_id = ? AND feature_name = ? AND usage_date = date("now")
    ''', (user_id, feature_name))
    
    row = cursor.fetchone()
    conn.close()
    
    return row[0] if row else 0

def increment_feature_limit(user_id, feature_name):
    """Збільшує лічильник запитів конкретної фічі на 1"""
    conn = sqlite3.connect('english_practice.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT requests_count FROM feature_usage 
        WHERE user_id = ? AND feature_name = ? AND usage_date = date("now")
    ''', (user_id, feature_name))
    row = cursor.fetchone()
    
    if row:
        cursor.execute('''
            UPDATE feature_usage 
            SET requests_count = requests_count + 1 
            WHERE user_id = ? AND feature_name = ? AND usage_date = date("now")
        ''', (user_id, feature_name))
    else:
        cursor.execute('''
            INSERT INTO feature_usage (user_id, feature_name, usage_date, requests_count) 
            VALUES (?, ?, date("now"), 1)
        ''', (user_id, feature_name))
        
    conn.commit()
    conn.close()

# Чорний список (сюди вписуєш ID тих, кого хочеш заблокувати, через кому)
BANNED_USERS = [] 

class BanMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        # Перевіряємо, чи є ID відправника у чорному списку
        if event.from_user.id in BANNED_USERS:
            # Якщо так — просто зупиняємо обробку (бот промовчить)
            # Можна розкоментувати рядок нижче, щоб бот щось відповідав:
            # await event.answer("🚫 Доступ до бота заблоковано.")
            return 
            
        # Якщо користувача немає в списку — пропускаємо його далі
        return await handler(event, data)

# "Ставимо охоронця на двері" — реєструємо Middleware для всіх повідомлень
dp.message.middleware(BanMiddleware())

def get_user_recent_texts(user_id, limit=5):
    """Дістає останні тексти користувача для розуміння його інтересів"""
    conn = sqlite3.connect('english_practice.db')
    cursor = conn.cursor()
    # Беремо тексти, відсортовані за часом створення (найновіші)
    cursor.execute('''
        SELECT original_text 
        FROM submissions 
        WHERE user_id = ? 
        ORDER BY created_at DESC LIMIT ?
    ''', (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    return [row[0] for row in rows]

def save_to_db(user_id, original_text, analysis):
    """Функція для збереження тексту та деталей помилок у базу даних"""
    conn = sqlite3.connect('english_practice.db')
    cursor = conn.cursor()
    
    # 1. Створюємо таблиці, якщо їх ще немає (з фіксацією часу created_at)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            original_text TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER,
            error_category TEXT,
            description TEXT,
            FOREIGN KEY(submission_id) REFERENCES submissions(id)
        )
    ''')
    
    # 2. Зберігаємо оригінальний текст (дата додасться автоматично)
    cursor.execute('''
        INSERT INTO submissions (user_id, original_text) 
        VALUES (?, ?)
    ''', (user_id, original_text))
    
    submission_id = cursor.lastrowid
    
    # 3. Зберігаємо всі знайдені помилки, прив'язуючи їх до ID тексту
    errors = analysis.get('errors', [])
    for error in errors:
        # Витягуємо нові поля з JSON
        category = error.get('category', 'General')
        inc = error.get('incorrect_fragment', '')
        cor = error.get('correct_fragment', '')
        exp = error.get('explanation', '')
        
        # Склеюємо деталі для збереження в існуючу колонку description
        db_description = f"Помилка: '{inc}' -> Виправлено: '{cor}'. Пояснення: {exp}"
        
        cursor.execute('''
            INSERT INTO errors (submission_id, error_category, description)
            VALUES (?, ?, ?)
        ''', (submission_id, category, db_description))
        
    conn.commit()
    conn.close()

@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear() # Скидаємо стани
    
    welcome_text = (
        "Привіт! 👋 Я твій персональний AI-асистент з англійської мови.\n\n"
        "<b>Ось що я вмію:</b>\n"
        "📝 <b>Написати текст (5)</b> — виправлю твої помилки та поясню граматику.\n"
        "🎯 <b>Перевірити рівень (3)</b> — напиши від 80 слів, і я визначу твій рівень.\n"
        "💡 <b>Запропонувати тему (5)</b> — підберу цікаві ідеї для твоєї практики.\n"
        "📊 <b>Моя статистика (3)</b> — покажу твій прогрес та часті помилки.\n\n"
        "⚠️ <b>Важливо:</b> В дужках вказані ліміти запитів на добу.\n"
        "Він оновлюється щодня опівночі.\n\n"
        "Обирай дію в меню нижче і почнемо! 👇"
    )
    
    await message.answer(
        welcome_text,
        reply_markup=main_kb,
        parse_mode="HTML"
    )

# --- ОБРОБКА КНОПОК МЕНЮ ---

@dp.message(F.text == "📝 Написати текст")
async def btn_write_text(message: types.Message, state: FSMContext):
    
    await message.answer("Відправ мені свій текст англійською, і я перевірю його на помилки!")
    # Переводимо бота в режим очікування тексту
    await state.set_state(BotStates.waiting_for_text)

@dp.message(F.text == "🎯 Перевірити рівень")
async def btn_check_level(message: types.Message, state: FSMContext):
    
    await message.answer(
        "Напиши текст англійською (мінімум 80 слів) про те, як пройшов твій день, або на будь-яку іншу тему. "
        "Я проаналізую його і визначу твій рівень!"
    )
    # Переводимо в режим перевірки рівня
    await state.set_state(BotStates.waiting_for_level_check)

@dp.message(F.text == "💡 Запропонувати тему")
async def btn_suggest_topic(message: types.Message, state: FSMContext):

    # --- ПЕРЕВІРКА ЛІМІТУ ДЛЯ ІНШИХ ЗАВДАНЬ (5 на день) ---
    current_usage = get_feature_limit(message.from_user.id, "suggest_topic")
    if current_usage >= 5:
        await message.answer("🛑 <b>Денний ліміт запитів вичерпано (5/5)!</b>\nПовертайся завтра.", parse_mode="HTML")
        await state.clear()
        return
        
    increment_feature_limit(message.from_user.id, "suggest_topic")
    # --------------------------------

    await state.clear()
    processing_msg = await message.answer("🔄 Аналізую твої інтереси та підбираю цікаві теми...")
    
    # Дістаємо останні тексти з бази
    past_texts = get_user_recent_texts(message.from_user.id)
    
    # Генеруємо теми
    topics = generate_topic_suggestions(past_texts)
    
    if not topics or len(topics) != 4:
        try:
            await processing_msg.edit_text("❌ Виникла помилка при генерації тем. Спробуй ще раз.")
        except TelegramBadRequest:
            pass
        return
        
    # Зберігаємо згенеровані теми у тимчасову пам'ять (FSM)
    await state.update_data(suggested_topics=topics)
    
    # Створюємо 4 кнопки. У callback_data передаємо просто індекс теми (0, 1, 2, 3)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"1️⃣ {topics[0]['title']}", callback_data="topic_0")],
        [InlineKeyboardButton(text=f"2️⃣ {topics[1]['title']}", callback_data="topic_1")],
        [InlineKeyboardButton(text=f"3️⃣ {topics[2]['title']}", callback_data="topic_2")],
        [InlineKeyboardButton(text=f"4️⃣ {topics[3]['title']}", callback_data="topic_3")]
    ])
    
    try:
        await processing_msg.edit_text(
            "Ось 4 теми для тебе (частина з них базується на твоїх попередніх текстах). Обери ту, яка найбільше до душі:", 
            reply_markup=kb
        )
    except TelegramBadRequest:
        pass

# Хендлер, який спрацьовує, коли користувач тисне на одну з тем
@dp.callback_query(F.data.startswith("topic_"))
async def process_topic_selection(callback: CallbackQuery, state: FSMContext):
    # Дістаємо індекс вибраної теми з callback_data (наприклад, з "topic_2" дістанемо 2)
    topic_index = int(callback.data.split("_")[1])
    
    # Дістаємо збережені теми з пам'яті
    data = await state.get_data()
    topics = data.get("suggested_topics", [])
    
    if not topics:
        await callback.answer("Дані застаріли. Згенеруй теми ще раз.", show_alert=True)
        return
        
    selected_topic = topics[topic_index]
    title = selected_topic.get("title", "Тема")
    questions = selected_topic.get("questions", "Опиши свої думки на цю тему.")
    
    prompt_text = (
        f"🎯 <b>Класний вибір!</b>\n\n"
        f"<b>Тема:</b> {title}\n\n"
        f"💡 <b>Щоб тобі було легше почати, ось кілька питань-підказок:</b>\n"
        f"<i>{questions}</i>\n\n"
        f"📝 Чекаю на твій текст англійською!"
    )
    
    # Оновлюємо повідомлення (прибираємо кнопки і показуємо питання)
    await callback.message.edit_text(prompt_text, reply_markup=None, parse_mode="HTML")
    await callback.answer()
    
    # А тепер головне: переводимо бота у стан очікування тексту! 
    # Коли ти напишеш текст, спрацює твій стандартний handle_text
    await state.set_state(BotStates.waiting_for_text)

@dp.message(F.text == "📊 Моя статистика")
async def btn_statistics(message: types.Message, state: FSMContext):

    # --- ПЕРЕВІРКА ЛІМІТУ ДЛЯ СТАТИСТИКИ (3 на день) ---
    current_usage = get_feature_limit(message.from_user.id, "statistics")
    if current_usage >= 3:
        await message.answer("🛑 <b>Денний ліміт на статистику вичерпано (3/3)!</b>\nПовертайся завтра.", parse_mode="HTML")
        await state.clear()
        return
        
    increment_feature_limit(message.from_user.id, "statistics")
    # --------------------------------

    await state.clear()
    processing_msg = await message.answer("🔄 Збираю аналітику, генерую графіки та поради від AI...")
    
    # Викликаємо функцію генерації
    image_path, ai_advice = generate_statistics(message.from_user.id)
    
    if not image_path: # Якщо бази ще немає або вона порожня
        await processing_msg.edit_text(ai_advice)
        return
        
    photo = FSInputFile(image_path)
    
    # 1. Відправляємо лише фото з коротким підписом
    await bot.send_photo(
        chat_id=message.chat.id, 
        photo=photo, 
        caption="📊 <b>Твоя статистика</b>", 
        parse_mode="HTML"
    )

    # --- ДОДАЄМО КЛАВІАТУРУ ТУТ ---
    # Створюємо кнопку з твоїм посиланням на приватний канал
    book_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📘 Відкрити підручник Murphy", url="https://t.me/c/4465513809/3")]
    ])

    # 2. Відправляємо розгорнуту пораду окремим текстовим повідомленням
    await message.answer(
        f"💡 <b>Порада від AI:</b>\n{ai_advice}", 
        parse_mode="HTML",
        reply_markup= book_kb
    )
    
    # Видаляємо повідомлення "Збираю аналітику..."
    await processing_msg.delete()
    
    # Видаляємо картинку з комп'ютера, щоб не засмічувати пам'ять
    if os.path.exists(image_path):
        os.remove(image_path)

# --- ОБРОБКА АНГЛІЙСЬКОГО ТЕКСТУ ---

# Цей хендлер спрацює ТІЛЬКИ якщо бот перебуває у стані waiting_for_text
@dp.message(BotStates.waiting_for_text)
async def handle_text(message: types.Message, state: FSMContext):

# --- ПЕРЕВІРКА ЛІМІТУ ДЛЯ ІНШИХ ЗАВДАНЬ (5 на день) ---
    current_usage = get_feature_limit(message.from_user.id, "text_check")
    if current_usage >= 5:
        await message.answer("🛑 <b>Денний ліміт запитів вичерпано (5/5)!</b>\nПовертайся завтра.", parse_mode="HTML")
        await state.clear()
        return
        
    increment_feature_limit(message.from_user.id, "text_check")
# --------------------------------

    print(f"👀 Текст на перевірку надіслав користувач з ID: {message.from_user.id}")

    processing_msg = await message.answer("🔄 Аналізую текст...")
    
    analysis = analyze_english_text(message.text)
    
    if not analysis:
        try:
            await processing_msg.edit_text("❌ Виникла помилка при зверненні до нейромережі. Спробуй ще раз.")
        except TelegramBadRequest:
            pass
            
        return
    
    save_to_db(message.from_user.id, message.text, analysis)
    
    word_count = len(message.text.split())
    level = analysis.get("level", "Не визначено")
    recommendation = analysis.get("recommendation", "")
    corrected = analysis.get("corrected_text", "")
    errors = analysis.get("errors", [])
    
    response_text = f"🎯 <b>Орієнтовний рівень:</b> {level}\n"
    response_text += f"📝 <b>Кількість слів:</b> {word_count}\n"
    
    if recommendation:
        response_text += f"💡 <b>Порада:</b> {recommendation}\n"
        
    response_text += f"\n✅ <b>Виправлений текст:</b>\n{corrected}\n\n"
    
    if errors:
        response_text += "❗ <b>Деталі помилок:</b>\n\n"
        for err in errors:
            cat = err.get('category', 'Помилка')
            inc = err.get('incorrect_fragment', '')
            cor = err.get('correct_fragment', '')
            exp = err.get('explanation', '')
            response_text += f"❌ <s>{inc}</s> ➡️ ✅ <b>{cor}</b>\n<i>{cat}: {exp}</i>\n\n"
    else:
        response_text += "🎉 Чудова робота! Помилок не знайдено."
        
    # Захищаємо фінальний вивід від помилки TelegramBadRequest
    try:
        await processing_msg.edit_text(response_text, parse_mode="HTML")
    except TelegramBadRequest:
        pass
    
    # Виходимо з режиму очікування, щоб користувач знову міг користуватися меню
    await state.clear()

@dp.message(BotStates.waiting_for_level_check)
async def handle_level_check(message: types.Message, state: FSMContext):

# --- ПЕРЕВІРКА ЛІМІТУ ДЛЯ ІНШИХ ЗАВДАНЬ (3 на день) ---
    current_usage = get_feature_limit(message.from_user.id, "level_check")
    if current_usage >= 3:
        await message.answer("🛑 <b>Денний ліміт запитів вичерпано (3/3)!</b>\nПовертайся завтра.", parse_mode="HTML")
        await state.clear()
        return
        
    increment_feature_limit(message.from_user.id, "level_check")
# --------------------------------

    word_count = len(message.text.split())
    
    # Відсікаємо занадто короткі тексти
    if word_count < 80:
        await message.answer(
            f"⚠️ Твій текст містить лише {word_count} слів. Для точної оцінки рівня потрібно мінімум 80. "
            "Будь ласка, допиши ще кілька речень і відправ знову!"
        )
        return # Бот продовжує чекати на довший текст

    processing_msg = await message.answer("🔄 Визначаю твій рівень...")
    
    analysis = analyze_english_text(message.text)
    if not analysis:
        try:
            await processing_msg.edit_text("❌ Виникла помилка при зверненні до нейромережі. Спробуй ще раз.")
        except TelegramBadRequest:
            pass
        return
        
    save_to_db(message.from_user.id, message.text, analysis)
    
    level = analysis.get("level", "Не визначено")
    level_exp = analysis.get("level_explanation", "Оцінка виконана на основі словникового запасу.")
    errors = analysis.get("errors", [])
    corrected = analysis.get("corrected_text", "")
    error_count = len(errors)
    
    # Формуємо короткий звіт
    summary_text = (
        f"🎯 <b>Твій рівень: {level}</b>\n\n"
        f"📊 <b>Кількість знайдених помилок:</b> {error_count}\n"
        f"📝 <b>Аналіз:</b> {level_exp}"
    )
    
    # ЗБЕРІГАЄМО помилки, виправлений текст І сам звіт у пам'ять бота
    await state.update_data(errors=errors, corrected=corrected, summary=summary_text)
    
    # Створюємо інлайн-кнопку (тільки один раз!)
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Подивитися помилки", callback_data="show_errors")]
    ])
    
    try:
        await processing_msg.edit_text(summary_text, reply_markup=inline_kb, parse_mode="HTML")
    except TelegramBadRequest:
        pass
        
    # Знімаємо стан, але НЕ очищуємо дані, щоб кнопка змогла їх дістати
    await state.set_state(None)

@dp.callback_query(F.data == "show_errors")
async def process_show_errors(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    errors = data.get("errors", [])
    corrected = data.get("corrected", "")
    summary = data.get("summary", "") # Дістаємо попередній текст про рівень
    
    if not errors and not corrected:
        await callback.answer("Дані не знайдено або помилок немає.", show_alert=True)
        return
        
    # Починаємо формувати фінальне повідомлення зі старого тексту (про рівень)
    full_text = summary + "\n\n" + "-"*20 + "\n\n"
    
    full_text += f"✅ <b>Виправлений текст:</b>\n{corrected}\n\n"
    
    if errors:
        full_text += "❗ <b>Деталі помилок:</b>\n\n"
        for err in errors:
            cat = err.get('category', 'Помилка')
            inc = err.get('incorrect_fragment', '')
            cor = err.get('correct_fragment', '')
            exp = err.get('explanation', '')
            full_text += f"❌ <s>{inc}</s> ➡️ ✅ <b>{cor}</b>\n<i>{cat}: {exp}</i>\n\n"
    else:
        full_text += "🎉 Чудова робота! Помилок не знайдено."
        
    # Оновлюємо повідомлення: тепер там є і рівень, і помилки, а клавіатура (reply_markup) зникає
    await callback.message.edit_text(full_text, reply_markup=None, parse_mode="HTML")
    await callback.answer()
    await state.clear()

async def main():
    print("Бот запущений і чекає на повідомлення...")
    # Ця команда видаляє чергу старих повідомлень
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())