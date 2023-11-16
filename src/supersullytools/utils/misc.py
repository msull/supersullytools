from datetime import datetime
from random import choices
from string import ascii_lowercase


def date_id(now=None):
    now = now or datetime.utcnow()
    return now.strftime("%Y%m%d%H%M%S") + "".join(choices(ascii_lowercase, k=6))
