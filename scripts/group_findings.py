"""Group supporting typography and flow measurements without discarding evidence."""

TYPOGRAPHY = {"Font family", "Font size", "Font weight"}


def group_frame_findings(findings, mapping, reference, actual, tolerance=4):
    """Retain independent position changes and attach observed flow changes to text issues."""
    by_reference = {node["id"]: node for node in reference["nodes"]}
    by_actual = {node["id"]: node for node in actual["nodes"]}
    pairs = {row["label"]: (by_reference[row["reference_id"]], by_actual.get(row["comparison_id"]))
             for row in mapping}
    leaders = {}
    for index, finding in enumerate(findings):
        if finding["property"] in TYPOGRAPHY:
            leaders.setdefault(finding["label"], index)
    attached = {}
    for index, finding in enumerate(findings):
        leader = leaders.get(finding["label"])
        if leader is not None and finding["property"] in {"Width", "Height"}:
            attached[index] = leader

    for label, leader in leaders.items():
        left, right = pairs[label]
        if right is None:
            continue
        height_delta = right["box"]["height"] - left["box"]["height"]
        if abs(height_delta) <= tolerance:
            continue
        offset = ((right["box"]["y"] - actual["nodes"][0]["box"]["y"])
                  - (left["box"]["y"] - reference["nodes"][0]["box"]["y"]))
        path = left["path"].rsplit("/", 1)[0]
        # Find the nearest container containing other mapped elements.
        while path:
            members = {name for name, (node, partner) in pairs.items()
                       if node["path"].startswith(path + "/") and partner is not None}
            if len(members) >= 3:
                break
            path = path.rsplit("/", 1)[0]
        if not path:
            continue
        for index, finding in enumerate(findings):
            if index in attached or finding["property"] != "Y position" or finding["label"] not in members:
                continue
            node, partner = pairs[finding["label"]]
            observed = ((partner["box"]["y"] - actual["nodes"][0]["box"]["y"])
                        - (node["box"]["y"] - reference["nodes"][0]["box"]["y"]))
            predicted = offset
            if node["box"]["y"] >= left["box"]["y"] + left["box"]["height"] - tolerance:
                predicted += height_delta
            if abs(observed - predicted) <= tolerance:
                attached[index] = leader

    result = []
    for index, finding in enumerate(findings):
        if index in attached:
            continue
        item = dict(finding)
        related = [dict(findings[child]) for child, parent in attached.items() if parent == index]
        if related:
            item["related_measurements"] = related
            item["related"] = " | ".join(
                f"{row['label']}: {row['property']} {row['expected']} → {row['actual']}" for row in related)
        else:
            item["related"] = ""
        result.append(item)
    return result
