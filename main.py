import asyncio, aiohttp, os, uuid, urllib.parse, random, re, sqlite3
from datetime import date
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
import database as db
from config import BOT_TOKEN, ADMIN_IDS, HF_TOKEN

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
PRICES = {"photo": 15, "ask": 15, "homework": 10, "voice": 50, "meme": 10, "story": 15, "joke": 5, "video": 200}

# === ГОЛОСА - Silero TTS ===
# rate: 1.0 = скорость обычного человека. Больше 1.08 не ставим, чтобы не было х2
VOICES = {
    "andrey":    {"name": "1. Андрей - грубый мужской", "speaker": "aidar",   "rate": 0.95, "pitch": 0.90},
    "ivan":      {"name": "2. Иван - молодой парень",    "speaker": "eugene",  "rate": 1.05, "pitch": 1.08},
    "stepan":    {"name": "3. Степан - низкий бас",      "speaker": "aidar",   "rate": 0.92, "pitch": 0.85},
    "misha":     {"name": "4. Дядя Миша - сантехник",   "speaker": "eugene",  "rate": 0.97, "pitch": 0.92},
    "tolya":     {"name": "5. Деда Толя - хриплый",     "speaker": "aidar",   "rate": 0.90, "pitch": 0.84},
    "nastya":    {"name": "6. Настя - милая девочка",    "speaker": "kseniya", "rate": 1.06, "pitch": 1.10},
    "vera":      {"name": "7. Вера - взрослая женщина", "speaker": "baya",    "rate": 1.00, "pitch": 1.00},
    "anastasia": {"name": "8. Анастасия - нежная",       "speaker": "xenia",   "rate": 1.03, "pitch": 1.07},
    "sonya":     {"name": "9. Соня - писклявая малышка", "speaker": "kseniya", "rate": 1.08, "pitch": 1.15},
    "nina":      {"name": "10. Баба Нина - 85 лет",      "speaker": "baya",    "rate": 0.93, "pitch": 0.88},
}

user_state = {}
daily_claimed = {}
quiz_state = {}
user_stats = {}
banned_users = set()
used_free_photo = set()

def main_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🎨 Фото"), KeyboardButton(text="🎙 Голос")],[KeyboardButton(text="❓ Вопрос"), KeyboardButton(text="📚 ДЗ")],[KeyboardButton(text="🎭 Мем"), KeyboardButton(text="📖 История")],[KeyboardButton(text="🎲 Викторина"), KeyboardButton(text="😂 Шутка")],[KeyboardButton(text="💰 Баланс"), KeyboardButton(text="💰 Купить")],[KeyboardButton(text="🎁 Бонус"), KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)

def init_banned_table():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS banned_users (user_id INTEGER PRIMARY KEY, reason TEXT, banned_at TEXT)")
    conn.commit()
    conn.close()
def load_banned():
    init_banned_table()
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM banned_users")
    ids = {row[0] for row in cur.fetchall()}
    conn.close()
    return ids
