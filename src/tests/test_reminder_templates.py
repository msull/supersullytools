# test_template_parser.py

from datetime import date

from supersullytools.utils.reminder_templates import parse_template


def test_current_year():
    # Reference date: 2025-01-01 (use something fixed to avoid test breakage in real time)
    reference_date = date(2025, 1, 1)
    template = "This year is {current_year}"
    rendered = parse_template(template, reference_date=reference_date)
    assert rendered == "This year is 2025"


def test_offset_year_positive():
    reference_date = date(2025, 1, 1)
    template = "Next year is {offset_year(1)}"
    rendered = parse_template(template, reference_date=reference_date)
    assert rendered == "Next year is 2026"


def test_offset_year_zero():
    reference_date = date(2025, 1, 1)
    template = "This year is {offset_year(0)}"
    rendered = parse_template(template, reference_date=reference_date)
    assert rendered == "This year is 2025"


def test_age_simple_year():
    reference_date = date(2025, 1, 1)
    template = "Robin turns {age(2006)} this year"
    rendered = parse_template(template, reference_date=reference_date)
    # 2025 - 2006 = 19, but since 2025-01-01 hasn't "passed" 2006-01-01's birthday yet?
    assert rendered == "Robin turns 19 this year"


def test_age_month_day():
    reference_date = date(2025, 1, 1)
    template = "Robin turns {age(2006-10)} this year"
    rendered = parse_template(template, reference_date=reference_date)
    assert rendered == "Robin turns 19 this year"


def test_age_full_date():
    reference_date = date(2025, 1, 1)
    template = "On {current_year}-10-01, Robin turns {age(2006-19-01)}!"
    rendered = parse_template(template, reference_date=reference_date)
    assert rendered == "On 2025-10-01, Robin turns 19!"


def test_years_since():
    # Let's say married on 2008-06-15. On 2025-06-14, it's still 16 years,
    # because the anniversary date hasn't happened yet in 2025.
    # We'll pick 2025-06-14 as reference => 16 years
    reference_date = date(2025, 6, 14)
    template = "Married for {years_since(2008-06-15)} years so far"
    rendered = parse_template(template, reference_date=reference_date)
    assert rendered == "Married for 16 years so far"


def test_years_since_after_anniversary():
    # Same date, but now it's 2025-06-16 -> anniversary passed => 17 years
    reference_date = date(2025, 6, 16)
    template = "Married for {years_since(2008-06-15)} years so far"
    rendered = parse_template(template, reference_date=reference_date)
    assert rendered == "Married for 17 years so far"


def test_unrecognized_placeholder():
    # If there's a placeholder that doesn't match any pattern, your code
    # returns "[Unrecognized placeholder: ...]"
    # You may want to confirm that behavior.
    reference_date = date(2025, 1, 1)
    template = "This is {unknown(123)}"
    rendered = parse_template(template, reference_date=reference_date)
    assert rendered == "This is [Unrecognized placeholder: unknown(123)]"


def test_days_until_future():
    ref = date(2025, 1, 1)
    template = "Days until event: {days_until(2025-01-10)}"
    rendered = parse_template(template, reference_date=ref)
    # 2025-01-10 minus 2025-01-01 = 9 days
    assert rendered == "Days until event: 9"


def test_days_until_past():
    ref = date(2025, 1, 2)
    template = "Days until event: {days_until(2025-01-01)}"
    rendered = parse_template(template, reference_date=ref)
    # 2025-01-01 minus 2025-01-02 = -1
    assert rendered == "Days until event: -1"


def test_days_until_partial():
    # "2025-01-01" reference, and target is 2025-01 => which means 2025-01-01
    ref = date(2025, 1, 1)
    template = "Days until partial date: {days_until(2025-01)}"
    rendered = parse_template(template, reference_date=ref)
    # 2025-01-01 minus 2025-01-01 = 0
    assert rendered == "Days until partial date: 0"
