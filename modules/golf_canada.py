"""
golf_canada.py — Golf Canada Score Centre Automation
Golf Match Captain | Phase 2A

Uses Playwright to retrieve a player's score history from the
Golf Canada Score Centre by CPGA ID.

Architecture:
  - GolfCanadaScraper: the Playwright-based scraper class
  - parse_score_rows(): pure-Python parser (testable without a browser)
  - sync_player_scores(): orchestrates scrape + roster update
  - MockScraper: drop-in replacement for unit testing

Golf Canada Score Centre URL:
  https://www.golfcanada.ca/handicap/

The scraper navigates to the player's handicap profile, extracts
the 20 most recent score differentials, and returns them in a
format compatible with roster.add_score_record().
"""

from __future__ import annotations
import re
from datetime import date, datetime
from dataclasses import dataclass, field
from typing import Iterator

# Playwright is an optional Phase 2 dependency
try:
    from playwright.sync_api import sync_playwright, Page, Browser, TimeoutError as PWTimeout
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

from modules.roster import (
    add_score_record,
    get_score_records,
    delete_score_record,
    update_player,
    get_player,
)

# ---------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------

GOLF_CANADA_BASE_URL = "https://www.golfcanada.ca/handicap/"
SCORE_CENTRE_SEARCH  = "https://www.golfcanada.ca/handicap/score-centre/"

# CSS selectors — may need updating if Golf Canada redesigns their site
SELECTORS = {
    # Search input for CPGA ID / name
    "search_input":     "input[placeholder*='Search'], input[name*='search'], input[type='search']",
    # Score history table rows
    "score_table_rows": "table tbody tr, .score-history tr, [class*='score-row']",
    # Individual cell selectors within a row
    "cell_date":        "td:nth-child(1), [class*='date']",
    "cell_course":      "td:nth-child(2), [class*='course']",
    "cell_score":       "td:nth-child(3), [class*='score']",
    "cell_differential":"td:nth-child(4), [class*='differential'], [class*='diff']",
    # Player name confirmation
    "player_name":      "h1, h2, [class*='player-name'], [class*='handicap-name']",
    # Handicap index display
    "handicap_index":   "[class*='handicap-index'], [class*='current-index']",
}

MAX_SCORES_TO_FETCH = 20
DEFAULT_TIMEOUT_MS  = 15_000  # 15 seconds per page action


# ---------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------

@dataclass
class ScoreRow:
    """A single parsed score record from the Golf Canada site."""
    date:         str          # ISO format: YYYY-MM-DD
    course:       str
    posted_score: int | None
    differential: float
    tee_deck:     str = ""

    def is_valid(self) -> bool:
        """Basic sanity check before storing."""
        return (
            bool(self.course)
            and -10.0 <= self.differential <= 60.0
            and bool(self.date)
        )


@dataclass
class ScrapeResult:
    """Result of a scrape attempt for one player."""
    cpga_id:       str
    success:       bool
    player_name:   str          = ""
    current_index: float | None = None
    scores:        list[ScoreRow] = field(default_factory=list)
    error:         str          = ""
    rows_found:    int          = 0
    rows_imported: int          = 0


# ---------------------------------------------------------------
# Playwright scraper
# ---------------------------------------------------------------

