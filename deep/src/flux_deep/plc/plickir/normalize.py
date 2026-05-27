from __future__ import annotations


def split_parallel_networks(text: str) -> tuple[str, ...]:
    stripped = text.strip().rstrip(";").strip()
    if not stripped.startswith("[") or not stripped.endswith("]"):
        return (stripped,)

    body = stripped[1:-1]
    networks: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(body):
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif char == "," and depth == 0:
            networks.append(body[start:index].strip())
            start = index + 1
    networks.append(body[start:].strip())
    return tuple(network for network in networks if network)
