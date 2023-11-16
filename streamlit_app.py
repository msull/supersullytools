from pathlib import Path
from typing import Optional

import streamlit as st
from pydantic import Field
from streamlit_extras.echo_expander import echo_expander
from logzero import logger

from simplesingletable.utils import truncate_dynamo_table

TABLE_DEFINITION = Path(__file__).parent / "example_tables" / "standard.yaml"

st.header("Simple Single Table usage example")

basic_tab, advanced_tab, admin_tab = st.tabs(("Basic usage", "Advanced Usage", "Admin"))


with basic_tab:
    with st.expander('Start with imports and setting up the basic "memory" client'):
        with echo_expander(expander=False, label="Basic Setup"):
            from simplesingletable import (
                DynamoDBMemory,
                DynamodbResource,
                DynamodbVersionedResource,
            )

            memory = DynamoDBMemory(
                logger=logger,
                table_name="standardexample",
                endpoint_url="http://localhost:8000",
                connection_params={
                    "aws_access_key_id": "unused",
                    "aws_secret_access_key": "unused",
                    "region_name": "us-east-1",
                },
            )

            st.write(
                """
            In this example, I'm connecting to a local DynamoDB service running via docker, and have created 
            a table named `standardexample` with the following definition:
            """
            )
            st.code(TABLE_DEFINITION.read_text())

with admin_tab:
    stats_placeholder = st.empty()
    if st.button("Truncate dynamodb table"):
        with st.echo():
            st.write(truncate_dynamo_table(memory.dynamodb_table))
            st.session_state.clear()
            st.rerun()


with basic_tab:
    with st.expander("Model definition and basic create/update"):
        st.write(
            """
        Now define some resource classes for things you want to store in the database.
        Resource classes are Pydantic models that inherit from either `DynamodbResource` or
        `DynamodbVersionedResource`.
        The difference between these, as the name implies, is that one is versioned. 
        If the resource is "versioned" every time it is updated the full object is
        stored in the database again, allowing the full history of the object to be reviewed.
        
        Here are a few simple models:
        """
        )

        with st.echo():

            class User(DynamodbResource):
                name: str
                tags: Optional[set[str]] = None
                num_followers: int = 0
                other_set: set[str] = Field(default_factory=set)
                what_about: str = "this"

            class JournalEntry(DynamodbResource):
                content: str
                user_id: str

            class SimpleTask(DynamodbVersionedResource):
                task: str
                descr: Optional[str]
                completed: bool
                user_id: str
                tags: set[str]

        st.write("Now we can begin storing and retrieving objects from the database")

        RESOURCE_ID = st.text_input(
            "RESOURCE_ID", st.session_state.get("resource_id"), help="Clear this to generate a new resource"
        )
        if RESOURCE_ID:
            st.session_state["resource_id"] = RESOURCE_ID

        if not RESOURCE_ID:
            with st.echo():
                created_user = memory.create_new(User, {"name": "New User"})
                st.json(created_user.model_dump_json())
            st.session_state["resource_id"] = created_user.resource_id
        else:
            with st.echo():
                created_user = memory.read_existing(RESOURCE_ID, User)
                st.json(created_user.model_dump_json())
        st.write(
            """
        The resource automatically includes a `resource_id`, as well as `created_at` and `updated_at` attributes.
        The default `resource_id` is a ULID, which means that it sorts as a string in order of creation time.
        
        Having this ID sort by creation time is useful in our advanced access patterns that utilize secondary
        indices.
        
        The ID can be converted back to the ULID type with a helper function:
        """
        )
        with st.echo():
            ulid = created_user.resource_id_as_ulid()
            st.write(ulid.timestamp().datetime)

        st.write(
            """
        There are also helpers for viewing how recently resources were created or updated:
        """
        )

        with st.form("Update user object"):
            new_name = st.text_input("name", created_user.name)

            if st.form_submit_button("Update") and new_name:
                with st.echo():
                    created_user = memory.update_existing(created_user, {"name": new_name})
                    st.json(created_user.model_dump_json())
                st.info("Changed user name")

        with st.echo():
            st.write(f"Object was created {created_user.created_ago()}.")
            st.write(f"Object was updated {created_user.updated_ago()}.")
            st.write(f"Object was updated {created_user.updated_ago('seconds')}.")

        st.write("Non-versioned resources support atomic counters with an easy increment method:")
        increase_by = st.slider("Change Followers By", min_value=-10, max_value=10, value=1)
        num_followers = created_user.num_followers
        st.metric("Followers before", num_followers)

        if st.button("Update Followers"):
            with st.echo():
                num_followers = memory.increment_counter(created_user, "num_followers", incr_by=increase_by)
            st.session_state["resource_id"] = created_user.resource_id
            st.metric("Followers after", num_followers)

        st.write("Non-versioned resources support atomic set push / pop as well:")
        with st.form("Update tags"):
            st.write("Current Tags", created_user.tags)
            tag = st.text_input("tag")
            if st.form_submit_button("Add Tag") and tag:
                with st.echo():
                    memory.add_to_set(created_user, "tags", tag)
                    created_user = memory.read_existing(created_user.resource_id, User, consistent_read=True)
                    st.write("Updated Tags", created_user.tags)
            if st.form_submit_button("Remove Tag") and tag:
                with st.echo():
                    memory.remove_from_set(created_user, "tags", tag)
                    created_user = memory.read_existing(created_user.resource_id, User, consistent_read=True)
                    st.write("Updated Tags", created_user.tags)

        with st.form("Update other set"):
            st.write("Current Values", created_user.other_set)
            value = st.text_input("value")
            if st.form_submit_button("Add Value") and value:
                with st.echo():
                    memory.add_to_set(created_user, "other_set", value)
                    created_user = memory.read_existing(created_user.resource_id, User, consistent_read=True)
                    st.write("Updated Values", created_user.values)
            if st.form_submit_button("Remove Value") and value:
                with st.echo():
                    memory.remove_from_set(created_user, "other_set", value)
                    created_user = memory.read_existing(created_user.resource_id, User, consistent_read=True)
                    st.write("Updated Values", created_user.other_set)


# update the stats on the admin tab as the last step
stats_placeholder.code(memory.get_stats().model_dump_json(indent=2))
