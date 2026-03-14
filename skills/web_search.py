from langchain_community.tools import DuckDuckGoSearchRun

def get_tools():
    return [DuckDuckGoSearchRun()]