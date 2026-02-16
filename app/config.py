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
    GRAB_RETRY_DELAY = 2  # seconds
    PRE_SALE_WARMUP = 60  # seconds before sale to start browser
    PRE_SALE_OPEN_PAGE = 30  # seconds before sale to open page
    PRE_SALE_POLL = 5  # seconds before sale to start polling
    POLL_INTERVAL = 0.5  # seconds between polls

    # Monitor settings
    MONITOR_POLL_INTERVAL = 15       # seconds between polls (normal)
    MONITOR_FAST_POLL_INTERVAL = 5   # seconds between polls (within golden hour)
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


class TimingConfig:
    """
    Realistic human timing behavior configuration.
    
    Uses normal distribution to generate click delays that mimic natural human
    variance while maximizing speed for competitive ticket grabbing.
    """
    
    # Timing mode: "racing" (aggressive) or "normal" (scheduled)
    TIMING_MODE = "racing"
    
    # Racing mode - someone actively watching and clicking fast
    # Range: 20-50ms (well-documented human reaction time for racing scenarios)
    RACING_CLICK_MEAN = 35      # ms - center of realistic human range
    RACING_CLICK_STDDEV = 8     # ms - natural variance (not robotic)
    RACING_CLICK_MIN = 20       # ms - fastest realistic clicks
    RACING_CLICK_MAX = 50       # ms - slower end of racing range
    
    # Normal mode - scheduled automation with comfortable delays
    # Range: 50-150ms (standard human interaction speeds)
    NORMAL_CLICK_MEAN = 120     # ms - comfortable reaction time
    NORMAL_CLICK_STDDEV = 30    # ms - natural variance
    NORMAL_CLICK_MIN = 50       # ms - lower bound
    NORMAL_CLICK_MAX = 150      # ms - upper bound
    
    # Page load waits - network and rendering delays
    # Networks are naturally variable, adding variance keeps human appearance
    PAGE_LOAD_MEAN = 1200       # ms - typical page load expectation
    PAGE_LOAD_STDDEV = 300      # ms - network variance (±25%)
    
    # UI interaction waits - for modals, banners, animations
    # Allows time for UI elements to dismiss and DOM to stabilize
    UI_INTERACTION_MEAN = 500   # ms - typical UI animation time
    UI_INTERACTION_STDDEV = 100 # ms - variance in UI rendering
