"""
Matching functionality.

This module provides the functionality to define matching rules to be used
within a Pact contract. These rules define the expected content of the data
being exchanged in a way that is more flexible than a simple equality check.

As an example, a contract may define how a new record is to be created through
a POST request. The consumer would define the new information to be sent, and
the expected response. The response may contain additional data added by the
provider, such as an ID and a creation timestamp. The contract would define
that the ID is of a specific format (e.g., an integer or a UUID), and that the
creation timestamp is ISO 8601 formatted.

!!! warning

    Do not import functions directly from this module. Instead, import the
    `match` module and use the functions from there:

    ```python
    # Good
    from pact.v3 import match

    match.int(...)

    # Bad
    from pact.v3.match import int

    int(...)
    ```

A number of functions in this module are named after the types they match
(e.g., `int`, `str`, `bool`). These functions will have aliases as well for
better interoperability with the rest of the Pact ecosystem. It is important
to note that these functions will shadow the built-in types if imported directly
from this module. This is why we recommend importing the `match` module and
using the functions from there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pact.v3.generators import (
    Generator,
    date_time,
    random_boolean,
    random_decimal,
    random_int,
    random_string,
)
from pact.v3.generators import date as date_generator
from pact.v3.generators import regex as regex_generator
from pact.v3.generators import time as time_generator
from pact.v3.match.matchers import ConcreteMatcher
from pact.v3.match.types import Matcher

if TYPE_CHECKING:
    from pact.v3.match.types import MatchType


def integer(
    value: int | None = None,
    min_val: int | None = None,
    max_val: int | None = None,
) -> Matcher:
    """
    Returns a matcher that matches an integer value.

    Args:
        value:
            The value to return when running a consumer test. Defaults to None.
        min_val:
            The minimum value of the integer to generate. Defaults to None.
        max_val:
            The maximum value of the integer to generate. Defaults to None.
    """
    return ConcreteMatcher(
        "integer",
        value,
        generator=random_int(min_val, max_val),
    )


def decimal(value: float | None = None, digits: int | None = None) -> Matcher:
    """
    Returns a matcher that matches a decimal value.

    Args:
        value:
            The value to return when running a consumer test. Defaults to None.
        digits:
            The number of decimal digits to generate. Defaults to None.
    """
    return ConcreteMatcher("decimal", value, generator=random_decimal(digits))


def number(
    value: float | None = None,
    min_val: int | None = None,
    max_val: int | None = None,
    digits: int | None = None,
) -> Matcher:
    """
    Returns a matcher that matches a number value.

    If all arguments are None, a random_decimal generator will be used.
    If value argument is an integer or either min_val or max_val are provided,
    a random_int generator will be used.

    Args:
        value:
            The value to return when running a consumer test.
            Defaults to None.
        min_val:
            The minimum value of the number to generate. Only used when
            value is an integer. Defaults to None.
        max_val:
            The maximum value of the number to generate. Only used when
            value is an integer. Defaults to None.
        digits:
            The number of decimal digits to generate. Only used when
            value is a float. Defaults to None.
    """
    if min_val is not None and digits is not None:
        msg = "min_val and digits cannot be used together"
        raise ValueError(msg)

    if isinstance(value, int) or any(v is not None for v in [min_val, max_val]):
        generator = random_int(min_val, max_val)
    else:
        generator = random_decimal(digits)
    return ConcreteMatcher("number", value, generator=generator)


def string(
    value: str | None = None,
    size: int | None = None,
    generator: Generator | None = None,
) -> Matcher:
    """
    Returns a matcher that matches a string value.

    Args:
        value:
            The value to return when running a consumer test. Defaults to None.
        size:
            The size of the string to generate. Defaults to None.
        generator:
            The generator to use when generating the value. Defaults to None. If
            no generator is provided and value is not provided, a random string
            generator will be used.
    """
    if generator is not None:
        return ConcreteMatcher("type", value, generator=generator, force_generator=True)
    return ConcreteMatcher("type", value, generator=random_string(size))


def boolean(*, value: bool | None = True) -> Matcher:
    """
    Returns a matcher that matches a boolean value.

    Args:
        value:
            The value to return when running a consumer test. Defaults to True.
    """
    return ConcreteMatcher("boolean", value, generator=random_boolean())


def date(format_str: str, value: str | None = None) -> Matcher:
    """
    Returns a matcher that matches a date value.

    Args:
        format_str:
            The format of the date. See
            [Java SimpleDateFormat](https://docs.oracle.com/javase/8/docs/api/java/text/SimpleDateFormat.html)
            for details on the format string.
        value:
            The value to return when running a consumer test. Defaults to None.
    """
    return ConcreteMatcher(
        "date", value, format=format_str, generator=date_generator(format_str)
    )


def time(format_str: str, value: str | None = None) -> Matcher:
    """
    Returns a matcher that matches a time value.

    Args:
        format_str:
            The format of the time. See
            [Java SimpleDateFormat](https://docs.oracle.com/javase/8/docs/api/java/text/SimpleDateFormat.html)
            for details on the format string.
        value:
            The value to return when running a consumer test. Defaults to None.
    """
    return ConcreteMatcher(
        "time", value, format=format_str, generator=time_generator(format_str)
    )


def timestamp(format_str: str, value: str | None = None) -> Matcher:
    """
    Returns a matcher that matches a timestamp value.

    Args:
        format_str:
            The format of the timestamp. See
            [Java SimpleDateFormat](https://docs.oracle.com/javase/8/docs/api/java/text/SimpleDateFormat.html)
            for details on the format string.
        value:
            The value to return when running a consumer test. Defaults to None.
    """
    return ConcreteMatcher(
        "timestamp",
        value,
        format=format_str,
        generator=date_time(format_str),
    )


def null() -> Matcher:
    """
    Returns a matcher that matches a null value.
    """
    return ConcreteMatcher("null")


def like(
    value: MatchType,
    min_count: int | None = None,
    max_count: int | None = None,
    generator: Generator | None = None,
) -> Matcher:
    """
    Returns a matcher that matches the given template.

    Args:
        value:
            The template to match against. This can be a primitive value, a
            dictionary, or a list and matching will be done by type.
        min_count:
            The minimum number of items that must match the value. Defaults to None.
        max_count:
            The maximum number of items that must match the value. Defaults to None.
        generator:
            The generator to use when generating the value. Defaults to None.
    """
    return ConcreteMatcher(
        "type", value, min=min_count, max=max_count, generator=generator
    )


def each_like(
    value: MatchType,
    min_count: int | None = 1,
    max_count: int | None = None,
) -> Matcher:
    """
    Returns a matcher that matches each item in an array against a given value.

    Note that the matcher will validate the array length be at least one.
    Also, the argument passed will be used as a template to match against
    each item in the array and generally should not itself be an array.

    Args:
        value:
            The value to match against.
        min_count:
            The minimum number of items that must match the value. Default is 1.
        max_count:
            The maximum number of items that must match the value.
    """
    return ConcreteMatcher("type", [value], min=min_count, max=max_count)


def includes(value: str, generator: Generator | None = None) -> Matcher:
    """
    Returns a matcher that matches a string that includes the given value.

    Args:
        value:
            The value to match against.
        generator:
            The generator to use when generating the value. Defaults to None.
    """
    return ConcreteMatcher("include", value, generator=generator, force_generator=True)


def array_containing(variants: list[MatchType]) -> Matcher:
    """
    Returns a matcher that matches the items in an array against a number of variants.

    Matching is successful if each variant occurs once in the array. Variants may be
    objects containing matching rules.

    Args:
        variants:
            A list of variants to match against.
    """
    return ConcreteMatcher("arrayContains", variants=variants)


def regex(regex: str, value: str | None = None) -> Matcher:
    """
    Returns a matcher that matches a string against a regular expression.

    If no value is provided, a random string will be generated that matches
    the regular expression.

    Args:
        regex:
            The regular expression to match against.
        value:
            The value to return when running a consumer test. Defaults to None.
    """
    return ConcreteMatcher(
        "regex",
        value,
        generator=regex_generator(regex),
        regex=regex,
    )


def each_key_matches(value: MatchType, rules: Matcher | list[Matcher]) -> Matcher:
    """
    Returns a matcher that matches each key in a dictionary against a set of rules.

    Args:
        value:
            The value to match against.
        rules:
            The matching rules to match against each key.
    """
    if isinstance(rules, Matcher):
        rules = [rules]
    return ConcreteMatcher("eachKey", value, rules=rules)


def each_value_matches(value: MatchType, rules: Matcher | list[Matcher]) -> Matcher:
    """
    Returns a matcher that matches each value in a dictionary against a set of rules.

    Args:
        value:
            The value to match against.
        rules:
            The matching rules to match against each value.
    """
    if isinstance(rules, Matcher):
        rules = [rules]
    return ConcreteMatcher("eachValue", value, rules=rules)