import os
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import time

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

def generate_statistics(user_id):
    conn = sqlite3.connect('english_practice.db')
    
    df_activity = pd.read_sql_query('''
        SELECT date(created_at) as date, COUNT(id) as count
        FROM submissions
        WHERE user_id = ? AND created_at >= date('now', '-84 days')
        GROUP BY date
    ''', conn, params=(user_id,))
    
    df_errors = pd.read_sql_query('''
        SELECT e.error_category, COUNT(e.id) as count
        FROM errors e
        JOIN submissions s ON e.submission_id = s.id
        WHERE s.user_id = ? AND s.created_at >= date('now', '-7 days')
        GROUP BY e.error_category
    ''', conn, params=(user_id,))
    
    # ОНОВЛЕНО: Тепер ми дістаємо не тільки опис, а й категорію, і без ліміту в 15 штук, 
    # щоб ШІ бачив повну картину по кожному розділу
    df_error_details = pd.read_sql_query('''
        SELECT e.error_category, e.description
        FROM errors e
        JOIN submissions s ON e.submission_id = s.id
        WHERE s.user_id = ? AND s.created_at >= date('now', '-7 days')
    ''', conn, params=(user_id,))
    
    conn.close()

    if df_activity.empty and df_errors.empty:
        return None, "Ти ще не написав жодного тексту. Час почати! 📝"

    # --- НАЛАШТУВАННЯ СТИЛЮ (Залишається без змін) ---
    plt.style.use('dark_background')
    BACKGROUND_COLOR = '#161b22' 
    CELL_EMPTY_COLOR = '#1c2128' 
    BORDER_COLOR = '#161b22'
    TEXT_COLOR = '#c9d1d9'
    
    fig = plt.figure(figsize=(14, 11), facecolor=BACKGROUND_COLOR)

    # --- ГРАФІК 1: КАЛЕНДАР ---
    ax1 = fig.add_subplot(2, 1, 1, facecolor=BACKGROUND_COLOR)
    today = datetime.today()
    days = [today - timedelta(days=i) for i in range(83, -1, -1)]
    df_cal = pd.DataFrame({'date': [d.strftime('%Y-%m-%d') for d in days]})
    
    if not df_activity.empty:
        df_cal = df_cal.merge(df_activity, on='date', how='left').fillna(0)
    else:
        df_cal['count'] = 0
        
    df_cal['date_obj'] = pd.to_datetime(df_cal['date'])
    df_cal['day_of_week'] = df_cal['date_obj'].dt.day_name()
    df_cal['week_str'] = df_cal['date_obj'].dt.strftime('%Y-%W')

    heatmap_data = df_cal.pivot_table(index='day_of_week', columns='week_str', values='count', aggfunc='sum').fillna(0)
    days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    heatmap_data = heatmap_data.reindex(days_order)

    annot_data = heatmap_data.applymap(lambda x: str(int(x)) if x > 0 else "")
    
    cmap = plt.cm.get_cmap('cool').copy()
    cmap.set_under(CELL_EMPTY_COLOR)

    sns.heatmap(heatmap_data, cmap=cmap, vmin=0.1, linewidths=5, linecolor=BORDER_COLOR, 
                cbar=False, square=True, annot=annot_data, fmt="", ax=ax1, 
                annot_kws={"size": 14, "weight": "bold", "color": "white"})
    
    ax1.set_title('Календар активності', fontsize=20, pad=30, color=TEXT_COLOR, fontweight='bold')
    ax1.set_ylabel('')
    
    months_ua = ['Січень', 'Лютий', 'Березень', 'Квітень', 'Травень', 'Червень', 'Липень', 'Серпень', 'Вересень', 'Жовтень', 'Листопад', 'Грудень']
    week_labels = []
    prev_month = None
    
    for week_col in heatmap_data.columns:
        sample_date = df_cal[df_cal['week_str'] == week_col]['date_obj'].min()
        curr_month = months_ua[sample_date.month - 1]
        
        if curr_month != prev_month:
            week_labels.append(curr_month)
            prev_month = curr_month
        else:
            week_labels.append("") 
            
    ax1.set_xticks([i + 0.5 for i in range(len(week_labels))])
    ax1.set_xticklabels(week_labels, fontsize=12, color=TEXT_COLOR, ha='center', rotation=0)
    ax1.set_xlabel('')
    ax1.tick_params(axis='y', colors=TEXT_COLOR, length=0, labelsize=12)
    ax1.tick_params(axis='x', length=0, pad=10) 

    # --- ГРАФІК 2: ПОМИЛКИ ---
    sorted_categories = []
    ax2 = fig.add_subplot(2, 1, 2, facecolor=BACKGROUND_COLOR)
    if not df_errors.empty:
        df_errors = df_errors.sort_values(by='count', ascending=False)
        # Зберігаємо відсортовані категорії для ШІ, щоб порядок порад точно збігався з графіком
        sorted_categories = df_errors['error_category'].tolist()
        
        sns.barplot(x='count', y='error_category', data=df_errors, hue='error_category', 
                    palette='cool', ax=ax2, legend=False)
        
        ax2.set_title('Помилки по категоріях', fontsize=20, pad=30, color=TEXT_COLOR, fontweight='bold')
        ax2.set_xlabel('')
        ax2.set_ylabel('')
        
        ax2.xaxis.grid(False) 
        ax2.set_xticks([])
        
        for p in ax2.patches:
            width = p.get_width()
            if width > 0:
                ax2.annotate(f'{int(width)}', 
                             (width, p.get_y() + p.get_height() / 2),
                             ha='left', va='center',
                             xytext=(15, 0), textcoords='offset points',
                             fontsize=16, color='white', fontweight='bold')

        for spine in ax2.spines.values():
            spine.set_visible(False)
    else:
        ax2.text(0.5, 0.5, "Немає помилок за цей тиждень! 🎉", ha='center', va='center', fontsize=16, color=TEXT_COLOR)
        ax2.axis('off')

    ax2.tick_params(axis='y', colors=TEXT_COLOR, length=0, labelsize=14)
    
    # --- РОЗДІЛЕННЯ ГРАФІКІВ ---
    line = plt.Line2D((0.1, 0.9), (0.52, 0.52), transform=fig.transFigure, color='#30363d', linewidth=2)
    fig.add_artist(line)

    plt.tight_layout(pad=4.0)
    fig.subplots_adjust(hspace=0.7) 
    
    image_path = f"stats_{user_id}.png"
    plt.savefig(image_path, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close()

    # Відправляємо деталі та ВІДСОРТОВАНИЙ список категорій
    ai_advice = get_ai_advice(df_error_details, sorted_categories)
    return image_path, ai_advice


def get_ai_advice(df_details, sorted_categories):
    if df_details.empty or not sorted_categories:
        return "Твоя статистика ідеальна! Продовжуй практикувати письмо, дивитися фільми та читати англійською."
        
    structured_errors_for_prompt = ""
    for cat in sorted_categories:
        cat_errors = df_details[df_details['error_category'] == cat]['description'].tolist()
        if cat_errors:
            structured_errors_for_prompt += f"[{cat}]\n"
            for err in list(set(cat_errors))[:5]:
                structured_errors_for_prompt += f"- {err}\n"
            structured_errors_for_prompt += "\n"
    
    prompt = f"""
    Ти викладач англійської мови. Ось помилки студента за тиждень, розбиті за категоріями:
    
    {structured_errors_for_prompt}
    
    Сформуй звіт.
    ВАЖЛИВІ ПРАВИЛА (ВИКОНУВАТИ СУВОРО):
    1. Збережи порядок категорій.
    2. Заголовок кожного блоку має бути строго таким: Category_name (Переклад_українською):
    3. Для блоку Grammar (Граматика) текст під заголовком має починатися з фрази "Вам варто повторити ці теми: ".
    4. Для інших блоків текст має починатися з фрази "Зверніть увагу на ці випадки: " і далі списком короткі нагадування: [помилка] -> [правильно] (пояснення).
    5. НЕ використовуй жодної markdown-розмітки.
    6. Не пиши жодних вступних чи завершальних речень.
    """
    
    data = {"contents": [{"parts": [{"text": prompt}]}]}
    
    # --- КАСКАДНА СИСТЕМА МОДЕЛЕЙ ---
    # Бот спробує їх по черзі. Якщо одна зайнята (503), він одразу стукає в іншу.
    models_to_try = [
        "gemini-3.5-flash", # Найлегша і найшвидша модель, рідше всього буває перевантажена
        "gemini-3.8-flash",    # Стандартна версія
        "gemini-3.6-flash",    # Нова версія (якщо доступна)
        "gemini-3.0-flash"       # Важка модель (на крайній випадок)
    ]
    
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
        
        try:
            resp = requests.post(url, headers={'Content-Type': 'application/json'}, json=data)
            
            if resp.status_code == 200:
                # Успіх! Повертаємо текст і виходимо з функції
                return resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            else:
                print(f"[AI] Модель {model_name} зайнята або недоступна. Код: {resp.status_code}. Пробуємо наступну...")
                continue # Переходимо до наступної моделі в списку
                
        except Exception as e:
            print(f"[AI] Збій при зверненні до {model_name}: {e}")
            continue
            
    # Якщо ЖОДНА з 4 моделей не відповіла (що буває вкрай рідко)
    return "Графіки згенеровані! 📊\n(ШІ-порада тимчасово недоступна: глобальні сервери Google зараз повністю перевантажені)."