def add_ban_db(target_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO banned_users (user_id, reason, banned_at) VALUES (?, ?, ?)", (target_id, "ban by admin", str(date.today())))
    conn.commit()
    conn.close()
    banned_users.add(target_id)
def remove_ban_db(target_id):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("DELETE FROM banned_users WHERE user_id = ?", (target_id,))
    conn.commit()
    conn.close()
    banned_users.discard(target_id)
def is_banned(uid):
    return uid in banned_users
def add_stat(uid, kind):
    if uid not in user_stats:
        user_stats[uid] = {"photo": 0, "voice": 0, "ask": 0, "total": 0}
    if kind in user_stats[uid]:
        user_stats[uid][kind] += 1
    user_stats[uid]["total"] += 1
def clean_prompt(text):
    t = text.strip()
    t = re.sub(r'\bмне\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\bпожалуйста\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\bсделай\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\bнарисуй\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\bсгенерируй\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\bфото\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\bкартинку\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\bкартинка\b', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+', ' ', t).strip()
    return t
FOOD_WORDS = ["борщ", "пельмени", "пицца", "суп", "салат", "блины", "пирог", "торт", "паста", "плов", "шашлык", "котлета", "оладьи", "сырники", "вареники", "хинкали", "суши", "роллы", "бургер", "картошка", "курица", "рыба", "стейк", "каша", "омлет", "завтрак", "обед", "ужин", "блюдо", "еда", "десерт", "мороженое", "шоколад", "кофе", "чай"]
async def translate_to_english(text):
    if all(ord(c) < 128 for c in text):
        return text
    try:
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=ru&tl=en&dt=t&q={urllib.parse.quote(text)}"
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=10) as r:
                data = await r.json()
                translated = "".join([x[0] for x in data[0] if x[0]])
                return translated if translated else text
    except:
        return text
async def ask_free_ai(prompt):
    url = f"https://text.pollinations.ai/{urllib.parse.quote(prompt)}"
    async with aiohttp.ClientSession() as s:
        async with s.get(url) as r:
            return await r.text()
async def gen_free_photo(prompt_ru):
    cleaned = clean_prompt(prompt_ru)
    if not cleaned:
        cleaned = "cute cat"
    low_cleaned = cleaned.lower()
    is_food = any(w in low_cleaned for w in FOOD_WORDS)
    prompt = await translate_to_english(cleaned)
    if is_food:
        prompt_en = f"Delicious {prompt}, traditional dish, served in a bowl on wooden table, close-up food photography, appetizing, steam, realistic, high detail"
    else:
        prompt_en = f"A photo of {prompt}, high quality, detailed, photorealistic, centered composition"
    filename = f"photo_{uuid.uuid4().hex}.jpg"
    for attempt in range(3):
        safe = urllib.parse.quote(prompt_en)
        headers = {"User-Agent": "Mozilla/5.0"}
        urls = [f"https://image.pollinations.ai/prompt/{safe}?width=1024&height=1024&seed={random.randint(1,999999)}&model=flux&nologo=true", f"https://image.pollinations.ai/prompt/{safe}?width=1024&height=1024&seed={random.randint(1,999999)}&model=turbo&nologo=true", f"https://image.pollinations.ai/prompt/{safe}?width=1024&height=1024&seed={random.randint(1,999999)}&model=flux-realism&nologo=true"]
        async with aiohttp.ClientSession(headers=headers) as s:
            for url in urls:
                try:
                    async with s.get(url, timeout=60) as r:
                        data = await r.read()
                        if len(data) > 15000 and r.headers.get("content-type", "").startswith("image"):
                            open(filename, "wb").write(data)
                            return filename
                except Exception as e:
                    print(f"Pollinations упал: {e}")
                    continue
        if HF_TOKEN and HF_TOKEN.startswith("hf_"):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post("https://api-inference.huggingface.co/models/runwayml/stable-diffusion-v1-5", headers={"Authorization": f"Bearer {HF_TOKEN}"}, json={"inputs": prompt_en}, timeout=120) as r:
                        data = await r.read()
                        if r.status == 200 and len(data) > 15000 and data[:10] != b'{"error"':
                            open(filename, "wb").write(data)
                            return filename
            except Exception as e:
                print(f"HF упал: {e}")
        if attempt < 2:
            await asyncio.sleep(5)
    raise Exception("Все серверы фото перегружены. Подожди 1 минуту и попробуй еще раз")
async def gen_10sec_video(prompt_ru):
    photo_file = await gen_free_photo(prompt_ru)
    from PIL import Image
    img = Image.open(photo_file).convert("RGB")
    img = img.resize((480, 480))
    w, h = img.size
    frames = []
    for i in range(100):
        zoom = 1.0 + (i / 100) * 0.4
        crop_w = int(w / zoom)
        crop_h = int(h / zoom)
        left = (w - crop_w) // 2
        top = (h - crop_h) // 2
        frame = img.crop((left, top, left + crop_w, top + crop_h))
        frame = frame.resize((480, 480))
        frames.append(frame)
    video_file = f"video_{uuid.uuid4().hex}.gif"
    frames[0].save(video_file, save_all=True, append_images=frames[1:], duration=100, loop=0, optimize=True)
    try: os.remove(photo_file)
    except: pass
    return video_file

# === Silero TTS ===
_silero_model = None
_silero_sample_rate = 48000
def _load_silero():
    global _silero_model
    if _silero_model is not None:
        return _silero_model
    import torch
    import torch.hub
    print("Скачиваю / гружу Silero TTS, первый раз ~60 МБ, жди...")
    model, _ = torch.hub.load(repo_or_dir='snakers4/silero-models', model='silero_tts', language='ru', speaker='v4_ru', trust_repo=True)
    model.to('cpu')
    _silero_model = model
    print("Silero загружен - OK")
    return model
def _change_speed_pitch(audio, sample_rate, rate, pitch):
    import numpy as np
    if rate == 1.0:
        return audio, sample_rate
    old_len = len(audio)
    new_len = int(old_len / rate)
    x_old = np.linspace(0, 1, old_len)
    x_new = np.linspace(0, 1, new_len)
    audio = np.interp(x_new, x_old, audio).astype(np.float32)
    return audio, sample_rate
async def gen_free_voice(text, voice_key):
    v = VOICES[voice_key]
    text = text[:200].strip()
    if not text:
        raise Exception("Пустой текст")
    final = f"voice_{uuid.uuid4().hex}.wav"
    print(f"ГОЛОС Silero: {v['name']} speaker={v['speaker']} rate={v['rate']} pitch={v['pitch']}")
    def _make():
        import soundfile as sf
        import numpy as np
        model = _load_silero()
        audio = model.apply_tts(text=text, speaker=v["speaker"], sample_rate=_silero_sample_rate, put_accent=True, put_yo=True)
        audio_np = audio.numpy() if hasattr(audio, 'numpy') else np.array(audio)
        audio_np, new_sr = _change_speed_pitch(audio_np, _silero_sample_rate, v["rate"], v["pitch"])
        sf.write(final, audio_np, new_sr)
        return final
    await asyncio.to_thread(_make)
    if os.path.exists(final) and os.path.getsize(final) > 3000:
        print(f"Голос Silero {v['name']} - OK")
        return final
    raise Exception("Silero не сгенерировал голос. Монеты не списаны.")

def pay_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Купить 100 монет за 10 ⭐", callback_data="buy_100")],[InlineKeyboardButton(text="💰 Купить 1000 монет за 90 ⭐", callback_data="buy_1000")]])
def balance_text(uid):
    bal = db.get_balance(uid)
    photos = bal // 15
    return f"💰 Баланс: {bal} монет\n\nЭтого хватит на:\n🎨 {photos} фото\n❓ {bal // 15} вопросов\n😂 {bal // 5} шуток"
async def check_balance(message, cost):
    bal = db.get_balance(message.from_user.id)
    if bal < cost:
        await message.answer(f"❌ У тебя {bal} монет, а нужно {cost}.\n\nМонеты закончились! Но не переживай, купить можно в любой момент:", reply_markup=pay_kb())
        return False
    return True
@dp.message(Command("start"))
async def start(m: types.Message):
    if is_banned(m.from_user.id):
        await m.answer("🚫 Ты забанен навсегда. Обратись к админу.")
        return
    db.init()
    key = db.create_user(m.from_user.id, m.from_user.username or "")
    await m.answer(f"👋 Привет, {m.from_user.first_name}! Я твой личный ИИ-помощник 🤖\n\n🎁 ПОДАРОК: первое фото — БЕСПЛАТНО! Просто нажми кнопку 🎨 Фото ниже и напиши, что нарисовать.\n\n💰 У тебя уже {db.get_balance(m.from_user.id)} монет — этого хватит на 6 фото!\n🔑 Твой ключ: `{key}`\n\n👇 Нажми кнопку внизу, не надо писать команды:", reply_markup=main_kb())
@dp.message(Command("help"))
async def help_cmd(m: types.Message):
    await m.answer("📖 ПОМОЩЬ — просто нажимай кнопки внизу 👇\n\n🎨 Фото — фото (15 монет, первое — бесплатно)\n🎬 Видео — напиши «видео кот в космосе» (200 монет)\n❓ Вопрос — нажми, потом напиши вопрос ИИ (15 монет)\n📚 ДЗ — помощь с домашкой (10 монет)\n🎙 Голос — озвучка 10 голосами (50 монет)\n🎭 Мем — мем (10 монет)\n📖 История — история (15 монет)\n🎲 Викторина — выиграй до +20 монет\n😂 Шутка — шутка (5 монет)\n💰 Баланс — сколько монет и на что хватит\n💰 Купить — купить монеты в любой момент\n🎁 Бонус — +20 монет каждый день", reply_markup=main_kb())
@dp.message(Command("balance"))
async def balance(m: types.Message):
    await m.answer(balance_text(m.from_user.id) + "\n\nХочешь еще? Купи в любой момент:", reply_markup=pay_kb())
@dp.message(Command("profile"))
async def profile(m: types.Message):
    uid = m.from_user.id
    bal = db.get_balance(uid)
    st = user_stats.get(uid, {"photo": 0, "voice": 0, "ask": 0, "total": 0})
    await m.answer(f"👤 Твой профиль: {m.from_user.first_name}\n🆔 ID: {uid}\n💰 Баланс: {bal} монет (хватит на {bal//15} фото)\n🎨 Фото: {st['photo']}\n🎙 Голосов: {st['voice']}\n❓ Вопросов: {st['ask']}\n📊 Всего: {st['total']}\n\n🎁 Не забудь /daily!", reply_markup=main_kb())
@dp.message(Command("top"))
async def top(m: types.Message):
    if not user_stats:
        await m.answer("🏆 Топ пока пустой. Стань первым! Нажми 🎨 Фото", reply_markup=main_kb())
        return
    sorted_users = sorted(user_stats.items(), key=lambda x: x[1]["total"], reverse=True)[:5]
    text = "🏆 ТОП-5 САМЫХ АКТИВНЫХ:\n\n"
    medals = ["🥇", "🥈", "🥉", "4.", "5."]
    for i, (uid, st) in enumerate(sorted_users):
        name = "Ты" if uid == m.from_user.id else f"ID {uid}"
        text += f"{medals[i]} {name} - {st['total']} действий\n"
    await m.answer(text, reply_markup=main_kb())
@dp.message(Command("daily"))
async def daily(m: types.Message):
    uid = m.from_user.id
    today = str(date.today())
    if daily_claimed.get(uid) == today:
        await m.answer("❌ Ты уже забрал бонус сегодня! Приходи завтра за +20 монет.", reply_markup=main_kb())
        return
    daily_claimed[uid] = today
    db.add_balance(uid, 20)
    await m.answer(f"🎁 Бонус дня! +20 монет!\n\n{balance_text(uid)}\nПриходи завтра за новым бонусом!", reply_markup=main_kb())
@dp.message(Command("buy"))
async def buy_cmd(m: types.Message):
    if is_banned(m.from_user.id):
        await m.answer("🚫 Ты забанен навсегда.")
        return
    bal = db.get_balance(m.from_user.id)
    await m.answer(f"💰 ПОКУПКА МОНЕТ\n\nТвой баланс сейчас: {bal} монет (хватит на {bal//15} фото)\n\nКупить можно в любой момент:\n• 100 монет = 10 ⭐\n• 1000 монет = 90 ⭐ (выгоднее!)\n\nВыбери пакет:", reply_markup=pay_kb())
@dp.callback_query(F.data.startswith("buy_"))
async def buy(c: types.CallbackQuery):
    if is_banned(c.from_user.id):
        await c.answer("🚫 Ты забанен.", show_alert=True)
        return
    amount = 100 if c.data == "buy_100" else 1000
    stars = 10 if c.data == "buy_100" else 90
    try:
        await bot.send_invoice(chat_id=c.from_user.id, title=f"{amount} монет", description=f"Пополнение баланса: {amount} монет для генерации фото, видео и голоса", payload=f"topup_{amount}", provider_token="", currency="XTR", prices=[LabeledPrice(label=f"{amount} монет", amount=stars)])
        await c.answer()
    except Exception as e:
        print(f"Ошибка отправки счета: {e}")
        await c.message.answer(f"❌ Ошибка оплаты: {e}\n\nНапиши админу, он починит.")
@dp.pre_checkout_query()
async def pre(q: types.PreCheckoutQuery):
    await bot.answer_pre_checkout_query(q.id, ok=True)
@dp.message(F.successful_payment)
async def paid(m: types.Message):
    try:
        amount = int(m.successful_payment.invoice_payload.split("_")[1])
    except:
        amount = 100
    db.add_balance(m.from_user.id, amount)
    await m.answer(f"✅ Оплачено! +{amount} монет.\n\n{balance_text(m.from_user.id)}\n\nСпасибо за покупку! ⭐", reply_markup=main_kb())
@dp.message(Command("stars"))
async def my_stars(m: types.Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("⛔ Только для админа")
        return
    try:
        bal = await bot.get_my_star_balance()
        await m.answer(f"⭐ Баланс звезд бота: {bal.amount} ⭐\n\nЭто звезды, которые тебе заплатили пользователи. Вывести их можно через @BotFather -> Баланс звезд -> Вывести на Fragment.")
    except Exception as e:
        await m.answer(f"Не смог получить баланс звезд: {e}")
@dp.message(Command("photo"))
async def photo_cmd(m: types.Message):
    await m.answer("🎨 Напиши, что нарисовать.\nПример: `фото кота в космосе`\n\nПервое фото — бесплатно! 🎁", reply_markup=main_kb())
@dp.message(Command("video"))
async def video_cmd(m: types.Message):
    bal = db.get_balance(m.from_user.id)
    await m.answer(f"🎬 10-СЕКУНДНОЕ ВИДЕО\n\n💰 Цена: 200 монет\nТвой баланс: {bal} монет\n\nНапиши, что должно быть в видео.\nПример: `видео кот в космосе`", reply_markup=main_kb())
@dp.message(Command("ask"))
async def ask_cmd(m: types.Message):
    user_state[m.from_user.id] = ("ask",)
    await m.answer("❓ Ты в режиме ВОПРОС ИИ.\n\nНапиши свой вопрос, я отвечу. Пример: `Привет, кто ты?`\nЧтобы выйти — нажми ❌ Отмена", reply_markup=main_kb())
@dp.message(Command("homework"))
async def homework_cmd(m: types.Message):
    await m.answer("📚 Напиши текстом, что задали. Пример: `реши: 2x + 5 = 15`", reply_markup=main_kb())
@dp.message(Command("voice"))
async def voice_cmd(m: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=v["name"], callback_data=f"voice_{k}")] for k, v in VOICES.items()])
    await m.answer("🎙 Выбери голос (50 монет, до 2 минут):\n\nЧтобы выйти — нажми ❌ Отмена внизу", reply_markup=kb)
