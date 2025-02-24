import os
import requests
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from dotenv import load_dotenv
from aiogram.types import BotCommand
import asyncio

load_dotenv()

TOKEN = os.getenv('BOT_TOKEN')

bot = Bot(token=TOKEN)
dp = Dispatcher()

users = {}


class ProfileStates(StatesGroup):
    weight = State()
    height = State()
    age = State()
    activity = State()
    city = State()


class FoodLogStates(StatesGroup):
    waiting_for_grams = State()

def calculate_water_goal(weight: int, activity: int) -> int:
    base = weight * 30
    activity_add = (activity // 30) * 500
    weather_add = 500
    return base + activity_add + weather_add


def calculate_calorie_goal(weight: int, height: int, age: int, activity: int) -> int:
    base = 10 * weight + 6.25 * height - 5 * age
    activity_add = activity * 7  # 7 ккал/минуту
    return int(base + activity_add)


def get_food_info(product_name: str) -> dict | None:
    url = f"https://world.openfoodfacts.org/cgi/search.pl?search_terms={product_name}&json=1"
    response = requests.get(url)
    if response.ok:
        data = response.json()
        if data['products']:
            product = data['products'][0]
            return {
                'name': product.get('product_name', product_name),
                'calories': product.get('nutriments', {}).get('energy-kcal_100g', 0)
            }
    return None


@dp.message(Command('start'))
async def send_welcome(message: Message):
    help_text = (
        "Привет! Я бот для отслеживания воды, калорий и активности.\n\n"
        "📋 Список доступных команд:\n\n"
        "/start - Начать работу с ботом\n"
        "/set_profile - Настроить профиль (вес, рост, возраст, активность, город)\n"
        "/log_water <количество> - Записать выпитую воду (в мл)\n"
        "/log_food <продукт> - Записать съеденный продукт\n"
        "/log_workout <тип> <минуты> - Записать тренировку\n"
        "/check_progress - Проверить прогресс по воде и калориям\n"
    )
    await message.answer(help_text)

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу с ботом"),
        BotCommand(command="set_profile", description="Настроить профиль"),
        BotCommand(command="log_water", description="Записать выпитую воду"),
        BotCommand(command="log_food", description="Записать съеденный продукт"),
        BotCommand(command="log_workout", description="Записать тренировку"),
        BotCommand(command="check_progress", description="Проверить прогресс"),
    ]
    await bot.set_my_commands(commands)


@dp.message(Command('set_profile'))
async def start_profile(message: Message, state: FSMContext):
    await message.answer("Введите ваш вес (кг):")
    await state.set_state(ProfileStates.weight)


@dp.message(ProfileStates.weight)
async def process_weight(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введите число!")
    await state.update_data(weight=int(message.text))
    await message.answer("Введите ваш рост (см):")
    await state.set_state(ProfileStates.height)


@dp.message(ProfileStates.height)
async def process_height(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введите число!")
    await state.update_data(height=int(message.text))
    await message.answer("Введите ваш возраст:")
    await state.set_state(ProfileStates.age)


@dp.message(ProfileStates.age)
async def process_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введите число!")
    await state.update_data(age=int(message.text))
    await message.answer("Сколько минут активности в день?")
    await state.set_state(ProfileStates.activity)


@dp.message(ProfileStates.activity)
async def process_activity(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введите число!")
    await state.update_data(activity=int(message.text))
    await message.answer("В каком городе вы находитесь?")
    await state.set_state(ProfileStates.city)


@dp.message(ProfileStates.city)
async def process_city(message: Message, state: FSMContext):
    data = await state.get_data()
    city = message.text.strip()

    user_data = {
        'weight': data['weight'],
        'height': data['height'],
        'age': data['age'],
        'activity': data['activity'],
        'city': city,
        'water_goal': calculate_water_goal(data['weight'], data['activity']),
        'calorie_goal': calculate_calorie_goal(data['weight'], data['height'], data['age'], data['activity']),
        'logged_water': 0,
        'logged_calories': 0,
        'burned_calories': 0
    }

    users[message.from_user.id] = user_data
    await message.answer(
        f"Профиль сохранён!\n"
        f"Норма воды: {user_data['water_goal']} мл/день\n"
        f"Норма калорий: {user_data['calorie_goal']} ккал/день"
    )
    await state.clear()


@dp.message(Command('log_water'))
async def log_water(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        return await message.answer("Сначала настройте профиль!")

    try:
        amount = int(message.text.split()[1])
        users[user_id]['logged_water'] += amount
        remaining = users[user_id]['water_goal'] - users[user_id]['logged_water']
        await message.answer(f"Добавлено {amount} мл. Осталось: {remaining} мл")
    except (IndexError, ValueError):
        await message.answer("Используйте: /log_water <объём в мл>")


@dp.message(Command('log_food'))
async def log_food(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in users:
        return await message.answer("Сначала настройте профиль!")

    try:
        product = message.text.split(maxsplit=1)[1]
        food_info = get_food_info(product)
        if not food_info or food_info['calories'] <= 0:
            return await message.answer("Продукт не найден!")

        await state.update_data(food_info=food_info)
        await message.answer(
            f"{food_info['name']} - {food_info['calories']} ккал/100г\n"
            "Сколько грамм вы съели?"
        )
        await state.set_state(FoodLogStates.waiting_for_grams)
    except IndexError:
        await message.answer("Используйте: /log_food <название продукта>")


@dp.message(FoodLogStates.waiting_for_grams)
async def process_grams(message: Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Введите число!")

    data = await state.get_data()
    grams = int(message.text)
    calories = (data['food_info']['calories'] * grams) / 100
    users[message.from_user.id]['logged_calories'] += calories
    await message.answer(f"Добавлено {calories:.1f} ккал")
    await state.clear()


@dp.message(Command('log_workout'))
async def log_workout(message: Message):
    types = ('бег','ходьба', 'велосипед')
    user_id = message.from_user.id
    if user_id not in users:
        return await message.answer("Сначала настройте профиль!")

    try:
        _, workout_type, minutes = message.text.split()
        minutes = int(minutes)
        if workout_type not in types:
            return await message.answer(f"Выберите корректный тип из списка "
                                        f"{', '.join(types)}")


        calories_burned = {
                              'бег': 10,
                              'ходьба': 5,
                              'велосипед': 8
                          }.get(workout_type.lower()) * minutes

        users[user_id]['burned_calories'] += calories_burned
        water_needed = (minutes // 30) * 200
        await message.answer(
            f"🏋️ {workout_type} {minutes} мин: {calories_burned} ккал сожжено\n"
            f"💧 Выпейте {water_needed} мл воды"
        )
    except (ValueError, IndexError):
        await message.answer(
            "Используйте: /log_workout <тип> <минуты>\n"
            f"<тип> in ({', '.join(types)})"
        )


@dp.message(Command('check_progress'))
async def check_progress(message: Message):
    user_id = message.from_user.id
    if user_id not in users:
        return await message.answer("Сначала настройте профиль!")

    user = users[user_id]
    progress = (
        f"💧 Вода: {user['logged_water']}/{user['water_goal']} мл\n"
        f"🔥 Калории: {user['logged_calories']:.1f} съедено\n"
        f"🏃 {user['burned_calories']} сожжено\n"
        f"🎯 Осталось: {user['calorie_goal'] - (user['logged_calories'] - user['burned_calories']):.1f} ккал"
    )
    await message.answer(progress)

async def main():
    await set_commands(bot)
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())