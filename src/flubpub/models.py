from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class IndexFilter(BaseModel):
    """Which pages an index page lists. All fields are optional; an empty
    filter matches every page (today's behavior)."""
    tags_any: list[str] = Field(default_factory=list)
    tags_all: list[str] = Field(default_factory=list)
    tags_none: list[str] = Field(default_factory=list)
    theme: str | list[str] | None = None
    color_scheme: str | list[str] | None = None
    content_type: str | list[str] | None = None
    slug_glob: str | None = None
    slug_regex: str | None = None
    before: datetime | None = None
    after: datetime | None = None
    parent: str | None = None
    kind: str | None = None       # "index" | "page"
    exclude_self: bool = True


class IndexSort(BaseModel):
    by: str = "created_at"        # created_at | updated_at | title | random | manual
    order: str = "desc"           # desc | asc
    seed: int | None = None       # used when by=random
    manual: list[str] = Field(default_factory=list)


class IndexSpec(BaseModel):
    """Per-page configuration for an index page. Lives at pages.json[i].index."""
    template: str = "gallery"     # name of a folder under templates/
    vars: dict[str, Any] = Field(default_factory=dict)
    filter: IndexFilter = Field(default_factory=IndexFilter)
    sort: IndexSort = Field(default_factory=IndexSort)
    limit: int | None = None
    group_by: str | None = None   # year | month | quarter | theme | color_scheme | tags[0]
    shaper: str | None = None     # named function in flubpub.index_payload.SHAPERS
    show_dates: bool = True       # render per-entry date in the default <ul>; toggle off on landing pages


class PageCreate(BaseModel):
    title: str
    slug: str | None = None
    content: str
    content_type: str = "html"
    theme: str | None = None
    color_scheme: str | None = None
    index: IndexSpec | None = None
    parent: str | None = None
    excerpt: str | None = None
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    tile: dict[str, Any] | None = None


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
    color_scheme: str | None = None
    index: IndexSpec | None = None
    parent: str | None = None
    excerpt: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    tile: dict[str, Any] | None = None


class PageResponse(PageMeta):
    url: str


class PageDetail(PageResponse):
    content: str
    content_type: str
