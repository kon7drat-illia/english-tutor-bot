import os
import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime, timedelta
import requests
from dotenv import load_dotenv
import time
from anthropic import Anthropic
import matplotlib as mpl

load_dotenv()

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

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

    annot_data = heatmap_data.map(lambda x: str(int(x)) if x > 0 else "")
    
    cmap = mpl.colormaps['cool'].copy()
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
        
        ax2.set_title('Помилки по категоріях за тиждень', fontsize=20, pad=30, color=TEXT_COLOR, fontweight='bold')
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
        ax2.text(0.5, 0.5, "Немає помилок за цей тиждень!", ha='center', va='center', fontsize=16, color=TEXT_COLOR)
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
        
    structured_errors = ""
    for cat in sorted_categories:
        cat_errors = df_details[df_details['error_category'] == cat]['description'].tolist()
        if cat_errors:
            structured_errors += f"[{cat}]\n"
            for err in list(set(cat_errors))[:5]:
                structured_errors += f"- {err}\n"
            structured_errors += "\n"
    
    prompt = f"""
    Проаналізуй помилки студента за тиждень по категоріях:
    {structured_errors}
    
    Сформуй корисний звіт для роботи над помилками.
    Вимоги:
    1. Почни звіт рівно з одного речення: "Ось теми та слова, які варто повторити, спираючись на твої помилки за тиждень:"
    2. Заголовки блоків пиши ТІЛЬКИ англійською: Grammar:, Articles:, Vocabulary & Spelling:.
    3. Об'єднай усі помилки з Vocabulary та Spelling в спільну категорію "Vocabulary & Spelling:".
    4. ЖОРСТКИЙ ЛІМІТ ТА ГРУПУВАННЯ: 
    - Обери МАКСИМУМ 5 найважливіших теми для Grammar, МАКСИМУМ 2 для Articles і МАКСИМУМ 10 слів для Vocabulary & Spelling. Не пиши всі помилки!
    - НІКОЛИ не дублюй юніти! Кожен Unit має з'являтися у звіті лише ОДИН раз. Якщо є кілька помилок з одного правила, обери лише один найкращий приклад виправлення
    5. Для Grammar та Articles: 
       - Назву теми бери СУВОРО з "ДОВІДНИКА ЮНІТІВ" нижче. НЕ вигадуй власних назв!
       - Формат виводу для кожної теми має бути строго на ТРЬОХ рядках:
         - [Точна назва з довідника]
         📍 Unit [Номер]
         👉 [ТІЛЬКИ правильний варіант, без порівняння чи дужок]
         - ЖОДНИХ порожніх рядків між темами всередині однієї категорії! Порожній рядок має бути ТІЛЬКИ перед новою категорією
    6. Для Vocabulary & Spelling: пиши ТІЛЬКИ правильне слово/фразу через тире (-). ЖОДНИХ пояснень чи прикладів!
    7. Наприкінці звіту (з нового абзацу) ОБОВ'ЯЗКОВО додай рівно одне речення: "📚 Щоб закріпити матеріал, відкрий вказані юніти у підручнику нижче та виконай вправи!"
    8. НЕ використовуй зірочок (*), жирного тексту чи іншого markdown. Тільки чистий текст, тире та вказані емодзі.
    
    ДОВІДНИК ЮНІТІВ:
    U1: Present continuous (I am doing)
    U2: Present simple (I do)
    U3: Present continuous and present simple 1 (I am doing and I do)
    U4: Present continuous and present simple 2 (I am doing and I do)
    U5: Past simple (I did)
    U6: Past continuous (I was doing)
    U7: Present perfect 1 (I have done)
    U8: Present perfect 2 (I have done)
    U9: Present perfect continuous (I have been doing)
    U10: Present perfect continuous and simple (I have been doing and I have done)
    U11: how long have you (been) ...?
    U12: for and since when...? and how long...?
    U13: Present perfect and past 1 (I have done and I did)
    U14: Present perfect and past 2 (I have done and I did)
    U15: Past perfect (I had done)
    U16: Past perfect continuous (I had been doing)
    U17: have and have got
    U18: used to (do)
    U19: Present tenses (I am doing / I do) for the future
    U20: I'm going to (do)
    U21: will and shall 1
    U22: will and shall 2
    U23: I will and I'm going to
    U24: will be doing and will have done
    U25: when I do and when I've done if and when
    U26: can, could and (be) able to
    U27: could (do) and could have (done)
    U28: must and can't
    U29: may and might 1
    U30: may and might 2
    U31: have to and must
    U32: must mustn't needn't
    U33: should 1
    U34: should 2
    U35: I'd better... it's time
    U36: would
    U37: can/could/would you ...? etc.
    U38: if I do... and if I did ...
    U39: if I knew... I wish I knew
    U40: if I had known... I wish I had known...
    U41: wish
    U42: Passive 1 (is done / was done)
    U43: Passive 2 (be done / been done / being done)
    U44: Passive 3
    U45: it is said that... he is said to he is supposed to
    U46: have something done
    U47: Reported speech 1 (he said that ...)
    U48: Reported speech 2
    U49: Questions 1
    U50: Questions 2 (do you know where...? / he asked me where ...)
    U51: Auxiliary verbs (have/do/can etc.) I think so / I hope so etc.
    U52: Question tags (do you? isn't it? etc.)
    U53: Verb +-ing (enjoy doing/stop doing etc.)
    U54: Verb + to... (decide to ... / forget to... etc.)
    U55: Verb (+ object) + to (I want you to ...)
    U56: Verb +-ing or to ... 1 (remember, regret etc.)
    U57: Verb +-ing or to... 2 (try, need, help)
    U58: Verb +-ing or to ... 3 (like / would like etc.)
    U59: prefer and would rather
    U60: Preposition (in/for/about etc.) + -ing
    U61: be/get used to... (I'm used to ...)
    U62: Verb + preposition + -ing (succeed in-ing/insist on -ing etc.)
    U63: there's no point in -ing, it's worth-ing etc.
    U64: to..., for... and so that ...
    U65: Adjective + to
    U66: to... (afraid to do) and preposition + -ing (afraid of -ing)
    U67: see somebody do and see somebody doing
    U68: -ing clauses (He hurt his knee playing football.)
    U69: Countable and uncountable 1
    U70: Countable and uncountable 2
    U71: Countable nouns with a/an and some
    U72: a/an and the
    U73: the 1
    U74: the 2 (school/ the school etc.)
    U75: the 3 (children / the children)
    U76: the 4 (the giraffe / the telephone / the old etc.)
    U77: Names with and without the 1
    U78: Names with and without the 2
    U79: Singular and plural
    U80: Noun + noun (a bus driver / a headache)
    U81: 's (your sister's name) and of... (the name of the book)
    U82: myself/yourself/themselves etc.
    U83: a friend of mine my own house on my own/by myself
    U84: there and it
    U85: some and any
    U86: no/none/any nothing/nobody etc.
    U87: much, many, little, few, a lot, plenty
    U88: all all of most/most of no/none of etc.
    U89: both/both of neither / neither of either/ either of
    U90: all every whole
    U91: each and every
    U92: Relative clauses 1: clauses with who/that/which
    U93: Relative clauses 2: clauses with and without who/that/which
    U94: Relative clauses 3: whose/whom/where
    U95: Relative clauses 4: extra information clauses (1)
    U96: Relative clauses 5: extra information clauses (2)
    U97: -ing and-ed clauses
    U98: Adjectives ending in -ing and -ed (boring/bored etc.)
    U99: Adjectives: a nice new house, you look tired
    U100: Adjectives and adverbs 1 (quick/quickly)
    U101: Adjectives and adverbs 2 (well, fast, late, hard/hardly)
    U102: so and such
    U103: enough and too
    U104: quite, pretty, rather and fairly
    U105: Comparative 1 (cheaper, more expensive etc.)
    U106: Comparative 2 (much better / any better etc.)
    U107: Comparative 3 (as... as / than)
    U108: Superlative (the longest, the most enjoyable etc.)
    U109: Word order 1: verb + object; place and time
    U110: Word order 2: adverbs with the verb
    U111: still any more yet already
    U112: even
    U113: although though even though in spite of despite
    U114: in case
    U115: unless as long as provided
    U116: as (as I walked ... / as I was ... etc.)
    U117: like and as
    U118: like as if
    U119: during for while
    U120: by and until by the time
    U121: at/on/in (time)
    U122: on time and in time
    U123: in/at/on (position) 1
    U124: in/at/on (position) 2
    U125: in/at/on (position) 3
    U126: to, at, in and into
    U127: in/on/at (other uses)
    U128: by at the end and in the end
    U129: Noun + preposition (reason for, cause of etc.)
    U130: Adjective + preposition 1
    U131: Adjective + preposition 2
    U132: Verb + preposition 1 to and at
    U133: Verb + preposition 2 about/for/of/after
    U134: Verb + preposition 3 about and of
    U135: Verb + preposition 4 of/for/from/on
    U136: Verb + preposition 5 in/into/with/to/on
    U137: Phrasal verbs 1 Introduction
    U138: Phrasal verbs 2 in/out
    U139: Phrasal verbs 3 out
    U140: Phrasal verbs 4 on/off (1)
    U141: Phrasal verbs 5 on/off (2)
    U142: Phrasal verbs 6 up/down
    U143: Phrasal verbs 7 up (1)
    U144: Phrasal verbs 8 up (2)
    U145: Phrasal verbs 9 away/back

    Приклад ідеального виводу:
    Ось теми та слова, які варто повторити, спираючись на твої помилки за тиждень:
    
    Grammar:
    - Present simple (I do)
    📍 Unit 2
    👉 Sometimes I watch matches
    - Past continuous (I was doing)
    📍 Unit 6
    👉 I was reading a book
    
    Articles:
    - a/an and the
    📍 Unit 72
    👉 an extraordinary player
    
    Vocabulary & Spelling:
    - faith
    - pave the way
    - driver's license

    📚 Щоб закріпити матеріал, відкрий вказані юніти у підручнику нижче та виконай вправи!
    """
    
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"[CLAUDE ADVICE ERROR]: {e}")
        return "Графіки згенеровані! (Порада тимчасово недоступна)."