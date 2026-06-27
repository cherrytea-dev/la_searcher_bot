"""Unit tests for :mod:`_dependencies.bot.handler_registry`.

Tests cover:
- :func:`match_conditions` — all condition types and combinations
- :class:`HandlerRegistry` — registration, matching, priority, clear
"""

from typing import Any

from _dependencies.bot.handler_registry import (
    Handler,
    HandlerConditions,
    HandlerRegistry,
    match_conditions,
)

# ═══════════════════════════════════════════════════════════════════════
# match_conditions — text exact match
# ═══════════════════════════════════════════════════════════════════════


class TestMatchTextExact:
    def test_single_string_matches(self) -> None:
        assert match_conditions(HandlerConditions(text='hello'), text='hello')

    def test_single_string_does_not_match(self) -> None:
        assert not match_conditions(HandlerConditions(text='hello'), text='world')

    def test_list_matches_any(self) -> None:
        assert match_conditions(HandlerConditions(text=['a', 'b', 'c']), text='b')

    def test_list_does_not_match(self) -> None:
        assert not match_conditions(HandlerConditions(text=['a', 'b']), text='c')

    def test_case_sensitive(self) -> None:
        assert not match_conditions(HandlerConditions(text='Hello'), text='hello')

    def test_missing_text_value_returns_false(self) -> None:
        assert not match_conditions(HandlerConditions(text='hello'), state='radius_input')

    def test_none_text_in_values_returns_false(self) -> None:
        assert not match_conditions(HandlerConditions(text='hello'), text=None)


# ═══════════════════════════════════════════════════════════════════════
# match_conditions — text_startswith
# ═══════════════════════════════════════════════════════════════════════


class TestMatchTextStartswith:
    def test_prefix_matches(self) -> None:
        assert match_conditions(HandlerConditions(text_startswith='+'), text='+12345')

    def test_prefix_does_not_match(self) -> None:
        assert not match_conditions(HandlerConditions(text_startswith='+'), text='12345')

    def test_missing_text_returns_false(self) -> None:
        assert not match_conditions(HandlerConditions(text_startswith='+'), state='radius_input')


# ═══════════════════════════════════════════════════════════════════════
# match_conditions — text_regex
# ═══════════════════════════════════════════════════════════════════════


class TestMatchTextRegex:
    def test_regex_matches(self) -> None:
        assert match_conditions(HandlerConditions(text_regex=r'^\d{5}$'), text='12345')

    def test_regex_does_not_match(self) -> None:
        assert not match_conditions(HandlerConditions(text_regex=r'^\d{5}$'), text='123456')

    def test_regex_search_not_fullmatch(self) -> None:
        """``re.search`` is used, so a substring match is enough."""
        assert match_conditions(HandlerConditions(text_regex=r'\d+'), text='abc123def')

    def test_missing_text_returns_false(self) -> None:
        assert not match_conditions(HandlerConditions(text_regex=r'\d+'), state='radius_input')


# ═══════════════════════════════════════════════════════════════════════
# match_conditions — callback_data
# ═══════════════════════════════════════════════════════════════════════


class TestMatchCallbackData:
    def test_single_string_matches(self) -> None:
        assert match_conditions(HandlerConditions(callback_data='paginate_nav'), callback_data='paginate_nav')

    def test_single_string_does_not_match(self) -> None:
        assert not match_conditions(HandlerConditions(callback_data='paginate_nav'), callback_data='paginate_toggle')

    def test_list_matches_any(self) -> None:
        assert match_conditions(
            HandlerConditions(callback_data=['nav', 'toggle']),
            callback_data='toggle',
        )

    def test_missing_callback_data_returns_false(self) -> None:
        assert not match_conditions(HandlerConditions(callback_data='nav'), text='hello')


# ═══════════════════════════════════════════════════════════════════════
# match_conditions — state
# ═══════════════════════════════════════════════════════════════════════


class TestMatchState:
    def test_state_matches(self) -> None:
        assert match_conditions(HandlerConditions(state='radius_input'), state='radius_input')

    def test_state_does_not_match(self) -> None:
        assert not match_conditions(HandlerConditions(state='radius_input'), state='not_defined')

    def test_missing_state_returns_false(self) -> None:
        assert not match_conditions(HandlerConditions(state='radius_input'), text='hello')


