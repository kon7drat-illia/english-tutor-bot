import os
import json
import re
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def analyze_english_text(user_text):
    system_prompt = """
    You are an expert English language tutor. 
    Analyze the text, correct mistakes, and evaluate the CEFR level.
    
    CRITICAL INSTRUCTIONS FOR CONCISENESS (TO AVOID LARGE RESPONSES):
    1. "level_explanation" MUST be exactly 1 short sentence.
    2. "recommendation" MUST be exactly 1 short sentence.
    3. For each error in the array, "explanation" MUST be extremely brief (maximum 5-8 words).
    
    You must respond STRICTLY with a raw JSON object. Do not wrap it in markdown code blocks.
    Structure:
    {
        "level": "B1",
        "level_explanation": "Коротке пояснення (1 речення).",
        "recommendation": "Коротка порада (1 речення).",
        "corrected_text": "...",
        "errors": [
            {
                "category": "Grammar",
                "incorrect_fragment": "...",
                "correct_fragment": "...",
                "explanation": "Дуже коротке пояснення (до 8 слів)."
            }
        ]
    }
    """
    
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001", # (або та назва, яку ти скопіював)
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_text}]
        )
        
        text_response = response.content[0].text.strip()
        
        # Очищення від маркдауну
        match = re.search(r'\{.*\}', text_response, re.DOTALL)
        raw_json = match.group(0) if match else text_response
        
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError as e:
            print(f"\n[JSON ERROR] Помилка форматування: {e}")
            print("--- СИРИЙ ТЕКСТ ВІД CLAUDE ---")
            print(raw_json)
            print("------------------------------\n")
            return None
            
    except Exception as e:
        print(f"[CLAUDE ERROR] Помилка: {e}")
        return None