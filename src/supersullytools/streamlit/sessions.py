from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from logging import Logger
from typing import ClassVar, Generic, MutableMapping, Optional, Type, TypeVar

import streamlit as st
from humanize import precisedelta
from pydantic import BaseModel, ConfigDict, Field
from simplesingletable import DynamoDbMemory, DynamoDbResource, DynamoDbVersionedResource
from simplesingletable.models import ResourceConfig

from ..utils.misc import date_id

T = TypeVar("T", bound=BaseModel)


class StreamlitSessionBase(BaseModel):
    """Represents a user session in a Streamlit application with an expiration mechanism.

    Subclass this and add attributes for whatever you need to track in the user session.

    Attributes:
        session_id (str): Unique identifier for the session, generated using a custom method.
        expires_at (Optional[Decimal]): Timestamp at which the session expires.

    Methods:
        expires_in: Returns a string indicating the time remaining until session expiration.
        save_to_session_state: Saves session data to Streamlit's session state for persistence.
    """

    session_id: str = Field(default_factory=date_id)
    expires_at: Optional[Decimal] = None

    @property
    def expires_in(self) -> str:
        if self.expires_at:
            now = datetime.utcnow()
            expiration = datetime.fromtimestamp(float(self.expires_at))

            time_remaining = expiration - now
            if time_remaining.total_seconds() < 0:
                return f"expired {precisedelta(time_remaining)} ago"
            else:
                return f"expires in {precisedelta(time_remaining)}"

        else:
            return ""

    @property
    def is_expired(self) -> bool:
        if self.expires_at:
            now = datetime.utcnow()
            expiration = datetime.fromtimestamp(float(self.expires_at))
            time_remaining = expiration - now
            return time_remaining.total_seconds() < 0
        else:
            return False

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        self.save_to_session_state()

    def save_to_session_state(self):
        datakey = self.__class__.__name__
        if datakey not in st.session_state:
            st.session_state[datakey] = {}
        for k, v in self.model_dump().items():
            st.session_state[datakey][k] = v

    # model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")


SessionType = TypeVar("SessionType", bound=StreamlitSessionBase)


@dataclass
class SessionManagerInterface(ABC, Generic[SessionType]):
    """Defines an interface for managing user sessions in a Streamlit application.

    Methods to be implemented:
        persist_session: Persists the given session.
        get_session: Retrieves a session based on the session ID.
        get_session_model: Returns the session model class.
        get_query_param_name: Returns the query parameter name for the session.
        set_session_expiration: Sets the expiration for a session.
        init_session: Initializes a session, either by creating a new one or loading an existing one.
        clear_session_data: Clears session data from the session state.
        switch_session: Switches to a different session based on the provided session ID.
    """

    logger: Logger
    model_type: Type[SessionType]
    query_param_name: Optional[str] = None

    @abstractmethod
    def persist_session(self, session: SessionType):
        pass

    @abstractmethod
    def get_session(self, session_id: str) -> Optional[SessionType]:
        pass

    # @abstractmethod
    # def get_session_model(self) -> Type[SessionType]:
    #     pass
    #
    # @abstractmethod
    # def get_query_param_name(self) -> str:
    #     pass

    def get_session_model(self) -> Type[SessionType]:
        return self.model_type

    def get_query_param_name(self) -> str:
        if not self.query_param_name:
            return self.get_session_model().__name__
        return self.query_param_name

    def set_session_expiration(self, session: SessionType, expiration: datetime | timedelta):
        match expiration:
            case datetime():
                expires_at = expiration.timestamp()
            case timedelta():
                expires_at = (datetime.utcnow() + expiration).timestamp()
            case _:
                raise ValueError("Invalid type for expiration")
        expires_at = Decimal(str(expires_at).split(".")[0])
        session.expires_at = expires_at
        self.persist_session(session)
        return session

    def init_session(
        self, expiration: Optional[datetime | timedelta] = None, auto_extend_session_expiration=False
    ) -> SessionType:
        datakey = self.get_session_model().__name__
        query_session = st.query_params.get(self.get_query_param_name())
        if query_session:
            if st.session_state.get(datakey, {}).get("session_id") != query_session:
                # no, the requested session isn't loaded -- clear out any existing session data
                self.logger.info("Clearing outdated session")
                self.clear_session_data()
        if datakey not in st.session_state:
            st.session_state[datakey] = {}

        session: Optional[T] = None
        if st.session_state[datakey].get("session_id"):
            # since we have a session id in the session_state already, we've done an init and can load the data
            session = self.get_session_model().model_validate(st.session_state[datakey])
        elif query_session:
            self.logger.info("Loading session from query param")
            session = self.get_session(query_session)
            if not session:
                self.logger.warning(f"No session matching query param found {query_session=}")
                try:
                    del st.query_params[self.get_query_param_name()]
                except KeyError:
                    pass

        if not session:
            self.logger.info(f"Starting new session {datakey=}")
            if expiration:
                match expiration:
                    case datetime():
                        expires_at = expiration.timestamp()
                    case timedelta():
                        expires_at = (datetime.utcnow() + expiration).timestamp()
                    case _:
                        raise ValueError("Invalid type for expiration")
                expires_at = Decimal(str(expires_at).split(".")[0])
                session = self.get_session_model()(expires_at=expires_at)
            else:
                session = self.get_session_model()()

        session: StreamlitSessionBase

        if session.is_expired:
            self.logger.info("Session is expired; clearing and starting new")
            self.clear_session_data()
            session = self.init_session(expiration=expiration)
        else:
            if expiration and auto_extend_session_expiration:
                match expiration:
                    case datetime():
                        expires_at = expiration.timestamp()
                    case timedelta():
                        expires_at = (datetime.utcnow() + expiration).timestamp()
                    case _:
                        raise ValueError("Invalid type for expiration")
                expires_at = Decimal(str(expires_at).split(".")[0])
                session.expires_at = expires_at
        session.save_to_session_state()
        return session

    def clear_session_data(self):
        datakey = self.get_session_model().__name__
        st.session_state.pop(datakey, None)
        try:
            del st.query_params[self.get_query_param_name()]
        except KeyError:
            pass

    def switch_session(self, switch_to_session_id):
        incoming_session = self.get_session(switch_to_session_id)
        self.clear_session_data()
        incoming_session.save_to_session_state()