# ═══════════════════════════════════════════════════════════════════════
# match_conditions — combined (AND logic)
# ═══════════════════════════════════════════════════════════════════════


class TestMatchCombined:
    def test_all_conditions_match(self) -> None:
        assert match_conditions(
            HandlerConditions(text='ввести радиус', state='radius_input'),
            text='ввести радиус',
            state='radius_input',
        )

    def test_text_matches_but_state_does_not(self) -> None:
        assert not match_conditions(
            HandlerConditions(text='ввести радиус', state='radius_input'),
            text='ввести радиус',
            state='not_defined',
        )

    def test_state_matches_but_text_does_not(self) -> None:
        assert not match_conditions(
            HandlerConditions(text='ввести радиус', state='radius_input'),
            text='something_else',
            state='radius_input',
        )

    def test_text_and_callback_data(self) -> None:
        assert match_conditions(
            HandlerConditions(text='hello', callback_data='nav'),
            text='hello',
            callback_data='nav',
        )

    def test_text_startswith_and_state(self) -> None:
        assert match_conditions(
            HandlerConditions(text_startswith='+', state='radius_input'),
            text='+12345',
            state='radius_input',
        )

    def test_text_regex_and_callback_data(self) -> None:
        assert match_conditions(
            HandlerConditions(text_regex=r'^\d+$', callback_data='submit'),
            text='42',
            callback_data='submit',
        )


# ═══════════════════════════════════════════════════════════════════════
# match_conditions — edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestMatchEdgeCases:
    def test_no_conditions_always_matches(self) -> None:
        """If all conditions are None, any input matches."""
        assert match_conditions(HandlerConditions(), text='anything')
        assert match_conditions(HandlerConditions(), state='radius_input')
        assert match_conditions(HandlerConditions(), callback_data='nav')

    def test_empty_string_text(self) -> None:
        assert match_conditions(HandlerConditions(text=''), text='')

    def test_empty_string_startswith(self) -> None:
        """``str.startswith('')`` is always True."""
        assert match_conditions(HandlerConditions(text_startswith=''), text='anything')

    def test_none_values_in_kwargs(self) -> None:
        """If a condition expects 'text' but it's explicitly None."""
        assert not match_conditions(HandlerConditions(text='hello'), text=None)


# ═══════════════════════════════════════════════════════════════════════
# HandlerRegistry — registration
# ═══════════════════════════════════════════════════════════════════════


class TestHandlerRegistryRegistration:
    def test_register_adds_handler(self) -> None:
        registry = HandlerRegistry()

        def my_handler(ctx: Any) -> None:
            pass

        handler = Handler(func=my_handler, conditions=HandlerConditions(text='test'))
        registry.register(handler)
        assert len(registry.all()) == 1
        assert registry.all()[0].func == my_handler

    def test_register_multiple_handlers(self) -> None:
        registry = HandlerRegistry()

        def h1(ctx: Any) -> None:
            pass

        def h2(ctx: Any) -> None:
            pass

        registry.register(Handler(func=h1, conditions=HandlerConditions(text='a')))
        registry.register(Handler(func=h2, conditions=HandlerConditions(text='b')))
        assert len(registry.all()) == 2

    def test_clear_removes_all(self) -> None:
        registry = HandlerRegistry()

        def my_handler(ctx: Any) -> None:
            pass

        registry.register(Handler(func=my_handler, conditions=HandlerConditions(text='test')))
        registry.clear()
        assert len(registry.all()) == 0


# ═══════════════════════════════════════════════════════════════════════
# HandlerRegistry — matching
# ═══════════════════════════════════════════════════════════════════════


