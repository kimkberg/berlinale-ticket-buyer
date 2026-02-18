from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.config import Config, TimingConfig
from app.models import GrabTask
from app.timing import HumanTiming

logger = logging.getLogger(__name__)

# Browser navigation constants
BLANK_PAGE_URL = "about:blank"


class BrowserManager:
    """Manages a persistent Playwright browser context for Eventim sessions."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        # Extract domain from config URL for consistency
        # e.g., "https://www.eventim.de/myAccount" -> "eventim.de"
        from urllib.parse import urlparse
        parsed = urlparse(Config.EVENTIM_LOGIN_URL)
        self._eventim_domain = parsed.netloc.replace("www.", "")

    async def init_browser(self) -> None:
        """Start Playwright and create a persistent browser context."""
        if self._initialized:
            return

        async with self._init_lock:
            # Double-check after acquiring the lock
            if self._initialized:
                return

            from playwright.async_api import async_playwright

            profile_dir = Path(Config.BROWSER_PROFILE_DIR).resolve()
            profile_dir.mkdir(parents=True, exist_ok=True)

            # Remove stale SingletonLock from previous crashed browser
            lock_file = profile_dir / "SingletonLock"
            if lock_file.exists():
                lock_file.unlink(missing_ok=True)
                logger.warning("Removed stale SingletonLock from %s", profile_dir)

            self._playwright = await async_playwright().start()

            launch_args = {
                "user_data_dir": str(profile_dir),
                "headless": False,
                "viewport": {"width": 1280, "height": 900},
                "locale": "de-DE",
                "timezone_id": Config.TIMEZONE,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-dev-shm-usage",
                    "--start-maximized",
                ],
            }

            if Config.PROXY_URL:
                launch_args["proxy"] = {"server": Config.PROXY_URL}
                logger.info("Using proxy: %s", Config.PROXY_URL)

            self._context = await self._playwright.chromium.launch_persistent_context(**launch_args)

            # Apply stealth to existing and future pages
            try:
                from playwright_stealth import stealth_async
                for page in self._context.pages:
                    await stealth_async(page)
                self._context.on("page", lambda p: asyncio.ensure_future(stealth_async(p)))
            except ImportError:
                logger.warning("playwright-stealth not installed, skipping stealth setup")

            self._initialized = True
            logger.info("Browser initialized with persistent profile at %s", profile_dir)

    async def get_page(self) -> "Page":
        """Get the main browser page, creating one if needed."""
        if not self._initialized:
            await self.init_browser()
        
        try:
            pages = self._context.pages
            if pages:
                return pages[0]
            page = await self._context.new_page()
            await self._apply_stealth(page)
            return page
        except Exception as e:
            # Browser context was closed, reinitialize
            error_str = str(e).lower()
            if "closed" in error_str or "target" in error_str:
                logger.warning("Browser context was closed, reinitializing...")
                self._initialized = False
                self._context = None
                await self.init_browser()
                # Retry once after reinitializing
                pages = self._context.pages
                if pages:
                    return pages[0]
                page = await self._context.new_page()
                await self._apply_stealth(page)
                return page
            raise

    async def new_page(self) -> "Page":
        """Create a new browser tab."""
        if not self._initialized:
            await self.init_browser()
        
        try:
            page = await self._context.new_page()
            await self._apply_stealth(page)
            return page
        except Exception as e:
            # Browser context was closed, reinitialize
            error_str = str(e).lower()
            if "closed" in error_str or "target" in error_str:
                logger.warning("Browser context was closed, reinitializing...")
                self._initialized = False
                self._context = None
                await self.init_browser()
                # Retry once after reinitializing
                page = await self._context.new_page()
                await self._apply_stealth(page)
                return page
            raise

    async def open_login_page(self) -> bool:
        """Open Eventim login page for manual user login.
        
        If a page is already open, brings it to front instead of reloading.
        This preserves the user's session and any login state.
        """
        try:
            await self.init_browser()
            
            # Ensure context was successfully initialized
            if not self._context:
                logger.error("Browser context not initialized")
                return False
            
            # Check if we already have pages open
            pages = self._context.pages
            if pages:
                # Get the first page and bring it to front
                page = pages[0]
                await page.bring_to_front()
                
                # Only navigate if not already on a relevant page
                current_url = page.url
                
                # Check in order: blank page, then Eventim domain, then other domains
                if current_url == BLANK_PAGE_URL:
                    # Blank page, navigate to login
                    await page.goto(Config.EVENTIM_LOGIN_URL, wait_until="domcontentloaded")
                    logger.info("Navigated to Eventim login page from blank page")
                elif self._eventim_domain in current_url.lower():
                    # Already on Eventim, just bring to front
                    logger.info("Brought existing Eventim page to front (no reload)")
                else:
                    # On a different domain, navigate to login
                    await page.goto(Config.EVENTIM_LOGIN_URL, wait_until="domcontentloaded")
                    logger.info("Navigated to Eventim login page")
            else:
                # No pages open, create one and navigate
                page = await self._context.new_page()
                await self._apply_stealth(page)
                await page.goto(Config.EVENTIM_LOGIN_URL, wait_until="domcontentloaded")
                logger.info("Created new page and opened Eventim login page")
            
            return True
        except Exception:
            logger.exception("Failed to open login page")
            return False
    
    async def _apply_stealth(self, page: "Page") -> None:
        """Apply stealth mode to a page to avoid detection."""
        try:
            from playwright_stealth import stealth_async
            await stealth_async(page)
        except ImportError:
            pass

    async def check_session(self) -> dict:
        """Check if the current Eventim session is valid."""
        try:
            if not self._initialized:
                return {"logged_in": False, "message": "Browser not started"}

            page = await self.get_page()
            await page.goto(Config.EVENTIM_LOGIN_URL, wait_until="domcontentloaded")
            page_wait = HumanTiming.get_page_wait(1000)
            await page.wait_for_timeout(page_wait)

            url = page.url
            if "/login" in url.lower() or "/signin" in url.lower():
                return {"logged_in": False, "message": "Not logged in"}

            try:
                account_el = await page.query_selector(
                    '[class*="account"], [class*="user"], [class*="profile"]'
                )
                if account_el:
                    return {"logged_in": True, "message": "Session active"}
            except Exception:
                pass

            if "myaccount" in url.lower() or "account" in url.lower():
                return {"logged_in": True, "message": "Session active"}

            return {"logged_in": False, "message": "Session status unclear"}
        except Exception as e:
            logger.exception("Failed to check session")
            return {"logged_in": False, "message": str(e)}

    async def close(self) -> None:
        """Close the browser and cleanup."""
        if self._context:
            await self._context.close()
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
        self._initialized = False
        logger.info("Browser closed")

    @property
    def is_initialized(self) -> bool:
        return self._initialized


class TicketGrabber:
    """Automates the ticket purchasing flow on Eventim using Playwright."""

    # Timing constants for smart waits and interactions
    SMART_WAIT_TIMEOUT_MS = 3000  # Maximum time to wait for expected elements/navigation
    SMART_WAIT_FALLBACK_MS = 1500  # Fallback delay if smart wait times out

    # JavaScript function to detect cart/checkout navigation
    JS_WAIT_FOR_CART = """() => {
        const url = window.location.href.toLowerCase();
        return url.includes('cart') || url.includes('warenkorb') ||
               url.includes('basket') || url.includes('checkout');
    }"""

    # JavaScript function to detect cart/checkout/order navigation (extended)
    JS_WAIT_FOR_CART_EXTENDED = """() => {
        const url = window.location.href.toLowerCase();
        return url.includes('cart') || url.includes('warenkorb') ||
               url.includes('basket') || url.includes('checkout') ||
               url.includes('order');
    }"""

    # JavaScript function to detect cart-related page elements
    JS_WAIT_FOR_CART_ELEMENTS = """() => {
        const url = window.location.href.toLowerCase();
        return url.includes('cart') || url.includes('warenkorb') ||
               url.includes('basket') || url.includes('checkout') ||
               document.querySelector('[class*="cart"]') ||
               document.querySelector('[class*="checkout"]');
    }"""

    # JavaScript function to detect ticket purchase elements
    JS_WAIT_FOR_TICKET_ELEMENTS = """() => {
        return document.querySelector('button.js-stepper-action') ||
               document.querySelector('[data-qa="more-tickets"]') ||
               (document.querySelectorAll('button').length < 50 &&
                Array.from(document.querySelectorAll('button')).some(b => b.textContent.includes('Ticket')));
    }"""

    def __init__(self, browser_manager: BrowserManager):
        self.browser = browser_manager
        self._last_mouse_x = 640.0  # Start at viewport center
        self._last_mouse_y = 450.0

    async def _human_click(self, page, element) -> None:
        """Move mouse to element with human-like trajectory, then click."""
        try:
            box = await element.bounding_box()
            if not box:
                await element.click()
                return
            
            # Target: random point within the element (not dead center)
            # Click within 30-70% of width/height to avoid edges
            from app.timing import _get_random
            rng = _get_random()
            target_x = box['x'] + box['width'] * (0.3 + rng.random() * 0.4)
            target_y = box['y'] + box['height'] * (0.3 + rng.random() * 0.4)
            
            # Use tracked mouse position from previous click
            start_x = self._last_mouse_x
            start_y = self._last_mouse_y
            
            path = HumanTiming.generate_mouse_path(start_x, start_y, target_x, target_y)
            
            for x, y in path:
                await page.mouse.move(x, y)
                move_delay = HumanTiming.get_mouse_move_delay()
                await page.wait_for_timeout(move_delay)
            
            await page.mouse.click(target_x, target_y)
            
            # Track mouse position for next click
            self._last_mouse_x = target_x
            self._last_mouse_y = target_y
        except Exception:
            # Fallback to simple click if mouse movement fails
            await element.click()

    async def grab_ticket(self, task: GrabTask, on_status=None) -> dict:
        """Execute the full ticket grabbing flow.

        Returns dict with "success" bool, "message" string, and "page" (kept open on success).
        """
        if not task.eventim_url:
            return {"success": False, "message": "No Eventim URL available"}

        async def _report(status: str, msg: str):
            if on_status:
                await on_status(status, msg)
            logger.info("Grab [%s] %s: %s", task.ext_id_screening, status, msg)

        page = None
        try:
            await _report("grabbing", "Opening Eventim page...")
            page = await self.browser.new_page()

            # Navigate to the event URL
            try:
                await page.goto(task.eventim_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                # Eventim sometimes blocks; retry with commit
                await _report("grabbing", "Retrying navigation...")
                await page.goto(task.eventim_url, wait_until="commit", timeout=30000)

            page_wait = HumanTiming.get_page_wait(1000)
            await page.wait_for_timeout(page_wait)
            await _report("grabbing", "Page loaded, handling consent & finding tickets...")

            # Step 0: Dismiss cookie consent banner if present
            await self._dismiss_cookie_banner(page)

            # Step 1: Try the Eventim purchase flow
            result = await self._eventim_purchase_flow(page, task.ticket_count, _report)
            if result["success"]:
                # Don't close the page - let user complete payment
                return result

            # Step 2: Retry
            for attempt in range(Config.GRAB_RETRY_COUNT):
                await _report("grabbing", f"Retry {attempt + 1}/{Config.GRAB_RETRY_COUNT}...")
                retry_delay = HumanTiming.get_page_wait(1000) / 1000  # Convert ms to seconds with jitter
                await asyncio.sleep(retry_delay)
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    await page.reload(wait_until="commit", timeout=15000)
                page_wait = HumanTiming.get_page_wait(1000)
                await page.wait_for_timeout(page_wait)
                await self._dismiss_cookie_banner(page)

                result = await self._eventim_purchase_flow(page, task.ticket_count, _report)
                if result["success"]:
                    return result

            await _report("failed", "Could not complete purchase after all retries")
            return {"success": False, "message": "Purchase flow failed after retries"}

        except Exception as e:
            logger.exception("Grab error for %s", task.ext_id_screening)
            await _report("failed", str(e))
            return {"success": False, "message": str(e)}

    async def _dismiss_cookie_banner(self, page) -> None:
        """Dismiss Eventim cookie/consent banner if present."""
        consent_selectors = [
            '#cmpbntyestxt',  # common Eventim consent button ID
            'button[id*="consent"]',
            'button[id*="accept"]',
            'button:has-text("Accept")',
            'button:has-text("Akzeptieren")',
            'button:has-text("Accept All")',
            'button:has-text("Alle akzeptieren")',
            'button:has-text("Agree")',
            'button:has-text("OK")',
            '[class*="consent"] button',
            '[class*="cookie"] button',
            '#onetrust-accept-btn-handler',
        ]
        for sel in consent_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await self._human_click(page, btn)
                    logger.info("Dismissed consent banner: %s", sel)
                    ui_delay = HumanTiming.get_ui_interaction_delay()
                    await page.wait_for_timeout(ui_delay)
                    return
            except Exception:
                continue

    async def _eventim_purchase_flow(self, page, ticket_count: int, report) -> dict:
        """Handle Eventim's actual purchase flow.

        The /noapp/event/{ID}/ URL leads to the Eventim event page.
        Flow: Event page -> Select tickets -> Add to cart -> Cart page
        """
        current_url = page.url
        await report("grabbing", f"On page: {current_url[:80]}...")

        # Take a screenshot for debugging
        try:
            await page.screenshot(path="data/eventim_debug.png")
        except Exception:
            pass

        # --- Phase 1: Find and click the main ticket/buy action ---
        # Eventim pages may show: a direct ticket selector, or a "Tickets" button to reveal it

        # Check if we're already on a ticket selection / seat map page
        if any(kw in current_url.lower() for kw in ["cart", "warenkorb", "basket", "checkout"]):
            await report("success", "Already on cart/checkout page!")
            return {"success": True, "message": "Reached cart/checkout page"}

        # Look for ticket quantity selectors (Eventim uses <select> or +/- buttons)
        qty_set = await self._set_ticket_quantity(page, ticket_count)
        if qty_set:
            await report("grabbing", f"Set quantity to {ticket_count}")

        # Look for the main action button to buy/reserve/add to cart
        buy_clicked = await self._click_buy_button(page)

        if buy_clicked:
            await report("grabbing", "Clicked buy button, waiting for next page...")
            # Smart wait: try to wait for URL change or cart-related elements
            try:
                await page.wait_for_function(
                    self.JS_WAIT_FOR_CART_ELEMENTS,
                    timeout=self.SMART_WAIT_TIMEOUT_MS
                )
            except Exception:
                # Fallback to minimal wait if no cart elements detected
                fallback_wait = HumanTiming.get_page_wait(self.SMART_WAIT_FALLBACK_MS)
                await page.wait_for_timeout(fallback_wait)

            # Check where we ended up
            new_url = page.url
            if any(kw in new_url.lower() for kw in ["cart", "warenkorb", "basket", "checkout", "order"]):
                await report("success", "Reached cart/checkout page!")
                return {"success": True, "message": "Ticket added to cart - complete payment in browser"}

            # We might be on a seat selection or intermediate page
            # Try to find and click through additional steps
            await report("grabbing", "Navigating through additional steps...")
            result = await self._handle_intermediate_steps(page, ticket_count, report)
            if result:
                return result

            # Even if we're not sure, if we clicked the button, report semi-success
            try:
                await page.screenshot(path="data/eventim_after_buy.png")
            except Exception:
                pass
            await report("success", "Buy button clicked - check browser to complete purchase")
            return {"success": True, "message": "Buy button clicked - check browser window to continue"}

        # --- Phase 2: Maybe we need to click a "Tickets" link first ---
        ticket_link_clicked = await self._click_ticket_link(page)
        if ticket_link_clicked:
            await report("grabbing", "Clicked ticket link, waiting...")
            # Smart wait with fallback - check for ticket purchase elements
            try:
                await page.wait_for_function(
                    self.JS_WAIT_FOR_TICKET_ELEMENTS,
                    timeout=self.SMART_WAIT_TIMEOUT_MS
                )
            except Exception:
                fallback_wait = HumanTiming.get_page_wait(self.SMART_WAIT_FALLBACK_MS)
                await page.wait_for_timeout(fallback_wait)
            await self._dismiss_cookie_banner(page)

            qty_set = await self._set_ticket_quantity(page, ticket_count)
            buy_clicked = await self._click_buy_button(page)
            if buy_clicked:
                # Smart wait with fallback
                try:
                    await page.wait_for_function(
                        self.JS_WAIT_FOR_CART,
                        timeout=self.SMART_WAIT_TIMEOUT_MS
                    )
                except Exception:
                    fallback_wait = HumanTiming.get_page_wait(self.SMART_WAIT_FALLBACK_MS)
                    await page.wait_for_timeout(fallback_wait)
                await report("success", "Buy button clicked - check browser to complete")
                return {"success": True, "message": "Ticket process started - check browser window"}

        await report("grabbing", "Could not find purchase elements on page")
        return {"success": False, "message": "No purchase elements found on page"}

    async def _set_ticket_quantity(self, page, count: int) -> bool:
        """Set ticket quantity using Eventim's stepper UI.

        Eventim Berlinale uses:
          <button class="js-stepper-more"> with <span class="icon icon-plus">
          <button class="js-stepper-less"> with <span class="icon icon-minus">
          <div class="js-stepper-amount-text">0</div>
        The first stepper row is for full-price tickets.
        """
        # Primary: Eventim's js-stepper-more button (the "+" button)
        plus_buttons = await page.query_selector_all('button.js-stepper-more')
        for btn in plus_buttons:
            try:
                if await btn.is_visible():
                    for _ in range(count):
                        await self._human_click(page, btn)
                        click_delay = HumanTiming.get_click_delay(TimingConfig.TIMING_MODE)
                        await page.wait_for_timeout(click_delay)
                    logger.info("Clicked js-stepper-more %d times", count)
                    return True
            except Exception:
                continue

        # Fallback: data-qa="more-tickets" button
        btn = await page.query_selector('[data-qa="more-tickets"]')
        if btn:
            try:
                if await btn.is_visible():
                    for _ in range(count):
                        await self._human_click(page, btn)
                        click_delay = HumanTiming.get_click_delay(TimingConfig.TIMING_MODE)
                        await page.wait_for_timeout(click_delay)
                    logger.info("Clicked more-tickets %d times", count)
                    return True
            except Exception:
                pass

        # Fallback: title="Increase amount" button
        btn = await page.query_selector('button[title*="Increase"], button[title*="ncrease"]')
        if btn:
            try:
                if await btn.is_visible():
                    for _ in range(count):
                        await self._human_click(page, btn)
                        click_delay = HumanTiming.get_click_delay(TimingConfig.TIMING_MODE)
                        await page.wait_for_timeout(click_delay)
                    logger.info("Clicked increase-amount %d times", count)
                    return True
            except Exception:
                pass

        return False

    async def _click_buy_button(self, page) -> bool:
        """Click the cart/checkout button on Eventim.

        Eventim Berlinale uses:
          <button class="btn js-stepper-action"> "N Tickets, € XX.XX" </button>
        This button submits the form to checkout.html.
        """
        # Priority 1: Eventim's js-stepper-action button (the cart button)
        btn = await page.query_selector('button.js-stepper-action')
        if btn:
            try:
                if await btn.is_visible():
                    text = (await btn.inner_text()).strip()
                    # Only click if tickets have been selected (not "0 Tickets")
                    if "0 Ticket" not in text:
                        await btn.scroll_into_view_if_needed()
                        await self._human_click(page, btn)
                        logger.info("Clicked js-stepper-action: '%s'", text)
                        return True
                    else:
                        logger.warning("Cart button shows 0 tickets: '%s'", text)
            except Exception:
                pass

        # Priority 2: Any button with "Ticket" in text and non-zero count
        try:
            ticket_btn = await page.query_selector('button:has-text("Ticket")')
            if ticket_btn and await ticket_btn.is_visible():
                text = (await ticket_btn.inner_text()).strip()
                if "0 Ticket" not in text and "Ticket" in text:
                    await ticket_btn.scroll_into_view_if_needed()
                    await self._human_click(page, ticket_btn)
                    logger.info("Clicked ticket button: '%s'", text)
                    return True
        except Exception:
            pass

        # Priority 3: Standard selectors
        selectors = [
            'button:has-text("In den Warenkorb")',
            'button:has-text("Add to cart")',
            'button:has-text("Add to basket")',
            'button:has-text("Buy tickets")',
            'button:has-text("Buy now")',
            'button:has-text("Kaufen")',
        ]
        for sel in selectors:
            try:
                b = await page.query_selector(sel)
                if b and await b.is_visible():
                    await b.scroll_into_view_if_needed()
                    await self._human_click(page, b)
                    logger.info("Clicked buy button: %s", sel)
                    return True
            except Exception:
                continue

        return False

    async def _click_ticket_link(self, page) -> bool:
        """Click a "Tickets" link that may reveal the purchase section."""
        selectors = [
            'a:has-text("Tickets")',
            'a:has-text("Karten")',
            'a:has-text("Book")',
            'button:has-text("Tickets")',
            'button:has-text("Karten")',
            '[class*="ticket-button"]',
            '[class*="ticketButton"]',
            'a[href*="ticket"]',
        ]
        for sel in selectors:
            try:
                el = await page.query_selector(sel)
                if el and await el.is_visible():
                    await self._human_click(page, el)
                    logger.info("Clicked ticket link: %s", sel)
                    return True
            except Exception:
                continue
        return False

    async def _handle_intermediate_steps(self, page, ticket_count: int, report) -> dict | None:
        """Handle seat selection or other intermediate steps after initial buy click."""
        # Wait for possible page transition
        page_wait = HumanTiming.get_page_wait(1000)
        await page.wait_for_timeout(page_wait)
        current_url = page.url

        # Check if we're now on a seat map / selection page
        # Try to find "continue" or "next" or "weiter" button
        continue_selectors = [
            'button:has-text("Continue")',
            'button:has-text("Weiter")',
            'button:has-text("Next")',
            'button:has-text("Proceed")',
            'button:has-text("Fortfahren")',
            'a:has-text("Continue")',
            'a:has-text("Weiter")',
            'button:has-text("Accept")',
            'button:has-text("Confirm")',
            'button:has-text("Bestätigen")',
        ]

        for sel in continue_selectors:
            try:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await self._human_click(page, btn)
                    logger.info("Clicked continue: %s", sel)
                    # Smart wait with fallback
                    try:
                        await page.wait_for_function(
                            self.JS_WAIT_FOR_CART_EXTENDED,
                            timeout=self.SMART_WAIT_TIMEOUT_MS
                        )
                    except Exception:
                        fallback_wait = HumanTiming.get_page_wait(self.SMART_WAIT_FALLBACK_MS)
                        await page.wait_for_timeout(fallback_wait)

                    new_url = page.url
                    if any(kw in new_url.lower() for kw in ["cart", "warenkorb", "basket", "checkout", "order"]):
                        await report("success", "Reached checkout!")
                        return {"success": True, "message": "Reached checkout - complete payment in browser"}
            except Exception:
                continue

        # Try another round of buy button clicks (new page might have different structure)
        buy_clicked = await self._click_buy_button(page)
        if buy_clicked:
            # Smart wait with fallback
            try:
                await page.wait_for_function(
                    self.JS_WAIT_FOR_CART,
                    timeout=self.SMART_WAIT_TIMEOUT_MS
                )
            except Exception:
                fallback_wait = HumanTiming.get_page_wait(self.SMART_WAIT_FALLBACK_MS)
                await page.wait_for_timeout(fallback_wait)
            new_url = page.url
            if any(kw in new_url.lower() for kw in ["cart", "warenkorb", "basket", "checkout"]):
                return {"success": True, "message": "Ticket added to cart"}

        return None

    async def preheat(self, task: GrabTask) -> "Page | None":
        """Open the Eventim page ahead of time to warm up."""
        if not task.eventim_url:
            return None
        try:
            page = await self.browser.new_page()
            try:
                await page.goto(task.eventim_url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                await page.goto(task.eventim_url, wait_until="commit", timeout=30000)
            await self._dismiss_cookie_banner(page)
            logger.info("Preheated page for %s", task.ext_id_screening)
            return page
        except Exception:
            logger.exception("Preheat failed for %s", task.ext_id_screening)
            return None

    async def grab_with_refresh(self, page, task: GrabTask, on_status=None) -> dict:
        """Grab ticket by refreshing a preheated page at sale time."""
        async def _report(status: str, msg: str):
            if on_status:
                await on_status(status, msg)

        try:
            await _report("grabbing", "Refreshing page at sale time...")
            try:
                await page.reload(wait_until="domcontentloaded", timeout=15000)
            except Exception:
                await page.reload(wait_until="commit", timeout=15000)
            page_wait = HumanTiming.get_page_wait(1000)
            await page.wait_for_timeout(page_wait)
            await self._dismiss_cookie_banner(page)

            result = await self._eventim_purchase_flow(page, task.ticket_count, _report)
            if result["success"]:
                return result

            for attempt in range(Config.GRAB_RETRY_COUNT):
                await _report("grabbing", f"Retry {attempt + 1}...")
                retry_delay = HumanTiming.get_page_wait(1000) / 1000  # Convert ms to seconds with jitter
                await asyncio.sleep(retry_delay)
                try:
                    await page.reload(wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    await page.reload(wait_until="commit", timeout=15000)
                page_wait = HumanTiming.get_page_wait(1000)
                await page.wait_for_timeout(page_wait)

                result = await self._eventim_purchase_flow(page, task.ticket_count, _report)
                if result["success"]:
                    return result

            await _report("failed", "All retries exhausted")
            return {"success": False, "message": "Failed after all retries"}
        except Exception as e:
            logger.exception("grab_with_refresh error")
            await _report("failed", str(e))
            return {"success": False, "message": str(e)}


# Global singletons
browser_manager = BrowserManager()
ticket_grabber = TicketGrabber(browser_manager)
