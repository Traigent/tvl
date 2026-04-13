from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence


class StructuralParseError(ValueError):
    """Raised when a structural constraint cannot be parsed."""


@dataclass(frozen=True)
class Literal:
    kind: str  # comparison, membership, interval
    ident: str
    operator: str
    values: Sequence[str]
    value_types: Sequence[str] = ()
    negated: bool = False


@dataclass
class DNF:
    clauses: List[List[Literal]]


class _Token:
    __slots__ = ("type", "value")

    def __init__(self, typ: str, value: str) -> None:
        self.type = typ
        self.value = value

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"_Token({self.type!r}, {self.value!r})"


def parse_expression(text: str) -> DNF:
    tokens = _tokenize(text)
    parser = _Parser(tokens)
    ast = parser.parse()
    nnf = _to_nnf(ast)
    clauses: List[List[Literal]] = []
    for conjunction in _to_dnf(nnf):
        literals = [_literal_from_ast(node) for node in conjunction]
        literals.sort(key=lambda lit: (lit.ident, lit.operator, tuple(lit.values), lit.negated))
        clauses.append(literals)
    clauses.sort(key=lambda lits: [(lit.ident, lit.operator, tuple(lit.values), lit.negated) for lit in lits])
    return DNF(clauses=clauses)


def clause_to_string(clause: Sequence[Literal]) -> str:
    if not clause:
        return "true"
    parts: List[str] = []
    for lit in clause:
        prefix = "not " if lit.negated else ""
        if lit.kind == "interval":
            parts.append(prefix + lit.operator)
        elif lit.kind == "membership":
            formatted_values = ",".join(
                _format_value(value_type, value)
                for value_type, value in zip(lit.value_types, lit.values)
            )
            parts.append(prefix + f"{lit.ident} in {{{formatted_values}}}")
        else:
            value_repr = _format_value(lit.value_types[0] if lit.value_types else "", lit.values[0])
            parts.append(prefix + f"{lit.ident} {lit.operator} {value_repr}")
    return " and ".join(parts)


def canonical_dnf_string(dnf: DNF) -> str:
    return " or ".join(clause_to_string(clause) for clause in dnf.clauses)


def _format_value(token_type: str, value: str) -> str:
    if token_type == "STRING":
        return repr(value)
    if token_type == "BOOLEAN":
        return value.lower()
    return value


def _tokenize(text: str) -> List[_Token]:
    tokens: List[_Token] = []
    pos = 0
    length = len(text)

    while pos < length:
        ch = text[pos]

        if ch.isspace():
            pos += 1
            continue

        if text.startswith("=>", pos):
            tokens.append(_Token("IMPLIES", "=>"))
            pos += 2
            continue

        if text.startswith("<=", pos):
            tokens.append(_Token("LE", "<="))
            pos += 2
            continue

        if text.startswith(">=", pos):
            tokens.append(_Token("GE", ">="))
            pos += 2
            continue

        if text.startswith("==", pos):
            tokens.append(_Token("EQ", "=="))
            pos += 2
            continue

        if text.startswith("!=", pos):
            tokens.append(_Token("NE", "!="))
            pos += 2
            continue

        if ch in "<>=":
            tokens.append(_Token({"<": "LT", ">": "GT", "=": "EQ"}[ch], ch))
            pos += 1
            continue

        if ch in "{}[](),":
            mapping = {
                "{": "LBRACE",
                "}": "RBRACE",
                "[": "LBRACKET",
                "]": "RBRACKET",
                "(": "LPAREN",
                ")": "RPAREN",
                ",": "COMMA",
            }
            tokens.append(_Token(mapping[ch], ch))
            pos += 1
            continue

        if ch in "'\"":
            quote = ch
            pos += 1
            chars: List[str] = []
            while pos < length:
                current = text[pos]
                if current == "\\":
                    if pos + 1 >= length:
                        raise StructuralParseError("Unterminated escape sequence in string literal")
                    chars.append(text[pos + 1])
                    pos += 2
                    continue
                if current == quote:
                    tokens.append(_Token("STRING", "".join(chars)))
                    pos += 1
                    break
                chars.append(current)
                pos += 1
            else:
                raise StructuralParseError("Unterminated string literal")
            continue

        if ch.isdigit() or (ch in "+-" and pos + 1 < length and text[pos + 1].isdigit()):
            start = pos
            pos += 1
            has_dot = False
            while pos < length:
                current = text[pos]
                if current.isdigit():
                    pos += 1
                elif current == "." and not has_dot:
                    has_dot = True
                    pos += 1
                else:
                    break
            tokens.append(_Token("NUMBER", text[start:pos]))
            continue

        if ch.isalpha() or ch == "_":
            start = pos
            pos += 1
            while pos < length and (text[pos].isalnum() or text[pos] in "_.-"):
                pos += 1
            ident = text[start:pos]
            lowered = ident.lower()
            if lowered in {"or", "and", "not", "in"}:
                mapping = {"or": "OR", "and": "AND", "not": "NOT", "in": "IN"}
                tokens.append(_Token(mapping[lowered], lowered))
            elif lowered in {"true", "false"}:
                tokens.append(_Token("BOOLEAN", lowered))
            else:
                tokens.append(_Token("IDENT", ident))
            continue

        raise StructuralParseError(f"Unexpected token starting at position {pos}: {text[pos:pos+10]!r}")

    tokens.append(_Token("EOF", ""))
    return tokens