class GolfCanadaScraper:
    """
    Playwright-based scraper for the Golf Canada Score Centre.

    Usage:
        with GolfCanadaScraper(headless=True) as scraper:
            result = scraper.fetch_scores("CA-123456")
    """

    def __init__(self, headless: bool = True, timeout_ms: int = DEFAULT_TIMEOUT_MS):
        if not PLAYWRIGHT_AVAILABLE:
            raise ImportError(
                "Playwright is not installed. Run: "
                "pip install playwright && playwright install chromium"
            )
        self.headless   = headless
        self.timeout_ms = timeout_ms
        self._playwright = None
        self._browser: Browser | None = None

    def __enter__(self):
        self._playwright = sync_playwright().start()
        self._browser    = self._playwright.chromium.launch(headless=self.headless)
        return self

    def __exit__(self, *args):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    def fetch_scores(self, cpga_id: str) -> ScrapeResult:
        """
        Navigate to the Golf Canada Score Centre, find the player
        by CPGA ID, and extract their score history.

        Returns a ScrapeResult whether or not scores were found.
        """
        result = ScrapeResult(cpga_id=cpga_id, success=False)

        try:
            page = self._browser.new_page()
            page.set_default_timeout(self.timeout_ms)

            # Step 1 — navigate to Score Centre
            page.goto(GOLF_CANADA_SEARCH_URL, wait_until="domcontentloaded")

            # Step 2 — search for CPGA ID
            search_box = page.locator(SELECTORS["search_input"]).first
            search_box.fill(cpga_id)
            search_box.press("Enter")
            page.wait_for_load_state("networkidle", timeout=self.timeout_ms)

            # Step 3 — check if we landed on a player profile
            name_el = page.locator(SELECTORS["player_name"]).first
            if name_el.is_visible():
                result.player_name = name_el.inner_text().strip()

            # Step 4 — extract current index if displayed
            idx_el = page.locator(SELECTORS["handicap_index"]).first
            if idx_el.is_visible():
                idx_text = idx_el.inner_text().strip()
                result.current_index = _parse_float(idx_text)

            # Step 5 — extract score rows
            html = page.content()
            result.scores    = parse_score_rows_from_html(html)
            result.rows_found = len(result.scores)

            result.success = True
            page.close()

        except PWTimeout:
            result.error = (
                "Page timed out. Golf Canada Score Centre may be slow or "
                "the CPGA ID was not found."
            )
        except Exception as exc:
            result.error = f"Scrape failed: {exc}"

        return result


# Golf Canada search URL constant (used in scraper)
GOLF_CANADA_SEARCH_URL = SCORE_CENTRE_SEARCH


# ---------------------------------------------------------------
# HTML parser (pure Python — no browser required for testing)
# ---------------------------------------------------------------

def parse_score_rows_from_html(html: str) -> list[ScoreRow]:
    """
    Parse score rows from Golf Canada page HTML.
    Uses regex patterns that match the Score Centre table structure.

    This function is kept pure (no Playwright dependency) so it
    can be unit tested with static HTML fixtures.
    """
    scores: list[ScoreRow] = []

    # Pattern 1: standard HTML table rows
    # Matches: <tr> ... <td>date</td><td>course</td><td>score</td><td>diff</td> ...
    table_row_pattern = re.compile(
        r"<tr[^>]*>(.*?)</tr>", re.DOTALL | re.IGNORECASE
    )
    td_pattern = re.compile(r"<td[^>]*>(.*?)</td>", re.DOTALL | re.IGNORECASE)
    tag_strip  = re.compile(r"<[^>]+>")

    for row_match in table_row_pattern.finditer(html):
        row_html = row_match.group(1)
        cells    = td_pattern.findall(row_html)
        if len(cells) < 3:
            continue

        # Strip HTML tags from cell contents
        cell_texts = [tag_strip.sub("", c).strip() for c in cells]
        row = _try_parse_row(cell_texts)
        if row and row.is_valid():
            scores.append(row)
            if len(scores) >= MAX_SCORES_TO_FETCH:
                break

    # Pattern 2: JSON-like embedded data (some Golf Canada pages use this)
    if not scores:
        scores = _parse_json_scores(html)

    return scores[:MAX_SCORES_TO_FETCH]


