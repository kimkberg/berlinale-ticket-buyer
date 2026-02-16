from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.config import Config
from app.models import DayProgramme, Event, Film, TicketInfo

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        client_kwargs = {
            "base_url": Config.BERLINALE_BASE_URL,
            "timeout": 15.0,
            "headers": {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*",
                "Accept-Language": "en-US,en;q=0.9",
            },
        }
        if Config.PROXY_URL:
            client_kwargs["proxy"] = Config.PROXY_URL
            logger.info("Berlinale API using proxy: %s", Config.PROXY_URL)

        _client = httpx.AsyncClient(**client_kwargs)
    return _client


# ─── todayOnSale ─────────────────────────────────────────────

async def fetch_today_on_sale() -> list[Film]:
    """Fetch films on sale today from /api/v1/en/event/todayOnSale.

    Response format:
        { "sectionContentList": [ { "section": {...}, "contentList": [...] } ] }
    """
    client = _get_client()
    try:
        resp = await client.get(Config.TODAY_ON_SALE_API)
        resp.raise_for_status()
        data = resp.json()
        return _parse_section_content_list(data)
    except Exception:
        logger.exception("Failed to fetch todayOnSale")
        return []


# ─── Ticket status ───────────────────────────────────────────

async def fetch_ticket_status() -> dict[str, TicketInfo]:
    """Fetch ticket status from /10am/10am_ticket_en.js.

    Response format:
        { "success": "true", "date": "...", "tickets": { "EXT_ID": {...}, ... } }
    """
    client = _get_client()
    try:
        resp = await client.get(Config.TICKET_STATUS_URL)
        resp.raise_for_status()
        text = resp.text
        return _parse_ticket_js(text)
    except Exception:
        logger.exception("Failed to fetch ticket status")
        return {}


# ─── Programme (POST /api/v1/en/festival-program) ────────────

async def fetch_programme(day: str | None = None) -> list[Film]:
    """Fetch programme from the Berlinale festival-program POST API.

    Args:
        day: Optional date string in YYYY-MM-DD format to filter by day.
             If None, returns all programme items.
    """
    client = _get_client()
    body: dict = {
        "Sort": ["asc"],
        "Page": 1,
        "ResultsPerPage": 200,
    }

    if day is not None:
        try:
            dt = datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=ZoneInfo(Config.TIMEZONE))
            body["Date"] = [str(int(dt.timestamp()))]
        except ValueError:
            logger.warning("Invalid day format %r, fetching without date filter", day)

    try:
        all_items: list[dict] = []
        page = 1
        while True:
            body["Page"] = page
            resp = await client.post(Config.PROGRAMME_API, json=body)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items") or []
            all_items.extend(items)
            paging = data.get("paging") or {}
            if page >= (paging.get("last") or 1):
                break
            page += 1

        return _parse_programme_items(all_items)
    except Exception:
        logger.exception("Failed to fetch programme (day=%s)", day)
        return []


async def fetch_programme_with_tickets(day: str | None = None) -> list[Film]:
    """Fetch programme and merge with ticket status."""
    films = await fetch_programme(day)
    ticket_map = await fetch_ticket_status()
    return _merge_ticket_status(films, ticket_map)


async def get_day_programmes() -> list[DayProgramme]:
    """Get full programme organized by day with ticket status."""
    films = await fetch_programme_with_tickets()
    return _group_by_day(films)


async def get_day_programme(day: str) -> DayProgramme | None:
    """Get programme for a specific day."""
    films = await fetch_programme_with_tickets(day)
    days = _group_by_day(films)
    for d in days:
        if d.date == day:
            return d
    return None


# ─── Parsers ─────────────────────────────────────────────────

def _compute_sale_time_from_screening(unixtime: int) -> str:
    """Compute sale time: screening_date - 3 days at 10:00."""
    if not unixtime:
        return ""
    try:
        tz = ZoneInfo(Config.TIMEZONE)
        screening_dt = datetime.fromtimestamp(unixtime, tz=tz)
        sale_date = screening_dt.date() - timedelta(days=Config.SALE_ADVANCE_DAYS)
        sale_dt = datetime(
            sale_date.year, sale_date.month, sale_date.day,
            Config.SALE_TIME_HOUR, Config.SALE_TIME_MINUTE,
            tzinfo=tz,
        )
        return sale_dt.isoformat()
    except Exception:
        return ""


