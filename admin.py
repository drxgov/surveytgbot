from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from database import SessionFactory
from models import Answer, Question, User
from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload

admin_router = Router()

cancel_keyboard = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="❌ Отмена")]],
    resize_keyboard=True,
    one_time_keyboard=True,
)
# ---------------- KEYBOARD ----------------


def admin_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить вопрос")],
            [KeyboardButton(text="❌ Удалить вопрос")],
            [KeyboardButton(text="📋 Вопросы")],
            [KeyboardButton(text="📊 Ответы")],
            [KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="👑 Назначить админа")],
            [KeyboardButton(text="🚫 Убрать админа")],
            [KeyboardButton(text="⬅️ Выйти")],
        ],
        resize_keyboard=True,
    )


# ---------------- FSM ----------------


class AdminState(StatesGroup):
    adding_question = State()
    deleting_question = State()
    make_admin = State()
    remove_admin = State()


# ---------------- Проверка админа ----------------


async def is_admin(user_id: int) -> bool:
    async with SessionFactory() as session:
        stmt = select(User).where(User.telegram_id == user_id)
        user = (await session.execute(stmt)).scalar_one_or_none()
        return user and user.is_admin


# ---------------- Панель ----------------


@admin_router.message(Command("admin"))
async def open_admin(message: Message):
    if not await is_admin(message.from_user.id):
        return

    await message.answer(
        "Админ панель открыта",
        reply_markup=admin_keyboard(),
    )


# ---------------- Добавить вопрос ----------------


@admin_router.message(F.text == "➕ Добавить вопрос")
async def add_question_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.adding_question)
    await message.answer(
        "Отправь текст нового вопроса.",
        reply_markup=cancel_keyboard,
    )


@admin_router.message(AdminState.adding_question)
async def save_question(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Действие отменено", reply_markup=admin_keyboard())
        return

    async with SessionFactory() as session:
        session.add(Question(text=message.text))
        await session.commit()

    await state.clear()
    await message.answer("Вопрос добавлен ✅", reply_markup=admin_keyboard())


# ---------------- Удалить вопрос ----------------


@admin_router.message(F.text == "❌ Удалить вопрос")
async def delete_question_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.deleting_question)
    await message.answer(
        "Отправь ID вопроса для удаления.",
        reply_markup=cancel_keyboard,
    )


@admin_router.message(AdminState.deleting_question)
async def delete_question_confirm(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Действие отменено", reply_markup=admin_keyboard())
        return

    try:
        qid = int(message.text)
    except ValueError:
        await message.answer("Нужен ID (число).")
        return

    async with SessionFactory() as session:
        await session.execute(delete(Question).where(Question.id == qid))
        await session.commit()

    await state.clear()
    await message.answer("Вопрос удалён ❌", reply_markup=admin_keyboard())


# ---------------- Вопросы ----------------


@admin_router.message(F.text == "📋 Вопросы")
async def list_questions(message: Message):
    async with SessionFactory() as session:
        result = await session.execute(select(Question))
        questions = result.scalars().all()

    if not questions:
        await message.answer("Вопросов нет.")
        return

    text = "\n".join(f"{q.id}. {q.text}" for q in questions)
    await message.answer(text)


# ---------------- Ответы ----------------


@admin_router.message(F.text == "📊 Ответы")
async def list_answers(message: Message):
    async with SessionFactory() as session:
        stmt = select(Answer).options(
            selectinload(Answer.user),
            selectinload(Answer.question),
        )
        result = await session.execute(stmt)
        answers = result.scalars().all()

    if not answers:
        await message.answer("Ответов нет.")
        return

    text = "\n\n".join(
        f"@{a.user.username or a.user.telegram_id}\n"
        f"{a.question.text}\n"
        f"Ответ: {a.answer_text}"
        for a in answers
    )

    await message.answer(text)


# ---------------- Пользователи ----------------


@admin_router.message(F.text == "👥 Пользователи")
async def list_users(message: Message):
    async with SessionFactory() as session:
        result = await session.execute(select(User))
        users = result.scalars().all()

    text = "\n".join(
        f"{u.telegram_id} | @{u.username or '—'} | admin={u.is_admin}" for u in users
    )

    await message.answer(text)


# ---------------- Назначить админа ----------------


@admin_router.message(F.text == "👑 Назначить админа")
async def make_admin_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.make_admin)
    await message.answer(
        "Отправь telegram_id пользователя.",
        reply_markup=cancel_keyboard,
    )


@admin_router.message(AdminState.make_admin)
async def make_admin_confirm(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Действие отменено", reply_markup=admin_keyboard())
        return

    try:
        tg_id = int(message.text)
    except ValueError:
        await message.answer("Нужен telegram_id.")
        return

    async with SessionFactory() as session:
        await session.execute(
            update(User).where(User.telegram_id == tg_id).values(is_admin=True)
        )
        await session.commit()

    await state.clear()
    await message.answer("Пользователь теперь админ 👑", reply_markup=admin_keyboard())


# ---------------- Убрать админа ----------------


@admin_router.message(F.text == "🚫 Убрать админа")
async def remove_admin_start(message: Message, state: FSMContext):
    await state.set_state(AdminState.remove_admin)
    await message.answer(
        "Отправь telegram_id пользователя.",
        reply_markup=cancel_keyboard,
    )


@admin_router.message(AdminState.remove_admin)
async def remove_admin_confirm(message: Message, state: FSMContext):
    if message.text == "❌ Отмена":
        await state.clear()
        await message.answer("Действие отменено", reply_markup=admin_keyboard())
        return

    try:
        tg_id = int(message.text)
    except ValueError:
        await message.answer("Нужен telegram_id.")
        return

    async with SessionFactory() as session:
        await session.execute(
            update(User).where(User.telegram_id == tg_id).values(is_admin=False)
        )
        await session.commit()

    await state.clear()
    await message.answer("Админ права сняты 🚫", reply_markup=admin_keyboard())


# ---------------- Выход ----------------


@admin_router.message(F.text == "⬅️ Выйти")
async def exit_admin(message: Message):
    await message.answer("Выход из админ панели.", reply_markup=ReplyKeyboardRemove())