def _try_parse_row(cells: list[str]) -> ScoreRow | None:
    """
    Attempt to parse a list of cell strings into a ScoreRow.
    Tries multiple column orderings to handle layout variations.
    Returns None if the row doesn't look like a score record.
    """
    if len(cells) < 3:
        return None

    # Try to identify which columns hold which data
    date_val   = None
    course_val = ""
    score_val  = None
    diff_val   = None

    for cell in cells:
        # Date patterns: YYYY-MM-DD, MM/DD/YYYY, Mon DD, YYYY
        if not date_val:
            d = _parse_date_str(cell)
            if d:
                date_val = d
                continue

        # Differential: a number between -10 and 60, often with one decimal
        if diff_val is None:
            f = _parse_float(cell)
            if f is not None and -10 <= f <= 60:
                diff_val = f
                continue

        # Posted score: an integer between 55 and 130
        if score_val is None:
            try:
                i = int(cell.replace("+", "").strip())
                if 55 <= i <= 130:
                    score_val = i
                    continue
            except ValueError:
                pass

        # Course: a non-empty string that isn't a number or date
        if not course_val and len(cell) > 3 and not _parse_float(cell):
            course_val = cell

    if date_val and diff_val is not None:
        return ScoreRow(
            date=date_val,
            course=course_val or "Unknown",
            posted_score=score_val,
            differential=diff_val,
        )
    return None


def _parse_json_scores(html: str) -> list[ScoreRow]:
    """
    Fallback: attempt to extract scores from embedded JSON data.
    Some Golf Canada pages render data as a JSON blob in a script tag.
    """
    import json

    scores = []
    # Look for JSON arrays with score-like data
    json_pattern = re.compile(
        r'"scores?"\s*:\s*(\[.*?\])', re.DOTALL | re.IGNORECASE
    )
    for match in json_pattern.finditer(html):
        try:
            raw = json.loads(match.group(1))
            for item in raw:
                if not isinstance(item, dict):
                    continue
                diff = (
                    item.get("differential") or
                    item.get("diff") or
                    item.get("scoreDifferential")
                )
                date_str = (
                    item.get("date") or
                    item.get("playedDate") or
                    item.get("postedDate")
                )
                course = (
                    item.get("course") or
                    item.get("courseName") or
                    item.get("facility") or ""
                )
                score = item.get("score") or item.get("grossScore")

                if diff is not None and date_str:
                    d = _parse_date_str(str(date_str))
                    f = _parse_float(str(diff))
                    if d and f is not None:
                        scores.append(ScoreRow(
                            date=d,
                            course=str(course),
                            posted_score=int(score) if score else None,
                            differential=f,
                        ))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    return scores[:MAX_SCORES_TO_FETCH]


# ---------------------------------------------------------------
# Date and number parsers
# ---------------------------------------------------------------

