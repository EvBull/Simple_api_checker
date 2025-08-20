import json
import asyncio
import requests
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.types import Message,BotCommand
from aiogram.filters import Command
from aiogram.client.default import DefaultBotProperties

ENV_FILE = "settings.env"
USERS_FILE = "users.json"

# URLs
load_dotenv(ENV_FILE)
api_url = os.getenv("api_url")
api_login_url = os.getenv("api_login_url")


# Device info


jwt_token = os.getenv("jwt_token")  
phone = os.getenv("phone")
device_id = os.getenv("device_id")
bot_token = os.getenv("BOT_TOKEN")
# debug place:

# print(f"ENV TOKEN: {bot_token}")
# print(f"API_Login \n {api_login_url} Api_General \n {api_url}" )
# print(f") 
bot = Bot(token=str(bot_token), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# === Работа с пользователями ===
def load_users():
    try:
        with open(USERS_FILE, "r") as f:
            content = f.read().strip()
            if not content:
                print("⚠️ Пустой users.json — инициализация нового словаря.")
                return {}

            data = json.loads(content)
            if isinstance(data, dict):
                return data
            else:
                print("⚠️ users.json содержит устаревший формат (список). Преобразуем.")
                return {str(user_id): "all" for user_id in data}  # миграция из списка в словарь

    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as e:
        print(f"❌ Ошибка чтения users.json: {e}")
        return {}


def save_users(users: dict):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f)

def save_user(chat_id: int, mode="all"):
    users = load_users()
    if not isinstance(users, dict):  # Доп. защита, если вдруг load_users() кто-то обошёл
        users = {}
    if str(chat_id) not in users:
        users[str(chat_id)] = mode
        save_users(users)
        print(f"🆕 Новый подписчик: {chat_id} (режим: {mode})")

async def setup_bot_commands():
    commands = [
        BotCommand(command="start", description="Подписаться на уведомления"),
        BotCommand(command="mute", description="Получать только ошибки"),
        BotCommand(command="unmute", description="Получать все уведомления"),
        BotCommand(command="help", description="Список команд"),
    ]
    await bot.set_my_commands(commands)

@dp.message(Command(commands=["subscribe"]))
async def handle_subscribe(message: Message):
    save_user(message.chat.id, mode="all")
    await message.answer("✅ Вы подписаны на все уведомления. Используй /mute, чтобы получать только про ошибки.")

@dp.message(Command(commands=["mute"]))
async def handle_mute(message: Message):
    users = load_users()
    users[str(message.chat.id)] = "errors"
    save_users(users)
    await message.answer("🔕 Вы будете получать только уведомления об ошибках. Используйте /unmute что бы получать все уведомления")

@dp.message(Command(commands=["unmute"]))
async def handle_unmute(message: Message):
    users = load_users()
    users[str(message.chat.id)] = "all"
    save_users(users)
    await message.answer("🔔 Вы будете получать все уведомления. Используйте /mute что бы получать только ошибки.")

# === Уведомление всем ===
async def notify_all(text: str, is_error=False):
    users = load_users()
    for user_id, mode in users.items():
        if mode == "errors" and not is_error:
            continue  # Пропускаем, если пользователь хочет только ошибки
        try:
            await bot.send_message(user_id, text)
        except Exception as e:
            print(f"❌ Не удалось отправить {user_id}: {e}")



# === Проверка API ===
async def check_api_status():
    try:
        response = requests.get(api_url)
        response.raise_for_status()
        await notify_all(f"✅ Общий API работает: статус {response.status_code}")
    except requests.exceptions.RequestException as e:
        await notify_all(f"❌ Проблема с общим API: {e}", is_error=True)

async def check_login_api():
    headers = {
        "Host": "api.samuapp.com",
        "Cookie": f"jwt={jwt_token}",
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json",
        "user-agent": "SamuApp/1.3 CFNetwork/3826.500.131 Darwin/24.5.0",
        "accept-language": "en-US,en;q=0.9"
    }
    payload = {
        "phone": phone,
        "deviceId": device_id
    }
    try:
        response = requests.post(api_login_url, headers=headers, json=payload)
        status = response.status_code
        if response.ok:
            print(f"✅ Авторизация работает: {status}")
            await notify_all(f"✅ Авторизация работает: статус {status}")
        elif status == 401:
            print("🔐 JWT токен просрочен")
        else:
            print(f"❌ Ошибка авторизации: {status}")
            await notify_all(f"❌ Ошибка авторизации: статус {status}, ответ: {response.text}")
    except Exception as e:
        print(f"🚫 Ошибка запроса авторизации: {e}")
        await notify_all(f"🚫 Ошибка авторизации: {e}")


# === Цикл проверки ===
async def monitor_loop():
    while True:
        await check_api_status()
        await check_login_api()
        await asyncio.sleep(300)  # Проверять каждые 5 минут


# === Основной запуск ===
async def main():
    # Запускаем и бота, и проверку API параллельно
    await setup_bot_commands()

    await asyncio.gather(
        dp.start_polling(bot),
        monitor_loop()
    )

if __name__ == "__main__":
    asyncio.run(main())