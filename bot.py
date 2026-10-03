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
from analytics import generate_statistics
from ai_module import analyze_english_text

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
    await state.clear() # Скидаємо стани, якщо вони були
    await message.answer(
        "Привіт! Я твій AI-асистент з англійської. Обирай дію в меню нижче 👇",
        reply_markup=main_kb
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
    await state.clear()
    await message.answer("Ця функція на стадії розробки (Етап 5). Скоро бот навчиться підбирати теми персонально для тебе!")

@dp.message(F.text == "📊 Моя статистика")
async def btn_statistics(message: types.Message, state: FSMContext):
    await state.clear()
    processing_msg = await message.answer("🔄 Збираю аналітику, генерую графіки та поради від AI...")
    
    # Викликаємо функцію генерації
    image_path, ai_advice = generate_statistics(message.from_user.id)
    
    if not image_path: # Якщо бази ще немає або вона порожня
        await processing_msg.edit_text(ai_advice)
        return
        
    # Відправляємо згенеровану картинку з графіками
    photo = FSInputFile(image_path)
    caption = f"📊 <b>Твоя статистика</b>\n\n💡 <b>Порада від AI:</b>\n{ai_advice}"
    
    await bot.send_photo(chat_id=message.chat.id, photo=photo, caption=caption, parse_mode="HTML")
    await processing_msg.delete()
    
    # Видаляємо картинку з комп'ютера, щоб не засмічувати пам'ять
    if os.path.exists(image_path):
        os.remove(image_path)

# --- ОБРОБКА АНГЛІЙСЬКОГО ТЕКСТУ ---

# Цей хендлер спрацює ТІЛЬКИ якщо бот перебуває у стані waiting_for_text
@dp.message(BotStates.waiting_for_text)
async def handle_text(message: types.Message, state: FSMContext):
    processing_msg = await message.answer("🔄 Аналізую текст...")
    
    analysis = analyze_english_text(message.text)
    
    if not analysis:
        await processing_msg.edit_text("❌ Виникла помилка при зверненні до нейромережі. Спробуй ще раз.")
        # Залишаємо в режимі очікування, щоб можна було відправити текст повторно
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
        
    await processing_msg.edit_text(response_text, parse_mode="HTML")
    
    # Виходимо з режиму очікування, щоб користувач знову міг користуватися меню
    await state.clear()

@dp.message(BotStates.waiting_for_level_check)
async def handle_level_check(message: types.Message, state: FSMContext):
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
        await processing_msg.edit_text("❌ Виникла помилка при зверненні до нейромережі. Спробуй ще раз.")
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
    
    # Створюємо інлайн-кнопку
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Подивитися помилки", callback_data="show_errors")]
    ])
    
    await processing_msg.edit_text(summary_text, reply_markup=inline_kb, parse_mode="HTML")
    
    # Створюємо інлайн-кнопку
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👀 Подивитися помилки", callback_data="show_errors")]
    ])
    
    await processing_msg.edit_text(summary_text, reply_markup=inline_kb, parse_mode="HTML")
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
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())