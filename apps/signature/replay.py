"""Time-travel transfer replay data normalization."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def replay_transfers(edges: Sequence[Mapping[str, Any]], *, entity_id: str | None = None) -> dict[str, Any]:
    selected = [dict(edge) for edge in edges]
    if entity_id:
        selected = [edge for edge in selected if edge.get("source") == entity_id or edge.get("target") == entity_id]
    selected.sort(key=lambda edge: (int(edge.get("ts", 0)), str(edge.get("id", ""))))
    cumulative = 0.0
    seen: set[str] = set()
    frames: list[dict[str, Any]] = []
    close_index: int | None = None
    for index, edge in enumerate(selected):
        source, target = str(edge.get("source")), str(edge.get("target"))
        amount = float(edge.get("amount", 0.0))
        was_seen = target in seen
        cumulative += amount
        seen.add(source)
        seen.add(target)
        if close_index is None and entity_id is not None and target == entity_id and was_seen:
            close_index = index
        frames.append({"index": index, "source": source, "target": target, "amount": amount, "ts": int(edge.get("ts", 0)), "cumulative_volume": round(cumulative, 2), "cycle_closed": close_index == index})
    return {"entity_id": entity_id, "edges": frames, "cumulative_volume": round(cumulative, 2), "cycle_close_index": close_index, "cycle_closed_at": frames[close_index]["ts"] if close_index is not None else None}