@dp.callback_query(F.data.startswith("voice_"))
async def voice_pick(c: types.CallbackQuery):
    key = c.data.replace("voice_", "")
    if key not in VOICES:
        await c.answer("Ошибка выбора голоса")
        return
    user_state[c.from_user.id] = ("voice", key)
    await c.message.answer(f"Выбран: {VOICES[key]['name']}\n\nТеперь напиши текст для озвучки. Можно даже просто `привет` — я озвучу его.\nЕсли передумал — напиши «отмена»")
    await c.answer()
@dp.message(Command("meme"))
async def meme_cmd(m: types.Message):
    topic = m.text.replace("/meme", "").strip()
    if not topic:
        await m.answer("🎭 Напиши тему для мема.\nПример: `/meme школа`")
        return
    if not await check_balance(m, 10):
        return
    await m.answer("🎭 Придумываю мем... 5 сек...")
    text = await ask_free_ai(f"Придумай смешной мем про: {topic}. Формат: ЗАГОЛОВОК: ... ТЕКСТ МЕМА: ... ПОДПИСЬ: ... Коротко, смешно, на русском, для школьников.")
    db.spend(m.from_user.id, 10)
    add_stat(m.from_user.id, "ask")
    await m.answer(f"🎭 Твой мем про «{topic}»:\n\n{text[:3000]}\n\n-10 монет. {balance_text(m.from_user.id)}", reply_markup=main_kb())
