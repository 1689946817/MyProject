import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from .database import Base


class ImageRecord(Base):
    __tablename__ = "image_records"

    id = Column(String, primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    file_path = Column(String, nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow)
    generated_description = Column(Text, nullable=True)
    status = Column(String, default="Processing", index=True)
    source_dataset = Column(String, nullable=True)
    tags = Column(String, nullable=True)
    extra_metadata = Column(Text, nullable=True)

