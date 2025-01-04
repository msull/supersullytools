from datetime import date, datetime

import streamlit as st

# Import your GoogleCalendarDataAccess class
# Replace 'supersullytools.gcalendar_access' with the actual path if different.
from supersullytools.gcalendar_access import CalendarDataAccessError, GoogleCalendarDataAccess

# Initialize the data access object
# Update the args below to match your environment (files, default calendar, timezone, etc.)
calendar_dao = GoogleCalendarDataAccess(
    credentials_file="credentials.json",
    token_file="token.json",
    default_calendar_id="primary",
    fallback_timezone="America/Los_Angeles",
)

# ------------------------------------------------------------------------------
# Streamlit Layout / UI
# ------------------------------------------------------------------------------
st.title("Google Calendar Streamlit Demo")

st.write(
    """
This app demonstrates basic Google Calendar operations using the 
**GoogleCalendarDataAccess** class. 
"""
)

# ------------------------------------------------------------------------------
# List Calendars
# ------------------------------------------------------------------------------
st.subheader("1. List Calendars")

if st.button("List All Calendars"):
    try:
        calendars = calendar_dao.list_calendars()
        if calendars:
            st.write("Found the following calendars:")
            for cal in calendars:
                st.write(f"- **{cal.get('summary')}** (ID: `{cal.get('id')}`) " f"TimeZone: {cal.get('timeZone')}")
        else:
            st.write("No calendars found or no access.")
    except CalendarDataAccessError as e:
        st.error(f"Error listing calendars: {e}")

# ------------------------------------------------------------------------------
# Add an Event
# ------------------------------------------------------------------------------
st.subheader("2. Add a New Event")

with st.form("add_event_form"):
    event_summary = st.text_input("Event Summary", "Sample Event")

    col1, col2 = st.columns(2)
    with col1:
        start_date_input = st.date_input("Start Date", date.today())
        start_time_input = st.time_input("Start Time", datetime.now().time())
    with col2:
        end_date_input = st.date_input("End Date", date.today())
        end_time_input = st.time_input("End Time", (datetime.now()).time())

    event_description = st.text_area("Description", "Discuss holiday plans")
    event_location = st.text_input("Location", "Somewhere nice...")

    submitted = st.form_submit_button("Add Event")
    if submitted:
        # Combine date and time
        start_dt = datetime.combine(start_date_input, start_time_input)
        end_dt = datetime.combine(end_date_input, end_time_input)

        # Attempt to add the event
        try:
            created_event = calendar_dao.add_event(
                summary=event_summary,
                start_datetime=start_dt,
                end_datetime=end_dt,
                description=event_description,
                location=event_location,
            )
            st.success(f"Event created: {created_event.get('htmlLink')}")
        except CalendarDataAccessError as e:
            st.error(f"Error adding event: {e}")

# ------------------------------------------------------------------------------
# Get Events on a Specific Date
# ------------------------------------------------------------------------------
st.subheader("3. Fetch Events on a Date")

fetch_date = st.date_input("Select Date", date.today())
if st.button("Get Events"):
    try:
        events = calendar_dao.get_events_on_date(fetch_date)
        if not events:
            st.info("No events found on this date.")
        else:
            st.write(f"Found {len(events)} event(s) on {fetch_date}:")
            for event in events:
                start_info = event.get("start", {}).get("dateTime")
                summary = event.get("summary")
                event_id = event.get("id")
                st.write(f"- **{summary}**")
                st.write(f"  - **Start**: {start_info}")
                st.write(f"  - **ID**: {event_id}")
                st.write("---")
    except CalendarDataAccessError as e:
        st.error(f"Error getting events: {e}")
