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


class PageUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    content_type: str | None = None
    theme: str | None = None


class PageResponse(PageMeta):
    url: str


class PageDetail(PageResponse):
    content: str
    content_type: str
