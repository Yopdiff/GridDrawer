from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Drawer(BaseModel):
    width: float = Field(gt=0)
    depth: float = Field(gt=0)


class BoxRow(BaseModel):
    depth: float = Field(gt=0)
    qty: int = Field(ge=1)


class Column(BaseModel):
    name: str = "Column"
    width: float = Field(gt=0)
    boxes: list[BoxRow] = Field(default_factory=list)


class Defaults(BaseModel):
    height: float = 40
    wall: float = 2
    r: float = 4
    cover_width: float = 32
    cover_width_short: float = 26
    short_depth_below: float = 45


class Project(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = 1
    drawer: Drawer
    defaults: Defaults = Defaults()
    columns: list[Column] = Field(default_factory=list)


class BoxSpec(BaseModel, frozen=True):
    length: float
    width: float
    height: float
    wall: float
    r: float
    cover_width: float


class Issue(BaseModel):
    level: str
    msg: str
    where: str = ""
