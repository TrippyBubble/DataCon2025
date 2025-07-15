import logging
from aiogram.types import InputMediaPhoto
from aiogram.types import CallbackQuery
from aiogram.types import Message, FSInputFile, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from os import path
import sqlite3
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import asyncio


TOKEN = 'Впишите сюда токен'

bot = Bot(token=TOKEN)
dp = Dispatcher()
# Пути к изображениям
graphs = [
    FSInputFile(path.join('plots', 'parity_plot.jpg')),
    FSInputFile(path.join('plots', 'residuals_histogram.jpg')),
    FSInputFile(path.join('plots', 'residuals_plot.jpg')),
    FSInputFile(path.join('plots', 'metrics_summary.jpg'))
]

mainb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text='Расчитать активность нового вещества')],
    [KeyboardButton(text='Посмотреть метрики модели')],
[KeyboardButton(text='Вернуть информацию о старых поисках')]
])


# Клавиатура с кнопкой "Да, начать"
confirm_keyboard = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, начать", callback_data="confirm_start_search")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_start_search")]
    ]
)

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer('Я бот, который добавляет новые экспериментальные данные в БД и выводит актуальную информацию.', reply_markup=mainb)



# Определяем состояния
class DataInput(StatesGroup):
    waiting_for_input = State()
    waiting_for_confirmation = State()
    waiting_for_data = State()


@dp.message(F.text == 'Расчитать активность нового вещества')
async def request_input(message: types.Message, state: FSMContext):
    await message.answer("Введите ChemBL ID или SMILES:")
    await state.set_state(DataInput.waiting_for_input)


@dp.message(DataInput.waiting_for_input)
async def handle_input(message: types.Message, state: FSMContext):
    user_input = message.text.strip()
    await state.update_data(smiles_or_id=user_input)

    await message.answer(
        f"Вы ввели: `{user_input}`\n\n"
        "Начать поиск активных молекул для нового вещества?\n"
        "Это создаст новую БД, и доступ к текущей будет временно недоступен.",
        reply_markup=confirm_keyboard,
        parse_mode="Markdown"
    )
    await state.set_state(DataInput.waiting_for_confirmation)

# Создание клавиатуры с кнопками
def generate_table_keyboard():
    tables = get_table_names(DATABASE_PATH)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=table, callback_data=f"table:{table}")]
            for table in tables
        ]
    )
    return keyboard

@dp.message(F.text == 'Вернуть информацию о старых поисках')
async def request_input(message: types.Message, state: FSMContext):
    await message.answer("Выберите таблицу из предыдущих запусков:")
    await message.answer("Ниже список доступных таблиц. Тут конечно надо переименовывать, но что есть, то есть, "
                         "времени на верстку мало):", reply_markup=generate_table_keyboard())



DATABASE_PATH = '/Users/kuki/PycharmProjects/DataCon/data/Chem.db'
def get_table_names(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables


@dp.message(F.text == 'Посмотреть метрики модели')

async def send_graphs(message: types.Message):
    media_group = [
        InputMediaPhoto(media=FSInputFile('plots/parity_plot.jpg')),
        InputMediaPhoto(media=FSInputFile('plots/residuals_histogram.jpg')),
        InputMediaPhoto(media=FSInputFile('plots/residuals_plot.jpg')),
        InputMediaPhoto(media=FSInputFile('plots/metrics_summary.jpg'))
    ]
    await message.answer_media_group(media_group)




@dp.message(DataInput.waiting_for_data)
async def handle_input(message: types.Message, state: FSMContext):
    user_data = await state.get_data()
    data_index = user_data["data_index"]


# Обработчик нажатия на кнопку "Да, начать"
@dp.callback_query(F.data == "confirm_start_search")
async def confirmed_start_search(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✅ Поиск активных молекул для вещества запущен, после завершения вам придет "
                                     "уведомление")
    await state.set_state(DataInput.waiting_for_data)


# Обработчик нажатия на "Отмена"
@dp.callback_query(F.data == "cancel_start_search")
async def cancel_search(callback: CallbackQuery):
    await callback.message.edit_text("❎ Поиск отменён.")


async def main():
    await dp.start_polling(bot)

def start_bot():
    logging.basicConfig(level=logging.INFO)
    # чисто для теста и дебагинга, потом удалять строку ту что выше
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('Выход')

if __name__ == '__main__':
    start_bot()
