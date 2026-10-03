import os
import requests
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

# Делаем GET-запрос, чтобы получить список разрешенных моделей
url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    print("Вам доступны следующие модели:")
    for model in data.get('models', []):
        print(model['name'])
else:
    print("Ошибка проверки:", response.text)