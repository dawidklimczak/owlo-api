import uuid
from datetime import datetime
from pydantic import BaseModel
from app.models.notification import NotificationType


class NotificationResponse(BaseModel):
    id: uuid.UUID
    topic_id: uuid.UUID | None
    type: NotificationType
    sent_at: datetime
    read_at: datetime | None

    model_config = {"from_attributes": True}


class MarkReadRequest(BaseModel):
    notification_ids: list[uuid.UUID]
