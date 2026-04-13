from datetime import datetime
from pydantic import BaseModel


class PageCreate(BaseModel):
    title: str
    slug: str | None = None
    content: str
    content_type: str = "html"


class PageMeta(BaseModel):
    title: str
    slug: str
    created_at: datetime
    updated_at: datetime
