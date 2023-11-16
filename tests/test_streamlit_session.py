from streamlit.testing.v1 import AppTest
import supersullytools.streamlit.sessions as sst_session

def app_script():
    import streamlit as st
    import supersullytools.streamlit.sessions as streamlit_sst
    from logzero import logger

    class TestSession(streamlit_sst.StreamlitSessionBase):
        name: str = "Guest"

    manager = streamlit_sst.MemorySessionManager(memory=st.session_state.dynamodb_memory, model_type=TestSession, logger=logger)
    session = manager.init_session()
    manager.persist_session(session)


def test_basic(dynamodb_memory):
    dynamodb_memory.track_stats = False

    at = AppTest.from_function(app_script)
    at.session_state["dynamodb_memory"] = dynamodb_memory
    at.run()
    assert not at.exception
    items = dynamodb_memory.dynamodb_table.scan()['Items']
    assert len(items) == 1
