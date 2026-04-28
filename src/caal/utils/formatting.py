"""Formatting utilities for TTS and speech-friendly output."""

import re
from datetime import datetime


def strip_markdown_for_tts(text: str) -> str:
    """Strip markdown formatting that TTS would read aloud.

    Removes asterisks, underscores, and other markdown syntax while preserving
    the actual content for clean TTS output.
    """
    if not text:
        return text

    # Remove bold/italic markers: **text**, *text*, __text__, _text_
    # Handle bold first (** or __), then italic (* or _)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # **bold**
    text = re.sub(r'__(.+?)__', r'\1', text)       # __bold__
    text = re.sub(r'\*(.+?)\*', r'\1', text)       # *italic*
    text = re.sub(r'_(.+?)_', r'\1', text)         # _italic_

    # Remove inline code backticks
    text = re.sub(r'`(.+?)`', r'\1', text)

    # Remove markdown links [text](url) -> text
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)

    # Remove bracketed tool-invocation narration that some models emit
    # (e.g., "[Calling list_tools with search='calendar']").
    text = re.sub(r'\[\s*Calling[^\]]*\]', '', text, flags=re.IGNORECASE)

    # Remove any remaining standalone asterisks or underscores used as emphasis
    # (in case of unclosed markdown)
    text = re.sub(r'(?<!\w)\*(?!\w)', '', text)  # standalone *
    text = re.sub(r'(?<!\w)_(?!\w)', '', text)   # standalone _

    # Convert score patterns (30-23) to "30 to 23" so TTS doesn't say "minus"
    text = re.sub(r'(\d+)-(\d+)', r'\1 to \2', text)

    return text


def number_to_ordinal_word(n: int) -> str:
    """Convert a number to its ordinal word form (e.g., 1 -> 'first', 7 -> 'seventh')."""
    # Special cases for 1-31 (days of the month)
    ordinals = {
        1: 'first', 2: 'second', 3: 'third', 4: 'fourth', 5: 'fifth',
        6: 'sixth', 7: 'seventh', 8: 'eighth', 9: 'ninth', 10: 'tenth',
        11: 'eleventh', 12: 'twelfth', 13: 'thirteenth', 14: 'fourteenth',
        15: 'fifteenth', 16: 'sixteenth', 17: 'seventeenth', 18: 'eighteenth',
        19: 'nineteenth', 20: 'twentieth', 21: 'twenty-first', 22: 'twenty-second',
        23: 'twenty-third', 24: 'twenty-fourth', 25: 'twenty-fifth',
        26: 'twenty-sixth', 27: 'twenty-seventh', 28: 'twenty-eighth',
        29: 'twenty-ninth', 30: 'thirtieth', 31: 'thirty-first'
    }

    if n in ordinals:
        return ordinals[n]

    # For numbers beyond 31, construct the ordinal (shouldn't happen for dates, but handle it)
    # Since dates are 1-31, this is just a safety fallback
    if n < 100:
        tens = n // 10
        ones = n % 10
        tens_words = [
            '', '', 'twenty', 'thirty', 'forty', 'fifty',
            'sixty', 'seventy', 'eighty', 'ninety',
        ]
        if ones == 0:
            return f"{tens_words[tens]}th"
        else:
            # Get the ordinal for the ones place (should always be in dict for 1-9)
            ones_ordinal = ordinals.get(ones, f"{ones}th")
            return f"{tens_words[tens]}-{ones_ordinal}"

    # For larger numbers, use numeric form (unlikely for dates, but handle gracefully)
    return f"{n}th"


def format_date_speech_friendly(dt: datetime, language: str = "en") -> str:
    """Format a datetime in a speech-friendly way with ordinal words.

    Args:
        dt: Datetime to format
        language: ISO 639-1 language code ("en" or "fr")

    Examples:
        English: "Wednesday, January twenty-first, 2026"
        French: "mercredi 21 janvier 2026"
    """
    if language == "fr":
        return _format_date_french(dt)
    if language == "it":
        return _format_date_italian(dt)
    if language == "pt":
        return _format_date_portuguese(dt)
    if language == "da":
        return _format_date_danish(dt)
    if language == "ro":
        return _format_date_romanian(dt)

    # English (default)
    day_name = dt.strftime('%A')
    month_name = dt.strftime('%B')
    day_number = dt.day
    year = dt.year

    day_ordinal = number_to_ordinal_word(day_number)

    return f"{day_name}, {month_name} {day_ordinal}, {year}"


