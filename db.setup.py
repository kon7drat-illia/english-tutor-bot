import sqlite3

def create_database():
    # Підключаємось до файлу бази даних (якщо його немає, він створиться автоматично)
    conn = sqlite3.connect('english_practice.db')
    cursor = conn.cursor()

    # Створюємо таблицю для збереження надісланих текстів
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            original_text TEXT NOT NULL,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Створюємо таблицю для збереження розібраних помилок
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            submission_id INTEGER NOT NULL,
            error_category TEXT NOT NULL,
            description TEXT NOT NULL,
            FOREIGN KEY (submission_id) REFERENCES submissions (id) ON DELETE CASCADE
        )
    ''')

    # Зберігаємо зміни та закриваємо з'єднання
    conn.commit()
    conn.close()
    
    print("Базу даних та таблиці успішно створено!")

if __name__ == '__main__':
    create_database()