from duckduckgo_search import DDGS
from pydantic import BaseModel

from supersullytools.llm.agent import AgentTool, PydanticModel


class NewsSearch(BaseModel):
    """Search recent US news."""

    q: str


class WebSearch(BaseModel):
    q: str


def get_ddg_tools(include_news=True, include_web=True) -> list[AgentTool]:
    def _handle_tool_usage(params: PydanticModel):
        with DDGS() as ddgs:
            match params:
                case NewsSearch():
                    result = ddgs.news(params.q, region="us-en", safesearch="off", max_results=10)
                case WebSearch():
                    result = ddgs.text(params.q, region="us-en", safesearch="off", backend="api", max_results=10)
                case _:
                    raise ValueError(params)

        return result

    tools = []

    def _add_tool(model, is_safe):
        tools.append(
            AgentTool(name=model.__name__, params_model=model, mechanism=_handle_tool_usage, safe_tool=is_safe)
        )

    if include_web:
        _add_tool(WebSearch, True)
    if include_news:
        _add_tool(NewsSearch, True)

    return tools


# def get_result(search_type, query) -> list[dict | str]:
#     results = ["answer"]
#
#         match search_type:
#             case "text":
#                 print(f"Searching for text {query=}")
#
#             case "answers":
#                 print(f"Searching for answers {query=}")
#                 results = ddgs.answers(query)
#             case "news":
#                 print(f"Searching for news {query=}")
#                 results = ddgs.news(
#                     query,
#                     region="us-en",
#                     safesearch="off",
#                     max_results=10,
#                 )
#             case "images":
#                 print(f"Searching for images {query=}")
#                 results = ddgs.images(
#                     query,
#                     region="wt-wt",
#                     safesearch="off",
#                     size=None,
#                     # color="Monochrome",
#                     type_image=None,
#                     layout=None,
#                     license_image=None,
#                     max_results=10,
#                 )
#             case "videos":
#                 print(f"Searching for videos {query=}")
#                 results = ddgs.videos(
#                     query,
#                     region="wt-wt",
#                     safesearch="off",
#                     max_results=10,
#                 )
#             case "maps":
#                 pass
#             case "translate":
#                 pass
#             case "suggestions":
#                 results = ddgs.suggestions(query)
#             case _:
#                 raise ValueError("Unhandled search type")
#         return list(results)