def _format_date_french(dt: datetime) -> str:
    """Format a date in French speech-friendly style.

    French dates use cardinal numbers except "premier" for the 1st.
    Format: "lundi 21 janvier 2026" or "lundi premier janvier 2026"
    """
    fr_days = [
        "lundi", "mardi", "mercredi", "jeudi",
        "vendredi", "samedi", "dimanche",
    ]
    fr_months = [
        "janvier", "f\u00e9vrier", "mars", "avril", "mai", "juin",
        "juillet", "ao\u00fbt", "septembre", "octobre", "novembre", "d\u00e9cembre",
    ]

    day_name = fr_days[dt.weekday()]
    month_name = fr_months[dt.month - 1]
    day_number = "premier" if dt.day == 1 else str(dt.day)

    return f"{day_name} {day_number} {month_name} {dt.year}"


_HOUR_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
    11: "eleven", 12: "twelve",
}
_TENS_WORDS = {
    1: "ten", 2: "twenty", 3: "thirty", 4: "forty", 5: "fifty",
}
_ONES_WORDS = {
    1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
    6: "six", 7: "seven", 8: "eight", 9: "nine",
}


def _minute_to_words(minute: int) -> str:
    """Convert minutes 1-59 to spoken English words."""
    if minute < 10:
        return f"oh {_ONES_WORDS[minute]}"
    tens, ones = divmod(minute, 10)
    if ones == 0:
        return _TENS_WORDS[tens]
    return f"{_TENS_WORDS[tens]}-{_ONES_WORDS[ones]}"


def format_time_speech_friendly(dt: datetime, language: str = "en") -> str:
    """Format a time in a speech-friendly way for TTS.

    Returns fully spelled-out words so TTS reads correctly.

    Args:
        dt: Datetime to format
        language: ISO 639-1 language code

    Examples:
        English: 9:08 AM -> "nine oh eight AM"
                 3:30 PM -> "three thirty PM"
                 3:00 PM -> "three PM"
        French: 15:00 -> "15 heures", 15:30 -> "15 heures 30"
    """
    if language == "fr":
        return _format_time_french(dt)
    if language == "it":
        return _format_time_italian(dt)
    if language == "pt":
        return _format_time_portuguese(dt)
    if language == "da":
        return _format_time_danish(dt)
    if language == "ro":
        return _format_time_romanian(dt)

    # English (default)
    hour = dt.hour
    minute = dt.minute

    if hour == 12 and minute == 0:
        return "noon"
    if hour == 0 and minute == 0:
        return "midnight"

    hour_12 = hour % 12 or 12
    period = "AM" if hour < 12 else "PM"
    hour_word = _HOUR_WORDS[hour_12]

    if minute == 0:
        return f"{hour_word} {period}"
    return f"{hour_word} {_minute_to_words(minute)} {period}"


def _format_time_french(dt: datetime) -> str:
    """Format a time in French speech-friendly style.

    Uses 24-hour clock with special cases for midi/minuit.
    Examples: "15 heures 30", "15 heures", "midi", "minuit"
    """
    hour = dt.hour
    minute = dt.minute

    # Special cases
    if hour == 0 and minute == 0:
        return "minuit"
    if hour == 12 and minute == 0:
        return "midi"

    # 24-hour format
    if minute == 0:
        return f"{hour} heures"
    else:
        return f"{hour} heures {minute}"


def _format_date_italian(dt: datetime) -> str:
    """Format a date in Italian speech-friendly style.

    Italian dates use cardinal numbers except "primo" for the 1st.
    Format: "lunedì 2 febbraio 2026" or "lunedì primo gennaio 2026"
    """
    it_days = [
        "lunedì", "martedì", "mercoledì", "giovedì",
        "venerdì", "sabato", "domenica",
    ]
    it_months = [
        "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
    ]

    day_name = it_days[dt.weekday()]
    month_name = it_months[dt.month - 1]
    day_number = "primo" if dt.day == 1 else str(dt.day)

    return f"{day_name} {day_number} {month_name} {dt.year}"


