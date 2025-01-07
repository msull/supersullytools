# streamlit_app.py

from datetime import date

import streamlit as st

from supersullytools.utils.reminder_templates import parse_template


def main():
    st.title("Reminder Templates Demo")
    st.write("Use this simple app to try out the micro-templating functionality for date-based placeholders.")

    # A sample template for the user to try out.
    default_template = "Roland turns {age(1990-10-01)} in October {offset_year(0)}"

    # Input field for the user to enter any template string
    template_str = st.text_input("Enter your template string:", default_template)

    # Date input for picking a 'reference date'—this can be today or any other date
    reference_date = st.date_input("Choose a reference date:", date.today())

    # Button to parse the template
    if st.button("Parse"):
        rendered = parse_template(template_str, reference_date=reference_date)
        st.markdown("**Parsed Result:**")
        st.markdown(f"> {rendered}")

    st.write("---")
    st.markdown("### Supported Placeholders")
    st.markdown(
        """
        - `**{current_year}**`: Inserts the current year (based on your reference date).
        - `**{offset_year(N)}**`: Inserts the year offset by N from the current year.
        - `**{age(YYYY[-MM[-DD]])}**`: Calculates how old someone is this year (or at the given reference date).
            - If only the year is specified (e.g., `age(2006)`), it defaults to January 1 of that year.
        - `**{years_since(YYYY[-MM[-DD]])}**`: Calculates how many full years have passed since that date.
        - `**{days_until(YYYY[-MM[-DD]])}**`: Calculates the number of days from the reference date until the specified date
          (negative if the date has passed).
        """
    )


if __name__ == "__main__":
    main()
