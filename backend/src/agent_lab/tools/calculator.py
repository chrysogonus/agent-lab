"""Arithmetic via a hand-written recursive-descent parser. Never uses eval.

Grammar (Python precedence; ** is right-associative and binds tighter than unary minus):
    expr   := term (("+" | "-") term)*
    term   := unary (("*" | "/" | "%") unary)*
    unary  := ("+" | "-") unary | power
    power  := atom ("**" unary)?
    atom   := NUMBER | "(" expr ")"
"""

import re

from agent_lab.tools.base import Tool, ToolError

MAX_LENGTH = 200
MAX_EXPONENT = 64
MAX_RESULT_BITS = 10_000  # bounds CPU and memory of nested powers

_TOKEN = re.compile(r"\s*(?:(\d+(?:\.\d*)?|\.\d+)|(\*\*|[-+*/%()]))")

Number = int | float


def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    pos = 0
    text = text.rstrip()
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            raise ToolError(f"unexpected character {text[pos:].lstrip()[:1]!r}")
        tokens.append(match.group(1) or match.group(2))
        pos = match.end()
    return tokens


class _Parser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> str | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> str:
        token = self.peek()
        if token is None:
            raise ToolError("unexpected end of expression")
        self.pos += 1
        return token

    def expr(self) -> Number:
        value = self.term()
        while self.peek() in ("+", "-"):
            value = value + self.term() if self.take() == "+" else value - self.term()
        return value

    def term(self) -> Number:
        value = self.unary()
        while self.peek() in ("*", "/", "%"):
            op = self.take()
            rhs = self.unary()
            if op == "*":
                value = value * rhs
            elif rhs == 0:
                raise ToolError("division by zero")
            elif op == "/":
                value = value / rhs
            else:
                value = value % rhs
        return value

    def unary(self) -> Number:
        if self.peek() in ("+", "-"):
            return -self.unary() if self.take() == "-" else self.unary()
        return self.power()

    def power(self) -> Number:
        base = self.atom()
        if self.peek() != "**":
            return base
        self.take()
        exponent = self.unary()
        if abs(exponent) > MAX_EXPONENT:
            raise ToolError(f"exponent larger than {MAX_EXPONENT}")
        if base == 0 and exponent < 0:
            raise ToolError("division by zero")
        if isinstance(base, int) and int(base).bit_length() * abs(exponent) > MAX_RESULT_BITS:
            raise ToolError("result too large")
        result = base**exponent
        if isinstance(result, complex):
            raise ToolError("result is not a real number")
        return result

    def atom(self) -> Number:
        text = self.take()
        if text == "(":
            value = self.expr()
            if self.take() != ")":
                raise ToolError("expected ')'")
            return value
        if text[0].isdigit() or text[0] == ".":
            return float(text) if "." in text else int(text)
        raise ToolError(f"unexpected token {text!r}")


def calculate(expression: object) -> str:  # object: arguments come from model JSON
    if not isinstance(expression, str) or not expression.strip():
        raise ToolError("expression must be a non-empty string")
    if len(expression) > MAX_LENGTH:
        raise ToolError(f"expression longer than {MAX_LENGTH} characters")
    parser = _Parser(_tokenize(expression))
    try:
        value = parser.expr()
    except OverflowError as exc:
        raise ToolError("result too large") from exc
    if parser.peek() is not None:
        raise ToolError(f"unexpected token {parser.peek()!r}")
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        value = int(value)
    return str(value)


CALCULATOR = Tool(
    name="calculator",
    description="Evaluate an arithmetic expression with + - * / % ** and parentheses.",
    parameters={
        "type": "object",
        "properties": {"expression": {"type": "string", "description": "e.g. (17*23)+4"}},
        "required": ["expression"],
        "additionalProperties": False,
    },
    fn=calculate,
)
