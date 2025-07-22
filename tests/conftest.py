import importlib.util

pytest_plugins = []
if importlib.util.find_spec("pytest_asyncio"):
    pytest_plugins.append("pytest_asyncio")
