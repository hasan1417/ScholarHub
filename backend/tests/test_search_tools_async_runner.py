import asyncio

from app.services.discussion_ai.mixins.search_tools_mixin import SearchToolsMixin


class _SearchToolsHarness(SearchToolsMixin):
    pass


def test_run_async_operation_without_running_loop():
    tools = _SearchToolsHarness()

    async def _operation():
        await asyncio.sleep(0)
        return 42

    assert tools._run_async_operation(_operation) == 42


def test_run_async_operation_with_running_loop():
    tools = _SearchToolsHarness()

    async def _outer():
        async def _operation():
            await asyncio.sleep(0)
            return "ok"

        return tools._run_async_operation(_operation)

    assert asyncio.run(_outer()) == "ok"