class _Parser:
    def __init__(self, tokens: Iterable[_Token]) -> None:
        self.tokens = list(tokens)
        self.index = 0

    def current(self) -> _Token:
        return self.tokens[self.index]

    def advance(self) -> _Token:
        token = self.tokens[self.index]
        self.index += 1
        return token

    def accept(self, *types: str) -> bool:
        if self.current().type in types:
            self.advance()
            return True
        return False

    def expect(self, typ: str) -> _Token:
        token = self.current()
        if token.type != typ:
            raise StructuralParseError(f"Expected {typ}, found {token.type}")
        return self.advance()

    def parse(self):
        expr = self.implication()
        if self.current().type != "EOF":
            raise StructuralParseError("Unexpected trailing input in structural constraint")
        return expr

    def implication(self):
        left = self.disjunction()
        if self.accept("IMPLIES"):
            right = self.disjunction()
            return ("=>", left, right)
        return left

    def disjunction(self):
        expr = self.conjunction()
        while self.accept("OR"):
            expr = ("or", expr, self.conjunction())
        return expr

    def conjunction(self):
        expr = self.unary()
        while self.accept("AND"):
            expr = ("and", expr, self.unary())
        return expr

    def unary(self):
        if self.accept("NOT"):
            return ("not", self.unary())
        if self.accept("LPAREN"):
            expr = self.implication()
            self.expect("RPAREN")
            return expr
        return self.atom()

    def atom(self):
        tok = self.current()
        if tok.type == "NUMBER":
            return self.interval()
        if tok.type == "IDENT":
            return self.comparison_or_membership()
        raise StructuralParseError(f"Unexpected token {tok.type} in atom")

    def interval(self):
        left = self.expect("NUMBER").value
        op1 = self._expect_interval_op()
        ident = self.expect("IDENT").value
        op2 = self._expect_interval_op()
        right = self.expect("NUMBER").value
        return ("interval", ident, op1, op2, left, right)

    def comparison_or_membership(self):
        ident = self.expect("IDENT").value
        if self.accept("IN"):
            values = self.set_literal()
            return ("membership", ident, values)
        op_token = self.current()
        if op_token.type in {"EQ", "NE", "LE", "GE", "LT", "GT"}:
            op = self.advance().value
            value = self.value_token()
            return ("comparison", ident, op, value)
        raise StructuralParseError(f"Expected comparison operator after identifier '{ident}'")

    def set_literal(self) -> List[tuple[str, str]]:
        values: List[tuple[str, str]] = []
        if self.accept("LBRACE"):
            closing = "RBRACE"
        else:
            self.expect("LBRACKET")
            closing = "RBRACKET"
        if self.accept(closing):
            return values
        while True:
            values.append(self.value_token())
            if self.accept("COMMA"):
                continue
            self.expect(closing)
            break
        return values

    def value_token(self) -> tuple[str, str]:
        tok = self.current()
        if tok.type in {"NUMBER", "STRING", "BOOLEAN", "IDENT"}:
            value = tok.value
            self.advance()
            return tok.type, value
        if tok.type == "LPAREN":
            self.advance()
            items: List[str] = []
            if self.accept("RPAREN"):
                return "TUPLE_VAL", "()"
            while True:
                vtype, vval = self.value_token()
                if vtype == "STRING":
                    # Re-quote strings to preserve type fidelity through
                    # the string-based tuple representation.
                    escaped = vval.replace("\\", "\\\\").replace('"', '\\"')
                    items.append(f'"{escaped}"')
                else:
                    items.append(vval)
                if self.accept("COMMA"):
                    continue
                self.expect("RPAREN")
                break
            return "TUPLE_VAL", f"({', '.join(items)})"
        raise StructuralParseError(f"Unexpected token {tok.type} in value")

    def _expect_interval_op(self) -> str:
        tok = self.current()
        if tok.type in {"LE", "LT"}:
            return self.advance().value
        raise StructuralParseError(f"Expected interval operator, found {tok.type}")


