from datetime import date


class Config:
    # Berlinale website
    BERLINALE_BASE_URL = "https://www.berlinale.de"
    TODAY_ON_SALE_API = "/api/v1/en/event/todayOnSale"
    TICKET_STATUS_URL = "/10am/10am_ticket_en.js"
    PROGRAMME_API = "/api/v1/en/festival-program"

    # Eventim integration
    EVENTIM_BASE_URL = "https://www.eventim.de"
    EVENTIM_LOGIN_URL = "https://www.eventim.de/myAccount"
    EVENTIM_PARTNER = 3
    EVENTIM_AFFILIATE = "BNA"

    # Local paths
    BROWSER_PROFILE_DIR = "data/browser_profile"
    TASKS_FILE = "data/tasks.json"

    # Server
    SERVER_HOST = "0.0.0.0"
    SERVER_PORT = 8000

    # Ticket polling
    TICKET_POLL_INTERVAL = 10  # seconds

    # Grab settings
    GRAB_RETRY_COUNT = 3
    GRAB_RETRY_DELAY = 1.0  # seconds (optimized from 2s for faster retries while avoiding rate limits)
    PRE_SALE_WARMUP = 60  # seconds before sale to start browser
    PRE_SALE_OPEN_PAGE = 15  # seconds before sale to open page (optimized from 30s)
    PRE_SALE_POLL = 5  # seconds before sale to start polling
    POLL_INTERVAL = 0.5  # seconds between polls

    # Monitor settings
    MONITOR_POLL_INTERVAL = 15       # seconds between polls (normal)
    MONITOR_FAST_POLL_INTERVAL = 2   # seconds between polls (optimized from 5s for faster availability detection)
    MONITOR_GOLDEN_HOUR_MINUTES = 60 # minutes before screening to switch to fast poll

    # Festival dates
    FESTIVAL_DATES = {
        "start": date(2026, 2, 12),
        "end": date(2026, 2, 22),
    }

    # Sale schedule
    SALE_ADVANCE_DAYS = 3
    SALE_TIME_HOUR = 10
    SALE_TIME_MINUTE = 0
    TIMEZONE = "Europe/Berlin"
