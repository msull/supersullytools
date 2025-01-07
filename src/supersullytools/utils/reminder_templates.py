"""
reminder_template.py
--------------------

This module defines a simple "micro" templating system to handle date-based
placeholders in reminder strings. The core function, `parse_template`, processes
templates containing placeholders such as:

- `{current_year}` to insert the current year.
- `{offset_year(N)}` to insert a year offset by N from the current year.
- `{age(YYYY-MM-DD)}` (or partial YYYY-MM, or YYYY) to compute how old
  an entity is in the current year.
- `{years_since(YYYY-MM-DD)}` to compute how many full years have elapsed
  since a given start date.

By default, `parse_template` uses today's date for calculations, but you can
provide a `reference_date` for testing or to fix the rendered results to a
specific point in time.

Usage:
    from reminder_template import parse_template
    from datetime import date

    # Example reminder
    template_str = "John turns {age(2006-10-01)} in October {offset_year(0)}"
    rendered_str = parse_template(template_str, reference_date=date(2025, 1, 1))
    print(rendered_str)  # "John turns 18 in October 2025" (for 2025-01-01)

See the `test_reminder_templates.py` file in the repository for example pytest
tests that validate correct placeholder parsing and date calculations.
"""

import re
from datetime import date


def parse_template(template: str, reference_date=None) -> str:
    """
    Parses a reminder template string and replaces supported date placeholders:
      - {current_year}
      - {offset_year(N)}
      - {age(...)}
      - {years_since(...)}
      - {days_until(...)}   <-- NEW
    """
    if reference_date is None:
        today = date.today()
    else:
        # Ensure we have a date object (if passed a datetime)
        today = reference_date if isinstance(reference_date, date) else reference_date.date()

    current_year = today.year
    pattern = r"\{([^{}]+)\}"  # captures content inside {...}

    def compute_replacement(match):
        expr = match.group(1).strip()

        # 1) current_year
        if expr == "current_year":
            return str(current_year)

        # 2) offset_year(N)
        if expr.startswith("offset_year(") and expr.endswith(")"):
            inner = expr[len("offset_year(") : -1].strip()
            try:
                offset = int(inner)
            except ValueError:
                return f"[Error: invalid offset '{inner}']"
            return str(current_year + offset)

        # 3) age(...)
        if expr.startswith("age(") and expr.endswith(")"):
            date_str = expr[len("age(") : -1].strip()
            return str(compute_age(today, date_str))

        # 4) years_since(...)
        if expr.startswith("years_since(") and expr.endswith(")"):
            date_str = expr[len("years_since(") : -1].strip()
            return str(compute_years_since(today, date_str))

        # 5) days_until(...)  <-- NEW
        if expr.startswith("days_until(") and expr.endswith(")"):
            date_str = expr[len("days_until(") : -1].strip()
            return str(compute_days_until(today, date_str))

        # Unrecognized
        return f"[Unrecognized placeholder: {expr}]"

    # Helper functions (existing ones omitted for brevity, only the new one shown below).
    # e.g. compute_age, compute_years_since, parse_date_str, etc.

    def compute_days_until(reference_day: date, future_str: str) -> int:
        """
        Returns how many days from 'reference_day' until the date specified by 'future_str'.

        If the date is in the past, the result will be negative or zero.
        The 'future_str' can be YYYY, YYYY-MM, or YYYY-MM-DD, and defaults missing
        month/day to 1 (January 1, or first day of the month, etc.).
        """
        y, m, d = parse_date_str(future_str)
        future_date = date(y, m, d)
        return (future_date - reference_day).days

    def parse_date_str(date_str: str):
        """
        Parses a string of the form YYYY, YYYY-MM, or YYYY-MM-DD
        and returns (year, month, day) with defaults for missing parts.
        """
        parts = date_str.split("-")
        year = int(parts[0])
        month = 1
        day = 1

        if len(parts) >= 2:
            month = int(parts[1])
        if len(parts) == 3:
            day = int(parts[2])

        return year, month, day

    def compute_age(reference_day, birth_str: str) -> int:
        """
        Returns how old a person will be during the reference year's calendar.
        This does NOT check if the birthday has already happened or not; it
        simply uses (reference_year - birth_year).
        """
        birth_year, birth_month, birth_day = parse_date_str(birth_str)
        this_year = reference_day.year
        # No subtraction for not-yet-reached birthday
        return this_year - birth_year

    def compute_years_since(reference_day, start_str: str) -> int:
        """
        Returns how many full years have passed from 'start_str' up to the
        reference_day. Subtracts 1 if the reference_day is before the month/day
        in the reference year.
        """
        start_year, start_month, start_day = parse_date_str(start_str)
        this_year = reference_day.year
        years = this_year - start_year

        # If we haven't reached the month/day of 'start_str' in this_year, subtract 1
        anniversary_date_this_year = date(this_year, start_month, start_day)
        if reference_day < anniversary_date_this_year:
            years -= 1

        return years

    # Finally, run the re.sub with the compute_replacement function
    rendered = re.sub(pattern, compute_replacement, template)
    return rendered


# EXAMPLE USAGE
if __name__ == "__main__":
    sample_reminders = [
        "John turns {age(2011-10-01)} in October {offset_year(0)}",
        "Married for {years_since(2015-06-15)} years in {current_year}",
        "Caramel apple candy corn is Jenny’s favorite",
        "Next big event is {offset_year(3)}",
    ]

    for reminder in sample_reminders:
        print(parse_template(reminder))