@dp.message(Command("story"))
async def story_cmd(m: types.Message):
    topic = m.text.replace("/story", "").strip()
    if not topic:
        await m.answer("📖 Напиши тему истории.\nПример: `/story кот в космосе`")
        return
    if not await check_balance(m, 15):
        return
    await m.answer("📖 Пишу историю... 5 сек...")
    text = await ask_free_ai(f"Напиши короткую интересную историю на 10-12 предложений про: {topic}. Весело, с неожиданным концом, на русском.")
    db.spend(m.from_user.id, 15)
    add_stat(m.from_user.id, "ask")
    await m.answer(f"📖 История про «{topic}»:\n\n{text[:3500]}\n\n-15 монет. {balance_text(m.from_user.id)}", reply_markup=main_kb())
@dp.message(Command("joke"))
async def joke_cmd(m: types.Message):
    topic = m.text.replace("/joke", "").strip() or "школа"
    if not await check_balance(m, 5):
        return
    text = await ask_free_ai(f"Расскажи 1 короткую смешную шутку про: {topic}. Только шутку, без лишнего, на русском.")
    db.spend(m.from_user.id, 5)
    add_stat(m.from_user.id, "ask")
    await m.answer(f"😂 {text[:1000]}\n\n-5 монет. {balance_text(m.from_user.id)}", reply_markup=main_kb())
QUIZ_QUESTIONS = [{"q": "Сколько будет 2 + 2 * 2?", "options": ["6", "8", "4"], "correct": 0},{"q": "Столица Франции?", "options": ["Лондон", "Париж", "Берлин"], "correct": 1},{"q": "Какая планета самая большая?", "options": ["Марс", "Юпитер", "Венера"], "correct": 1},{"q": "Сколько дней в високосном году?", "options": ["365", "366", "364"], "correct": 1},{"q": "Кто написал «Войну и мир»?", "options": ["Пушкин", "Толстой", "Достоевский"], "correct": 1}]
def quiz_kb(q_idx):
    q = QUIZ_QUESTIONS[q_idx]
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=opt, callback_data=f"quiz_{q_idx}_{i}")] for i, opt in enumerate(q["options"])])
@dp.message(Command("quiz"))
async def quiz_cmd(m: types.Message):
    uid = m.from_user.id
    questions = QUIZ_QUESTIONS.copy()
    random.shuffle(questions)
    quiz_state[uid] = {"q": 0, "score": 0, "questions": questions}
    q = questions[0]
    await m.answer(f"🎲 Викторина! 5 вопросов.\nЕсли ответишь на все правильно - получишь +20 монет!\n\nВопрос 1/5:\n{q['q']}", reply_markup=quiz_kb(QUIZ_QUESTIONS.index(q)))
