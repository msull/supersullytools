from logzero import logger
from pydantic import BaseModel

from supersullytools.llm.agent import AgentTool, AgentToolResponse


class WriteStory(BaseModel):
    title: str
    content: str


def handle_write_story(params: WriteStory) -> AgentToolResponse:
    logger.info(params.model_dump_json(indent=2))
    title = params.title
    return AgentToolResponse(output_content=f"Story {title=} completed!", replace_input="")


def get_demo_tools() -> list[AgentTool]:
    tools = [AgentTool(name=WriteStory.__name__, params_model=WriteStory, mechanism=handle_write_story, safe_tool=True)]
    return tools
