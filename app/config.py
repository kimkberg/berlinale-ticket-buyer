import os
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
    TICKET_COUNT = 2  # default number of tickets to grab
    GRAB_RETRY_COUNT = 3
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
    # String representations for API
    FESTIVAL_START_DATE = FESTIVAL_DATES["start"].isoformat()
    FESTIVAL_END_DATE = FESTIVAL_DATES["end"].isoformat()

    # Sale schedule
    SALE_ADVANCE_DAYS = 3
    SALE_TIME_HOUR = 10
    SALE_TIME_MINUTE = 0
    TIMEZONE = "Europe/Berlin"

    # Proxy settings (optional)
    PROXY_URL = os.environ.get("PROXY_URL", None)  # e.g. "http://proxy:8080" or "socks5://proxy:1080"

    # Time synchronization settings (optional)
    TIME_SYNC_ENABLED = os.environ.get("TIME_SYNC_ENABLED", "true").lower() == "true"
    TIME_SYNC_METHOD = os.environ.get("TIME_SYNC_METHOD", "auto")  # "ntp", "http", or "auto"
    TIME_SYNC_INTERVAL = int(os.environ.get("TIME_SYNC_INTERVAL", "300"))  # seconds between re-syncs
    
    # Debug settings
    DEBUG_MODE = os.environ.get("DEBUG_MODE", "false").lower() == "true"


class TimingConfig:
    """
    Realistic human timing behavior configuration.
    
    Uses normal distribution to generate click delays that mimic natural human
    variance while maximizing speed for competitive ticket grabbing.
    """
    
    # Timing mode: "racing" (aggressive) or "normal" (scheduled)
    TIMING_MODE = "racing"
    
    # Racing mode - competitive but humanly possible
    # Range: 80-300ms (fast but realistic human reaction time)
    RACING_CLICK_MEAN = 30      # ms
    RACING_CLICK_STDDEV = 10    # ms
    RACING_CLICK_MIN = 10       # ms
    RACING_CLICK_MAX = 80       # ms
    
    # Normal mode - comfortable human interaction
    # Range: 150-600ms (relaxed clicking speed)
    NORMAL_CLICK_MEAN = 350     # ms
    NORMAL_CLICK_STDDEV = 80    # ms
    NORMAL_CLICK_MIN = 150      # ms
    NORMAL_CLICK_MAX = 600      # ms
    
    # Page load waits - network and rendering delays
    # Networks are naturally variable, adding variance keeps human appearance
    PAGE_LOAD_MEAN = 50       # ms
    PAGE_LOAD_STDDEV = 10     # ms
    PAGE_LOAD_MIN = 50        # ms
    PAGE_LOAD_MAX = 100       # ms
    
    # UI interaction waits - for modals, banners, animations
    # Allows time for UI elements to dismiss and DOM to stabilize
    UI_INTERACTION_MEAN = 150   # ms
    UI_INTERACTION_STDDEV = 30 # ms
    UI_INTERACTION_MIN = 50
    UI_INTERACTION_MAX = 100