@dp.callback_query(F.data.startswith("quiz_"))
async def quiz_answer(c: types.CallbackQuery):
    uid = c.from_user.id
    if uid not in quiz_state:
        await c.answer("Начни заново: /quiz")
        return
    _, q_idx_str, ans_str = c.data.split("_")
    q_idx = int(q_idx_str); ans = int(ans_str)
    state = quiz_state[uid]
    orig_q = QUIZ_QUESTIONS[q_idx]
    if ans == orig_q["correct"]:
        state["score"] += 1
        await c.message.answer("✅ Правильно!")
    else:
        await c.message.answer(f"❌ Неправильно! Правильный ответ: {orig_q['options'][orig_q['correct']]}")
    state["q"] += 1
    if state["q"] >= 5:
        score = state["score"]
        del quiz_state[uid]
        if score == 5:
            db.add_balance(uid, 20)
            await c.message.answer(f"🎉 ИДЕАЛЬНО! 5/5! +20 монет!\n{balance_text(uid)}", reply_markup=main_kb())
        elif score >= 3:
            db.add_balance(uid, 10)
            await c.message.answer(f"👍 Хорошо! {score}/5! +10 монет!\n{balance_text(uid)}", reply_markup=main_kb())
        else:
            await c.message.answer(f"😅 Получилось {score}/5. Попробуй еще раз: /quiz", reply_markup=main_kb())
        await c.answer()
        return
    next_q = state["questions"][state["q"]]
    orig_idx = QUIZ_QUESTIONS.index(next_q)
    await c.message.answer(f"Вопрос {state['q']+1}/5:\n{next_q['q']}", reply_markup=quiz_kb(orig_idx))
    await c.answer()
@dp.message(Command("complaint"))
async def complaint_start(m: types.Message):
    user_state[m.from_user.id] = ("complaint", "text")
    await m.answer("🛠 Опиши, что случилось? Что за ошибка?\nЯ сохраню ее, а команда после исправления выдаст тебе 15.000 монет компенсации.\n\nЕсли передумал — напиши «отмена»")
