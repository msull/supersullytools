import datetime
import logging
import os
from typing import Any, Dict, List, Optional, Union
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# -------------------------------------------------------------------
# Configure logging
# -------------------------------------------------------------------
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
# You can add handlers if desired, e.g. to file or console:
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

# -------------------------------------------------------------------
# Constants & Custom Exceptions
# -------------------------------------------------------------------
SCOPES = ["https://www.googleapis.com/auth/calendar"]


class CalendarDataAccessError(Exception):
    """
    Custom exception for calendar data access errors.
    """

    pass


# -------------------------------------------------------------------
# Class: GoogleCalendarDataAccess
# -------------------------------------------------------------------
class GoogleCalendarDataAccess:
    """
    A convenience wrapper for interacting with Google Calendar via the v3 API.

    Attributes:
        credentials_file (str): Path to the Google OAuth 2.0 credentials JSON file.
        token_file (str): Path to the local JSON file for storing the authenticated user token.
        default_calendar_id (str): Which calendar to use if none is specified in method calls.
        fallback_timezone (str): Default timezone to use if the calendar does not provide one.
        service (Resource): The Google Calendar API resource built using `googleapiclient.discovery`.
    """

    def __init__(
        self,
        credentials_file: str = "local/credentials.json",
        token_file: str = "local/token.json",
        default_calendar_id: str = "primary",
        fallback_timezone: str = "America/Los_Angeles",
    ) -> None:
        """
        Initialize the GoogleCalendarDataAccess.

        Args:
            credentials_file: The path to the credentials JSON from Google Cloud Console.
            token_file: The path to the local user token JSON, where OAuth tokens are stored.
            default_calendar_id: The calendar to use if no calendarId is explicitly provided.
            fallback_timezone: The timezone to fall back on if the calendar doesn't specify one.
        """
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.default_calendar_id = default_calendar_id
        self.fallback_timezone = fallback_timezone
        self.service = self._get_service()

    def _get_service(self):
        """
        Build and return the Google Calendar API Resource object.

        Returns:
            Resource: A googleapiclient Resource for interacting with the Calendar API.

        Raises:
            CalendarDataAccessError: If the credentials file is not found or not accessible.
        """
        creds = None

        # Load existing credentials if available
        if os.path.exists(self.token_file):
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)

        # If no valid credentials, run the OAuth flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired credentials.")
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    raise CalendarDataAccessError(f"Credentials file not found at: {self.credentials_file}")
                logger.info("Running local server flow for new credentials.")
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)

            # Save the new/updated credentials
            with open(self.token_file, "w") as token:
                token.write(creds.to_json())

        return build("calendar", "v3", credentials=creds)

    def _get_calendar_timezone(self, calendar_id: Optional[str] = None) -> str:
        """
        Retrieve the timezone configured on a given Google Calendar.

        Args:
            calendar_id: The calendar ID, or None to use default_calendar_id.

        Returns:
            str: The timezone string (e.g., "America/Los_Angeles").

        Raises:
            CalendarDataAccessError: If there's an error from the Google Calendar API.
        """
        if calendar_id is None:
            calendar_id = self.default_calendar_id

        try:
            calendar = self.service.calendars().get(calendarId=calendar_id).execute()
            return calendar.get("timeZone", self.fallback_timezone)
        except HttpError as error:
            logger.error(f"An error occurred while fetching calendar info: {error}")
            return self.fallback_timezone

    def list_calendars(self) -> List[Dict[str, Any]]:
        """
        List all calendars accessible to the user.

        Returns:
            A list of dictionary objects representing the calendars.

        Raises:
            CalendarDataAccessError: If there's an error listing calendars.
        """
        try:
            result = self.service.calendarList().list().execute()
            return result.get("items", [])
        except HttpError as error:
            logger.error(f"An error occurred while listing calendars: {error}")
            raise CalendarDataAccessError("Unable to list calendars.") from error

    def set_default_calendar_id(self, calendar_id: str) -> None:
        """
        Set a new default calendar ID to use for operations.

        Args:
            calendar_id: The new default calendar ID.
        """
        self.default_calendar_id = calendar_id
        logger.debug(f"Default calendar ID set to: {calendar_id}")

    def get_events_on_date(
        self, date: Union[datetime.date, str], calendar_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all events for a specific local date in the calendar's timezone.

        Args:
            date: The local date. Can be a `datetime.date` or a string in 'YYYY-MM-DD' format.
            calendar_id: The calendar to query. Defaults to `self.default_calendar_id`.

        Returns:
            A list of events (dictionary objects) on the specified date.
        """
        if calendar_id is None:
            calendar_id = self.default_calendar_id

        # 1) Figure out the calendar’s actual timezone
        cal_tz_name = self._get_calendar_timezone(calendar_id)
        cal_tz = ZoneInfo(cal_tz_name)

        # 2) Build start/end of day as aware datetimes
        if isinstance(date, datetime.date):
            year, month, day = date.year, date.month, date.day
        else:
            year, month, day = map(int, date.split("-"))

        start_dt = datetime.datetime(year, month, day, 0, 0, 0, tzinfo=cal_tz)
        end_dt = datetime.datetime(year, month, day, 23, 59, 59, tzinfo=cal_tz)

        # 3) Pass these datetimes to get_events_in_range
        return self.get_events_in_range(start_dt, end_dt, calendar_id=calendar_id)

    def get_events_in_range(
        self,
        start_datetime: Union[datetime.datetime, str],
        end_datetime: Union[datetime.datetime, str],
        calendar_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch events in the inclusive range [start_datetime, end_datetime].
        The times should be fully offset-aware datetimes (or RFC3339 strings).

        Args:
            start_datetime: Start of the range, as a datetime with tz info or an RFC3339 string.
            end_datetime: End of the range, as a datetime with tz info or an RFC3339 string.
            calendar_id: The calendar to query. Defaults to `self.default_calendar_id`.

        Returns:
            A list of event dictionary objects from Google Calendar.

        Raises:
            CalendarDataAccessError: If there's an error from the API.
        """
        if calendar_id is None:
            calendar_id = self.default_calendar_id

        # Get the calendar timezone (optional for listing events, but can be useful)
        cal_tz = self._get_calendar_timezone(calendar_id)

        # Convert datetimes to RFC3339 if needed
        if isinstance(start_datetime, datetime.datetime):
            start_str = start_datetime.isoformat()
        else:
            start_str = start_datetime

        if isinstance(end_datetime, datetime.datetime):
            end_str = end_datetime.isoformat()
        else:
            end_str = end_datetime

        # Query the events
        try:
            events_result = (
                self.service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=start_str,
                    timeMax=end_str,
                    singleEvents=True,
                    orderBy="startTime",
                    timeZone=cal_tz,
                )
                .execute()
            )
            return events_result.get("items", [])
        except HttpError as error:
            logger.error(f"An error occurred while fetching events: {error}")
            raise CalendarDataAccessError("Unable to fetch events in range.") from error

    def add_event(
        self,
        summary: str,
        start_datetime: Union[datetime.datetime, str],
        end_datetime: Union[datetime.datetime, str],
        description: Optional[str] = None,
        location: Optional[str] = None,
        calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a time-based event to the specified (or default) calendar.

        Args:
            summary: Event title or summary.
            start_datetime: Start time (datetime or RFC3339 string).
            end_datetime: End time (datetime or RFC3339 string).
            description: Optional text for event description.
            location: Optional event location (string).
            calendar_id: Target calendar ID (defaults to default_calendar_id).

        Returns:
            The event data returned by Google Calendar API.

        Raises:
            CalendarDataAccessError: If the API call fails.
        """
        if calendar_id is None:
            calendar_id = self.default_calendar_id

        cal_tz = self._get_calendar_timezone(calendar_id)

        # Convert Python datetime objects to ISO 8601 strings if needed
        if isinstance(start_datetime, datetime.datetime):
            start_datetime = start_datetime.isoformat()
        if isinstance(end_datetime, datetime.datetime):
            end_datetime = end_datetime.isoformat()

        event_body = {
            "summary": summary,
            "start": {"dateTime": start_datetime, "timeZone": cal_tz},
            "end": {"dateTime": end_datetime, "timeZone": cal_tz},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        try:
            created_event = self.service.events().insert(calendarId=calendar_id, body=event_body).execute()
            logger.info(f"Event created: {created_event.get('htmlLink')}")
            return created_event
        except HttpError as error:
            logger.error(f"An error occurred while adding the event: {error}")
            raise CalendarDataAccessError("Unable to add event.") from error

    def add_all_day_event(
        self,
        summary: str,
        date: Union[datetime.date, str],
        description: Optional[str] = None,
        location: Optional[str] = None,
        calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Add a single-day, all-day event to the specified (or default) calendar.
        For all-day events, we use 'date' instead of 'dateTime' and omit time zones.

        Args:
            summary: Event title or summary.
            date: The local date of the all-day event (datetime.date or 'YYYY-MM-DD' string).
            description: Optional text for event description.
            location: Optional event location (string).
            calendar_id: Target calendar ID (defaults to default_calendar_id).

        Returns:
            The event data returned by Google Calendar API.

        Raises:
            CalendarDataAccessError: If the API call fails.
        """
        if calendar_id is None:
            calendar_id = self.default_calendar_id

        if isinstance(date, datetime.date):
            date_str = date.strftime("%Y-%m-%d")
        else:
            date_str = date  # assume it's already a YYYY-MM-DD string

        # According to Google Calendar, the `end.date` must be the day after for single-day all-day events.
        # For example, if date is 2025-01-06, then end.date = 2025-01-07
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        end_dt = dt + datetime.timedelta(days=1)
        end_date_str = end_dt.strftime("%Y-%m-%d")

        event_body = {
            "summary": summary,
            "start": {"date": date_str},  # no timeZone
            "end": {"date": end_date_str},  # no timeZone
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location

        try:
            created_event = self.service.events().insert(calendarId=calendar_id, body=event_body).execute()
            logger.info(f"All-day event created: {created_event.get('htmlLink')}")
            return created_event
        except HttpError as error:
            logger.error(f"An error occurred while adding the all-day event: {error}")
            raise CalendarDataAccessError("Unable to add all-day event.") from error

    def update_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start_datetime: Optional[Union[datetime.datetime, str]] = None,
        end_datetime: Optional[Union[datetime.datetime, str]] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        calendar_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update an existing event in the specified (or default) calendar.

        Args:
            event_id: The unique identifier of the event to update.
            summary: Optional new summary/title.
            start_datetime: Optional new start time (datetime or RFC3339 string).
            end_datetime: Optional new end time (datetime or RFC3339 string).
            description: Optional new description text.
            location: Optional new location.
            calendar_id: Target calendar ID (defaults to default_calendar_id).

        Returns:
            The updated event data from Google Calendar API.

        Raises:
            CalendarDataAccessError: If the API call fails.
        """
        if calendar_id is None:
            calendar_id = self.default_calendar_id

        cal_tz = self._get_calendar_timezone(calendar_id)

        # Fetch the existing event
        try:
            event = self.service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        except HttpError as error:
            logger.error(f"An error occurred while fetching the event to update: {error}")
            raise CalendarDataAccessError("Unable to fetch event for update.") from error

        # Apply changes
        if summary is not None:
            event["summary"] = summary

        # If we received dateTimes, update them (assuming the existing event is a time-based event).
        # If you plan on converting events to/from all-day to time-based, you'll also need to adjust
        # the 'start'/'end' to use 'date' or 'dateTime' accordingly.
        if start_datetime is not None:
            if isinstance(start_datetime, datetime.datetime):
                start_datetime = start_datetime.isoformat()
            event["start"]["dateTime"] = start_datetime
            event["start"]["timeZone"] = cal_tz
        if end_datetime is not None:
            if isinstance(end_datetime, datetime.datetime):
                end_datetime = end_datetime.isoformat()
            event["end"]["dateTime"] = end_datetime
            event["end"]["timeZone"] = cal_tz

        if description is not None:
            event["description"] = description
        if location is not None:
            event["location"] = location

        # Update via API
        try:
            updated_event = self.service.events().update(calendarId=calendar_id, eventId=event_id, body=event).execute()
            logger.info(f"Event updated: {updated_event.get('htmlLink')}")
            return updated_event
        except HttpError as error:
            logger.error(f"An error occurred while updating the event: {error}")
            raise CalendarDataAccessError("Unable to update event.") from error

    def delete_event(self, event_id: str, calendar_id: Optional[str] = None) -> bool:
        """
        Delete an event by event_id from the specified (or default) calendar.

        Args:
            event_id: The unique identifier of the event to delete.
            calendar_id: Target calendar ID (defaults to default_calendar_id).

        Returns:
            True if the deletion was successful; otherwise False.

        Raises:
            CalendarDataAccessError: If the API call fails.
        """
        if calendar_id is None:
            calendar_id = self.default_calendar_id

        try:
            self.service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
            logger.info("Event deleted.")
            return True
        except HttpError as error:
            logger.error(f"An error occurred while deleting the event: {error}")
            raise CalendarDataAccessError("Unable to delete event.") from error


# -------------------------------------------------------------------
# Example usage (CLI or script usage)
# -------------------------------------------------------------------
if __name__ == "__main__":
    # Instantiate the class with your default calendar ID
    calendar_dao = GoogleCalendarDataAccess(
        credentials_file="credentials.json",
        token_file="token.json",
        default_calendar_id="primary",
        fallback_timezone="America/Los_Angeles",
    )

    # Example: Create a single-day, all-day event on 2025-01-06
    # (This will appear in Google Calendar as an "all day" event on that date.)
    try:
        all_day_event = calendar_dao.add_all_day_event(
            summary="My All-Day Event",
            date="2025-01-06",
            description="This is a single-day, all-day event example",
        )
        logger.info(f"All-day event created with ID: {all_day_event.get('id')}")
    except CalendarDataAccessError as e:
        logger.error(f"Could not create all-day event: {e}")