def _parse_programme_items(items: list[dict]) -> list[Film]:
    """Parse the items list from the festival-program POST API."""
    film_map: dict[int, Film] = {}
    no_id_films: list[Film] = []
    for item in items:
        film = _parse_film_item(item)
        if film:
            if film.id == 0 or film.id not in film_map:
                if film.id == 0:
                    no_id_films.append(film)
                else:
                    film_map[film.id] = film
            else:
                film_map[film.id].events.extend(film.events)
    return list(film_map.values()) + no_id_films


def _parse_section_content_list(data: dict) -> list[Film]:
    """Parse the sectionContentList response format from Berlinale API."""
    film_map: dict[int, Film] = {}
    no_id_films: list[Film] = []

    section_list = data.get("sectionContentList") or []
    for section_block in section_list:
        section_info = section_block.get("section") or {}
        section_name = section_info.get("name") or ""
        section_color = section_info.get("color") or ""

        content_list = section_block.get("contentList") or []
        for item in content_list:
            film = _parse_film_item(item, section_name, section_color)
            if film:
                if film.id == 0 or film.id not in film_map:
                    if film.id == 0:
                        no_id_films.append(film)
                    else:
                        film_map[film.id] = film
                else:
                    film_map[film.id].events.extend(film.events)

    return list(film_map.values()) + no_id_films


def _parse_film_item(item: dict, section_name: str = "", section_color: str = "") -> Film | None:
    """Parse a single film/content item from the API."""
    try:
        film_id = item.get("id", 0)
        title = item.get("title") or ""

        # Other titles
        other_titles = []
        ot = item.get("otherTitles")
        if isinstance(ot, list):
            other_titles = [t for t in ot if isinstance(t, str)]
        elif isinstance(ot, str) and ot:
            other_titles = [ot]

        # Section (may come from item itself or from parent)
        item_section = item.get("section") or {}
        if isinstance(item_section, dict):
            section_name = item_section.get("name") or section_name
            section_color = item_section.get("color") or section_color

        # Image
        image_url = ""
        img = item.get("image")
        if isinstance(img, dict):
            default_img = img.get("default") or {}
            if isinstance(default_img, dict):
                uri = default_img.get("uri") or ""
                if uri:
                    image_url = Config.BERLINALE_BASE_URL + uri if uri.startswith("/") else uri

        # Meta
        meta = item.get("meta") or []
        if not isinstance(meta, list):
            meta = []

        # Cast / crew
        cast = []
        for m in (item.get("reducedCastMembers") or item.get("castMembers") or []):
            if isinstance(m, dict) and m.get("name"):
                cast.append(m["name"])

        crew = []
        for m in (item.get("reducedCrewMembers") or item.get("crewMembers") or []):
            if isinstance(m, dict) and m.get("name"):
                crew.append(m["name"])

        # Link
        link_url = ""
        link = item.get("link")
        if isinstance(link, dict):
            link_url = link.get("url") or ""
            if link_url and link_url.startswith("/"):
                link_url = Config.BERLINALE_BASE_URL + link_url

        # Information
        information = item.get("information") or []
        if isinstance(information, str):
            information = [information] if information else []

        # Events / screenings
        events = []
        for ev_data in (item.get("events") or []):
            event = _parse_event(ev_data)
            if event:
                events.append(event)

        return Film(
            id=film_id,
            title=title,
            other_titles=other_titles,
            short_synopsis=item.get("shortSynopsis") or "",
            section_name=section_name,
            section_color=section_color,
            image_url=image_url,
            meta=meta,
            information=information,
            cast=cast,
            crew=crew,
            link_url=link_url,
            events=events,
        )
    except Exception:
        logger.exception("Failed to parse film item (id=%s, title=%r)", item.get("id", "?"), item.get("title", "?"))
        return None


