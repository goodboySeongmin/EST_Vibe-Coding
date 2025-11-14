# models.py
from sqlalchemy import Column, Integer, Float, Text, DateTime
from sqlalchemy.sql import func

from database import Base  # 같은 폴더에 database.py 있다고 가정

class ChatLog(Base):
    __tablename__ = "chat_logs"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    source_question = Column(Text, nullable=True)
    score = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