def _format_time_italian(dt: datetime) -> str:
    """Format a time in Italian speech-friendly style.

    Uses 24-hour clock with "e" for minutes.
    Examples: "15 e 30", "15", "mezzogiorno", "mezzanotte"
    """
    hour = dt.hour
    minute = dt.minute

    # Special cases
    if hour == 0 and minute == 0:
        return "mezzanotte"
    if hour == 12 and minute == 0:
        return "mezzogiorno"

    # 24-hour format
    if minute == 0:
        return f"{hour}"
    else:
        return f"{hour} e {minute}"


def _format_date_portuguese(dt: datetime) -> str:
    """Format a date in Brazilian Portuguese speech-friendly style.

    Portuguese dates use cardinal numbers except "primeiro" for the 1st.
    Format: "segunda-feira, 2 de fevereiro de 2026" or "quarta-feira, primeiro de janeiro de 2026"
    """
    pt_days = [
        "segunda-feira", "terca-feira", "quarta-feira", "quinta-feira",
        "sexta-feira", "sabado", "domingo",
    ]
    pt_months = [
        "janeiro", "fevereiro", "marco", "abril", "maio", "junho",
        "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
    ]

    day_name = pt_days[dt.weekday()]
    month_name = pt_months[dt.month - 1]
    day_number = "primeiro" if dt.day == 1 else str(dt.day)

    return f"{day_name}, {day_number} de {month_name} de {dt.year}"


def _format_time_portuguese(dt: datetime) -> str:
    """Format a time in Brazilian Portuguese speech-friendly style.

    Uses 24-hour clock with "e" for minutes.
    Examples: "15 e 30", "15 horas", "meio-dia", "meia-noite"
    """
    hour = dt.hour
    minute = dt.minute

    # Special cases
    if hour == 0 and minute == 0:
        return "meia-noite"
    if hour == 12 and minute == 0:
        return "meio-dia"

    # 24-hour format
    if minute == 0:
        return f"{hour} horas"
    else:
        return f"{hour} e {minute}"


def _format_date_danish(dt: datetime) -> str:
    """Format a date in Danish speech-friendly style.

    Danish dates use cardinal numbers with "den" prefix.
    Format: "onsdag den 21. januar 2026"
    """
    da_days = [
        "mandag", "tirsdag", "onsdag", "torsdag",
        "fredag", "lørdag", "søndag",
    ]
    da_months = [
        "januar", "februar", "marts", "april", "maj", "juni",
        "juli", "august", "september", "oktober", "november", "december",
    ]

    day_name = da_days[dt.weekday()]
    month_name = da_months[dt.month - 1]

    return f"{day_name} den {dt.day}. {month_name} {dt.year}"


def _format_time_danish(dt: datetime) -> str:
    """Format a time in Danish speech-friendly style.

    Uses 24-hour clock.
    Examples: "klokken 15 og 30", "klokken 15", "midnat", "middag"
    """
    hour = dt.hour
    minute = dt.minute

    if hour == 0 and minute == 0:
        return "midnat"
    if hour == 12 and minute == 0:
        return "middag"

    if minute == 0:
        return f"klokken {hour}"
    else:
        return f"klokken {hour} og {minute}"


def _format_date_romanian(dt: datetime) -> str:
    """Format a date in Romanian speech-friendly style.

    Romanian dates use cardinal numbers with "întâi" for the 1st.
    Format: "miercuri, 21 ianuarie 2026"
    """
    ro_days = [
        "luni", "marți", "miercuri", "joi",
        "vineri", "sâmbătă", "duminică",
    ]
    ro_months = [
        "ianuarie", "februarie", "martie", "aprilie", "mai", "iunie",
        "iulie", "august", "septembrie", "octombrie", "noiembrie", "decembrie",
    ]

    day_name = ro_days[dt.weekday()]
    month_name = ro_months[dt.month - 1]
    day_number = "întâi" if dt.day == 1 else str(dt.day)

    return f"{day_name}, {day_number} {month_name} {dt.year}"


def _format_time_romanian(dt: datetime) -> str:
    """Format a time in Romanian speech-friendly style.

    Uses 24-hour clock with "și" for minutes.
    Examples: "15 și 30", "15", "miezul nopții", "amiază"
    """
    hour = dt.hour
    minute = dt.minute

    if hour == 0 and minute == 0:
        return "miezul nopții"
    if hour == 12 and minute == 0:
        return "amiază"

    if minute == 0:
        return f"ora {hour}"
    else:
        return f"{hour} și {minute}"
