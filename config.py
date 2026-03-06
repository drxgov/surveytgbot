from pydantic import BaseModel


class Settings(BaseModel):
    bot_token: str
    admin_id: int


settings = Settings(bot_token="ваш токен", admin_id=asdj)