def _parse_event(ev: dict) -> Event | None:
    """Parse a single event/screening from the API.

    Format:
        {
            "displayDate": {"dayAndMonth": "Feb 16", "weekday": "Mon"},
            "extIdScreening": "63-20260216-1000",
            "id": 33729,
            "time": {"durationInMinutes": 114, "text": "10:00", "unixtime": 1771232400},
            "venueHall": "Urania",
            "ticket": null | {"state": "...", "text": "...", "url": "..."},
            "information": "...",
            "subtitles": "..."
        }
    """
    try:
        ext_id = ev.get("extIdScreening") or ""
        time_info = ev.get("time") or {}
        display_date = ev.get("displayDate") or {}
        ticket = ev.get("ticket") or {}

        unixtime = time_info.get("unixtime") or 0

        # Build display date string
        day_month = display_date.get("dayAndMonth") or ""
        weekday = display_date.get("weekday") or ""
        date_display = f"{weekday} {day_month}".strip()

        # Ticket info from the event itself (may be null)
        ticket_state = ""
        ticket_url = None
        ticket_text = ""
        if isinstance(ticket, dict) and ticket:
            ticket_state = ticket.get("state") or ""
            ticket_url = ticket.get("url")
            ticket_text = ticket.get("text") or ""

        return Event(
            id=ev.get("id", 0),
            ext_id_screening=str(ext_id),
            date_display=date_display,
            weekday=weekday,
            time_text=time_info.get("text") or "",
            unixtime=unixtime,
            duration_minutes=time_info.get("durationInMinutes") or 0,
            venue_hall=ev.get("venueHall") or "",
            ticket_state=ticket_state,
            ticket_url=ticket_url,
            ticket_text=ticket_text,
            sale_time_str=_compute_sale_time_from_screening(unixtime),
        )
    except Exception:
        logger.exception("Failed to parse event (ext_id=%s)", ev.get("extIdScreening", "?"))
        return None


def _parse_ticket_js(text: str) -> dict[str, TicketInfo]:
    """Parse /10am/10am_ticket_en.js response.

    Format: {"success":"true","date":"...","environment":"prod","tickets":{...}}
    """
    ticket_map: dict[str, TicketInfo] = {}

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Could not parse ticket JS as JSON")
        return ticket_map

    # The tickets are nested under a "tickets" key
    tickets_data = data.get("tickets") or data
    if not isinstance(tickets_data, dict):
        return ticket_map

    for key, val in tickets_data.items():
        if not isinstance(val, dict):
            continue
        info = TicketInfo(
            ext_id_screening=val.get("extIdScreening") or str(key),
            state=val.get("state") or "unknown",
            text=val.get("text") or "",
            url=val.get("url"),
        )
        ticket_map[info.ext_id_screening] = info

    return ticket_map


def _merge_ticket_status(films: list[Film], ticket_map: dict[str, TicketInfo]) -> list[Film]:
    """Merge ticket status into film events."""
    if not ticket_map:
        return films

    for film in films:
        for event in film.events:
            if event.ext_id_screening in ticket_map:
                info = ticket_map[event.ext_id_screening]
                event.ticket_state = info.state
                if info.url:
                    event.ticket_url = info.url
                if info.text:
                    event.ticket_text = info.text

    return films


def _group_by_day(films: list[Film]) -> list[DayProgramme]:
    """Group films by screening date into DayProgramme objects."""
    # day_str -> section_name -> list of (film, event)
    day_sections: dict[str, dict[str, list[tuple[Film, Event]]]] = defaultdict(lambda: defaultdict(list))

    for film in films:
        for event in film.events:
            day_str = _extract_date(event)
            if not day_str:
                continue
            section = film.section_name or "Other"
            day_sections[day_str][section].append((film, event))

    programmes: list[DayProgramme] = []
    for day_str in sorted(day_sections.keys()):
        try:
            d = date.fromisoformat(day_str)
            weekday = d.strftime("%a")
        except ValueError:
            weekday = ""

        sections = []
        for section_name in sorted(day_sections[day_str].keys()):
            pairs = day_sections[day_str][section_name]
            # Build films with only the events for this day
            film_map: dict[int, Film] = {}
            for film, event in pairs:
                if film.id not in film_map:
                    film_map[film.id] = film.model_copy(update={"events": []})
                film_map[film.id].events.append(event)

            color = pairs[0][0].section_color if pairs else ""
            sections.append({
                "section_name": section_name,
                "section_color": color,
                "films": [f.model_dump() for f in film_map.values()],
            })

        programmes.append(DayProgramme(date=day_str, weekday=weekday, sections=sections))

    return programmes


def _extract_date(event: Event) -> str:
    """Extract YYYY-MM-DD date string from an event."""
    # Best: derive from unixtime
    if event.unixtime:
        try:
            return datetime.fromtimestamp(event.unixtime, tz=ZoneInfo(Config.TIMEZONE)).strftime("%Y-%m-%d")
        except Exception:
            pass
    # Fallback: parse from ext_id_screening (format: VENUE-YYYYMMDD-HHMM)
    ext = event.ext_id_screening
    if ext:
        parts = ext.split("-")
        if len(parts) >= 3:
            date_part = parts[-2]  # YYYYMMDD
            if len(date_part) == 8 and date_part.isdigit():
                return f"{date_part[:4]}-{date_part[4:6]}-{date_part[6:8]}"
    return ""


async def close():
    """Close the HTTP client."""
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