def _parse_date_str(s: str) -> str | None:
    """
    Try to parse a date string into ISO format (YYYY-MM-DD).
    Handles: YYYY-MM-DD, MM/DD/YYYY, DD/MM/YYYY, Month DD YYYY,
             DD-Mon-YYYY, YYYY/MM/DD.
    Returns None if no date pattern is found.
    """
    s = s.strip()
    if not s or len(s) < 6:
        return None

    MONTH_ABBR = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4,
        "may": 5, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    formats = [
        "%Y-%m-%d",    # 2025-07-15
        "%m/%d/%Y",    # 07/15/2025
        "%d/%m/%Y",    # 15/07/2025
        "%B %d, %Y",   # July 15, 2025
        "%b %d, %Y",   # Jul 15, 2025
        "%d-%b-%Y",    # 15-Jul-2025
        "%Y/%m/%d",    # 2025/07/15
        "%d %b %Y",    # 15 Jul 2025
        "%d %B %Y",    # 15 July 2025
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None


def _parse_float(s) -> float | None:
    """Parse a string to float, stripping common non-numeric characters."""
    if s is None:
        return None
    try:
        cleaned = re.sub(r"[^\d.\-\+]", "", str(s).strip())
        if cleaned:
            return float(cleaned)
    except (ValueError, TypeError):
        pass
    return None


# ---------------------------------------------------------------
# Roster sync — orchestrates scrape + database update
# ---------------------------------------------------------------

def sync_player_scores(
    player_id: int,
    cpga_id: str,
    headless: bool = True,
    update_index: bool = True,
) -> ScrapeResult:
    """
    Scrape Golf Canada for a player's scores and update the roster.

    Steps:
      1. Run the Playwright scraper
      2. Wipe existing score records for the player
      3. Insert the freshly scraped records (up to 20)
      4. Optionally update the player's current index from the scraped value

    Returns the ScrapeResult for display in the UI.
    """
    with GolfCanadaScraper(headless=headless) as scraper:
        result = scraper.fetch_scores(cpga_id)

    if not result.success or not result.scores:
        return result

    # Clear existing records
    existing = get_score_records(player_id)
    for rec in existing:
        delete_score_record(rec["record_id"])

    # Insert new records (already sorted newest-first by the scraper)
    imported = 0
    for row in result.scores:
        try:
            add_score_record(
                player_id=player_id,
                date=row.date,
                course=row.course,
                differential=row.differential,
                posted_score=row.posted_score,
                tee_deck=row.tee_deck,
            )
            imported += 1
        except Exception:
            pass  # Skip malformed records

    result.rows_imported = imported

    # Update handicap index if Golf Canada returned one
    if update_index and result.current_index is not None:
        player = get_player(player_id)
        if player:
            update_player(
                player_id=player_id,
                name=player["name"],
                current_index=result.current_index,
                cpga_id=player["cpga_id"] or cpga_id,
                tee_preference=player["tee_preference"] or "",
                notes=player["notes"] or "",
            )

    return result


# ---------------------------------------------------------------
# Mock scraper — for unit tests and UI demos
# ---------------------------------------------------------------

class MockScraper:
    """
    Drop-in replacement for GolfCanadaScraper that returns
    realistic synthetic data without hitting a real website.

    Used in tests and optionally in the UI for demonstration.
    """

    SAMPLE_COURSES = [
        "Heron Point GC", "Cobble Beach GC", "Loch March GC",
        "Camelot GC", "Eagle Creek GC", "Rockway GC",
    ]

    def __init__(self, base_index: float = 14.0, n_scores: int = 15):
        self.base_index = base_index
        self.n_scores   = n_scores

    def fetch_scores(self, cpga_id: str) -> ScrapeResult:
        import random
        import math
        random.seed(hash(cpga_id) % 10000)

        scores = []
        for i in range(self.n_scores):
            # Simulate a realistic spread around the base index
            diff = round(self.base_index + random.gauss(0, 2.5), 1)
            diff = max(-5.0, min(40.0, diff))

            month  = ((i // 2) % 9) + 1
            day    = (i * 7 % 27) + 1
            scores.append(ScoreRow(
                date=f"2025-{month:02d}-{day:02d}",
                course=random.choice(self.SAMPLE_COURSES),
                posted_score=int(72 + diff + random.uniform(-2, 2)),
                differential=diff,
                tee_deck="White",
            ))

        best8 = sorted(s.differential for s in scores)[:8]
        derived_index = round(sum(best8) / len(best8), 1) if best8 else self.base_index

        return ScrapeResult(
            cpga_id=cpga_id,
            success=True,
            player_name=f"Player {cpga_id}",
            current_index=derived_index,
            scores=scores,
            rows_found=len(scores),
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def sync_player_scores_mock(
    player_id: int,
    cpga_id: str,
    base_index: float = 14.0,
) -> ScrapeResult:
    """
    Sync using MockScraper — used when Playwright is not installed
    or for demonstration purposes.
    """
    with MockScraper(base_index=base_index) as scraper:
        result = scraper.fetch_scores(cpga_id)

    if not result.scores:
        return result

    existing = get_score_records(player_id)
    for rec in existing:
        delete_score_record(rec["record_id"])

    imported = 0
    for row in result.scores:
        try:
            add_score_record(
                player_id=player_id,
                date=row.date,
                course=row.course,
                differential=row.differential,
                posted_score=row.posted_score,
                tee_deck=row.tee_deck,
            )
            imported += 1
        except Exception:
            pass

    result.rows_imported = imported
    return result
