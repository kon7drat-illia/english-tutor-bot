import sqlite3

conn = sqlite3.connect('english_practice.db')
cursor = conn.cursor()

# Команда DROP TABLE видаляє таблицю назавжди
cursor.execute('DROP TABLE IF EXISTS feature_usage')
conn.commit()

print("Стару таблицю видалено!")
conn.close()