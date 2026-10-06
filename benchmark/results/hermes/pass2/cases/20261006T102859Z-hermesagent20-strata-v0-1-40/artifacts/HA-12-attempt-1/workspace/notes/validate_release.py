def validate_release(tag: str) -> bool:
    return tag.startswith('v') and len(tag) > 1