def _to_nnf(node):
    if isinstance(node, tuple):
        op = node[0]
        if op == "not":
            child = node[1]
            if isinstance(child, tuple):
                cop = child[0]
                if cop == "not":
                    return _to_nnf(child[1])
                if cop == "and":
                    return ("or", _to_nnf(("not", child[1])), _to_nnf(("not", child[2])))
                if cop == "or":
                    return ("and", _to_nnf(("not", child[1])), _to_nnf(("not", child[2])))
                if cop == "=>":
                    return _to_nnf(("and", child[1], ("not", child[2])))
            return ("not_atom", child)
        if op == "=>":
            _, antecedent, consequent = node
            return ("or", _to_nnf(("not", antecedent)), _to_nnf(consequent))
        if op in {"and", "or"}:
            return (op, _to_nnf(node[1]), _to_nnf(node[2]))
    return node


def _to_dnf(node):
    if isinstance(node, tuple):
        op = node[0]
        if op == "and":
            left = _to_dnf(node[1])
            right = _to_dnf(node[2])
            product: List[List[tuple]] = []
            for l in left:
                for r in right:
                    product.append(l + r)
            return product
        if op == "or":
            return _to_dnf(node[1]) + _to_dnf(node[2])
        if op == "not_atom":
            return [[node]]
    return [[node]]


def _literal_from_ast(node) -> Literal:
    kind = node[0]
    if kind == "interval":
        _, ident, op1, op2, left, right = node
        canonical = f"{left}{op1}{ident}{op2}{right}"
        return Literal(kind="interval", ident=ident, operator=canonical, values=(left, right, op1, op2))
    if kind == "membership":
        _, ident, values = node
        if values:
            value_types, raw_values = zip(*values)
        else:
            value_types, raw_values = (), ()
        return Literal(
            kind="membership",
            ident=ident,
            operator="in",
            values=tuple(raw_values),
            value_types=tuple(value_types),
        )
    if kind == "comparison":
        _, ident, op, value_info = node
        value_type, value = value_info
        normalized_op = "==" if op == "=" else op
        return Literal(
            kind="comparison",
            ident=ident,
            operator=normalized_op,
            values=(value,),
            value_types=(value_type,),
        )
    if kind == "not_atom":
        literal = _literal_from_ast(node[1])
        return Literal(
            kind=literal.kind,
            ident=literal.ident,
            operator=literal.operator,
            values=literal.values,
            value_types=literal.value_types,
            negated=not literal.negated,
        )
    raise StructuralParseError(f"Unsupported AST node: {node}")