class InMemorySessionManager(SessionManagerInterface[SessionType]):
    """Manager with no persistence at all."""

    def __init__(
        self,
        model_type: Type[SessionType],
        logger,
        memory: Optional[MutableMapping] = None,
        query_param_name: Optional[str] = None,
    ):
        if memory is None:
            memory = {}
        self.session_store = memory
        self.query_param_name = query_param_name
        self.logger = logger

        if not issubclass(model_type, StreamlitSessionBase):
            raise TypeError("model_type must be a subclass of StreamlitSessionBase")
        self.model_type = model_type

    def persist_session(self, session: SessionType):
        self.session_store[session.session_id] = session
        st.query_params[self.get_query_param_name()] = session.session_id

    def get_session(self, session_id: str) -> Optional[SessionType]:
        self.logger.info("Getting session from memory")
        if db_session := self.session_store.get(session_id):
            return db_session


class DynamoDbSessionManager(SessionManagerInterface[SessionType]):
    """Manages user sessions using DynamoDB as a storage backend in a Streamlit application.

    Attributes:
        logger (Logger): Logger for logging information.
        enable_versioning (bool): Flag to enable versioning for session data.
        _memory (DynamoDbMemory): DynamoDB memory object for data persistence.
        ttl_attribute_name (Optional[str]): Name of the attribute used for time-to-live in DynamoDB.
        _query_param_name (Optional[str]): Query parameter name used in URLs to identify sessions.
        model_type (Type[SessionType]): Type of the session model.

    Methods:
        get_session_model: Returns the session model class.
        get_query_param_name: Returns the query parameter name for the session.
        persist_session: Saves the session to DynamoDB.
        get_session: Retrieves a session from DynamoDB using the session ID.
        get_db_session: Helper method to retrieve a session wrapper from DynamoDB.
    """

    def __init__(
        self,
        model_type: Type[SessionType],
        memory: DynamoDbMemory,
        logger,
        ttl_attribute_name: Optional[str] = None,
        query_param_name: Optional[str] = None,
        enable_versioning: bool = False,
    ):
        self.query_param_name = query_param_name
        self.logger = logger
        self.enable_versioning = enable_versioning
        self._memory = memory
        self.ttl_attribute_name = ttl_attribute_name

        if not issubclass(model_type, StreamlitSessionBase):
            raise TypeError("model_type must be a subclass of StreamlitSessionBase")
        self.model_type = model_type

        if enable_versioning:

            class DbSession(DynamoDbVersionedResource):
                session: model_type
                model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

                def to_dynamodb_item(self, v0_object: bool = False) -> dict:
                    base = super().to_dynamodb_item(v0_object)
                    if self.session.expires_at and v0_object and ttl_attribute_name:
                        base[ttl_attribute_name] = self.session.expires_at
                    return base

        else:

            class DbSession(DynamoDbResource):
                session: model_type
                model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")
                resource_config = ResourceConfig(compress_data=True)

                def to_dynamodb_item(self) -> dict:
                    base = super().to_dynamodb_item()
                    if self.session.expires_at and ttl_attribute_name:
                        base[ttl_attribute_name] = self.session.expires_at
                    return base

        self._db_model = DbSession

    def persist_session(self, session: SessionType):
        existing = self.get_db_session(session.session_id)
        if not existing:
            self._memory.create_new(self._db_model, data={"session": session}, override_id=session.session_id)
        else:
            if existing.session != session:
                self._memory.update_existing(existing, update_obj={"session": session})
        st.query_params[self.get_query_param_name()] = session.session_id

    def get_session(self, session_id: str) -> Optional[SessionType]:
        self.logger.info("Getting session from database")
        if db_session := self.get_db_session(session_id):
            return db_session.session

    # not part of the interface
    def get_db_session(self, session_id: str):
        return self._memory.get_existing(session_id, data_class=self._db_model)
