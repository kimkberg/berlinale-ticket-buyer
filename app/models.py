from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from app.config import Config


class Event(BaseModel):
    id: int = 0
    ext_id_screening: str = ""
    date_display: str = ""
    weekday: str = ""
    time_text: str = ""
    unixtime: int = 0
    duration_minutes: int = 0
    venue_hall: str = ""
    ticket_state: str = ""  # available / pending / sold_out
    ticket_url: Optional[str] = None
    ticket_text: str = ""
    sale_time_str: Optional[str] = None


class Film(BaseModel):
    id: int = 0
    title: str = ""
    other_titles: list[str] = []
    short_synopsis: str = ""
    section_name: str = ""
    section_color: str = ""
    image_url: str = ""
    meta: list[str] = []
    information: list[str] = []
    cast: list[str] = []
    crew: list[str] = []
    link_url: str = ""
    events: list[Event] = []


class TicketInfo(BaseModel):
    ext_id_screening: str
    state: str
    text: str = ""
    url: Optional[str] = None


class GrabTask(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex[:8])
    film_id: int = 0
    film_title: str = ""
    ext_id_screening: str = ""
    venue: str = ""
    screening_time: str = ""
    sale_time: str = ""
    eventim_url: Optional[str] = None
    status: str = "pending"  # pending / watching / grabbing / success / failed / cancelled
    mode: str = "browser"  # browser / api
    created_at: str = ""
    updated_at: str = ""
    result_message: Optional[str] = None
    ticket_count: int = Config.TICKET_COUNT


class DayProgramme(BaseModel):
    date: str = ""
    weekday: str = ""
    sections: list[dict] = []
    # Each section: {"section_name": str, "section_color": str, "films": list[Film]}


class TaskCreate(BaseModel):
    film_id: int = 0
    film_title: str = ""
    ext_id_screening: str = ""
    venue: str = ""
    screening_time: str = ""
    sale_time: str = ""
    eventim_url: Optional[str] = None
    mode: str = "browser"
    ticket_count: int = Config.TICKET_COUNT


class StatusMessage(BaseModel):
    type: str  # ticket_status / task_update / grab_result
    data: dict = {}
