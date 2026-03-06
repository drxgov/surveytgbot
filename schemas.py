from pydantic import BaseModel, Field


class AnswerCreate(BaseModel):
    user_id: int
    question_id: int
    answer_text: str = Field(min_length=1, max_length=1000)
