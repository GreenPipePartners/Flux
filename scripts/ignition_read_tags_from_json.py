# Ignition Gateway/Perspective script, Jython 2.7 compatible.
#
# Purpose:
# - Read a tag document from disk.
# - Extract tag paths from a top-level `tag_list` field, or from a raw list.
# - Perform bulk system.tag.readBlocking calls.
#
# The file may be strict JSON:
#   {"tag_list": ["[default]Path/Tag"]}
#
# Or the current Python-literal export shape:
#   {'tag_list': ["[default]Path/Tag"]}


DEFAULT_BATCH_SIZE = 5000
DEFAULT_TIMEOUT_MS = 60000


def load_tag_document(file_path):
    """Load a tag document using Ignition's file APIs."""
    text = system.file.readFileAsString(file_path)
    return decode_tag_document(text)


def decode_tag_document(text):
    """Decode strict JSON first, then Python literal syntax as a fallback."""
    try:
        return system.util.jsonDecode(text)
    except Exception:
        pass

    # tag.json currently looks like a Python dict repr, not strict JSON.
    # ast.literal_eval safely handles that shape without executing code.
    import ast

    return ast.literal_eval(text)


def extract_tag_paths(document):
    """Return a cleaned list of tag paths from a decoded document."""
    if isinstance(document, dict):
        tag_paths = document.get("tag_list") or document.get("tags") or document.get("tagPaths")
    else:
        tag_paths = document

    if tag_paths is None:
        raise ValueError("Tag document must contain `tag_list`, `tags`, `tagPaths`, or be a raw list.")

    cleaned = []
    seen = set()
    for tag_path in tag_paths:
        if tag_path is None:
            continue
        tag_path = str(tag_path).strip()
        if not tag_path or tag_path in seen:
            continue
        cleaned.append(tag_path)
        seen.add(tag_path)

    return cleaned


def read_tag_paths(tag_paths, batch_size=DEFAULT_BATCH_SIZE, timeout_ms=DEFAULT_TIMEOUT_MS):
    """Read tag paths in bulk batches and return row dictionaries."""
    rows = []
    total = len(tag_paths)

    for start in range(0, total, batch_size):
        batch_paths = tag_paths[start:start + batch_size]
        qualified_values = system.tag.readBlocking(batch_paths, timeout_ms)

        for index in range(len(batch_paths)):
            qualified_value = qualified_values[index]
            rows.append({
                "tagPath": batch_paths[index],
                "value": qualified_value.value,
                "quality": str(qualified_value.quality),
                "timestamp": qualified_value.timestamp,
            })

        system.util.getLogger("Flux.TagRead").info(
            "Read %d/%d tags" % (min(start + len(batch_paths), total), total)
        )

    return rows


def read_tags_from_file(file_path, batch_size=DEFAULT_BATCH_SIZE, timeout_ms=DEFAULT_TIMEOUT_MS):
    """Load tag paths from a document and read them in bulk."""
    document = load_tag_document(file_path)
    tag_paths = extract_tag_paths(document)
    return read_tag_paths(tag_paths, batch_size, timeout_ms)


def read_tags_from_file_timed(file_path, batch_size=DEFAULT_BATCH_SIZE, timeout_ms=DEFAULT_TIMEOUT_MS):
    """Read tags and return rows plus timing metadata for the read event."""
    import time

    logger = system.util.getLogger("Flux.TagRead")
    start_time = system.date.now()
    start_seconds = time.time()

    document = load_tag_document(file_path)
    tag_paths = extract_tag_paths(document)
    rows = read_tag_paths(tag_paths, batch_size, timeout_ms)

    end_time = system.date.now()
    elapsed_seconds = time.time() - start_seconds
    event = {
        "filePath": file_path,
        "startTime": start_time,
        "endTime": end_time,
        "elapsedSeconds": elapsed_seconds,
        "tagCount": len(tag_paths),
        "rowCount": len(rows),
        "batchSize": batch_size,
        "timeoutMs": timeout_ms,
    }

    logger.info(
        "Read event complete: %d tags in %.3f seconds from %s"
        % (len(rows), elapsed_seconds, file_path)
    )

    return {"rows": rows, "event": event}


def rows_to_dataset(rows):
    """Convert read results to a dataset for easy display or DB handoff."""
    headers = ["tagPath", "value", "quality", "timestamp"]
    data = []
    for row in rows:
        data.append([row["tagPath"], row["value"], row["quality"], row["timestamp"]])
    return system.dataset.toDataSet(headers, data)


# Example Gateway Script Console usage:
#
# file_path = "C:/path/to/tag.json"
# result = read_tags_from_file_timed(file_path, batch_size=5000, timeout_ms=60000)
# rows = result["rows"]
# event = result["event"]
# dataset = rows_to_dataset(rows)
# print "Read %d tags in %.3f seconds" % (event["rowCount"], event["elapsedSeconds"])
# print "Started: %s" % event["startTime"]
# print "Ended: %s" % event["endTime"]
