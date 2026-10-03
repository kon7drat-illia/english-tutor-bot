import os
import json
import requests
from dotenv import load_dotenv
import re

# Завантажуємо ключ
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

def analyze_english_text(user_text):
    # Прямий URL до API Google (використовуємо стабільну модель)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash:generateContent?key={API_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    
    system_instruction = """
    You are an expert English language tutor and analyzer. 
    Analyze the provided text, correct any grammatical, spelling, or vocabulary mistakes.
    
    Evaluate the text's English proficiency level according to the CEFR scale (A1, A2, B1, B2, C1, C2). 
    Since you do not know the user's baseline, estimate the level purely based on the vocabulary, grammar complexity, and sentence structure used in this specific text.
    If the text is too short to make a highly accurate assessment (e.g., under 30 words), provide your best guess for the 'level', but include a friendly recommendation in Ukrainian to write longer texts for a more precise evaluation in the 'recommendation' field. If the length is sufficient, leave 'recommendation' empty.
    
    You must respond STRICTLY in JSON format. All JSON keys must be exactly as specified below, strictly in lowercase.
    {
        "level": "<string: A1, A2, B1, B2, C1, or C2>",
        "level_explanation": "<string: 1-2 short sentences in Ukrainian explaining why this level was assigned based on vocabulary and grammar>",
        "recommendation": "<string: advice to write more if text is too short, otherwise empty string>",
        "corrected_text": "<string: the fully corrected text>",
        "errors": [
            {
                "category": "<string: e.g., 'Grammar', 'Punctuation', 'Vocabulary', 'Articles'>",
                "incorrect_fragment": "<string: the exact wrong word or phrase from the original text>",
                "correct_fragment": "<string: how it should be written>",
                "explanation": "<string: brief explanation of the rule in English>"
            }
        ]
    }
    If there are no errors, return an empty array for "errors".
    """

    # Формуємо тіло запиту згідно з офіційною документацією REST API
    data = {
        "system_instruction": {
            "parts": [{"text": system_instruction}]
        },
        "contents": [{
            "parts": [{"text": user_text}]
        }],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }

    try:
        # Відправляємо запит
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status() 
        
        # Розпаковуємо відповідь від Google
        result = response.json()
        text_response = result['candidates'][0]['content']['parts'][0]['text']
        
        # --- ОЧИЩЕННЯ ВІД ЗАЙВОГО ТЕКСТУ (МАРКДАУНУ) ---
        # Шукаємо текст суворо від першої { до останньої }
        match = re.search(r'\{.*\}', text_response, re.DOTALL)
        
        if match:
            clean_json = match.group(0)
            return json.loads(clean_json)
        else:
            print("Помилка: Модель не повернула JSON-структуру.")
            print("Сира відповідь:", text_response)
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Помилка з'єднання з API: {e}")
        if 'response' in locals() and response.text:
            print("Деталі від сервера:", response.text)
        return None
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Помилка обробки JSON відповіді: {e}")
        # Виводимо проблемний рядок, щоб розуміти, що пішло не так
        if 'clean_json' in locals():
            print("Проблемний рядок:", clean_json)
        return None

if __name__ == "__main__":
    test_text = "I has a proficient level of English, but I doing many mistakes."
    print(f"Аналізуємо текст: '{test_text}'...\n")
    
    analysis = analyze_english_text(test_text)
    
    if analysis:
        print(json.dumps(analysis, indent=4, ensure_ascii=False))