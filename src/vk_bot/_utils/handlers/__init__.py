"""VK bot handler modules.

Each handler receives (vk_message: VKMessage, state: DialogState | None, user_id: int)
and returns VKHandlerResult | None.

Handlers are registered in the HANDLER_CHAIN in dispatcher.py.
"""