def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],[InlineKeyboardButton(text="⭐ Баланс звезд", callback_data="admin_stars")],[InlineKeyboardButton(text="🏆 Топ пользователей", callback_data="admin_top")],[InlineKeyboardButton(text="🎁 Выдать 1000 монет себе", callback_data="admin_give_me")],[InlineKeyboardButton(text="🎁 Раздать всем +100 монет", callback_data="admin_give_all")],[InlineKeyboardButton(text="🚫 Забанить пользователя", callback_data="admin_ban")],[InlineKeyboardButton(text="✅ Разбанить пользователя", callback_data="admin_unban")],[InlineKeyboardButton(text="📋 Жалобы", callback_data="admin_complaints")],[InlineKeyboardButton(text="🔄 Обновить", callback_data="admin_refresh")]])
@dp.message(Command("admin"))
async def admin_panel(m: types.Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer(f"⛔ Только для админа.\n\nТвой ID: {m.from_user.id}\nДобавь его в config.py в ADMIN_IDS")
        return
    total_actions = sum(s["total"] for s in user_stats.values())
    await m.answer(f"🛠 АДМИН-ПАНЕЛЬ\n\n👥 Пользователей в топе: {len(user_stats)}\n📊 Всего действий: {total_actions}\n💰 Твой баланс: {db.get_balance(m.from_user.id)} монет\n🚫 Забанено навсегда: {len(banned_users)} чел.\n🎁 Бонус дня забрали: {len(daily_claimed)} чел.\n\nВыбери действие:", reply_markup=admin_kb())
@dp.callback_query(F.data.startswith("admin_"))
async def admin_buttons(c: types.CallbackQuery):
    if c.from_user.id not in ADMIN_IDS:
        await c.answer("⛔ Только для админа", show_alert=True)
        return
    if c.data == "admin_stats":
        total_actions = sum(s["total"] for s in user_stats.values())
        await c.message.edit_text(f"📊 СТАТИСТИКА\n\n👥 Пользователей в топе: {len(user_stats)}\n📊 Всего действий: {total_actions}\n🎨 Фото: {sum(s['photo'] for s in user_stats.values())}\n🎙 Голосов: {sum(s['voice'] for s in user_stats.values())}\n❓ Вопросов: {sum(s['ask'] for s in user_stats.values())}\n🚫 Забанено навсегда: {len(banned_users)} чел.\n🎁 Бонус дня: {len(daily_claimed)} чел.", reply_markup=admin_kb())
    elif c.data == "admin_stars":
        try:
            bal = await bot.get_my_star_balance()
            await c.message.edit_text(f"⭐ БАЛАНС ЗВЕЗД БОТА: {bal.amount} ⭐\n\nЭто звезды, которые заплатили пользователи.\nВывести: @BotFather -> Баланс звезд -> Вывести на Fragment.", reply_markup=admin_kb())
        except Exception as e:
            await c.message.edit_text(f"❌ Не смог получить баланс звезд: {e}", reply_markup=admin_kb())
    elif c.data == "admin_top":
        if not user_stats:
            await c.message.edit_text("🏆 Топ пока пустой.", reply_markup=admin_kb())
        else:
            sorted_users = sorted(user_stats.items(), key=lambda x: x[1]["total"], reverse=True)[:5]
            text = "🏆 ТОП-5:\n\n"
            for i, (uid, st) in enumerate(sorted_users):
                text += f"{i+1}. ID {uid} - {st['total']} действий\n"
            await c.message.edit_text(text, reply_markup=admin_kb())
    elif c.data == "admin_give_me":
        db.add_balance(c.from_user.id, 1000)
        await c.message.edit_text(f"✅ Выдано +1000 монет!\n\n💰 Баланс: {db.get_balance(c.from_user.id)}", reply_markup=admin_kb())
    elif c.data == "admin_give_all":
        all_ids = set(user_stats.keys())
        try:
            conn = sqlite3.connect("bot.db")
            cur = conn.cursor()
            cur.execute("SELECT user_id FROM users")
            for row in cur.fetchall():
                all_ids.add(row[0])
            conn.close()
        except Exception as e:
            print(f"Не смог прочитать всех: {e}")
        count = 0
        for uid in all_ids:
            try:
                db.add_balance(uid, 100)
                count += 1
                try:
                    await bot.send_message(uid, "🎁 Админ раздал всем +100 монет! Проверь /balance")
                except:
                    pass
            except:
                pass
        await c.message.edit_text(f"✅ Раздано +100 монет всем!\n\n👥 Получили: {count} чел.", reply_markup=admin_kb())
    elif c.data == "admin_ban":
        user_state[c.from_user.id] = ("admin_ban", "wait_id")
        await c.message.edit_text("🚫 КОГО ЗАБАНИТЬ?\n\nПришли ID пользователя.\nПример: `123456789`\nЧтобы отменить - напиши `отмена`", reply_markup=admin_kb())
    elif c.data == "admin_unban":
        user_state[c.from_user.id] = ("admin_unban", "wait_id")
        await c.message.edit_text(f"✅ КОГО РАЗБАНИТЬ?\n\nСейчас забанено навсегда: {len(banned_users)} чел.\nСписок: {list(banned_users) if banned_users else 'никого'}\n\nПришли ID для разбана. Пример: `123456789`\nЧтобы отменить - напиши `отмена`", reply_markup=admin_kb())
    elif c.data == "admin_complaints":
        try:
            conn = sqlite3.connect("bot.db")
            cur = conn.cursor()
            cur.execute("SELECT user_id, username, text FROM complaints ORDER BY id DESC LIMIT 5")
            rows = cur.fetchall()
            conn.close()
            if not rows:
                await c.message.edit_text("📋 Жалоб пока нет.", reply_markup=admin_kb())
            else:
                text = "📋 ПОСЛЕДНИЕ ЖАЛОБЫ:\n\n"
                for uid, username, txt in rows:
                    text += f"От @{username} (ID {uid}):\n{txt[:200]}\n---\n"
                await c.message.edit_text(text[:4000], reply_markup=admin_kb())
        except Exception as e:
            await c.message.edit_text(f"📋 Жалобы: ошибка: {e}", reply_markup=admin_kb())
    elif c.data == "admin_refresh":
        total_actions = sum(s["total"] for s in user_stats.values())
        await c.message.edit_text(f"🛠 АДМИН-ПАНЕЛЬ\n\n👥 Пользователей в топе: {len(user_stats)}\n📊 Всего действий: {total_actions}\n💰 Твой баланс: {db.get_balance(c.from_user.id)} монет\n🚫 Забанено навсегда: {len(banned_users)} чел.\n\nВыбери действие:", reply_markup=admin_kb())
    await c.answer()
@dp.message(Command("give"))
async def give(m: types.Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("⛔ Только для админа")
        return
    try:
        parts = m.text.split()
        target_id = int(parts[1]); amount = int(parts[2])
        db.add_balance(target_id, amount)
        await m.answer(f"✅ Выдано {amount} монет пользователю {target_id}")
        await bot.send_message(target_id, f"🎉 Тебе выдана компенсация: +{amount} монет!")
    except:
        await m.answer("Используй: /give 123456789 15000")
@dp.message(Command("stats"))
async def stats_cmd(m: types.Message):
    if m.from_user.id not in ADMIN_IDS:
        await m.answer("⛔ Только для админа")
        return
    total_actions = sum(s["total"] for s in user_stats.values())
    await m.answer(f"📊 Статистика:\n\n👥 Пользователей в топе: {len(user_stats)}\n📊 Всего действий: {total_actions}\n🎁 Бонус дня забрали: {len(daily_claimed)} чел.")
@dp.message(F.text.startswith("/"))
async def unknown_command(m: types.Message):
    await m.answer("❓ Я не знаю такую команду.\n\nПросто нажимай кнопки внизу 👇\n🎨 Фото • 🎙 Голос • ❓ Вопрос • 💰 Купить", reply_markup=main_kb())
@dp.message(F.text.in_(["🎨 Фото", "🎙 Голос", "❓ Вопрос", "📚 ДЗ", "🎭 Мем", "📖 История", "🎲 Викторина", "😂 Шутка", "💰 Баланс", "💰 Купить", "🎁 Бонус", "❌ Отмена"]))
async def buttons_handler(m: types.Message):
    txt = m.text
    if txt == "❌ Отмена":
        user_state.pop(m.from_user.id, None)
        await m.answer("✅ Отменено. Что делаем? Нажимай кнопку внизу 👇", reply_markup=main_kb())
        return
    if txt == "🎨 Фото":
        await m.answer("🎨 Напиши, что нарисовать.\nПример: `фото кота в космосе`\n\nПервое фото — бесплатно! 🎁")
        return
    if txt == "🎙 Голос":
        await voice_cmd(m)
        return
    if txt == "❓ Вопрос":
        await ask_cmd(m)
        return
    if txt == "📚 ДЗ":
        await m.answer("📚 Напиши текстом, что задали. Пример: `реши: 2x + 5 = 15`")
        return
    if txt == "🎭 Мем":
        await m.answer("🎭 Напиши тему для мема.\nПример: `мем школа`")
        return
    if txt == "📖 История":
        await m.answer("📖 Напиши тему истории.\nПример: `история кот в космосе`")
        return
    if txt == "🎲 Викторина":
        await quiz_cmd(m)
        return
    if txt == "😂 Шутка":
        await joke_cmd(m)
        return
    if txt == "💰 Баланс":
        await balance(m)
        return
    if txt == "💰 Купить":
        await buy_cmd(m)
        return
    if txt == "🎁 Бонус":
        await daily(m)
        return
@dp.message(F.text)
async def handle_text(m: types.Message):
    uid = m.from_user.id
    text = m.text.strip()
    low = text.lower().strip()
    if low in ["отмена", "❌ отмена", "назад", "стоп", "cancel"]:
        user_state.pop(uid, None)
        await m.answer("✅ Отменено. Что делаем?", reply_markup=main_kb())
        return
    if uid in user_state and user_state[uid][0] in ("admin_ban", "admin_unban"):
        action = user_state[uid][0]
        try:
            target_id = int(text.strip())
        except:
            await m.answer("❌ Это не ID. Пришли только цифры, например: 123456789")
            return
        del user_state[uid]
        if action == "admin_ban":
            if target_id in ADMIN_IDS:
                await m.answer("❌ Нельзя забанить админа!")
                return
            add_ban_db(target_id)
            await m.answer(f"🚫 Пользователь {target_id} ЗАБАНЕН НАВСЕГДА!", reply_markup=admin_kb())
            try:
                await bot.send_message(target_id, "🚫 Ты забанен админом навсегда. Бот для тебя больше не работает.")
            except:
                pass
        else:
            if is_banned(target_id):
                remove_ban_db(target_id)
                await m.answer(f"✅ Пользователь {target_id} РАЗБАНЕН!", reply_markup=admin_kb())
                try:
                    await bot.send_message(target_id, "✅ Тебя разбанили! Снова можешь пользоваться ботом.")
                except:
                    pass
            else:
                await m.answer(f"❌ Пользователь {target_id} не в бане.", reply_markup=admin_kb())
        return
    if is_banned(uid):
        await m.answer("🚫 Ты забанен навсегда. Обратись к админу.")
        return
    if uid in user_state and user_state[uid][0] == "complaint" and user_state[uid][1] == "text":
        user_state[uid] = ("complaint", "email", text)
        await m.answer("Понял. Записал.\n\nПришли свою почту, если хочешь. Если нет - напиши `пропустить`")
        return
    if uid in user_state and user_state[uid][0] == "complaint" and user_state[uid][1] == "email":
        complaint_text = user_state[uid][2]
        email = "" if low == "пропустить" else text
        user_state[uid] = ("complaint", "phone", complaint_text, email)
        await m.answer("Почту записал.\n\nПришли номер телефона, если хочешь. Если нет - `пропустить`")
        return
    if uid in user_state and user_state[uid][0] == "complaint" and user_state[uid][1] == "phone":
        complaint_text = user_state[uid][2]
        email = user_state[uid][3]
        phone = "" if low == "пропустить" else text
        db.save_complaint(uid, m.from_user.username or "", complaint_text, email, phone)
        del user_state[uid]
        await m.answer("✅ Жалоба сохранена! Команда посмотрит и выдаст 15.000 монет после исправления.", reply_markup=main_kb())
        for admin in ADMIN_IDS:
            try:
                await bot.send_message(admin, f"🚨 Новая жалоба!\nОт: @{m.from_user.username} (ID: {uid})\nПочта: {email}\nТелефон: {phone}\nТекст: {complaint_text}")
            except:
                pass
        return
    if uid in user_state and user_state[uid][0] == "voice":
        voice_key = user_state[uid][1]
        if voice_key not in VOICES:
            del user_state[uid]
            await m.answer("❌ Голос сброшен, выбери заново", reply_markup=main_kb())
            return
        if not await check_balance(m, 50):
            return
        await m.answer(f"🎙 Генерирую голос {VOICES[voice_key]['name']}... 10 сек, жди...")
        try:
            file = await gen_free_voice(text, voice_key)
            db.spend(uid, 50)
            db.save_history(uid, "voice", text, file)
            add_stat(uid, "voice")
            await m.answer_voice(FSInputFile(file), caption=f"Готово! Голос: {VOICES[voice_key]['name']}\n-50 монет. {balance_text(uid)}\n\nНапиши еще текст для озвучки или нажми ❌ Отмена", reply_markup=main_kb())
            try: os.remove(file)
            except: pass
        except Exception as e:
            await m.answer(f"❌ Ошибка голоса: {e}\n\nВыбор голоса сохранен: {VOICES[voice_key]['name']}. Просто напиши текст еще раз.", reply_markup=main_kb())
        return
    if uid in user_state and user_state[uid][0] == "ask":
        if not await check_balance(m, 15):
            return
        await m.answer("🤔 Думаю... 5 сек...")
        try:
            answer = await ask_free_ai(text)
        except Exception as e:
            await m.answer(f"❌ ИИ не отвечает: {e}", reply_markup=main_kb())
            return
        db.spend(uid, 15)
        db.save_history(uid, "ask", text, answer)
        add_stat(uid, "ask")
        await m.answer(answer[:4000] + f"\n\n-15 монет. {balance_text(uid)}\n\nНапиши еще вопрос или нажми ❌ Отмена", reply_markup=main_kb())
        return
    if low in ["привет", "привет!", "ку", "хай", "hello", "hi", "спасибо", "спс", "как дела", "как дела?", "что делаешь", "кто ты", "что ты умеешь"]:
        await m.answer("👋 Чтобы я ответил тебе — нажми кнопку ❓ Вопрос внизу, а потом напиши свой вопрос.\n\nА если хочешь озвучить «привет» голосом — нажми 🎙 Голос и выбери голос.", reply_markup=main_kb())
        return
    if low.startswith("видео") or low.startswith("video"):
        if not await check_balance(m, 200):
            return
        prompt = clean_prompt(text)
        if not prompt:
            prompt = "cute cat in space"
        await m.answer("🎬 Рисую кадр и собираю видео 10 сек... Это займет 40-60 сек, не уходи, я работаю! ⏳")
        try:
            file = await gen_10sec_video(prompt)
            db.spend(uid, 200)
            db.save_history(uid, "video", prompt, file)
            add_stat(uid, "photo")
            if file.endswith(".gif"):
                await m.answer_animation(FSInputFile(file), caption=f"🎬 Готово! Видео 10 сек: {prompt}\n\n-200 монет. {balance_text(uid)}", reply_markup=main_kb())
            else:
                await m.answer_video(FSInputFile(file), caption=f"🎬 Готово! Видео 10 сек: {prompt}\n\n-200 монет. {balance_text(uid)}", reply_markup=main_kb())
            try: os.remove(file)
            except: pass
        except Exception as e:
            await m.answer(f"❌ Ошибка видео: {e}\nМонеты НЕ списаны, попробуй еще раз через минуту.", reply_markup=main_kb())
        return
    if low.startswith("фото") or low.startswith("photo") or "нарисуй" in low or "сгенерируй" in low or "картинка" in low or "сделай фото" in low or "покажи" in low or low.startswith("мем") or low.startswith("история"):
        if low.startswith("мем"):
            topic = text.replace("мем", "").strip() or "школа"
            if not await check_balance(m, 10):
                return
            await m.answer("🎭 Придумываю мем... 5 сек...")
            t = await ask_free_ai(f"Придумай смешной мем про: {topic}. Формат: ЗАГОЛОВОК: ... ТЕКСТ МЕМА: ... ПОДПИСЬ: ... Коротко, смешно, на русском, для школьников.")
            db.spend(uid, 10)
            add_stat(uid, "ask")
            await m.answer(f"🎭 Твой мем про «{topic}»:\n\n{t[:3000]}\n\n-10 монет. {balance_text(uid)}", reply_markup=main_kb())
            return
        if low.startswith("история"):
            topic = text.replace("история", "").strip() or "кот"
            if not await check_balance(m, 15):
                return
            await m.answer("📖 Пишу историю... 5 сек...")
            t = await ask_free_ai(f"Напиши короткую интересную историю на 10-12 предложений про: {topic}. Весело, с неожиданным концом, на русском.")
            db.spend(uid, 15)
            add_stat(uid, "ask")
            await m.answer(f"📖 История про «{topic}»:\n\n{t[:3500]}\n\n-15 монет. {balance_text(uid)}", reply_markup=main_kb())
            return
        is_first = uid not in used_free_photo and user_stats.get(uid, {}).get("photo", 0) == 0
        if is_first:
            await m.answer(f"🎁 Первое фото — БЕСПЛАТНО! Рисую «{clean_prompt(text)}»... Это займет 40-60 сек, не уходи, я уже рисую! ⏳🎨")
            try:
                file = await gen_free_photo(text)
                used_free_photo.add(uid)
                db.save_history(uid, "photo", clean_prompt(text), file)
                add_stat(uid, "photo")
                await m.answer_photo(FSInputFile(file), caption=f"Готово! Твое первое фото — бесплатно! 🎁\n\nПонравилось? Следующее фото — 15 монет. У тебя {db.get_balance(uid)} монет.\nНажми 🎨 Фото еще раз!", reply_markup=main_kb())
                try: os.remove(file)
                except: pass
            except Exception as e:
                await m.answer(f"❌ {e}\n\nМонеты НЕ списаны, потому что первое фото бесплатное. Попробуй еще раз через 1 минуту.", reply_markup=main_kb())
            return
        if not await check_balance(m, 15):
            return
        prompt = clean_prompt(text)
        if not prompt:
            prompt = "cute cat"
        await m.answer(f"🎨 Рисую «{prompt}»... Это займет 40-60 сек, не уходи, я работаю! ⏳")
        try:
            file = await gen_free_photo(prompt)
            db.spend(uid, 15)
            db.save_history(uid, "photo", prompt, file)
            add_stat(uid, "photo")
            await m.answer_photo(FSInputFile(file), caption=f"Готово! «{prompt}» -15 монет. {balance_text(uid)}", reply_markup=main_kb())
            try: os.remove(file)
            except: pass
        except Exception as e:
            await m.answer(f"❌ Сервер фото перегружен, попробуй через 1 минуту.\n\nМонеты НЕ списаны! Твой баланс: {db.get_balance(uid)} монет", reply_markup=main_kb())
        return
    if "дз" in low or "домашка" in low or "реши" in low or "домашнее" in low:
        if not await check_balance(m, 10):
            return
        await m.answer("📚 Решаю ДЗ... 5 сек...")
        answer = await ask_free_ai(f"Ты лучший учитель. Реши подробно, по шагам: {text}")
        db.spend(uid, 10)
        db.save_history(uid, "homework", text, answer)
        add_stat(uid, "ask")
        await m.answer(answer[:4000] + f"\n\n-10 монет. {balance_text(uid)}", reply_markup=main_kb())
        return
    if text.startswith("/"):
        return
    await m.answer("👇 Нажми кнопку внизу, что ты хочешь?\n\n❓ Вопрос — задать вопрос ИИ\n🎨 Фото — нарисовать фото\n🎙 Голос — озвучить текст", reply_markup=main_kb())
@dp.message(F.photo)
async def homework_photo(m: types.Message):
    if is_banned(m.from_user.id):
        await m.answer("🚫 Ты забанен навсегда.")
        return
    if not await check_balance(m, 10):
        return
    await m.answer("📚 Вижу фото ДЗ!\nНапиши текстом, что там задано, например: `реши: 2x+5=15`", reply_markup=main_kb())
async def main():
    db.init()
    global banned_users
    banned_users = load_banned()
    print(f"Бот запущен! Забанено навсегда: {len(banned_users)} чел.")
    await dp.start_polling(bot)
if __name__ == "__main__":
    asyncio.run(main())