class TestHandlerRegistryMatch:
    def test_match_returns_matching_handlers(self) -> None:
        registry = HandlerRegistry()

        def h1(ctx: Any) -> None:
            pass

        def h2(ctx: Any) -> None:
            pass

        registry.register(Handler(func=h1, conditions=HandlerConditions(text='hello')))
        registry.register(Handler(func=h2, conditions=HandlerConditions(text='world')))

        results = list(registry.match(text='hello'))
        assert len(results) == 1
        assert results[0].func == h1

    def test_match_returns_empty_when_no_match(self) -> None:
        registry = HandlerRegistry()

        def my_handler(ctx: Any) -> None:
            pass

        registry.register(Handler(func=my_handler, conditions=HandlerConditions(text='hello')))
        results = list(registry.match(text='world'))
        assert len(results) == 0

    def test_match_returns_all_matching_handlers(self) -> None:
        registry = HandlerRegistry()

        def h1(ctx: Any) -> None:
            pass

        def h2(ctx: Any) -> None:
            pass

        registry.register(Handler(func=h1, conditions=HandlerConditions(text='hello')))
        registry.register(Handler(func=h2, conditions=HandlerConditions(text='hello')))

        results = list(registry.match(text='hello'))
        assert len(results) == 2

    def test_match_with_multiple_conditions(self) -> None:
        registry = HandlerRegistry()

        def h1(ctx: Any) -> None:
            pass

        def h2(ctx: Any) -> None:
            pass

        registry.register(Handler(func=h1, conditions=HandlerConditions(text='hello', state='radius_input')))
        registry.register(Handler(func=h2, conditions=HandlerConditions(text='hello', state='not_defined')))

        results = list(registry.match(text='hello', state='radius_input'))
        assert len(results) == 1
        assert results[0].func == h1


# ═══════════════════════════════════════════════════════════════════════
# HandlerRegistry — priority ordering
# ═══════════════════════════════════════════════════════════════════════


class TestHandlerRegistryPriority:
    def test_lower_priority_fires_first(self) -> None:
        registry = HandlerRegistry()
        order: list[str] = []

        def h1(ctx: Any) -> None:
            order.append('h1')

        def h2(ctx: Any) -> None:
            order.append('h2')

        registry.register(Handler(func=h1, conditions=HandlerConditions(text='test'), priority=10))
        registry.register(Handler(func=h2, conditions=HandlerConditions(text='test'), priority=0))

        for handler in registry.match(text='test'):
            handler.func(None)
        assert order == ['h2', 'h1']

    def test_default_priority_is_zero(self) -> None:
        registry = HandlerRegistry()
        order: list[str] = []

        def h1(ctx: Any) -> None:
            order.append('h1')

        def h2(ctx: Any) -> None:
            order.append('h2')

        registry.register(Handler(func=h1, conditions=HandlerConditions(text='test')))  # priority=0
        registry.register(Handler(func=h2, conditions=HandlerConditions(text='test'), priority=5))

        for handler in registry.match(text='test'):
            handler.func(None)
        assert order == ['h1', 'h2']

    def test_negative_priority(self) -> None:
        registry = HandlerRegistry()
        order: list[str] = []

        def h1(ctx: Any) -> None:
            order.append('h1')

        def h2(ctx: Any) -> None:
            order.append('h2')

        registry.register(Handler(func=h1, conditions=HandlerConditions(text='test'), priority=-1))
        registry.register(Handler(func=h2, conditions=HandlerConditions(text='test'), priority=0))

        for handler in registry.match(text='test'):
            handler.func(None)
        assert order == ['h1', 'h2']


# ═══════════════════════════════════════════════════════════════════════
# HandlerRegistry — edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestHandlerRegistryEdgeCases:
    def test_empty_registry_returns_empty(self) -> None:
        registry = HandlerRegistry()
        results = list(registry.match(text='anything'))
        assert len(results) == 0

    def test_handler_with_no_conditions_matches_anything(self) -> None:
        registry = HandlerRegistry()

        def my_handler(ctx: Any) -> None:
            pass

        registry.register(Handler(func=my_handler, conditions=HandlerConditions()))
        results = list(registry.match(text='anything'))
        assert len(results) == 1

    def test_clear_between_tests(self) -> None:
        """Registry should be reusable after clear()."""
        registry = HandlerRegistry()

        def h1(ctx: Any) -> None:
            pass

        registry.register(Handler(func=h1, conditions=HandlerConditions(text='a')))
        registry.clear()
        assert len(registry.all()) == 0

        def h2(ctx: Any) -> None:
            pass

        registry.register(Handler(func=h2, conditions=HandlerConditions(text='b')))
        assert len(registry.all()) == 1
        assert registry.all()[0].func == h2
