import asyncio

from admin import admin_router
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from config import settings
from database import SessionFactory, engine
from models import Answer, Base, Question, User
from schemas import AnswerCreate
from sqlalchemy import select
from sqlalchemy.orm import selectinload

bot = Bot(settings.bot_token)
dp = Dispatcher()


# ---------------- KEYBOARD ----------------


def start_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Начать анкету")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ---------------- FSM ----------------


class SurveyState(StatesGroup):
    answering = State()


# ---------------- DB INIT ----------------


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_questions():
    async with SessionFactory() as session:
        result = await session.execute(select(Question))
        if not result.scalars().first():
            session.add_all(
                [
                    Question(text="Как тебя зовут?"),
                    Question(text="Сколько тебе лет?"),
                    Question(text="Чем занимаешься?"),
                ]
            )
            await session.commit()


# ---------------- HANDLERS ----------------


@dp.message(Command("start"))
async def start_handler(message: Message):
    async with SessionFactory() as session:
        # 1️⃣ ищем пользователя
        stmt = select(User).where(User.telegram_id == message.from_user.id)
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()

        # 2️⃣ если нет — создаём
        if user is None:
            user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username,
                is_admin=(message.from_user.id == settings.admin_id),
            )
            session.add(user)
            await session.commit()

        # 3️⃣ если уже существует — проверяем админство
        else:
            if message.from_user.id == settings.admin_id and not user.is_admin:
                user.is_admin = True
                await session.commit()

    await message.answer(
        "Нажми кнопку ниже, чтобы начать анкетирование 👇",
        reply_markup=start_keyboard(),
    )


@dp.message(F.text == "Начать анкету")
async def start_survey(message: Message, state: FSMContext):
    async with SessionFactory() as session:
        result = await session.execute(select(Question))
        questions = result.scalars().all()

    if not questions:
        await message.answer("Вопросов пока нет.")
        return

    await state.update_data(questions=[q.id for q in questions], index=0)
    await state.set_state(SurveyState.answering)

    await message.answer(
        questions[0].text,
        reply_markup=ReplyKeyboardRemove(),
    )


@dp.message(SurveyState.answering)
async def handle_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    question_ids = data["questions"]
    index = data["index"]

    async with SessionFactory() as session:
        user_stmt = select(User).where(User.telegram_id == message.from_user.id)
        user = (await session.execute(user_stmt)).scalar_one()

        answer_schema = AnswerCreate(
            user_id=user.id,
            question_id=question_ids[index],
            answer_text=message.text,
        )

        answer = Answer(**answer_schema.model_dump())
        session.add(answer)
        await session.commit()

    index += 1

    if index >= len(question_ids):
        await state.clear()
        await message.answer("Анкетирование завершено ✅")
        return

    await state.update_data(index=index)

    async with SessionFactory() as session:
        question = await session.get(Question, question_ids[index])

    await message.answer(question.text)


# ---------------- ADMIN ----------------


@dp.message(Command("answers"))
async def admin_answers(message: Message):
    if message.from_user.id != settings.admin_id:
        return

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
        f"Вопрос: {a.question.text}\n"
        f"Ответ: {a.answer_text}"
        for a in answers
    )

    await message.answer(text)


# ---------------- MAIN ----------------


async def main():
    await init_db()
    await seed_questions()
    dp.include_router(admin_router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
