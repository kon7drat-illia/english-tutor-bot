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

def generate_topic_suggestions(past_texts):
    system_prompt = """
    You are a creative English tutor. Your task is to suggest exactly 4 writing topics for a student.
    Return ONLY a raw JSON array of 4 objects. Do NOT wrap it in markdown code blocks.
    
    Structure:
    [
      {
        "title": "Short title in English (max 3-5 words)", 
        "questions": "2-3 short guiding questions IN UKRAINIAN to help them expand on this topic."
      }
    ]
    
    Rules for generation:
    1. If past texts are provided, analyze them to understand the user's interests (e.g. video games, movies, work, daily routine). Base EXACTLY 2 topics on these personal interests.
    2. Base the remaining 2 topics on engaging, unexpected, or creative general themes.
    3. If no past texts are provided, generate 4 diverse engaging themes.
    """
    
    user_content = "Past texts from this user:\n" + "\n---\n".join(past_texts) if past_texts else "No past texts available yet. Generate general topics."
    
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001", 
            max_tokens=800,
            system=system_prompt,
            messages=[{"role": "user", "content": user_content}]
        )
        
        text_response = response.content[0].text.strip()
        
        # Очищення від можливого маркдауну
        import re
        match = re.search(r'\[.*\]', text_response, re.DOTALL)
        raw_json = match.group(0) if match else text_response
        
        import json
        return json.loads(raw_json)
    except Exception as e:
        print(f"[CLAUDE TOPIC ERROR]: {e}")
        return None